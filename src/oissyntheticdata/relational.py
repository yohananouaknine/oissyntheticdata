# -*- coding: utf-8 -*-
"""
Relational schema detection (stage 01, on-premises).

Given the real tables, infer the relationships between files from the data
itself, not from a hand-written schema and not from column-name heuristics:

  * a column is a LINK only when one file holds it uniquely (the parent) and
    another file's values for that column are a repeating subset of it (the
    child). This is type-agnostic, so integer surrogate keys, string ids, and
    dates are all detected, and shared *attribute* columns (a category that
    merely happens to share a name) are rejected because they are unique in
    neither file.
  * when a child carries several link columns, the finest one (most distinct
    values) is the PRIMARY parent; any other column the child shares with that
    parent and that the primary link functionally determines is INHERITED from
    the matched parent row, which is what makes within-row pairing exact.

The detected schema is structure only (file, column, and relationship names,
plus the fan-out distribution as robust quantiles); it carries no row values, so
it is disclosure-safe and travels in the run folder with the profiles.
"""

from ._common import (
    is_missing, percentile, QUANTILE_GRID, USE_ROBUST_BOUNDS, P_LOW, P_HIGH,
)


def _nonmissing(rows, c):
    return [r.get(c, "") for r in rows if not is_missing(r.get(c, ""))]


def _is_unique(rows, c):
    vals = _nonmissing(rows, c)
    return len(vals) > 0 and len(set(vals)) == len(vals)


def _determines(rows, a, b):
    """Does column a functionally determine column b (group by a -> constant b)?"""
    seen = {}
    for r in rows:
        av = r.get(a, "")
        if is_missing(av):
            continue
        bv = r.get(b, "")
        if av in seen:
            if seen[av] != bv:
                return False
        else:
            seen[av] = bv
    return True


def _fanout(rows, link_col, grid=QUANTILE_GRID, robust=USE_ROBUST_BOUNDS):
    """Distribution of children per parent (group sizes) as robust quantiles."""
    counts = {}
    for r in rows:
        v = r.get(link_col, "")
        if is_missing(v):
            continue
        counts[v] = counts.get(v, 0) + 1
    sizes = sorted(counts.values())
    g = list(grid)
    q = [percentile(sizes, p) for p in g]
    if robust and sizes:
        q[0] = percentile(sizes, P_LOW)
        q[-1] = percentile(sizes, P_HIGH)
    return g, [round(x, 6) for x in q], len(counts)


def _own_key(header, uniqmap):
    uniques = [c for c in header if uniqmap.get(c)]
    if not uniques:
        return None
    for c in uniques:
        cl = c.lower()
        if cl in ("id", "url") or cl.endswith(("_id", "_key", "_code")):
            return c
    return uniques[0]


def _topo(files):
    children = {b: [] for b in files}
    indeg = {b: 0 for b in files}
    for b, e in files.items():
        p = e["parent"]
        if p:
            children[p].append(b)
            indeg[b] += 1
    q = sorted(b for b in files if indeg[b] == 0)
    order = []
    while q:
        b = q.pop(0)
        order.append(b)
        for c in sorted(children[b]):
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)
        q.sort()
    for b in files:                       # any leftover (defensive: cycles)
        if b not in order:
            order.append(b)
    return order


def _all_int(values):
    if not values:
        return False
    for v in values:
        try:
            int(str(v))
        except (ValueError, TypeError):
            return False
    return True


def detect_schema(tables):
    """tables: {base: {"file": name, "header": [...], "rows": [dict, ...]}}.

    Returns {"files": {base: {parent, link, inherited, key, fanout_*}}, "order": [...]}.
    """
    bases = list(tables)
    uniq, valset, header = {}, {}, {}
    for b, t in tables.items():
        header[b] = t["header"]
        uniq[b], valset[b] = {}, {}
        for c in t["header"]:
            vals = _nonmissing(t["rows"], c)
            valset[b][c] = set(vals)
            uniq[b][c] = (len(vals) > 0 and len(set(vals)) == len(vals))

    def own(b):
        return _own_key(header[b], uniq[b])

    # 1:many links are unambiguous; 1:1 links (col unique in both) need a direction
    edges = {b: [] for b in bases}        # child -> list of (col, parent)
    one_to_one, seen_pair = [], set()
    for b in bases:
        for p in bases:
            if p == b:
                continue
            for c in header[b]:
                if c not in header[p]:
                    continue
                bv, pv = valset[b][c], valset[p][c]
                if not bv or not pv:
                    continue
                if uniq[p][c] and not uniq[b][c] and bv <= pv:
                    edges[b].append((c, p))                 # b is the many side
                elif uniq[p][c] and uniq[b][c] and bv == pv:
                    key = (min(b, p), max(b, p), c)
                    if key not in seen_pair:
                        seen_pair.add(key)
                        one_to_one.append((b, p, c))

    # resolve 1:1 direction: child = file with more other parents; then the file
    # whose own key is NOT this column; then a deterministic name order
    for a, bb, c in one_to_one:
        da, db = len(edges[a]), len(edges[bb])
        if da != db:
            child, parent = (a, bb) if da > db else (bb, a)
        elif (own(a) == c) != (own(bb) == c):
            child, parent = (a, bb) if own(a) != c else (bb, a)
        else:
            child, parent = max(a, bb), min(a, bb)
        edges[child].append((c, parent))

    files = {}
    for b in bases:
        links = edges[b]
        if not links:
            files[b] = {"file": tables[b]["file"], "parent": None, "link": None,
                        "inherited": [], "key": own(b),
                        "fanout_grid": None, "fanout_quantiles": None}
            continue
        # primary parent = link column with the most distinct values here (finest
        # grain); on a tie prefer an integer key, which synthesizes uniquely and
        # so keeps a parent join unambiguous
        primary_c, primary_p = max(
            links, key=lambda cp: (len(valset[b][cp[0]]), _all_int(valset[b][cp[0]])))
        phead = set(header[primary_p])
        inherited = [c for c in header[b]
                     if c != primary_c and c in phead
                     and not (c.endswith("_month") and c[:-6] in header[b])
                     and _determines(tables[b]["rows"], primary_c, c)]
        g, q, _ = _fanout(tables[b]["rows"], primary_c)
        files[b] = {"file": tables[b]["file"], "parent": primary_p, "link": primary_c,
                    "inherited": inherited, "key": own(b),
                    "fanout_grid": g, "fanout_quantiles": q}

    return {"files": files, "order": _topo(files)}


def schema_lines(schema):
    """Human-readable summary of the detected relationships."""
    lines = []
    for b in schema["order"]:
        e = schema["files"][b]
        if e["parent"]:
            extra = (" inheriting " + ", ".join(e["inherited"])) if e["inherited"] else ""
            lines.append("%s -> %s on %s%s" % (b, e["parent"], e["link"], extra))
        else:
            key = (" (key %s)" % e["key"]) if e["key"] else ""
            lines.append("%s: root%s" % (b, key))
    return lines
