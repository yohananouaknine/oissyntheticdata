# -*- coding: utf-8 -*-
"""oissyntheticdata._io — read CSV/XLSX and write CSV using ONLY the standard library."""

import os
import csv
import zipfile
import xml.etree.ElementTree as ET

MISSING_TOKENS = {"", "na", "n/a", ".", "nan", "null", "none"}


def _col_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _read_xlsx(path):
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(T)))
        sheet = "xl/worksheets/sheet1.xml"
        if sheet not in names:
            sheet = sorted(n for n in names
                           if n.startswith("xl/worksheets/") and n.endswith(".xml"))[0]
        root = ET.fromstring(z.read(sheet))
        rows = []
        for row in root.iter("{%s}row" % ns["a"]):
            cells, maxi = {}, -1
            for c in row.findall("a:c", ns):
                ref = c.get("r", "")
                idx = _col_index(ref) if ref else len(cells)
                t = c.get("t")
                v = c.find("a:v", ns)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    is_ = c.find("a:is", ns)
                    val = "".join(x.text or "" for x in is_.iter(T)) if is_ is not None else ""
                else:
                    val = v.text if v is not None else ""
                cells[idx] = val if val is not None else ""
                maxi = max(maxi, idx)
            rows.append([cells.get(i, "") for i in range(maxi + 1)])
        return rows


def _read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def read_table(path):
    """Return (header: list[str], columns: dict[str, list[str]])."""
    raw = _read_xlsx(path) if path.lower().endswith((".xlsx", ".xls")) else _read_csv(path)
    raw = [r for r in raw if any(str(c).strip() for c in r)]
    if not raw:
        return [], {}
    header = [str(h).strip() for h in raw[0]]
    cols = {h: [] for h in header}
    for r in raw[1:]:
        for i, h in enumerate(header):
            cols[h].append(str(r[i]).strip() if i < len(r) else "")
    return header, cols


def write_table(path, header, columns):
    n = len(columns[header[0]]) if header else 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i in range(n):
            w.writerow([columns[h][i] for h in header])


def is_missing(v):
    return str(v).strip().lower() in MISSING_TOKENS
