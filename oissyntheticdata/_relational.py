# -*- coding: utf-8 -*-
"""oissyntheticdata._relational — multi-table (relational) synthesis.

Extends sequential CART synthesis to a parent -> child schema while keeping
**referential integrity** (every synthetic foreign key points at a synthetic
parent) and the **parent->child structure** (fan-out and attribute correlation).

For each table, in parent-before-child order:
  1. Synthesize the table's attributes (sequential CART). For a child, the
     parent's synthetic attributes are supplied as fixed predictors, so child
     attributes are drawn conditioned on the parent they belong to.
  2. Mint fresh surrogate primary keys (1..n) — real identifiers are never
     reproduced.
  3. For each child, a regression CART models the number of children per parent
     from the parent's attributes (the fan-out), so realistic counts — and which
     parents have many vs. few children — are preserved. Foreign keys are drawn
     from the synthetic parent keys, guaranteeing valid joins.

Scope: a single-parent DAG (star / snowflake / chains). A table has at most one
parent; a parent may have many children; children may themselves be parents.
"""

import random
from . import _io
from . import _tree
from ._synth import type_columns, stringify, synth_core, _to_float


def _topo_order(schema):
    order, seen = [], set()
    tables = list(schema.keys())
    guard = 0
    while len(order) < len(tables):
        guard += 1
        if guard > len(tables) + 2:
            raise ValueError("Cyclic or unresolved parent reference in schema.")
        for t in tables:
            if t in seen:
                continue
            parent = schema[t].get("parent")
            if parent is None or parent in seen:
                order.append(t); seen.add(t)
    return order


def _child_counts(parent_keys_real, child_fk_real):
    """counts[parent_key] = number of real child rows with that foreign key."""
    counts = {}
    for k in child_fk_real:
        counts[k] = counts.get(k, 0) + 1
    return [float(counts.get(pk, 0)) for pk in parent_keys_real]


def _validate_schema(tables, schema):
    """Fail fast and explicitly on out-of-scope or malformed schemas.

    oissyntheticdata supports a single-parent DAG with single-column surrogate
    keys. Anything outside that scope (compound keys, many-to-many links, missing
    or dangling references) raises a clear error here rather than silently
    producing a broken synthetic dataset. Pre-resolve such structures to a single
    surrogate key before calling.
    """
    for t, spec in schema.items():
        if t not in tables:
            raise ValueError("Schema lists table %r, but it is not in `tables`." % t)
        header = tables[t][0]
        pk = spec.get("key")
        if pk is None:
            raise ValueError("Table %r has no 'key' in its schema." % t)
        if isinstance(pk, (list, tuple)):
            raise NotImplementedError(
                "Table %r uses a compound primary key %r. Compound keys are out of "
                "scope; add a single surrogate key column and use that instead." % (t, pk))
        if pk not in header:
            raise ValueError("Primary key %r is not a column of table %r." % (pk, t))

        parent = spec.get("parent")
        fk = spec.get("foreign_key")
        if parent is None:
            continue
        if parent not in schema:
            raise ValueError("Table %r names parent %r, which is not in the schema." % (t, parent))
        if fk is None:
            raise ValueError(
                "Child table %r names parent %r but has no 'foreign_key'." % (t, parent))
        if isinstance(fk, (list, tuple)):
            raise NotImplementedError(
                "Child table %r uses a compound foreign key %r. Compound keys are out "
                "of scope; pre-resolve to a single surrogate foreign key column." % (t, fk))
        if fk not in header:
            raise ValueError("Foreign key %r is not a column of table %r." % (fk, t))

        # A valid one-to-many parent must have a UNIQUE primary key (one row per
        # parent). Duplicate parent keys usually mean the "parent" is really the
        # many-side, i.e. a many-to-many / join-table relationship — out of scope.
        parent_pk = schema[parent]["key"]
        parent_keys = tables[parent][1][parent_pk]
        if len(set(parent_keys)) != len(parent_keys):
            raise NotImplementedError(
                "Parent table %r has non-unique values in its key %r. This package "
                "models one-to-many relationships only; a non-unique parent key "
                "indicates a many-to-many link, which is out of scope. Resolve it to "
                "a parent table with a unique key (e.g. via a join table you "
                "synthesize separately)." % (parent, parent_pk))


