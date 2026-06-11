# -*- coding: utf-8 -*-
"""
File I/O for the pipeline: CSV and *native* XLSX reading with the standard
library only (no pandas / openpyxl), so it runs inside locked environments.

Three read shapes are exposed, matching what each stage needs:
  * ``load_table``   -> (header, list-of-dict rows)        [stage 01]
  * ``load_columns`` -> {name: [string values]}            [stage 03]
  * ``load_grid``    -> list-of-rows (header + body)        [stage 00]
"""

import csv
import zipfile
import xml.etree.ElementTree as ET


def _col_index(cell_ref):
    """'AB12' -> zero-based column index using the letter part only."""
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def read_xlsx(path):
    """Read the first worksheet of an .xlsx into rows of strings (stdlib only)."""
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
            ws = sorted(n for n in names
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"))
            sheet = ws[0]
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


def read_csv_file(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def _read_raw(path):
    raw = read_xlsx(path) if path.lower().endswith((".xlsx", ".xls")) else read_csv_file(path)
    return [r for r in raw if any(str(c).strip() for c in r)]   # drop blank rows


def load_grid(path):
    """Return raw rows (header + body), blank rows dropped. [stage 00]"""
    return _read_raw(path)


def load_table(path):
    """Return (header:list[str], rows:list[dict]) from a CSV or XLSX file. [stage 01]"""
    raw = _read_raw(path)
    if not raw:
        return [], []
    header = [str(h).strip() for h in raw[0]]
    rows = []
    for r in raw[1:]:
        rows.append({header[i]: (str(r[i]).strip() if i < len(r) else "")
                     for i in range(len(header))})
    return header, rows


def load_columns(path):
    """Return dict {column_name: [string values]}. [stage 03]"""
    raw = _read_raw(path)
    if not raw:
        return {}
    header = [str(h).strip() for h in raw[0]]
    cols = {h: [] for h in header}
    for r in raw[1:]:
        for i, h in enumerate(header):
            cols[h].append(str(r[i]).strip() if i < len(r) else "")
    return cols


def write_csv(path, header, row_iter):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in row_iter:
            w.writerow(row)