def synthesize_relational(tables, schema, n=None, drop=None,
                          min_leaf=5, max_depth=12, smoothing=0.0, seed=12345):
    """Synthesize a set of related tables.

    tables : dict  table_name -> (header, columns)   [from oissyntheticdata.read_table]
    schema : dict  table_name -> {"key": pk,
                                   "parent": parent_table (optional),
                                   "foreign_key": fk (required if parent set)}
    n      : dict table_name -> rows for ROOT tables (children sized by fan-out);
             a single int applies to all roots; None = each root's real row count.
    drop   : dict table_name -> [columns to exclude] (besides keys), or a flat
             list applied to every table.

    Returns dict table_name -> (out_header, out_columns).
    """
    rng = random.Random(seed)
    _validate_schema(tables, schema)
    drop = drop or {}
    if isinstance(drop, (list, tuple, set)):
        drop = {t: list(drop) for t in tables}
    n_map = {} if n is None else (n if isinstance(n, dict) else {t: n for t in tables})

    synth_attr = {}   # table -> typed dict of synthesized attribute columns
    synth_key  = {}   # table -> list of surrogate pk strings
    is_num_of  = {}   # table -> is_num map for its attributes
    results    = {}

    for t in _topo_order(schema):
        header, cols = tables[t]
        spec = schema[t]
        pk = spec["key"]
        parent = spec.get("parent")
        fk = spec.get("foreign_key")
        drop_t = set(drop.get(t, [])) | {pk}
        if fk:
            drop_t.add(fk)
        attrs = [c for c in header if c not in drop_t]
        is_num, real = type_columns(cols, attrs)
        is_num_of[t] = is_num
        n_real = len(cols[header[0]])

        if parent is None:
            # -------- root table --------
            n_t = int(n_map.get(t, n_real))
            out = synth_core(real, is_num, attrs, n_t, rng,
                             min_leaf=min_leaf, max_depth=max_depth, smoothing=smoothing)
            synth_attr[t] = out
            synth_key[t] = [str(i + 1) for i in range(n_t)]
        else:
            # -------- child table --------
            p_attrs = list(synth_attr[parent].keys())
            p_is_num = is_num_of[parent]
            # real parent attributes, typed + a key->row lookup
            p_header, p_cols = tables[parent]
            _, p_real = type_columns(p_cols, p_attrs)
            p_pk_real = p_cols[schema[parent]["key"]]
            lookup = {k: i for i, k in enumerate(p_pk_real)}
            # fan-out: counts of real children per real parent
            counts = _child_counts(p_pk_real, cols[fk])

            # count model: counts ~ parent attributes (regression CART)
            n_parent = len(synth_key[parent])
            drawn = []
            if p_attrs:
                pred = {a: p_real[a] for a in p_attrs}
                croot = _tree.build_tree(list(range(len(counts))), counts, p_attrs,
                                         pred, p_is_num, "num", min_leaf=min_leaf, max_depth=max_depth)
                for i in range(n_parent):
                    row = {a: synth_attr[parent][a][i] for a in p_attrs}
                    c = _tree.sample_leaf(croot, row, p_is_num, rng, 0.0)
                    drawn.append(max(0, int(round(c if c is not None else 0))))
            else:
                pos = [c for c in counts]
                for _ in range(n_parent):
                    drawn.append(max(0, int(round(rng.choice(pos)))))

            # expand: child foreign keys + the parent attrs carried to each child row
            child_fk, parent_carry = [], {("p__" + a): [] for a in p_attrs}
            for i in range(n_parent):
                key_i = synth_key[parent][i]
                for _ in range(drawn[i]):
                    child_fk.append(key_i)
                    for a in p_attrs:
                        parent_carry["p__" + a].append(synth_attr[parent][a][i])
            total = len(child_fk)

            # real fitting data, restricted to child rows whose parent exists
            valid = [j for j in range(n_real) if cols[fk][j] in lookup]
            child_real = {a: [real[a][j] for j in valid] for a in attrs}
            fixed_real = {("p__" + a): [p_real[a][lookup[cols[fk][j]]] for j in valid] for a in p_attrs}
            combined_is_num = dict(is_num)
            for a in p_attrs:
                combined_is_num["p__" + a] = p_is_num[a]

            out = synth_core(child_real, combined_is_num, attrs, total, rng,
                             fixed_real=fixed_real, fixed_synth=parent_carry,
                             min_leaf=min_leaf, max_depth=max_depth, smoothing=smoothing)
            synth_attr[t] = out
            synth_key[t] = [str(i + 1) for i in range(total)]
            results[t] = ("__child__", child_fk)   # stash fk for assembly

        # ---- assemble this table's output in original column order ----
        out_header = [c for c in header if c not in (set(drop.get(t, [])))]
        # keep pk and fk columns in output even though they aren't "attrs"
        out_cols = {}
        strattr = stringify(synth_attr[t], list(synth_attr[t].keys()))
        nrows = len(synth_key[t])
        for c in out_header:
            if c == pk:
                out_cols[c] = list(synth_key[t])
            elif parent and c == fk:
                out_cols[c] = list(results[t][1])
            elif c in strattr:
                out_cols[c] = strattr[c]
            else:
                out_cols[c] = [""] * nrows
        results[t] = (out_header, out_cols)

    return results


def synthesize_relational_files(paths, schema, out_dir=".", **kw):
    """Read CSV/XLSX tables, synthesize relationally, write synthetic_<name>.csv.

    paths : dict table_name -> input file path
    Returns dict table_name -> (rows, cols).
    """
    import os
    tables = {t: _io.read_table(p) for t, p in paths.items()}
    res = synthesize_relational(tables, schema, **kw)
    summary = {}
    for t, (hdr, cols) in res.items():
        out_path = os.path.join(out_dir, "synthetic_%s.csv" % t)
        _io.write_table(out_path, hdr, cols)
        summary[t] = (len(cols[hdr[0]]) if hdr else 0, len(hdr))
    return summary
