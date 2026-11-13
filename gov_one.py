#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gov_one.py -- one file, Python standard library only, fully offline.

THE FLOW
  1. ON THE PREMISES   python gov_one.py profile
        Reads every Excel / CSV file in the folder, finds how the files relate to each
        other, and writes a folder  to_send/  holding
            profile_<table>.json   aggregates only (counts, shares, quantiles)
            schema.json            which column of which file points to which
            profile_summary.md     a plain list of exactly what leaves -- for the
                                   person who approves the e-mail
        No row, no identifier and no value seen fewer than MIN_CELL_COUNT times is written.
  2. AT HOME           python gov_one.py synth
        Rebuilds files with the same names, sheets, columns, types, distributions and
        working joins from the JSON files.  Every value is invented.
  3. AT HOME           write your own analysis script (analysis_template.py is a start):
            import gov_one as g
            T = g.open_tables('.')          # real files if present, else the synthetic ones
        and use the statistics in this file (describe, crosstab, chi_square, t_test, ols, its ...).
  4. BACK ON THE PREMISES   copy gov_one.py + your script, run the script on the real files.

  python gov_one.py            does step 1 when it sees data files, step 2 when it sees only JSON files
  python gov_one.py check      lists the files, sheets and headers it would read (no data shown)
  python gov_one.py settings   writes gov_one_settings.json (hide a column, declare a link, ...)

Nothing is imported from outside the standard library, nothing is downloaded, nothing is sent.
"""
import os
import re
import csv
import sys
import json
import math
import glob
import html
import time
import random
import bisect
import calendar
import zipfile
import argparse
import datetime

sys.dont_write_bytecode = True
VERSION = 'gov_one 3.0.0 offline (2026-11-12)'      # on PyPI: oissyntheticdata, same version number

# ==============================================================================
#  Settings.  Edit here, or -- on the premises -- in gov_one_settings.json.
# ==============================================================================
MIN_CELL_COUNT = 5            # a value / cell seen fewer times than this never leaves (k)
MIN_TABLE_ROWS = 20           # a table smaller than this is described by its shape only
MAX_CATEGORIES = 500          # a text column with more distinct values is treated as free text / id
ID_NAME_HINTS = ("id", "key", "code", "מזהה", "מיספור", "תז")
MIN_GROUP_KEYS = 20           # a key column needs more distinct values than this
QUANTILE_GRID = [0, 5, 10, 25, 50, 75, 90, 95, 100]
USE_ROBUST_BOUNDS = True
P_LOW, P_HIGH = 1.0, 99.0
MISSING_TOKENS = {"", "na", "n/a", ".", "nan", "null", "none", "#n/a", "#null!", "#div/0!", "#value!", "#ref!", "-"}
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]
OUTPUT_PREFIXES = ("synthetic_", "profile_", "~$")       # never read our own outputs or Excel lock files
SEND_DIR = "to_send"
SYNTH_DIR = "synthetic"
SETTINGS_FILE = "gov_one_settings.json"
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGIT = "0123456789"
DEFAULT_SEED = 12345
DEFAULT_INJECT_EDGES = False

# A column whose HEADER says it holds a person's name, an id number, a phone, an address or free
# text is described by its shape only (length, letters / digits) -- its values never leave.
SENSITIVE_PHRASES = (
    "שם פרטי", "שם משפחה", "שם מלא", "שם האב", "שם האם", "שם הלקוח", "שם לקוח", "שם המטופל", "שם מטופל",
    "שם הפונה", "שם פונה", "שם העובד", "שם עובד", "שם המטפל", "שם מטפל", "שם הרופא", "שם רופא",
    "שם התלמיד", "שם תלמיד", "שם האסיר", "שם אסיר", "שם המשפחה", "שם איש קשר", "תעודת זהות", "מספר זהות",
    "מס זהות", "מס' זהות", "ת.ז", "ת\"ז", "ת''ז", "דרכון", "טלפון", "נייד", "פלאפון", "כתובת", "רחוב",
    "דוא\"ל", "דואל", "מייל", "הערות", "הערה", "מלל חופשי", "תיאור המקרה", "פירוט", "איש קשר", "אנשי קשר",
    "איש הקשר", "קרוב משפחה", "אפוטרופוס", "contact person", "next of kin", "guardian",
    "first name", "last name", "full name", "surname", "family name", "given name", "patient name",
    "client name", "contact name", "passport", "phone", "mobile", "address", "street", "email",
    "e-mail", "remarks", "comments", "free text", "national id", "id number", "ssn")
SENSITIVE_WORDS = ("שם", "name", "notes", "note", "comment", "תיאור", "description")      # the whole header
# a header containing one of these words usually holds the NAME of a member of staff
SENSITIVE_ROLE_WORDS = ("עובד", "עובדת", "עו\"ס", "עוס", "רופא", "רופאה", "מטפל", "מטפלת", "אחראי", "אחראית", "מנהל",
                        "מנהלת", "פקיד", "פקידה", "מדריך", "מדריכה", "מורה", "מלווה", "רכז", "רכזת", "מפקח", "מפקחת",
                        "חוקר", "חוקרת", "קצין", "קצינה", "אח", "אחות", "worker", "doctor", "physician",
                        "therapist", "manager", "officer", "employee", "teacher", "nurse", "caseworker")

# joint (two-way) tables kept so that the synthetic columns move together like the real ones
JOINT_MAX_PARENT_LEVELS = 60
JOINT_MAX_CHILD_LEVELS = 300
JOINT_MAX_TABLES = 40
JOINT_MAX_SECOND = 20         # how many columns may follow a second column as well
JOINT_SAMPLE_ROWS = 20000
JOINT_MIN_V = 0.05
JOINT_MIN_V_SECOND = 0.03     # the same, for what a second column adds beyond the first
CROSSTAB_NUMERIC_BINS = 12


# ==============================================================================
#  Value helpers
# ==============================================================================
def is_missing(v):
    return str(v).strip().lower() in MISSING_TOKENS


def to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def looks_int(v):
    f = to_float(v)
    return f is not None and float(f).is_integer()


_RE_TS = re.compile(r'^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?)?\s*$')


def parse_date(v):
    """Return (datetime, format) or (None, None)."""
    sv = str(v).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(sv, fmt), fmt
        except ValueError:
            continue
    m = _RE_TS.match(sv)
    if m:
        try:
            g = [int(x) for x in m.groups() if x is not None]
            return datetime.datetime(*g), ("%Y-%m-%d %H:%M:%S" if len(g) > 3 else "%Y-%m-%d")
        except ValueError:
            return None, None
    return None, None


def parse_date_dt(v):
    """Return the datetime only (or None)."""
    return parse_date(v)[0]

EXCEL_EPOCH = datetime.datetime(1899, 12, 30)
SERIAL_MIN, SERIAL_MAX = 20000, 60000          # ~1954-09 .. ~2064-03
DATE_NAME_TOKENS = ("date", "תאריך", "yyyy", "dt")   # full calendar date (not year/month)


def excel_serial_to_date(v):
    """Excel serial number -> datetime (or None)."""
    f = to_float(v)
    if f is None:
        return None
    try:
        return EXCEL_EPOCH + datetime.timedelta(days=int(round(f)))
    except (ValueError, OverflowError):
        return None


def date_to_excel_serial(d):
    """datetime/date -> Excel serial number (int)."""
    if isinstance(d, datetime.date) and not isinstance(d, datetime.datetime):
        d = datetime.datetime(d.year, d.month, d.day)
    return int((d - EXCEL_EPOCH).days)


def name_is_dateish(name):
    nm = str(name).strip().lower()
    return any(tok in nm for tok in DATE_NAME_TOKENS)


def looks_like_serial(v):
    f = to_float(v)
    return f is not None and float(f).is_integer() and SERIAL_MIN <= f <= SERIAL_MAX


def is_serial_date_col(values, name=""):
    """True only when the column name signals a date and the values are integers in the
    Excel-serial range. Year (e.g. 2024) and month (1-12) columns fall below the range."""
    if not name_is_dateish(name):
        return False
    present = [v for v in values if not is_missing(v)]
    if not present:
        return False
    return sum(1 for v in present if looks_like_serial(v)) / len(present) > 0.9


def month_of(value):
    d = parse_date_dt(value)
    if d is None and looks_like_serial(value):
        d = excel_serial_to_date(value)
    return str(d.month) if d else ""


def signature(value):
    return "".join("D" if ch.isdigit() else "A" if ch.isalpha() else ch
                   for ch in str(value))


DATE_SAMPLE = 600


def _stride_sample(xs, k=DATE_SAMPLE):
    """Deterministic sample of at most k values spread over the column."""
    n = len(xs)
    if n <= k:
        return xs
    step = n / float(k)
    return [xs[int(i * step)] for i in range(k)]


def is_date_col(values, name=""):
    present = [v for v in values if not is_missing(v)]
    if not present:
        return False
    if is_serial_date_col(present, name):          # Excel-serial dates (numeric) count as dates
        return True
    if all(to_float(v) is not None for v in present):
        return False
    smp = _stride_sample(present)
    return sum(1 for v in smp if parse_date_dt(v) is not None) / len(smp) > 0.9


# ==============================================================================
# Statistics (standard library only)
# ==============================================================================

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def std_dev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5   # population SD


def percentile(sorted_xs, p):
    if not sorted_xs:
        return 0.0
    k = (len(sorted_xs) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_xs):
        return sorted_xs[f] + c * (sorted_xs[f + 1] - sorted_xs[f])
    return sorted_xs[f]


# ==============================================================================
#  Reading Excel (.xlsx / .xlsm) and CSV with the standard library
# ==============================================================================
_RE_ROW = re.compile(r'<row\b[^>]*?(?:/>|>(.*?)</row>)', re.S)
_RE_CELL = re.compile(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_RE_ATTR_R = re.compile(r'\br="([A-Z]+)\d*"')
_RE_ATTR_T = re.compile(r'\bt="([^"]*)"')
_RE_V = re.compile(r'<v>(.*?)</v>', re.S)
_RE_T = re.compile(r'<t\b[^>]*>(.*?)</t>', re.S)
_RE_SI = re.compile(r'<si\b[^>]*>(.*?)</si>', re.S)
_CHUNK = 8 * 1024 * 1024


_UNESC_MEMO = {}


def _unesc(x):
    if '&' not in x:
        return x
    y = _UNESC_MEMO.get(x)
    if y is None:
        import html as _html
        y = _html.unescape(x.replace('&#13;', ''))
        if len(_UNESC_MEMO) < 500000:
            _UNESC_MEMO[x] = y
    return y


def _col_idx(letters):
    ci = 0
    for ch in letters:
        ci = ci * 26 + (ord(ch) - 64)
    return ci - 1


def _stream_blocks(fh, pattern, close_tag):
    """Yield regex matches of complete blocks from a file object, chunk by chunk."""
    buf = ''
    dec_tail = b''
    while True:
        raw = fh.read(_CHUNK)
        if not raw and not dec_tail:
            break
        raw = dec_tail + raw
        try:
            txt = raw.decode('utf-8')
            dec_tail = b''
        except UnicodeDecodeError:              # chunk split inside a multibyte char
            for cut in range(1, 5):
                try:
                    txt = raw[:-cut].decode('utf-8')
                    dec_tail = raw[-cut:]
                    break
                except UnicodeDecodeError:
                    continue
            else:
                txt = raw.decode('utf-8', 'replace')
                dec_tail = b''
        buf += txt
        last = buf.rfind(close_tag)
        if last < 0:
            if not raw:
                break
            continue
        last += len(close_tag)
        for m in pattern.finditer(buf, 0, last):
            yield m
        buf = buf[last:]
        if not raw:
            break
    for m in pattern.finditer(buf):
        yield m


_RE_TAG_SHEET = re.compile(r'<sheet\b[^>]*>', re.S)
_RE_TAG_REL = re.compile(r'<Relationship\b[^>]*>', re.S)
_RE_A_NAME = re.compile(r'\bname="([^"]*)"')
_RE_A_RID = re.compile(r'\br:id="([^"]*)"')
_RE_A_ID = re.compile(r'\bId="([^"]*)"')
_RE_A_TARGET = re.compile(r'\bTarget="([^"]*)"')


class _SheetList(object):
    """attribute-order-independent parsing of <sheet .../> and <Relationship .../>"""
    @staticmethod
    def findall(txt):
        out = []
        for tag in _RE_TAG_SHEET.findall(txt):
            n, r = _RE_A_NAME.search(tag), _RE_A_RID.search(tag)
            if n and r:
                out.append((n.group(1), r.group(1)))
        return out


class _RelList(object):
    @staticmethod
    def findall(txt):
        out = []
        for tag in _RE_TAG_REL.findall(txt):
            i, t = _RE_A_ID.search(tag), _RE_A_TARGET.search(tag)
            if i and t:
                out.append((i.group(1), t.group(1)))
        return out

_RE_SHEET = _SheetList
_RE_REL = _RelList


def xlsx_sheets(path):
    """[(sheet name, zip part)] in workbook order; falls back to sorted parts."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        out = []
        try:
            wb = z.read('xl/workbook.xml').decode('utf-8', 'replace')
            rels = dict(_RE_REL.findall(z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'replace')))
            for sname, rid in _RE_SHEET.findall(wb):
                target = rels.get(rid, '')
                part = 'xl/' + target.lstrip('/').replace('xl/', '', 1)
                if part not in names:
                    cand = [n for n in names if n.endswith(os.path.basename(target))]
                    part = cand[0] if cand else ''
                if part:
                    out.append((_unesc(sname), part))
        except KeyError:
            pass
        if not out:
            out = [(os.path.basename(n), n) for n in sorted(
                n for n in names if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))]
        return out

def dedupe_header(header):
    """v2: duplicate or blank header names no longer collapse into one column.
    Blanks become col_N; repeats get a _2, _3 suffix. Returns (header, notes)."""
    out, seen, notes = [], {}, []
    for i, h in enumerate(header):
        h = str(h).strip()
        if not h:
            h = "col_%d" % (i + 1)
            notes.append("blank header at column %d -> %s" % (i + 1, h))
        if h in seen:
            seen[h] += 1
            new = "%s_%d" % (h, seen[h])
            notes.append("duplicate header %r at column %d -> %s" % (h, i + 1, new))
            h = new
        else:
            seen[h] = 1
        out.append(h)
    return out, notes

def _is_numeric(s):
    s = str(s).strip()
    if not s:
        return False
    if s[0] in "+-":
        s = s[1:]
    if not s or s == ".":
        return False
    seen_dot = seen_digit = False
    for ch in s:
        if ch == ".":
            if seen_dot:
                return False
            seen_dot = True
        elif ch.isdigit():
            seen_digit = True
        else:
            return False
    return seen_digit


def _xl_colref(c):
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def _xl_esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_RE_ATTR_S = re.compile(r'\bs="(\d+)"')
_RE_NUMFMT = re.compile(r'<numFmt\b[^>]*>')
_RE_XF = re.compile(r'<xf\b[^>]*>')
_RE_A_FMTID = re.compile(r'\bnumFmtId="(\d+)"')
_RE_A_FMTCODE = re.compile(r'\bformatCode="([^"]*)"')
_BUILTIN_DATE = set(range(14, 18)) | {22} | set(range(27, 37)) | set(range(50, 59))
_BUILTIN_TIME = {18, 19, 20, 21, 45, 46, 47}


def _date_styles(z, names):
    """{cell style index: 'date' | 'time'} for the styles Excel shows as dates or times."""
    if 'xl/styles.xml' not in names:
        return {}
    xml = z.read('xl/styles.xml').decode('utf-8', 'replace')
    custom = {}
    for tag in _RE_NUMFMT.findall(xml):
        i, c = _RE_A_FMTID.search(tag), _RE_A_FMTCODE.search(tag)
        if i and c:
            code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.', '', _unesc(c.group(1))).lower()
            if 'general' in code or not re.search(r'[dmyhs]', code):
                continue
            custom[int(i.group(1))] = 'date' if re.search(r'[dy]', code) else 'time'
    block = re.search(r'<cellXfs\b[^>]*>(.*?)</cellXfs>', xml, re.S)
    out = {}
    for k, tag in enumerate(_RE_XF.findall(block.group(1)) if block else []):
        m = _RE_A_FMTID.search(tag)
        fid = int(m.group(1)) if m else 0
        if fid in _BUILTIN_DATE:
            out[k] = 'date'
        elif fid in _BUILTIN_TIME:
            out[k] = 'time'
        elif fid in custom:
            out[k] = custom[fid]
    return out


def _serial_text(val, kind):
    """An Excel date / time number as text: 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS'."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f < 0 or f >= 2958466:
        return None
    if kind == 'time' or f < 1:
        s = int(round((f - int(f)) * 86400))
        return '%02d:%02d:%02d' % (s // 3600 % 24, s // 60 % 60, s % 60)
    d = EXCEL_EPOCH + datetime.timedelta(seconds=int(round(f * 86400)))
    if d.hour == d.minute == d.second == 0:
        return d.strftime('%Y-%m-%d')
    return d.strftime('%Y-%m-%d %H:%M:%S')


def read_sheet(path, part, max_rows=None):
    """One worksheet -> (rows of strings, {column index: number of date cells}).
    A cell Excel shows as a date comes back as 'YYYY-MM-DD' whatever the column is called."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if 'xl/sharedStrings.xml' in names:
            with z.open('xl/sharedStrings.xml') as fh:
                for m in _stream_blocks(fh, _RE_SI, '</si>'):
                    shared.append(_unesc(''.join(_RE_T.findall(m.group(1)))))
        dstyles = _date_styles(z, names)
        rows, datecells = [], {}
        with z.open(part) as fh:
            for rm in _stream_blocks(fh, _RE_ROW, '</row>'):
                if max_rows is not None and len(rows) >= max_rows:
                    break
                body = rm.group(1)
                if not body:
                    continue
                cells = {}
                for cm in _RE_CELL.finditer(body):
                    attrs, inner = cm.group(1), cm.group(2)
                    rr = _RE_ATTR_R.search(attrs)
                    ci = _col_idx(rr.group(1)) if rr else len(cells)
                    if not inner:
                        cells[ci] = ''
                        continue
                    tm = _RE_ATTR_T.search(attrs)
                    t = tm.group(1) if tm else ''
                    if t == 'inlineStr':
                        cells[ci] = _unesc(''.join(_RE_T.findall(inner)))
                        continue
                    vm = _RE_V.search(inner)
                    val = vm.group(1) if vm else None
                    if val is None:
                        cells[ci] = ''
                    elif t == 's':
                        try:
                            cells[ci] = shared[int(val)]
                        except (ValueError, IndexError):
                            cells[ci] = ''
                    else:
                        if dstyles and t in ('', 'n'):
                            sm = _RE_ATTR_S.search(attrs)
                            kind = dstyles.get(int(sm.group(1))) if sm else None
                            txt = _serial_text(val, kind) if kind else None
                            if txt is not None:
                                cells[ci] = txt
                                datecells[ci] = datecells.get(ci, 0) + 1
                                continue
                        cells[ci] = _unesc(val)
                if cells:
                    w = max(cells) + 1
                    rows.append([cells.get(i, '') for i in range(w)])
        return rows, datecells


def read_csv_rows(path):
    """A CSV file -> rows of strings.  Encoding (UTF-8, UTF-16, Windows Hebrew) and delimiter are detected."""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode('utf-16')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp1255', 'replace')
    head = text[:20000]
    delim = max(',;\t|', key=lambda d: head.count(d))
    return [row for row in csv.reader(text.splitlines(), delimiter=delim)]


def find_header_row(raw):
    """Index of the header row.  Ministry sheets often start with a title and a date; the header is
    the first row that is nearly as wide as the data below it and holds labels, not numbers."""
    look = raw[:60]
    if len(look) < 3:
        return 0
    widths = sorted(sum(1 for c in r if str(c).strip()) for r in look)
    typical = widths[len(widths) // 2]
    if typical < 2:
        return 0
    for i, r in enumerate(look[:30]):
        filled = [str(c).strip() for c in r if str(c).strip()]
        if len(filled) < max(2, 0.6 * typical):
            continue
        labels = sum(1 for c in filled if to_float(c) is None and parse_date_dt(c) is None)
        if labels >= 0.8 * len(filled) and len(set(filled)) >= 0.8 * len(filled):
            return i
    return 0


def read_file_tables(path):
    """Every non-empty sheet of a workbook (or the one table of a CSV) as a table:
    {'base', 'file', 'sheet', 'file_type', 'header', 'rows' (list of dict of str), 'notes',
     'excel_dates' (columns stored as real Excel dates), 'header_row'}.
    The first sheet is named after the file; further sheets are 'file#sheet'."""
    fname = os.path.basename(path)
    stem = os.path.splitext(fname)[0]
    if path.lower().endswith(('.csv', '.tsv')):
        sheets = [('', read_csv_rows(path), {})]
        ftype = 'csv'
    else:
        ftype = 'xlsx'
        sheets = []
        for sname, part in xlsx_sheets(path):
            rows, dc = read_sheet(path, part)
            sheets.append((sname, rows, dc))
    out = []
    for sname, raw, datecells in sheets:
        raw = [r for r in raw if any(str(c).strip() for c in r)]
        if not raw:
            continue
        h = find_header_row(raw)
        head = [str(c).strip() for c in raw[h]]
        while head and not head[-1]:
            head.pop()
        if not head:
            continue
        header, notes = dedupe_header(head)
        if h:
            notes.append("%d row(s) above the header were skipped (titles)" % h)
        width = len(header)
        rows = [{header[j]: (str(r[j]).strip() if j < len(r) else '') for j in range(width)} for r in raw[h + 1:]]
        wide = sum(1 for r in raw[h + 1:] if len(r) > width and any(str(c).strip() for c in r[width:]))
        if wide:
            notes.append("%d row(s) have values to the right of the last header cell; those cells were ignored" % wide)
        excel_dates = set()
        for j, cnt in datecells.items():
            if j < width:
                filled = sum(1 for r in rows if r[header[j]] != '')
                if filled and cnt >= 0.9 * filled:
                    excel_dates.add(header[j])
        out.append({'base': stem if not out else '%s#%s' % (stem, sname), 'file': fname, 'sheet': sname,
                    'sheet_index': len(out), 'file_type': ftype, 'header': header, 'rows': rows, 'notes': notes,
                    'excel_dates': excel_dates, 'header_row': h})
    return out


def find_inputs(folder):
    """(data files to read, files that cannot be read and why).  Our own outputs are never inputs."""
    good, bad = [], []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        low = name.lower()
        if not os.path.isfile(p) or low.startswith(OUTPUT_PREFIXES):
            continue
        if low.endswith(('.xlsx', '.xlsm', '.csv', '.tsv')):
            good.append(p)
        elif low.endswith('.xls'):
            bad.append((name, 'old .xls format: open it in Excel and save as .xlsx'))
        elif low.endswith('.xlsb'):
            bad.append((name, 'binary .xlsb format: open it in Excel and save as .xlsx'))
    return good, bad


# ==============================================================================
#  Writing Excel (several sheets, real date cells) with the standard library
# ==============================================================================
_STYLES_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
               '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
               '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
               '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
               '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
               '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
               '<xf numFmtId="22" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
               '</styleSheet>')


def _sheet_name(name, used):
    s = re.sub(r'[\[\]:*?/\\]', ' ', str(name or 'Sheet')).strip()[:31] or 'Sheet'
    base, k = s, 2
    while s.lower() in used:
        s = '%s %d' % (base[:28], k)
        k += 1
    used.add(s.lower())
    return s


def _cell_xml(ref, val):
    if val is None or val == '':
        return ''
    if isinstance(val, datetime.datetime):
        f = (val - EXCEL_EPOCH).total_seconds() / 86400.0
        if val.hour == val.minute == val.second == 0:
            return '<c r="%s" s="1"><v>%d</v></c>' % (ref, int(round(f)))
        return '<c r="%s" s="2"><v>%.8f</v></c>' % (ref, f)
    if isinstance(val, datetime.date):
        return '<c r="%s" s="1"><v>%d</v></c>' % (ref, (datetime.datetime(val.year, val.month, val.day) - EXCEL_EPOCH).days)
    if isinstance(val, bool):
        return '<c r="%s"><v>%d</v></c>' % (ref, int(val))
    if isinstance(val, int):
        return '<c r="%s"><v>%d</v></c>' % (ref, val)
    if isinstance(val, float):
        if val != val or val in (float('inf'), float('-inf')):
            return ''
        return '<c r="%s"><v>%s</v></c>' % (ref, repr(val))
    return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, _xl_esc(val))


def write_workbook(path, sheets):
    """sheets: [(sheet name, rows)].  A cell may be text, a number, a date / datetime, or empty.
    Numbers are written as numbers, dates as real Excel dates, text as text."""
    used, names = set(), []
    for name, _ in sheets:
        names.append(_sheet_name(name, used))
    n = len(sheets)
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(n))
              + '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_xl_esc(nm).replace('"', '&quot;'), i + 1, i + 1) for i, nm in enumerate(names))
          + '</sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(n))
              + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1)
              + '</Relationships>')

    def info(name):
        zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        return zi

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in (('[Content_Types].xml', ctypes), ('_rels/.rels', rels), ('xl/workbook.xml', wb),
                           ('xl/_rels/workbook.xml.rels', wbrels), ('xl/styles.xml', _STYLES_XML)):
            z.writestr(info(name), data)
        for i, (_, rows) in enumerate(sheets):
            with z.open(info('xl/worksheets/sheet%d.xml' % (i + 1)), 'w') as fh:
                fh.write(('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                          '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>').encode('utf-8'))
                buf = []
                for ri, row in enumerate(rows, start=1):
                    cells = ''.join(_cell_xml(_xl_colref(ci) + str(ri), (str(v) if ri == 1 and v is not None else v))
                                    for ci, v in enumerate(row))
                    buf.append('<row r="%d">%s</row>' % (ri, cells))
                    if len(buf) >= 5000:
                        fh.write(''.join(buf).encode('utf-8'))
                        buf = []
                fh.write((''.join(buf) + '</sheetData></worksheet>').encode('utf-8'))


# ==============================================================================
#  Relationships between tables (found from the values, on the premises; only
#  column names and group-size distributions are written down)
# ==============================================================================
def _norm_name(s):
    """Normalize for tolerant matching: trim, and treat '_' and ' ' as the same. This is
    why 'מגמה_מצבות...' in the spec matches a file named 'מגמה מצבות...' on disk."""
    return " ".join(str(s).strip().replace("_", " ").split())

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


ID_DISTINCT_RATIO = 0.5   # an integer column with at least this distinct-ratio looks like a key


_DATE_TOKENS = ("date", "time", "יום", "תאריך", "שנה", "שנת", "חודש", "year", "month")


def _dateish(name, present):
    """True for date/time columns (by name, by parseable date strings, or Excel serials),
    so they are never mistaken for keys even when stored as high-cardinality integers."""
    nm = str(name).strip().lower()
    if any(tok in nm for tok in _DATE_TOKENS):
        return True
    pv = present[:200]
    if pv and not _all_int(pv):
        hits = sum(1 for v in pv if parse_date(v)[0] is not None)
        if hits and hits / len(pv) > 0.9:
            return True
    return False


# v2: names that mark a MEASUREMENT, never a key (counts, ages, amounts). Without
# this, two small-integer count columns in different files can pass the value-
# containment test and be declared a foreign key ("כמות אירועים -> מיספור מאסר").
MEASURE_NAME_TOKENS = ("כמות", "count", "גיל", "age", "סכום", "amount", "total", "סה\"כ",
                       "מיספור מאסר", "מספר מאסרים",   # incarceration ORDINALS, not ids
                       "מספר חודש", "month", "שנה", "year")


def _measureish(name):
    nm = str(name).strip().lower()
    return any(tok in nm for tok in MEASURE_NAME_TOKENS)


def _keylike(rows, c, distinct_c):
    """A column that can act as a primary/foreign key: high-cardinality and either
    (integer-valued AND id-named) or near-unique, so free-text, small categoricals,
    dates and count/age measurements are excluded."""
    present = [r.get(c, "") for r in rows if not is_missing(r.get(c, ""))]
    n = len(present)
    if n == 0 or distinct_c <= MIN_GROUP_KEYS:
        return False
    if _dateish(c, present) or _measureish(c):
        return False
    nm = str(c).strip().lower()
    nm_words = set(nm.replace("/", " ").replace("-", " ").replace("_", " ").split())
    id_named = any(nm == h or nm.endswith("_" + h) or h in nm_words for h in ID_NAME_HINTS)
    near_unique = (distinct_c / n) >= ID_DISTINCT_RATIO
    return near_unique or (_all_int(present[:500]) and id_named)


MEASURE_NAME_TOKENS = ("count", "age", "amount", "total", "sum", "price", "salary", "income", "weight", "height",
                       "score", "percent", "days", "hours", "month", "year", "number of", "qty", "quantity",
                       "כמות", "גיל", "סכום", "סה\"כ", "סך", "מחיר", "שכר", "הכנסה", "משקל", "גובה", "ציון",
                       "אחוז", "ימים", "שעות", "חודש", "שנה", "שנת", "מספר ילדים", "מספר נפשות", "מספר ימי")


def _measureish(name):
    """A header that names a measurement (a count, an age, an amount) -- never a key.
    English words must match whole words ('age' does not match 'stage'); Hebrew matches as text."""
    nm = str(name).strip().lower()
    words = set(re.split(r'[^a-z0-9]+', nm))
    for tok in MEASURE_NAME_TOKENS:
        if tok.isascii():
            if (' ' in tok and tok in nm) or tok in words:
                return True
        elif tok in nm:
            return True
    return False


def is_sensitive_name(name):
    nm = ' '.join(str(name).strip().lower().replace('_', ' ').split())
    if nm in SENSITIVE_WORDS or any(p in nm for p in SENSITIVE_PHRASES):
        return True
    return bool(set(re.split(r"[\s\-./,()]+", nm)) & set(SENSITIVE_ROLE_WORDS))


_GENERIC_NAME_WORDS = {"id", "no", "num", "number", "code", "key", "מספר", "מס", "קוד", "מזהה", "של", "the", "of"}


def _name_words(name):
    return {w for w in re.split(r"[\s_\-./'\"]+", str(name).strip().lower()) if len(w) >= 2} - _GENERIC_NAME_WORDS


def _col_facts(rows, c):
    """What a column needs to be a key: enough distinct values, whole numbers or text, not a date, not a measure."""
    vals = _nonmissing(rows, c)
    if not vals:
        return None
    s = set(vals)
    if len(s) <= MIN_GROUP_KEYS:
        return None
    smp = _stride_sample(vals, 400)
    numeric = all(to_float(v) is not None for v in smp)
    is_int = numeric and all(looks_int(v) for v in smp)
    if (numeric and not is_int) or _dateish(c, vals) or _measureish(c):
        return None
    f = {'set': s, 'n': len(vals), 'distinct': len(s), 'ratio': len(s) / float(len(vals)), 'int': is_int}
    if is_int:
        try:
            nums = [float(str(v).replace(',', '')) for v in s]
            f['lo'], f['hi'] = min(nums), max(nums)
        except ValueError:
            f['int'] = False
    return f


def detect_links(tables, forced=(), forbidden=()):
    """tables: {base: {'file', 'header', 'rows'}}.  A column of one table is a link to a column of
    another when at least 80% of its distinct values are found there and the other side is close to
    unique.  Two whole-number columns with different names must also cover a similar range, so an
    age column is never 'linked' to a running number.  forced: [(child, col, parent, col)];
    forbidden: {'table.column'}.  Returns the schema written to schema.json."""
    bases = list(tables)
    header = {b: tables[b]['header'] for b in bases}
    rows = {b: tables[b]['rows'] for b in bases}
    facts = {b: {} for b in bases}
    uniq = {b: {} for b in bases}
    for b in bases:
        for c in header[b]:
            uniq[b][c] = _is_unique(rows[b], c)
            f = _col_facts(rows[b], c)
            if f:
                facts[b][c] = f
    cand = {b: {} for b in bases}
    for b in bases:
        for cc, cf in facts[b].items():
            if '%s.%s' % (b, cc) in forbidden:
                continue
            best = None
            for p in bases:
                if p == b:
                    continue
                for pc, pf in facts[p].items():
                    if pf['ratio'] < ID_DISTINCT_RATIO or pf['distinct'] < cf['distinct']:
                        continue
                    overlap = len(cf['set'] & pf['set']) / float(cf['distinct'])
                    if overlap < 0.8:
                        continue
                    same_name = _norm_name(cc).lower() == _norm_name(pc).lower()
                    if uniq[b][cc] and not same_name:
                        continue                           # two running numbers (case no. / payment no.) are not a link
                    if cf['int'] and pf['int'] and not same_name:
                        span_p = (pf['hi'] - pf['lo']) or 1.0
                        if (cf['hi'] - cf['lo']) / span_p < 0.5:
                            continue                       # e.g. ages 18-90 inside ids 1-5000
                    score = (same_name, len(_name_words(cc) & _name_words(pc)), overlap, uniq[p][pc], pf['distinct'])
                    if best is None or score > best[0]:
                        best = (score, p, pc)
            if best:
                _, p, pc = best
                mirror = (uniq[b][cc] and cf['set'] == facts[p][pc]['set'] and b > p)
                if not mirror:
                    cand[b][cc] = (p, pc, best[0][2])
    for a in bases:                                        # A->B and B->A: keep the stronger direction
        for ca, (pa, pca, oa) in list(cand[a].items()):
            for cb, (pb, pcb, ob) in list(cand.get(pa, {}).items()):
                if pb == a:
                    if ob <= oa:
                        cand[pa].pop(cb, None)
                    else:
                        cand[a].pop(ca, None)
    for (b, cc, p, pc) in forced:
        if b in tables and p in tables and cc in header[b] and pc in header[p]:
            cand[b][cc] = (p, pc, 1.0)
    files = {}
    for b in bases:
        links = []
        for cc, (p, pc, ov) in cand[b].items():
            g, q, _ = _fanout(rows[b], cc)
            links.append({"parent": p, "link": cc, "parent_key": pc, "share_found": round(ov, 3),
                          "fanout_grid": g, "fanout_quantiles": q})
        own = _own_key(header[b], uniq[b])
        if not links:
            files[b] = {"file": tables[b]['file'], "parent": None, "link": None, "parent_key": None,
                        "inherited": [], "key": own, "fanout_grid": None, "fanout_quantiles": None, "links": []}
            continue
        primary = max(links, key=lambda L: len(set(_nonmissing(rows[b], L["link"]))))
        for L in links:
            L["primary"] = (L is primary)
        phead = set(header[primary["parent"]])
        inherited = [c for c in header[b] if c != primary["link"] and c in phead
                     and _determines(rows[b], primary["link"], c)]
        files[b] = {"file": tables[b]['file'], "parent": primary["parent"], "link": primary["link"],
                    "parent_key": primary["parent_key"], "inherited": inherited, "key": own,
                    "fanout_grid": primary["fanout_grid"], "fanout_quantiles": primary["fanout_quantiles"],
                    "links": links}
    return {"tool": VERSION, "files": files,
            "order": _topo({b: {"parent": files[b]["parent"]} for b in bases})}


# ==============================================================================
#  Profiling one column (aggregates only)
# ==============================================================================
def _numeric_bins(values, nbins=CROSSTAB_NUMERIC_BINS):
    nums = sorted(to_float(v) for v in values if to_float(v) is not None)
    if not nums:
        return []
    edges = sorted({percentile(nums, 100.0 * i / nbins) for i in range(1, nbins)})
    return edges


def _bin_of(v, edges):
    f = to_float(v)
    if f is None:
        return ""
    return str(bisect.bisect_left(edges, f))

def profile_column(name, values,
                   min_cell_count=MIN_CELL_COUNT, use_robust=USE_ROBUST_BOUNDS,
                   p_low=P_LOW, p_high=P_HIGH, quantile_grid=QUANTILE_GRID,
                   max_categories=MAX_CATEGORIES, id_hints=ID_NAME_HINTS,
                   min_group_keys=MIN_GROUP_KEYS, force_key=False):
    present = [v for v in values if not is_missing(v)]
    n = len(values)
    n_missing = n - len(present)
    distinct = sorted(set(present))
    col = {"name": name, "n": n,
           "missing_rate": round(n_missing / n, 6) if n else 0.0,
           "n_unique": len(distinct)}
    if not present:
        col["kind"] = "empty"
        return col

    # Relationship-detected keys are profiled as identifiers regardless of their values,
    # so a foreign key with a low distinct-ratio is never sent through the numeric branch
    # (whose stored quantiles would be real key values). Identifier profiles hold only
    # counts and string lengths -- no key value ever leaves the premises.
    if force_key:
        lengths = [len(str(v)) for v in present]
        if len(distinct) == len(present):
            col.update({"kind": "identifier_unique",
                        "len_min": min(lengths), "len_max": max(lengths)})
        else:
            counts = {}
            for v in present:
                counts[v] = counts.get(v, 0) + 1
            sizes = sorted(counts.values())
            grid = list(quantile_grid)
            gq = [percentile(sizes, p) for p in grid]
            if use_robust:
                gq[0] = percentile(sizes, p_low)
                gq[-1] = percentile(sizes, p_high)
            col.update({"kind": "identifier_group", "n_groups": len(counts),
                        "group_size_grid": grid,
                        "group_size_quantiles": [round(x, 6) for x in gq]})
        return col

    all_numeric = all(to_float(v) is not None for v in present)
    all_int = all_numeric and all(looks_int(v) for v in present)
    _smp = _stride_sample(present)
    date_hits = sum(1 for v in _smp if parse_date(v)[0] is not None)
    is_date = (not all_numeric) and (date_hits / len(_smp) > 0.9)
    low = {v.lower() for v in present}
    is_bool = low <= {"0", "1", "true", "false", "yes", "no", "y", "n"} and len(distinct) <= 3
    nm = name.strip().lower()
    nm_words = set(nm.replace("/", " ").replace("-", " ").replace("_", " ").split())
    is_id_name = any(nm == h or nm.endswith("_" + h) or h in nm_words for h in id_hints)
    if _measureish(name):
        is_id_name = False

    # derived month columns are cyclic codes, not magnitudes -> categorical
    if nm.endswith("_month"):
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        freqs, rare_i = {}, 1
        for label, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            if cnt < min_cell_count:
                freqs["RARE_%03d" % rare_i] = cnt
                rare_i += 1
            else:
                freqs[label] = cnt
        col.update({"kind": "categorical", "frequencies": freqs,
                    "rare_levels_suppressed": rare_i - 1, "derived_month": True})
        return col

    # Excel-serial date columns are integers but are dates, not measurements or keys.
    # Profile them as datetime (with a 'serial' flag) so synthesis emits serials and the
    # derived _month column carries seasonality. Handled before the all-int branches.
    if is_serial_date_col(present, name):
        dts = [d for d in (excel_serial_to_date(v) for v in present) if d is not None]
        if dts:
            yfreq = {}
            for d in dts:
                yfreq[str(d.year)] = yfreq.get(str(d.year), 0) + 1
            col.update({"kind": "datetime", "format": "%Y-%m-%d", "serial": True,
                        "min": min(dts).strftime("%Y-%m-%d"),
                        "max": max(dts).strftime("%Y-%m-%d"), "year_freqs": yfreq})
            return col

    # integer identifiers are NOT measurements: handle before the numeric branch.
    # Require an id-like NAME here; columns that are merely all-distinct (a precise
    # measurement, a total, a monthly count) stay numeric. Real foreign/parent keys are
    # caught earlier by force_key (the relationship pass), so this never misses a join.
    if all_int and is_id_name and len(distinct) == len(present):
        lengths = [len(v) for v in present]
        col.update({"kind": "identifier_unique",
                    "len_min": min(lengths), "len_max": max(lengths)})
        return col

    if all_int and is_id_name and len(distinct) > min_group_keys:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        sizes = sorted(counts.values())
        grid = list(quantile_grid)
        gq = [percentile(sizes, p) for p in grid]
        if use_robust:
            gq[0] = percentile(sizes, p_low)
            gq[-1] = percentile(sizes, p_high)
        col.update({"kind": "identifier_group",
                    "n_groups": len(counts),
                    "group_size_grid": grid,
                    "group_size_quantiles": [round(x, 6) for x in gq]})
        return col

    if all_int and is_id_name:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        col.update({"kind": "identifier_group", "n_groups": len(counts), "group_size_grid": [0, 100], "group_size_quantiles": [min(counts.values()), max(counts.values())]})
        return col

    if all_numeric and not is_bool:
        nums = sorted(to_float(v) for v in present)
        grid = list(quantile_grid)
        qv = [percentile(nums, p) for p in grid]
        if use_robust:
            qv[0] = percentile(nums, p_low)
            qv[-1] = percentile(nums, p_high)
        col.update({"kind": "integer" if all_int else "float",
                    "is_integer": all_int,
                    "mean": round(mean(nums), 6),
                    "std": round(std_dev(nums), 6),
                    "quantile_grid": grid,
                    "quantile_values": [round(x, 6) for x in qv],
                    "has_negative": any(x < 0 for x in nums),
                    "has_zero": any(x == 0 for x in nums),
                    "zero_rate": round(sum(1 for x in nums if x == 0) / float(len(nums)), 6)})
        if not all_int:                                          # how many decimals the values are written with
            dec = sorted(min(6, len(str(v).split(".")[1].rstrip("0"))) if "." in str(v) and "e" not in str(v).lower() else 0
                         for v in present)
            col["decimals"] = dec[int(0.95 * (len(dec) - 1))]

    elif is_date:
        parsed = [parse_date(v) for v in present]
        fmts = [f for _, f in parsed if f]
        fmt = max(set(fmts), key=fmts.count)
        dts = [d for d, _ in parsed if d is not None]
        yfreq = {}
        for d in dts:
            y = str(d.year)
            yfreq[y] = yfreq.get(y, 0) + 1
        col.update({"kind": "datetime", "format": fmt,
                    "min": min(dts).strftime(fmt), "max": max(dts).strftime(fmt),
                    "year_freqs": yfreq})

    elif is_bool:
        freq = {}
        for v in present:
            freq[v] = freq.get(v, 0) + 1
        col.update({"kind": "boolean", "frequencies": freq})

    elif len(distinct) <= max_categories:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        freqs, rare_i = {}, 1
        for label, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            if cnt < min_cell_count:
                freqs["RARE_%03d" % rare_i] = cnt
                rare_i += 1
            else:
                freqs[label] = cnt
        col.update({"kind": "categorical", "frequencies": freqs,
                    "rare_levels_suppressed": rare_i - 1})

    else:  # high-cardinality -> ID / free-text
        sigs = {}
        for v in present:
            s = signature(v)
            sigs[s] = sigs.get(s, 0) + 1
        dom = max(sigs, key=sigs.get)
        lengths = [len(v) for v in present]
        col.update({"kind": "id_or_text", "dominant_signature": dom,
                    "signature_coverage": round(sigs[dom] / len(present), 4),
                    "len_min": min(lengths), "len_max": max(lengths),
                    "is_unique_key": len(distinct) == len(present)})
    return col

def key_columns_per_base(schema):
    """Every column that participates in a DETECTED relationship, grouped by table:
    foreign-key columns in each child and the parent-key columns they reference. These
    are profiled as identifiers (only counts and string lengths are stored), so a key
    column is never value-profiled and no key value leaves. Columns that merely look
    unique but join to nothing are left to the normal rules (kept as measurements)."""
    keys = {b: set() for b in schema.get("files", {})}
    for b, e in schema.get("files", {}).items():
        for L in (e.get("links") or []):
            keys.setdefault(b, set()).add(L["link"])
            keys.setdefault(L["parent"], set()).add(L["parent_key"])
    return keys


_KEY_HEADER_WORDS = {"id", "no", "num", "number", "code", "key", "מספר", "מס", "מס'", "קוד", "מזהה", "מספור", "סידורי"}


def _is_running_key(name, rows):
    """The table's own unique column is a key (counts only, no value summarised) when its values
    are whole numbers under a header that says 'number / id / code', or a dense run of numbers,
    or codes that are neither numbers nor dates.  A unique measurement (an amount) is not a key."""
    vals = [r.get(name, '') for r in rows if not is_missing(r.get(name, ''))]
    if len(vals) < MIN_TABLE_ROWS or len(set(vals)) != len(vals):
        return False
    smp = _stride_sample(vals, 400)
    if all(looks_int(v) and '.' not in str(v) for v in smp):
        words = set(re.split(r"[\s_\-./()]+", str(name).strip().lower()))
        nums = [to_float(v) for v in vals]
        return bool(words & _KEY_HEADER_WORDS) or (max(nums) - min(nums) + 1) <= 3 * len(vals)
    if any(to_float(v) is not None for v in smp):
        return False
    return sum(1 for v in smp[:60] if _to_dt(str(v)) is not None) < 0.5 * len(smp[:60])


def _shape_profile(name, values, why):
    """Shape only: how many, how many missing, and the commonest pattern of letters / digits.
    Used for hidden columns and for tables too small to summarise.  No value is kept."""
    present = [v for v in values if not is_missing(v)]
    n = len(values)
    col = {"name": name, "n": n, "missing_rate": round((n - len(present)) / float(n), 6) if n else 0.0,
           "n_unique": 0, "kind": "empty", "shape_only": why}
    if not present:
        return col
    sigs = {}
    for v in present:
        s = signature(v)
        sigs[s] = sigs.get(s, 0) + 1
    dom = max(sigs, key=sigs.get)
    lengths = [len(v) for v in present]
    col.update({"kind": "id_or_text", "dominant_signature": dom, "len_min": min(lengths), "len_max": max(lengths),
                "is_unique_key": False})
    return col


def _looks_like_id_number(present):
    """Whole numbers, nearly all different, all of one length of 7+ digits: an id / phone number, not a measure."""
    if len(present) < MIN_TABLE_ROWS:
        return False
    smp = _stride_sample(present, 600)
    if not all(looks_int(v) and '.' not in str(v) for v in smp):
        return False
    lens = {}
    for v in smp:
        L = len(str(v).lstrip('-'))
        lens[L] = lens.get(L, 0) + 1
    L, cnt = max(lens.items(), key=lambda kv: kv[1])
    return L >= 7 and cnt >= 0.9 * len(smp) and len(set(present)) >= 0.9 * len(present)


def _sig4(x):
    """Round to 4 significant figures (a quantile is a real value; its last digits do not leave)."""
    if x == 0 or x != x:
        return x
    d = 3 - int(math.floor(math.log10(abs(x))))
    r = round(x, d)
    return int(r) if d <= 0 else r


_DATE_MEMO = {}


def _to_dt(v, serial=False):
    if serial:
        return excel_serial_to_date(v)
    d = _DATE_MEMO.get(v)
    if d is None and v not in _DATE_MEMO:
        d = parse_date_dt(v)
        if len(_DATE_MEMO) < 300000:
            _DATE_MEMO[v] = d
    return d


RARE_LABEL = "(rare value)"              # stands in the synthetic files for labels seen fewer than k times


def _pool_rare(col, k):
    """Labels seen fewer than k times lose their name and their own count: they become one pooled
    count, kept only if it reaches k.  False when no label is left."""
    fr = col["frequencies"]
    keep = {a: c for a, c in fr.items() if c >= k}
    if not keep:
        return False
    pooled = sum(c for c in fr.values() if c < k)
    col["rare_levels_suppressed"] = len(fr) - len(keep)
    if pooled >= k:
        keep[RARE_LABEL] = keep.get(RARE_LABEL, 0) + pooled
    col["frequencies"] = keep
    return True


def profile_any(name, values, k=MIN_CELL_COUNT, force_key=False, hidden=False, excel_date=False):
    """profile_column plus the protections a general tool needs:
    hidden columns and id-number look-alikes never have their values summarised; no count below k
    is written (years, months, yes / no); the ends of a numeric range are the 5th / 95th percentile
    when there are fewer than 500 values; quantiles keep 4 significant figures; dates keep their
    month-by-month shape so before / after comparisons can be rehearsed."""
    present = [v for v in values if not is_missing(v)]
    if hidden and not force_key:
        return _shape_profile(name, values, "hidden: the header names personal or free-text content")
    auto_id = (not force_key) and (not excel_date) and _looks_like_id_number(present)
    col = profile_column(name, values, min_cell_count=k, force_key=force_key or auto_id)
    if auto_id:
        col["auto_identifier"] = True
    col["all_numeric"] = bool(present) and all(to_float(v) is not None for v in _stride_sample(present, 400))
    kind = col["kind"]
    if kind == "boolean":
        keep = {a: c for a, c in col["frequencies"].items() if c >= k}
        if not keep:
            return _shape_profile(name, values, "every value is rarer than %d" % k)
        col["rare_levels_suppressed"] = len(col["frequencies"]) - len(keep)
        col["frequencies"] = keep
    elif kind == "categorical":
        if not _pool_rare(col, k):
            return _shape_profile(name, values, "every value is rarer than %d" % k)
    elif kind in ("integer", "float"):
        qv = col["quantile_values"]
        if len(present) < 500:
            qv[0], qv[-1] = qv[1], qv[-2]
        if col["n_unique"] > 50:
            col["quantile_values"] = [_sig4(x) for x in qv]
            col["mean"], col["std"] = _sig4(col["mean"]), _sig4(col["std"])
        if kind == "integer" and col["n_unique"] <= 30:
            cnt = {}
            for v in present:
                key = str(int(to_float(v)))
                cnt[key] = cnt.get(key, 0) + 1
            keep = {a: c for a, c in cnt.items() if c >= k}
            if keep:
                col["value_freqs"] = keep
    elif kind == "datetime":
        serial = bool(col.get("serial"))
        dts = sorted(d for d in (_to_dt(v, serial) for v in present) if d is not None)
        if not dts:
            return _shape_profile(name, values, "dates could not be read")
        fmt = col.get("format", "%Y-%m-%d")
        col["excel_date"] = bool(excel_date)
        col["has_time"] = any(d.hour or d.minute or d.second for d in dts[:2000])
        col["year_freqs"] = {y: c for y, c in col.get("year_freqs", {}).items() if c >= k}
        if len(dts) >= 100:
            lo, hi = dts[int(0.01 * (len(dts) - 1))], dts[int(0.99 * (len(dts) - 1))]
        else:
            lo, hi = dts[0], dts[-1]
        lo = datetime.datetime(lo.year, lo.month, 1)                         # month resolution: no exact day leaves
        hi = datetime.datetime(hi.year, hi.month, calendar.monthrange(hi.year, hi.month)[1])
        col["min"], col["max"] = lo.strftime(fmt), hi.strftime(fmt)
        col["first_month"], col["last_month"] = lo.strftime("%Y-%m"), hi.strftime("%Y-%m")
        ym = {}
        for d in dts:
            key = "%04d-%02d" % (d.year, d.month)
            ym[key] = ym.get(key, 0) + 1
        keep = {a: c for a, c in sorted(ym.items()) if c >= k}
        other = sum(c for c in ym.values() if c < k)
        if other >= k:                                                       # a remainder below k is itself a small cell
            keep["_other"] = other
        col["ym_freqs"] = keep
        wd = [0] * 7                                                         # rows per day of the week (Monday first)
        for d in dts:
            wd[d.weekday()] += 1
        if min(wd) >= k:
            col["weekday_freqs"] = wd
    return col


def find_empty_rules(rows, columns):
    """A column that is empty exactly when another column has certain values (no closing date while
    the status is 'open', no year of immigration for people born in the country):
    sets column['empty_when'] = {'column', 'values'}.  Only labels the profile already shows are used."""
    cats = [c for c in columns if c["kind"] in ("categorical", "boolean") and not c.get("helper")
            and not c.get("shape_only") and 2 <= len(c.get("frequencies") or {}) <= JOINT_MAX_PARENT_LEVELS]
    smp = _stride_sample(rows, 20000)
    for c in columns:
        if c.get("helper") or not 0.02 <= (c.get("missing_rate") or 0.0) <= 0.98:
            continue
        for x in cats:
            if x is c:
                continue
            tot, mis = {}, {}
            for r in smp:
                xv = r.get(x["name"], '')
                if is_missing(xv):
                    continue
                tot[xv] = tot.get(xv, 0) + 1
                if is_missing(r.get(c["name"], '')):
                    mis[xv] = mis.get(xv, 0) + 1
            levels = [a for a in x["frequencies"] if a in tot and a != RARE_LABEL]
            share = {a: mis.get(a, 0) / float(tot[a]) for a in levels}
            empty = [a for a in levels if share[a] >= 0.98]
            if empty and len(empty) < len(levels) and all(s <= 0.02 or s >= 0.98 for s in share.values()):
                c["empty_when"] = {"column": x["name"], "values": empty}
                break


def find_derived_years(header, rows, columns):
    """A whole-number column that is simply the years between two dates of the same row (an age at
    the event): {column: (earlier date, later date)}.  It is then recomputed, not drawn."""
    by = {c["name"]: c for c in columns}
    dcols = [h for h in header if by.get(h, {}).get("kind") == "datetime"]
    out, smp = {}, _stride_sample(rows, 3000)
    for name in header:
        c = by.get(name) or {}
        if c.get("kind") != "integer" or c.get("helper") or not c.get("quantile_values") \
                or c["quantile_values"][0] < 0 or c["quantile_values"][-1] > 130:
            continue
        for a in dcols:
            for b in dcols:
                if a == b or name in out:
                    continue
                n = ok = 0
                for r in smp:
                    v, va, vb = to_float(r.get(name, '')), r.get(a, ''), r.get(b, '')
                    if v is None or is_missing(va) or is_missing(vb):
                        continue
                    da, db = _to_dt(va, bool(by[a].get("serial"))), _to_dt(vb, bool(by[b].get("serial")))
                    if da is None or db is None:
                        continue
                    n += 1
                    ok += abs((db - da).days / 365.25 - 0.5 - v) <= 1.0
                if n >= MIN_TABLE_ROWS and ok >= 0.97 * n:
                    out[name] = (a, b)
    return out


def period_scheme(dts):
    """How finely a date column can be cut into periods and stay under JOINT_MAX_PARENT_LEVELS:
    quarters, else years, else 5-year bands, else decades."""
    if not dts:
        return 'q'
    for scheme in ('q', 'y', 'y5', 'y10'):
        if len({period_label(d, scheme) for d in dts}) <= JOINT_MAX_PARENT_LEVELS:
            return scheme
    return 'y10'


def period_label(d, scheme):
    if scheme == 'q':
        return '%04d-Q%d' % (d.year, (d.month - 1) // 3 + 1)
    if scheme == 'y':
        return 'Y%04d' % d.year
    if scheme == 'y5':
        return 'Y%04d-%02d' % (d.year - d.year % 5, (d.year - d.year % 5 + 4) % 100)
    return 'Y%04ds' % (d.year - d.year % 10)


def period_months(label):
    """The (year, month) pairs a period label covers; [] when the label is not a period."""
    m = re.match(r'^(\d{4})-Q([1-4])$', str(label))
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return [(y, 3 * q - 2), (y, 3 * q - 1), (y, 3 * q)]
    m = re.match(r'^Y(\d{4})(?:(-\d{2})|(s))?$', str(label))
    if m:
        y = int(m.group(1))
        years = range(y, y + (5 if m.group(2) else 10 if m.group(3) else 1))
        return [(yy, mo) for yy in years for mo in range(1, 13)]
    return []


def gap_pairs(header, rows, columns, k=MIN_CELL_COUNT):
    """[(earlier date column, later date column)] for a later date that normally follows an earlier
    one (opened -> closed).  The days between them are then profiled like any other number, so
    durations and waiting times look real."""
    by = {c["name"]: c for c in columns}
    dcols = [h for h in header if by.get(h, {}).get("kind") == "datetime"]
    out = []
    for j in range(1, len(dcols)):
        b, best = dcols[j], None
        for a in dcols[:j]:
            sa, sb = bool(by[a].get("serial")), bool(by[b].get("serial"))
            n = ok = 0
            gaps, own = [], []
            for r in _stride_sample(rows, 20000):
                va, vb = r.get(a, ""), r.get(b, "")
                if is_missing(va) or is_missing(vb):
                    continue
                da, db = _to_dt(va, sa), _to_dt(vb, sb)
                if da is not None and db is not None:
                    n += 1
                    ok += 1 if db >= da else 0
                    gaps.append((db - da).days)
                    own.append(db.toordinal())
            if n < max(MIN_TABLE_ROWS, 4 * k) or ok < 0.9 * n:
                continue
            gaps.sort()
            own.sort()
            if gaps[(3 * n) // 4] - gaps[n // 4] > 0.9 * (own[(3 * n) // 4] - own[n // 4]):
                continue                 # too loose to pin the later date (date of birth -> date of the event)
            if best is None or n > best[1]:
                best = (a, n)
        if best:
            out.append((best[0], b))
    return out


def _assoc(xs, ys):
    """(mutual information, bias-corrected Cramer's V) of two lists of labels; '' is skipped."""
    cx, cy, cxy, n = {}, {}, {}, 0
    for x, y in zip(xs, ys):
        if x == '' or y == '':
            continue
        n += 1
        cx[x] = cx.get(x, 0) + 1
        cy[y] = cy.get(y, 0) + 1
        cxy[(x, y)] = cxy.get((x, y), 0) + 1
    r, c = len(cx), len(cy)
    if n < 50 or r < 2 or c < 2:
        return 0.0, 0.0
    mi = sum(v / float(n) * math.log(v * float(n) / (cx[x] * cy[y])) for (x, y), v in cxy.items())
    mi = max(0.0, mi - (r - 1.0) * (c - 1.0) / (2.0 * n))     # minus what chance alone gives to long lists of labels
    phi2 = sum(v * v / float(cx[x] * cy[y]) for (x, y), v in cxy.items()) - 1.0
    if p_chi2(n * phi2, (r - 1) * (c - 1)) >= 0.01:            # could be chance: not kept
        return 0.0, 0.0
    phi2c = max(0.0, phi2 - (r - 1.0) * (c - 1.0) / (n - 1.0))
    rc, cc = r - (r - 1.0) ** 2 / (n - 1.0), c - (c - 1.0) ** 2 / (n - 1.0)
    den = min(rc - 1.0, cc - 1.0)
    return mi, (math.sqrt(phi2c / den) if den > 0 else 0.0)


def _resid_assoc(zs, xs, ys):
    """How strongly x and y still move together once z is accounted for.  The x-by-y counts are
    compared with what they would be if y followed z alone (chi-square on the few cells of that
    table, so a small pointed effect is not drowned by the many values of z).  Returns a corrected
    Cramer's V, 0.0 when the difference could be chance (p >= 0.01).  '' is skipped."""
    nz, nxz, nyz, nxy, n = {}, {}, {}, {}, 0
    for z, x, y in zip(zs, xs, ys):
        if z == '' or x == '' or y == '':
            continue
        n += 1
        nz[z] = nz.get(z, 0) + 1
        nxz.setdefault(z, {})
        nxz[z][x] = nxz[z].get(x, 0) + 1
        nyz.setdefault(z, {})
        nyz[z][y] = nyz[z].get(y, 0) + 1
        nxy[(x, y)] = nxy.get((x, y), 0) + 1
    if n < 50:
        return 0.0
    exp = {}
    for z, tot in nz.items():
        for x, cx in nxz[z].items():
            for y, cy in nyz[z].items():
                exp[(x, y)] = exp.get((x, y), 0.0) + cx * cy / float(tot)
    r, c = len({x for x, _ in exp}), len({y for _, y in exp})
    df = (r - 1) * (c - 1)
    if df <= 0:
        return 0.0
    x2 = sum((nxy.get(key, 0) - e) ** 2 / e for key, e in exp.items() if e > 0)
    if p_chi2(x2, df) >= 0.01:
        return 0.0
    return math.sqrt(max(0.0, x2 / n - df / (n - 1.0)) / min(r - 1, c - 1))

def choose_joint_pairs(rows, columns, key_cols, cluster=None):
    """Which pairs of columns to keep a joint table for.  The categorical columns (including the
    period of each date and the columns brought over from the parent table) are linked into the
    tree that keeps the most shared information (Chow-Liu); every other column (a number, a
    duration, a long list of labels) hangs from the categorical column it depends on most.
    A column that comes from the parent table is only ever the 'given' side, and its strength is
    measured on ONE row per parent (cluster = the link column): many rows of the same parent
    repeat the parent's value and would make any two of its columns look related.
    A column may then get a SECOND 'given' column: the one that tells most about it beyond the
    first, among the columns drawn before it (so nothing goes in a circle).
    Returns [(given, column, is_second)].
    Chosen on a sample of rows; the tables themselves are then counted on all rows."""
    smp = _stride_sample(rows, JOINT_SAMPLE_ROWS)
    pick = None
    if cluster:
        seen_keys, one = set(), []
        for i, r in enumerate(smp):
            kv = r.get(cluster, '')
            if kv != '' and kv not in seen_keys:
                seen_keys.add(kv)
                one.append(i)
        if len(one) >= 50:
            pick = one
    lab, parents, leaves, fixed = {}, [], [], set()
    for c in columns:
        name, kind = c["name"], c["kind"]
        if name in key_cols or c.get("shape_only") or c.get("auto_identifier"):
            continue
        if kind in ("categorical", "boolean") or (kind == "integer" and c.get("value_freqs")):
            lab[name] = ['' if is_missing(r.get(name, '')) else r.get(name, '') for r in smp]
            levels = len(set(lab[name]) - {''})
            if 2 <= levels <= JOINT_MAX_PARENT_LEVELS:
                parents.append(name)
                if c.get("helper") == "parent":
                    fixed.add(name)
            elif levels <= JOINT_MAX_CHILD_LEVELS and c.get("helper") != "parent":
                leaves.append(name)
        elif kind in ("integer", "float"):
            vals = [r.get(name, '') for r in smp]
            edges = _numeric_bins(vals)
            if edges and c.get("helper") != "parent":
                lab[name] = ['' if is_missing(v) else _bin_of(v, edges) for v in vals]
                leaves.append(name)
    parents = parents[:40]
    nlev = {p: len(set(lab[p]) - {''}) for p in parents}

    if pick is not None:                                     # one row per parent for every comparison
        lab = {name: [vals[i] for i in pick] for name, vals in lab.items()}

    memo = {}

    def assoc(a, b):
        if (a, b) not in memo:
            memo[(a, b)] = memo[(b, a)] = _assoc(lab[a], lab[b])
        return memo[(a, b)]
    edges = []
    for i, a in enumerate(parents):
        for b in parents[i + 1:]:
            if a in fixed and b in fixed:
                continue
            mi, v = assoc(a, b)
            if v >= JOINT_MIN_V and mi > 0:
                edges.append((mi, a, b))
    edges.sort(reverse=True)
    comp = {p: p for p in parents}
    fx = [p for p in parents if p in fixed]
    for p in fx[1:]:                                         # the parent's columns already hang together, so each
        comp[p] = fx[0]                                      # column here joins them through its strongest link only

    def root(x):
        while comp[x] != x:
            x = comp[x]
        return x
    adj = {p: [] for p in parents}
    for mi, a, b in edges:                                # Kruskal: the heaviest tree
        ra, rb = root(a), root(b)
        if ra != rb:
            comp[ra] = rb
            adj[a].append(b)
            adj[b].append(a)
    pairs, seen = [], set(fixed)
    order = [p for p in parents if p in fixed] + sorted((p for p in parents if p not in fixed), key=lambda p: nlev[p])
    for start in order:
        if start in seen and start not in fixed:
            continue
        seen.add(start)
        queue = [start]
        while queue:
            a = queue.pop(0)
            for b in adj[a]:
                if b not in seen:
                    seen.add(b)
                    pairs.append((a, b))
                    queue.append(b)
    for leaf in leaves:
        best = None
        for p in parents:
            mi, v = assoc(p, leaf)
            if v >= JOINT_MIN_V and mi > 0 and (best is None or v > best[0]):
                best = (v, p)
        if best:
            pairs.append((best[1], leaf))
    pairs = pairs[:JOINT_MAX_TABLES]
    # The second 'given' column.  A candidate must already be drawn when the column is drawn (it is
    # never redrawn, or it comes earlier in the list), must be related to the column on its own with
    # at least 5 rows per cell on average, and must still be related to it once the first is accounted for.
    pos = {b: i for i, (_, b) in enumerate(pairs)}
    n_smp = len(next(iter(lab.values()))) if lab else 0
    seconds = []
    for i, (a, b) in enumerate(pairs):
        lev_b = len(set(lab[b]) - {''})
        cands = []
        for p in parents:
            if p == a or p == b or pos.get(p, -1) >= i or 5 * nlev[p] * lev_b > n_smp:
                continue
            mi, v = assoc(p, b)
            if v >= JOINT_MIN_V and mi > 0:
                cands.append((mi, p))
        best = None
        for _, p in sorted(cands, reverse=True)[:8]:
            extra = _resid_assoc(lab[a], lab[p], lab[b])
            if extra >= JOINT_MIN_V_SECOND and (best is None or extra > best[0]):
                best = (extra, p)
        if best:
            seconds.append((best[0], best[1], b))
    seconds.sort(reverse=True)
    return [(a, b, False) for a, b in pairs] + [(a, b, True) for _, a, b in seconds[:JOINT_MAX_SECOND]]


def build_joint_tables(rows, columns, key_cols, k=MIN_CELL_COUNT, cluster=None):
    """Two-way counts for the chosen pairs.  A cell below k is dropped and only its volume is kept
    ('_suppressed'); a parent value seen fewer than k times is dropped whole."""
    by = {c["name"]: c for c in columns}

    def label(c, v):
        return str(int(to_float(v))) if c.get("value_freqs") and to_float(v) is not None else v
    out, first_kept = [], set()
    for a, b, second in choose_joint_pairs(rows, columns, key_cols, cluster):
        if second and b not in first_kept:
            continue
        ca, cb = by[a], by[b]
        edges = None
        if cb["kind"] in ("integer", "float") and not cb.get("value_freqs"):
            edges = _numeric_bins([r.get(b, "") for r in rows])
            if not edges:
                continue
        cells = {}
        for r in rows:
            av, bv = r.get(a, ""), r.get(b, "")
            if is_missing(av) or is_missing(bv):
                continue
            av = label(ca, av)
            bv = _bin_of(bv, edges) if edges is not None else label(cb, bv)
            d2 = cells.setdefault(av, {})
            d2[bv] = d2.get(bv, 0) + 1
        row_tot = {av: sum(d2.values()) for av, d2 in cells.items()}
        col_tot = {}
        for d2 in cells.values():
            for bv, c in d2.items():
                col_tot[bv] = col_tot.get(bv, 0) + c
        vis = {av: {bv: c for bv, c in d2.items() if c >= k} for av, d2 in cells.items() if row_tot[av] >= k}
        changed = True
        while changed:                       # a hidden remainder of 1..k-1 in a row or a column could be found by
            changed = False                  # subtraction from the totals, so one more cell of that line is hidden
            for av, d2 in vis.items():
                if d2 and 0 < row_tot[av] - sum(d2.values()) < k:
                    del d2[min(d2, key=d2.get)]
                    changed = True
            shown = {}
            for av, d2 in vis.items():
                for bv, c in d2.items():
                    shown.setdefault(bv, []).append((c, av))
            for bv, lst in shown.items():
                if 0 < col_tot[bv] - sum(c for c, _ in lst) < k:
                    del vis[min(lst)[1]][bv]
                    changed = True
        kept = {}
        for av, keep in vis.items():
            if not keep:
                continue
            s = row_tot[av] - sum(keep.values())
            if s:
                keep["_suppressed"] = s
            kept[av] = keep
        if kept:
            rec = {"parent": a, "child": b, "cells": kept}
            if edges is not None:
                rec["child_bins"] = [round(e, 6) for e in edges]
            if second:
                rec["second"] = True
            else:
                first_kept.add(b)
            out.append(rec)
    return out


# ==============================================================================
#  Step 1 -- profile a folder (on the premises)
# ==============================================================================
SETTINGS_TEMPLATE = {
    "_how": "Optional. Put this file next to the data files and run 'python gov_one.py profile' again. "
            "A column is named as it appears in the header, or as 'table::column' to mean one table only.",
    "min_cell": MIN_CELL_COUNT,
    "hide": [],
    "show": [],
    "public_tables": [],
    "links": [],
    "no_links": [],
    "skip_files": [],
    "_examples": {
        "hide": ["שם עובד סוציאלי", "cases::worker"],
        "show": ["תיאור"],
        "public_tables": ["districts"],
        "links": ["payments::client = clients::client_id"],
        "no_links": ["cases::room"],
        "skip_files": ["old_copy.xlsx"],
        "_meaning": "hide: values never leave (shape only). show: cancel an automatic hide. public_tables: a "
                    "reference table with no personal data, copied as it is. links: a relationship the tool "
                    "missed. no_links: a relationship it found by mistake. skip_files: files not to read."},
}


def load_settings(folder):
    st = {a: (list(b) if isinstance(b, list) else b) for a, b in SETTINGS_TEMPLATE.items() if not a.startswith('_')}
    p = os.path.join(folder, SETTINGS_FILE)
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8-sig') as f:
                user = json.load(f)
            for a in st:
                if a in user:
                    st[a] = user[a]
            print('  settings : %s' % SETTINGS_FILE)
        except Exception as e:                                       # noqa: BLE001
            raise SystemExit('ERROR: %s could not be read (%s). Fix or delete it.' % (SETTINGS_FILE, e))
    return st


def _spec(specs, base, col):
    for s in specs or ():
        s = str(s).strip()
        if s == col or s == '%s::%s' % (base, col):
            return True
    return False


def _parse_links(specs):
    out = []
    for s in specs or ():
        m = re.match(r'^\s*(.+?)::(.+?)\s*=\s*(.+?)::(.+?)\s*$', str(s))
        if m:
            out.append(tuple(x.strip() for x in m.groups()))
        else:
            print('  [!] link not understood (use "child::column = parent::column"): %s' % s)
    return out


def read_folder(folder, skip=()):
    """Every table of every readable file in the folder -> (tables, unreadable files)."""
    paths, bad = find_inputs(folder)
    tables, seen = [], {}
    for p in paths:
        name = os.path.basename(p)
        if name in skip:
            continue
        print('  reading  : %s' % name, flush=True)
        try:
            tabs = read_file_tables(p)
        except zipfile.BadZipFile:
            bad.append((name, 'not a readable workbook (password-protected or damaged)'))
            continue
        except Exception as e:                                       # noqa: BLE001
            bad.append((name, 'could not be read (%s: %s)' % (type(e).__name__, e)))
            continue
        if not tabs:
            bad.append((name, 'no table found (empty)'))
        for t in tabs:
            if t['base'] in seen:                                    # a.xlsx and a.csv in one folder
                t['base'] = '%s (%s)' % (t['base'], t['file_type'])
            seen[t['base']] = 1
            tables.append(t)
    return tables, bad


def build_report(t, key_cols, k, st, entry=None, built=None, kids=None):
    """The profile of one table.  entry: its line in the schema; built: {base: (table, profile)} of
    the tables already profiled (parents come first), so a column of the parent table that this
    table depends on can be kept as a joint count."""
    header, rows, base = t['header'], t['rows'], t['base']
    rep = {"tool": VERSION, "source_file": t['file'], "file_type": t['file_type'], "sheet": t['sheet'],
           "sheet_index": t.get('sheet_index', 0), "base": base, "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "n_rows": len(rows), "n_cols": len(header), "header": header, "header_row": t['header_row'] + 1,
           "load_notes": t['notes'], "config": {"min_cell": k, "min_table_rows": MIN_TABLE_ROWS},
           "crosstabs": [], "date_gaps": []}
    if base in (st.get('public_tables') or ()):
        rep["public_table"] = True
        rep["verbatim_rows"] = [[r.get(h, '') for h in header] for r in rows]
        rep["columns"] = [{"name": h, "kind": "verbatim", "n": len(rows)} for h in header]
        return rep
    small = len(rows) < MIN_TABLE_ROWS
    rep["structure_only"] = small
    columns = []
    for name in header:
        vals = [r.get(name, '') for r in rows]
        if small:
            col = _shape_profile(name, vals, "the table has fewer than %d rows" % MIN_TABLE_ROWS)
        else:
            hidden = (is_sensitive_name(name) or _spec(st.get('hide'), base, name)) and not _spec(st.get('show'), base, name)
            col = profile_any(name, vals, k=k, force_key=name in key_cols, hidden=hidden,
                              excel_date=name in t['excel_dates'])
        columns.append(col)
    # Helper columns: never written to a synthetic file, they only carry structure.
    #   <date>__period   the quarter / year of a date, so other columns can depend on time
    #   <date>__gap      whole days from an earlier date of the same row (a duration, a waiting time)
    #   <parent>::<col>  a column of the parent table, so this table can depend on it
    helpers = []
    if not small:
        by = {c["name"]: c for c in columns}
        for name, (a, b) in find_derived_years(header, rows, columns).items():
            by[name]["derived_years"] = [a, b]
        find_empty_rules(rows, columns)
        for child_base, pkey, child_keys in (kids or []):        # has::<child>: does this row have rows in the child table?
            have = ['yes' if (r.get(pkey, '') != '' and r.get(pkey, '') in child_keys) else 'no' for r in rows]
            n_yes = have.count('yes')
            if n_yes < k or len(rows) - n_yes < max(k, 0.02 * len(rows)):
                continue                                         # (nearly) every row has some: nothing to keep
            hn = "has::%s" % child_base
            for r, v in zip(rows, have):
                r[hn] = v
            h = profile_any(hn, have, k=k)
            if h["kind"] in ("categorical", "boolean"):
                h.update({"helper": "has", "child": child_base, "missing_rate": 0.0})
                helpers.append(h)
        for c in columns:
            if c["kind"] != "datetime":
                continue
            name, serial = c["name"], bool(c.get("serial"))
            dts = [None if is_missing(r.get(name, '')) else _to_dt(r.get(name, ''), serial) for r in rows]
            scheme = period_scheme([d for d in dts if d is not None])
            hn = name + "__period"
            for r, d in zip(rows, dts):
                r[hn] = period_label(d, scheme) if d is not None else ''
            h = profile_column(hn, [r[hn] for r in rows], min_cell_count=k)
            if h["kind"] == "categorical" and _pool_rare(h, k):
                h["frequencies"].pop(RARE_LABEL, None)             # a period is drawn from the counted periods only
                h.update({"helper": "period", "of": name, "scheme": scheme, "missing_rate": 0.0})
                helpers.append(h)
        for a, b in gap_pairs(header, rows, columns, k):
            sa, sb, hn = bool(by[a].get("serial")), bool(by[b].get("serial")), b + "__gap"
            for r in rows:
                va, vb, gap = r.get(a, ''), r.get(b, ''), ''
                if not is_missing(va) and not is_missing(vb):
                    da, db = _to_dt(va, sa), _to_dt(vb, sb)
                    if da is not None and db is not None and db >= da:
                        gap = str((db - da).days)
                r[hn] = gap
            h = profile_any(hn, [r[hn] for r in rows], k=k)
            if h["kind"] == "integer":
                h.update({"helper": "gap", "of": b, "from": a, "missing_rate": 0.0})
                helpers.append(h)
        par = (entry or {}).get("parent")
        if par and built and par in built:
            ptab, prep = built[par]
            pk, link, index, taken = entry["parent_key"], entry["link"], {}, 0
            for pr in ptab['rows']:
                index.setdefault(pr.get(pk, ''), pr)
            for pc in prep["columns"]:
                if taken >= 16:
                    break
                if pc.get("shape_only") or pc.get("auto_identifier") or pc.get("helper") in ("gap", "pgap", "parent", "has"):
                    continue
                if not (pc["kind"] in ("categorical", "boolean") or pc.get("value_freqs")):
                    continue
                if pc["name"] in header or not 2 <= len(pc.get("value_freqs") or pc.get("frequencies") or {}) <= JOINT_MAX_PARENT_LEVELS:
                    continue
                hn = "%s::%s" % (par, pc["name"])
                shown = pc.get("value_freqs") or pc.get("frequencies") or {}     # only labels the parent's own profile shows
                for r in rows:
                    pr = index.get(r.get(link, ''))
                    v = pr.get(pc["name"], '') if pr is not None else ''
                    if v != '' and pc.get("value_freqs") and to_float(v) is not None:
                        v = str(int(to_float(v)))
                    if v != '' and v not in shown:                               # rare in the parent table: no name here either
                        v = RARE_LABEL if RARE_LABEL in shown else ''
                    r[hn] = v
                h = profile_any(hn, [r[hn] for r in rows], k=k)
                if h["kind"] in ("categorical", "boolean") or h.get("value_freqs"):
                    h.update({"helper": "parent", "parent_col": pc["name"]})
                    helpers.append(h)
                    taken += 1
            banded = 0
            for pc in prep["columns"]:                           # a number of the parent row (age, income): five bands
                if banded >= 4 or pc["kind"] not in ("integer", "float") or pc.get("helper") or pc.get("value_freqs") \
                        or pc.get("shape_only") or pc["name"] in header:
                    continue
                edges = sorted({_sig4(e) for e in _numeric_bins([pr.get(pc["name"], '') for pr in ptab['rows']], nbins=5)})
                if len(edges) < 2:
                    continue
                hn = "%s::%s" % (par, pc["name"])
                for r in rows:
                    pr = index.get(r.get(link, ''))
                    f = to_float(pr.get(pc["name"], '')) if pr is not None else None
                    r[hn] = '' if f is None else "B%d" % bisect.bisect_left(edges, f)
                h = profile_any(hn, [r[hn] for r in rows], k=k)
                if h["kind"] == "categorical":
                    h.update({"helper": "parent", "parent_col": pc["name"], "parent_bins": edges})
                    helpers.append(h)
                    banded += 1
            # <date>__pgap: whole days from a date of the parent row to this date (a payment after the
            # case was opened, a contact before the death), so the two tables stay in step in time
            pdates = [pc for pc in prep["columns"] if pc["kind"] == "datetime" and not pc.get("helper")]
            for c in columns:
                if c["kind"] != "datetime" or not pdates:
                    continue
                name, best = c["name"], None
                for pc in pdates:
                    gaps, n, pos, neg, own = [], 0, 0, 0, []
                    for r in rows:
                        pr = index.get(r.get(link, ''))
                        vc, vp = r.get(name, ''), (pr.get(pc["name"], '') if pr is not None else '')
                        dc = None if is_missing(vc) else _to_dt(vc, bool(c.get("serial")))
                        dp = None if is_missing(vp) else _to_dt(vp, bool(pc.get("serial")))
                        if dc is None or dp is None:
                            gaps.append('')
                            continue
                        d = (datetime.datetime(dc.year, dc.month, dc.day) - datetime.datetime(dp.year, dp.month, dp.day)).days
                        gaps.append(str(d))
                        own.append(dc.toordinal())
                        n, pos, neg = n + 1, pos + (d >= 0), neg + (d <= 0)
                    if n < max(MIN_TABLE_ROWS, 4 * k) or max(pos, neg) < 0.9 * n:
                        continue                                  # no steady order between the two dates
                    s = sorted(int(x) for x in gaps if x != '')
                    own.sort()
                    spread = s[(3 * len(s)) // 4] - s[len(s) // 4]
                    if spread > 0.9 * (own[(3 * len(own)) // 4] - own[len(own) // 4]):
                        continue                                  # too loose to pin this date (e.g. a date of birth)
                    if best is None or spread < best[0]:
                        best = (spread, pc["name"], gaps)
                if best:
                    hn = name + "__pgap"
                    for r, gv in zip(rows, best[2]):
                        r[hn] = gv
                    h = profile_any(hn, best[2], k=k)
                    if h["kind"] == "integer":
                        h.update({"helper": "pgap", "of": name, "parent_col": best[1], "missing_rate": 0.0})
                        helpers.append(h)
    rep["columns"] = columns + helpers
    if not small:
        rep["crosstabs"] = build_joint_tables(rows, rep["columns"], key_cols, k, (entry or {}).get("link"))
    return rep


def _nice(name, by):
    c = by.get(name) or {}
    if c.get("helper") == "period":
        return "%s (period)" % c["of"]
    if c.get("helper") == "gap":
        return "days from %s to %s" % (c["from"], c["of"])
    if c.get("helper") == "parent":
        pcol = c["parent_col"]
        if pcol.endswith("__period"):
            return "%s (period, from the linked table)" % pcol[:-len("__period")]
        return "%s (from the linked table%s)" % (pcol, ", in 5 bands" if c.get("parent_bins") else "")
    if c.get("helper") == "pgap":
        return "days from %s (linked table) to %s" % (c["parent_col"], c["of"])
    if c.get("helper") == "has":
        return "has rows in %s" % c["child"]
    return name


def _look_like_people(labels):
    """A guess, for the reviewer only: at least 8 labels, nearly all of them two or three short words of letters."""
    labs = [str(a) for a in labels if a != RARE_LABEL]
    if len(labs) < 8:
        return False
    hit = sum(1 for a in labs if 2 <= len(a.split()) <= 3 and all(w.replace("'", "").replace("-", "").isalpha() and len(w) <= 12
                                                                    for w in a.split()))
    return hit >= 0.85 * len(labs)


def _what_leaves(c):
    kind = c["kind"]
    if kind == "verbatim":
        return "EVERYTHING", "declared a public table in the settings"
    if c.get("helper"):
        return None, None
    if c.get("shape_only"):
        return "shape only", c["shape_only"]
    if kind in ("categorical", "boolean"):
        labs = [a for a in c["frequencies"] if not str(a).startswith("RARE_")]
        show = ", ".join(str(a) for a in labs[:8]) + (" ... +%d more" % (len(labs) - 8) if len(labs) > 8 else "")
        flag = "  **<- CHECK: many text values**" if len(labs) > 50 else ""
        if _look_like_people(labs):
            flag = "  **<- CHECK: THESE LOOK LIKE NAMES OF PEOPLE. If they are, add this header to \"hide\".**"
        return "labels + counts", "%d labels (%d rare ones hidden): %s%s" % (len(labs), c.get("rare_levels_suppressed", 0), show, flag)
    if kind in ("integer", "float"):
        how = "values + counts" if c.get("value_freqs") else "9 rounded quantiles"
        lo, hi = _sig4(c["quantile_values"][0]), _sig4(c["quantile_values"][-1])
        if c.get("is_integer") and 1800 <= lo <= hi <= 2100:                 # years: no thousands separator
            return how, "about %d to %d" % (lo, hi)
        return how, "about %s to %s, mean %s" % (fmt(lo), fmt(hi), fmt(_sig4(c["mean"])))
    if kind == "datetime":
        return "counts per month", "%s to %s (month and year only, never the day)" % (c.get("first_month"), c.get("last_month"))
    if kind in ("identifier_unique", "identifier_group"):
        return "nothing but counts", "key / id column%s" % (" (looked like an id number)" if c.get("auto_identifier") else "")
    if kind == "id_or_text":
        return "shape only", "free text or codes: pattern %s, length %d-%d" % (c["dominant_signature"][:24], c["len_min"], c["len_max"])
    return "nothing", "empty column"


def link_lines(schema):
    out = []
    for b in schema.get("order", []):
        e = schema["files"].get(b) or {}
        for L in e.get("links") or []:
            q = L.get("fanout_quantiles") or []
            mid = (" -- typically %s row(s) per %s" % (_sig4(q[len(q) // 2]), L["parent_key"])) if q else ""
            out.append("%s . %s  ->  %s . %s  (%d%% of its values found there%s)%s"
                       % (b, L["link"], L["parent"], L["parent_key"], round(100 * L.get("share_found", 1.0)),
                          "" if L.get("primary", True) else "; second link", mid))
        if e.get("inherited"):
            out.append("%s repeats these columns of %s: %s" % (b, e["parent"], ", ".join(e["inherited"])))
    return out


def write_summary(out_dir, reports, schema, bad, k, warnings):
    md = ["# What leaves the premises", "",
          "- Made %s by %s" % (datetime.datetime.now().isoformat(timespec="minutes"), VERSION),
          "- %d table(s) from %d file(s)" % (len(reports), len({r["source_file"] for r in reports})),
          "- **Aggregates only.** No row is copied. No value or combination seen fewer than **%d** times is written." % k,
          "- Ids, names, phone numbers, addresses and free text are described by their shape only (length, letters / digits).",
          "- Dates keep the month and the year, never the day. Numeric ranges are rounded and cut at the 5th / 95th "
          "percentile when there are fewer than 500 values.",
          "", "## Check before sending", "",
          "1. In the tables below, every column marked **labels + counts** sends its values as written. "
          "They must be categories (district, status, type) -- never names of people.",
          "2. To hide a column, add its header to \"hide\" in %s and run the profile again." % SETTINGS_FILE,
          "3. Send the whole `%s` folder. Nothing else is needed." % SEND_DIR, ""]
    if warnings or bad:
        md += ["## Warnings", ""] + ["- [!] %s" % w for w in warnings] + ["- [!] not read: %s -- %s" % b for b in bad] + [""]
    rel = link_lines(schema)
    md += ["## How the files relate", ""] + (["- %s" % r for r in rel] if rel else ["- no relationship was found between the tables"]) + [""]
    for rep in reports:
        title = rep["source_file"] + (" / sheet %s" % rep["sheet"] if rep["sheet"] else "")
        md += ["## %s" % rep["base"], "", "%s -- %d rows, %d columns%s" % (
            title, rep["n_rows"], rep["n_cols"],
            " -- **too small: shape only**" if rep.get("structure_only") else ""), ""]
        for n in rep.get("load_notes") or []:
            md.append("- note: %s" % n)
        md += ["", "| Column | What leaves | Detail | Missing |", "|---|---|---|---|"]
        for c in rep["columns"]:
            what, detail = _what_leaves(c)
            if what is None:
                continue
            md.append("| %s | %s | %s | %s |" % (str(c["name"]).replace("|", "/"), what, str(detail).replace("|", "/"),
                                              ("%.0f%%" % (100 * c.get("missing_rate", 0.0))) if "missing_rate" in c else ""))
        by = {c["name"]: c for c in rep["columns"]}
        gaps = ["%s -> %s" % (c["from"], c["of"]) for c in rep["columns"] if c.get("helper") == "gap"]
        gaps += ["%s (linked table) -> %s" % (c["parent_col"], c["of"]) for c in rep["columns"] if c.get("helper") == "pgap"]
        if gaps:
            md += ["", "Durations kept (quantiles of whole days): %s" % "; ".join(gaps)]
        for c in rep["columns"]:
            if c.get("helper") == "has":
                yes = (c.get("frequencies") or {}).get("yes", 0)
                md += ["", "Kept: how many rows have rows in %s (%d%% do)" % (c["child"], round(100.0 * yes / max(1, c.get("n", 1))))]
            if c.get("empty_when"):
                md += ["", "%s is empty when %s is: %s" % (c["name"], c["empty_when"]["column"], ", ".join(c["empty_when"]["values"]))]
            if c.get("derived_years"):
                md += ["", "%s is the number of years from %s to %s: it is recomputed in the synthetic file" % (
                    c["name"], c["derived_years"][0], c["derived_years"][1])]
        if rep.get("crosstabs"):
            md += ["", "Joint counts kept, so columns move together (cells below %d dropped): %s" % (
                k, "; ".join("%s x %s%s" % (_nice(x["parent"], by), _nice(x["child"], by), " (second link)" if x.get("second") else "")
                             for x in rep["crosstabs"]))]
        md.append("")
    with open(os.path.join(out_dir, "profile_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def run_profile(data_dir, out_dir=None, k=None):
    """Step 1.  Returns (out_dir, reports)."""
    st = load_settings(data_dir)
    k = int(k or st.get("min_cell") or MIN_CELL_COUNT)
    if k < 3:
        raise SystemExit("ERROR: the minimum cell count cannot be below 3.")
    out_dir = out_dir or os.path.join(data_dir, SEND_DIR)
    tables, bad = read_folder(data_dir, skip=st.get("skip_files") or ())
    if not tables:
        for b in bad:
            print("  [!] %s: %s" % b)
        raise SystemExit("ERROR: no readable Excel (.xlsx / .xlsm) or CSV file in %s" % data_dir)
    lt = {t['base']: {'file': t['file'], 'header': t['header'], 'rows': t['rows']} for t in tables}
    forbidden = {str(s).replace('::', '.') for s in st.get("no_links") or ()}
    print('  links    : comparing the columns of %d table(s)' % len(lt), flush=True)
    schema = detect_links(lt, forced=_parse_links(st.get("links")), forbidden=forbidden)
    keycols = key_columns_per_base(schema)
    for t in tables:                                             # a table's own running number is a key too
        own = (schema["files"].get(t['base']) or {}).get("key")
        if own and _is_running_key(own, t['rows']):
            keycols.setdefault(t['base'], set()).add(own)
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "profile_*.json")):
        os.remove(old)
    reports, warnings, fps, built = [], [], {}, {}
    by_base = {t['base']: t for t in tables}
    for base in [b for b in schema["order"] if b in by_base]:           # parents before their children
        t = by_base[base]
        print('  profiling: %s (%d rows, %d columns)' % (t['base'], len(t['rows']), len(t['header'])), flush=True)
        kids = [(cb, e["parent_key"], {r.get(e["link"], '') for r in by_base[cb]['rows']} - {''})
                for cb, e in schema["files"].items() if e.get("parent") == base and cb in by_base]
        rep = build_report(t, keycols.get(t['base'], set()), k, st, schema["files"].get(base), built, kids)
        built[base] = (t, rep)
        fp = json.dumps([{a: c.get(a) for a in ("name", "n", "kind", "n_unique", "frequencies", "quantile_values")}
                         for c in rep["columns"]], ensure_ascii=False, sort_keys=True)
        if rep["n_rows"] >= MIN_TABLE_ROWS and fp in fps:
            warnings.append("%s has exactly the same profile as %s -- one may be a copy of the other" % (rep["base"], fps[fp]))
        fps.setdefault(fp, rep["base"])
        if rep.get("public_table"):
            warnings.append("%s is copied in full (declared public in the settings): %d rows" % (rep["base"], rep["n_rows"]))
        with open(os.path.join(out_dir, "profile_%s.json" % rep["base"]), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        reports.append(rep)
    reports.sort(key=lambda r: [t['base'] for t in tables].index(r["base"]))     # back to file / sheet order
    schema["min_cell"] = k
    with open(os.path.join(out_dir, "schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=1)
    write_summary(out_dir, reports, schema, bad, k, warnings)
    print()
    for r in link_lines(schema):
        print('  link     : ' + r)
    for w in warnings:
        print('  [!] ' + w)
    for b in bad:
        print('  [!] not read: %s -- %s' % b)
    print('\nDONE. %d table(s) profiled. Folder to send: %s' % (len(reports), out_dir))
    print('Read profile_summary.md first: it lists exactly what leaves. Aggregates only; no cell below %d.' % k)
    return out_dir, reports


# ==============================================================================
#  Step 2 -- synthetic files from the JSON files (at home)
# ==============================================================================
def _marginal_child_sampler(col, n_hint=256):
    """Callable returning one marginal draw for the child (used for the suppressed share)."""
    kind = col["kind"]
    if kind in ("categorical", "boolean"):
        labels = list(col["frequencies"]); weights = list(col["frequencies"].values())
        return lambda: random.choices(labels, weights=weights, k=1)[0]
    if kind in ("integer", "float"):
        return lambda: sample_numeric(col, 1, inject_edges=False)[0]
    if kind == "id_or_text":
        return lambda: sample_id(col, 1)[0]
    return lambda: ""


def _bin_value(col, bins, j):
    """Draw a numeric value inside quantile bin j (edges = bins)."""
    grid = [g / 100.0 for g in col["quantile_grid"]]
    qv = col["quantile_values"]
    lo = qv[0] if j == 0 else bins[j - 1]
    hi = qv[-1] if j >= len(bins) else bins[j]
    if hi < lo:
        lo, hi = hi, lo
    v = random.uniform(lo, hi)
    return int(round(v)) if col.get("is_integer") else v


def _choosers(xt):
    """{given label: (child labels, weights, share hidden)} for one joint table."""
    out = {}
    for av, d in xt["cells"].items():
        labs = [k for k in d if k != "_suppressed"]
        wts = [d[k] for k in labs]
        sup = d.get("_suppressed", 0)
        tot = sum(wts) + sup
        out[av] = (labs, wts, sup / tot if tot else 1.0)
    return out


def _shares(xt, ccol):
    """One joint table as {given label: {child label: share}}.  The hidden part of a line is spread
    over the child labels that line does not show, following the child's own distribution."""
    bins = xt.get("child_bins")
    if bins is not None:
        base = {str(j): 1.0 for j in range(len(bins) + 1)}
    else:
        base = {str(a): float(b) for a, b in (ccol.get("value_freqs") or ccol.get("frequencies") or {}).items()}
    out = {}
    for av, d in xt["cells"].items():
        line = {str(a): float(b) for a, b in d.items() if a != "_suppressed"}
        sup = d.get("_suppressed", 0)
        if sup:
            rest = {a: w for a, w in base.items() if a not in line} or base
            tot = float(sum(rest.values())) or 1.0
            for a, w in rest.items():
                line[a] = line.get(a, 0.0) + sup * w / tot
        s = sum(line.values())
        if s > 0:
            out[str(av)] = {a: b / s for a, b in line.items()}
    return out


def _fit_two(t1, t2, A, B, n):
    """A column that follows two others.  For every (first, second) pair of values found in the rows:
    the weights of the child's labels that agree with BOTH joint tables and add nothing more
    (iterative proportional fitting).  Returns {(first, second): (labels, cumulative weights)}."""
    M = {}
    for i in range(n):
        key = (str(A[i]), str(B[i]))
        if key[0] in t1 and key[1] in t2:
            M[key] = M.get(key, 0) + 1
    labs = sorted({a for d in t1.values() for a in d} | {a for d in t2.values() for a in d})
    L = len(labs)
    if not M or len(M) * L > 400000:
        return {}
    ma, mb = {}, {}
    for (a, b), c in M.items():
        ma[a] = ma.get(a, 0) + c
        mb[b] = mb.get(b, 0) + c
    R1 = {a: [t1[a].get(x, 0.0) * ma[a] for x in labs] for a in ma}
    R2 = {b: [t2[b].get(x, 0.0) * mb[b] for x in labs] for b in mb}
    T = {(a, b): [float(c) if R1[a][j] > 0 and R2[b][j] > 0 else 0.0 for j in range(L)] for (a, b), c in M.items()}
    for _ in range(25):
        for side, R in ((0, R1), (1, R2)):                   # agree with each joint table in turn
            S = {g: [0.0] * L for g in R}
            for key, row in T.items():
                s = S[key[side]]
                for j in range(L):
                    s[j] += row[j]
            for key, row in T.items():
                s, r = S[key[side]], R[key[side]]
                for j in range(L):
                    if s[j] > 0:
                        row[j] *= r[j] / s[j]
        for key, row in T.items():                           # and with how often the pair itself occurs
            s = sum(row)
            if s > 0:
                f = M[key] / s
                for j in range(L):
                    row[j] *= f
    out = {}
    for key, row in T.items():
        cum, s = [], 0.0
        for w in row:
            s += w
            cum.append(s)
        if s > 0:
            out[key] = (labs, cum)
    return out


def apply_crosstabs(cols, report, n):
    """Redraw each column given the column(s) it follows, in order."""
    by_name = {c["name"]: c for c in report["columns"]}
    xts = report.get("crosstabs") or []
    second = {}
    for xt in xts:
        if xt.get("second") and xt["child"] not in second and xt["parent"] in cols:
            second[xt["child"]] = xt
    done = set()                       # one first 'given' column per child
    for xt in xts:
        if xt.get("second"):
            continue
        a, b = xt["parent"], xt["child"]
        if a not in cols or b not in cols or a == b or b in done:
            continue
        done.add(b)
        ccol = by_name.get(b)
        if ccol is None:
            continue
        bins = xt.get("child_bins")
        choosers = _choosers(xt)
        x2 = second.get(b)
        if x2 is not None and (x2["parent"] in (a, b) or x2.get("child_bins") != bins):
            x2 = None
        both, choosers2, p2 = {}, {}, None
        if x2 is not None:
            p2 = cols[x2["parent"]]
            both = _fit_two(_shares(xt, ccol), _shares(x2, ccol), cols[a], p2, n)
            choosers2 = _choosers(x2)
        marginal = _marginal_child_sampler(ccol)
        pa, out = cols[a], list(cols[b])
        for i in range(n):
            if out[i] == "":
                continue                                    # keep the missing draw
            if both:
                w = both.get((str(pa[i]), str(p2[i])))
                if w is not None:                           # follows both columns
                    v = random.choices(w[0], cum_weights=w[1], k=1)[0]
                    out[i] = _bin_value(ccol, bins, int(v)) if bins is not None else v
                    continue
            ch = choosers.get(str(pa[i]))
            if ch is None and p2 is not None:
                ch = choosers2.get(str(p2[i]))              # the first value is unknown here: follow the second
            if ch is None:
                continue                                    # unseen parent: keep marginal
            labs, wts, psup = ch
            if not labs or random.random() < psup:
                v = marginal()
            else:
                v = random.choices(labs, weights=wts, k=1)[0]
                if bins is not None:
                    v = _bin_value(ccol, bins, int(v))
            out[i] = v
        cols[b] = out

def sample_numeric(col, n, inject_edges=DEFAULT_INJECT_EDGES):
    grid = [g / 100.0 for g in col["quantile_grid"]]
    qv = col["quantile_values"]
    out = []
    for _ in range(n):
        u = random.random()
        j = 0
        while j < len(grid) - 1 and u > grid[j + 1]:
            j += 1
        lo_g, hi_g = grid[j], grid[min(j + 1, len(grid) - 1)]
        lo_v, hi_v = qv[j], qv[min(j + 1, len(qv) - 1)]
        frac = 0.0 if hi_g == lo_g else (u - lo_g) / (hi_g - lo_g)
        out.append(lo_v + frac * (hi_v - lo_v))
    if inject_edges and n >= 2:
        out[0], out[1] = qv[0], qv[-1]
    if col.get("has_zero") and n >= 3:
        out[2] = 0.0
    zr = col.get("zero_rate", 0.0) or 0.0
    if zr > 0.0 and col.get("is_integer") and not col.get("has_negative"):
        # reproduce the point mass at 0 exactly; the rest is drawn from the part
        # of the quantile function above the zero mass
        g = [x / 100.0 for x in col["quantile_grid"]]
        for i in range(len(out)):
            if random.random() < zr:
                out[i] = 0.0
            elif out[i] <= 0:
                out[i] = inv_cdf(g, qv, zr + (1.0 - zr) * random.random())
    if col.get("is_integer"):
        out = [int(round(x)) for x in out]
    return out


def sample_categorical(col, n, inject_edges=DEFAULT_INJECT_EDGES):
    labels = list(col["frequencies"].keys())
    weights = list(col["frequencies"].values())
    out = random.choices(labels, weights=weights, k=n)
    if inject_edges:
        for i, lab in enumerate(labels):
            if i < n:
                out[i] = lab
    return out


def sample_datetime(col, n):
    fmt = col.get("format", "%Y-%m-%d")
    serial = col.get("serial", False)
    lo = datetime.datetime.strptime(col["min"], fmt)
    hi = datetime.datetime.strptime(col["max"], fmt)
    span = max(int((hi - lo).total_seconds()), 1)
    out = []
    for _ in range(n):
        sec = random.randint(0, span)
        d = lo + datetime.timedelta(seconds=sec)
        out.append(str(date_to_excel_serial(d)) if serial else d.strftime(fmt))
    return out

STUDY_DATE_RANGE = ("2020-01-01", "2026-09-30")


def _looks_like_timestamp_sig(sig):
    return bool(re.match(r'^DDDD-DD-DD( DD:DD:DD(\.D+)?)?$', sig or ''))


def sample_timestamp_like(col, n):
    """v2.2: a text column profiled only by its signature, but whose signature is a
    date/timestamp (e.g. 'DDDD-DD-DD DD:DD:DD.DDDDDDD'): draw timestamps uniformly
    over STUDY_DATE_RANGE and render them in that exact shape."""
    sig = col.get("dominant_signature") or ""
    lo = datetime.datetime.strptime(STUDY_DATE_RANGE[0], "%Y-%m-%d")
    hi = datetime.datetime.strptime(STUDY_DATE_RANGE[1], "%Y-%m-%d")
    span = int((hi - lo).total_seconds())
    frac = len(sig.split(".")[1]) if "." in sig else 0
    out = []
    for _ in range(n):
        d = lo + datetime.timedelta(seconds=random.randint(0, span))
        s = d.strftime("%Y-%m-%d")
        if " " in sig:
            s += d.strftime(" %H:%M:%S")
            if frac:
                s += "." + "".join(random.choice(DIGIT) for _ in range(frac))
        out.append(s)
    return out


def sample_id(col, n):
    if _looks_like_timestamp_sig(col.get("dominant_signature")):
        return sample_timestamp_like(col, n)
    sig = col.get("dominant_signature") or ("D" * max(col.get("len_min", 6), 1))
    unique = col.get("is_unique_key", False)
    seen, out = set(), []
    while len(out) < n:
        val = "".join(random.choice(DIGIT) if ch == "D"
                      else random.choice(ALPHA) if ch == "A"
                      else ch for ch in sig)
        if unique and val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def apply_missing(values, rate):
    if rate <= 0:
        return values
    return ["" if random.random() < rate else v for v in values]


def inv_cdf(grid01, qv, u):
    j = 0
    while j < len(grid01) - 1 and u > grid01[j + 1]:
        j += 1
    lo_g, hi_g = grid01[j], grid01[min(j + 1, len(grid01) - 1)]
    lo_v, hi_v = qv[j], qv[min(j + 1, len(qv) - 1)]
    frac = 0.0 if hi_g == lo_g else (u - lo_g) / (hi_g - lo_g)
    return lo_v + frac * (hi_v - lo_v)


def sample_identifier_unique(col, n):
    """Running numbers in random order, with as many digits as the real key has (the real values
    themselves never left the premises)."""
    width = col.get("len_min") or 1
    start = 10 ** (width - 1) if col.get("all_numeric") and width == col.get("len_max") and 1 < width <= 15 \
        and n <= 9 * 10 ** (width - 1) else 1
    ids = list(range(start, start + n))
    random.shuffle(ids)
    return [str(x) for x in ids]


def sample_identifier_group(col, n):
    n_groups = min(n, max(1, int(col["n_groups"])))
    grid = [g / 100.0 for g in col["group_size_grid"]]
    qv = col["group_size_quantiles"]
    sizes = [max(1, int(round(inv_cdf(grid, qv, random.random())))) for _ in range(n_groups)]
    total = sum(sizes)
    scaled = [max(1, int(round(s * n / total))) for s in sizes] if total else [1] * n_groups
    diff = n - sum(scaled)
    while diff != 0:
        i = random.randrange(n_groups)
        if diff > 0:
            scaled[i] += 1; diff -= 1
        elif scaled[i] > 1:
            scaled[i] -= 1; diff += 1
    out = []
    for gid, size in enumerate(scaled, start=1):
        out.extend([gid] * size)
    random.shuffle(out)
    return [str(x) for x in out[:n]]

def _attach_indices(n, n_parents, grid, quantiles):
    """Assign n child rows to parent row indices; fan-out follows the real
    group-size distribution, and a parent may receive zero children."""
    if n_parents <= 0:
        return [0] * n
    if quantiles:
        g = [x / 100.0 for x in grid]
        sizes = [max(0, int(round(inv_cdf(g, quantiles, random.random()))))
                 for _ in range(n_parents)]
    else:
        sizes = [1] * n_parents
    total = sum(sizes)
    if total <= 0:
        sizes = [1] * n_parents
        total = n_parents
    scaled = [int(round(s * n / total)) for s in sizes]
    diff = n - sum(scaled)
    while diff != 0:
        i = random.randrange(n_parents)
        if diff > 0:
            scaled[i] += 1
            diff -= 1
        elif scaled[i] > 0:
            scaled[i] -= 1
            diff += 1
    idx = []
    for i, s in enumerate(scaled):
        idx.extend([i] * s)
    idx = idx[:n]
    while len(idx) < n:
        idx.append(random.randrange(n_parents))
    random.shuffle(idx)
    return idx


STUDY_DATE_RANGE = ("2015-01-01", datetime.date.today().isoformat())      # for date-shaped text in shape-only columns


def load_profiles(folder):
    reports = []
    for p in sorted(glob.glob(os.path.join(folder, "profile_*.json"))):
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        if isinstance(r, dict) and "columns" in r and "base" in r:
            reports.append(r)
    return reports


def _rand_time(d):
    return d + datetime.timedelta(seconds=random.randint(7 * 3600, 19 * 3600))


def _synth_dates(col, period_vals, mask, n):
    """Dates for one column.  The period (quarter / year) was already drawn, possibly conditioned on
    another column; the month inside it follows the month-by-month counts; the day is random.
    '' in mask = missing."""
    fmt = col.get("format", "%Y-%m-%d")
    try:
        lo, hi = datetime.datetime.strptime(col["min"], fmt), datetime.datetime.strptime(col["max"], fmt)
    except (KeyError, ValueError):
        lo, hi = datetime.datetime(2015, 1, 1), datetime.datetime.now()
    span = max(int((hi - lo).total_seconds()), 1)
    ymf, cache, out = col.get("ym_freqs") or {}, {}, []
    wdf, days_of = col.get("weekday_freqs"), {}
    for i in range(n):
        if mask[i] == "":
            out.append("")
            continue
        lab = period_vals[i] if period_vals else ""
        if lab not in cache:
            months = period_months(lab)
            w = [ymf.get("%04d-%02d" % ym, 0) for ym in months]
            cache[lab] = (months, w if any(w) else [1] * len(months))
        months, w = cache[lab]
        if months:
            y, mo = random.choices(months, weights=w, k=1)[0]
            if wdf:                                              # the day follows the real spread over the week
                if (y, mo) not in days_of:
                    dd = list(range(1, calendar.monthrange(y, mo)[1] + 1))
                    days_of[(y, mo)] = (dd, [wdf[datetime.date(y, mo, x).weekday()] for x in dd])
                d = datetime.datetime(y, mo, random.choices(days_of[(y, mo)][0], weights=days_of[(y, mo)][1], k=1)[0])
            else:
                d = datetime.datetime(y, mo, random.randint(1, calendar.monthrange(y, mo)[1]))
        else:
            d = lo + datetime.timedelta(seconds=random.randint(0, span))
            d = datetime.datetime(d.year, d.month, d.day)
        out.append(_rand_time(d) if col.get("has_time") else d)
    return out


def _format_dates(col, vals, as_excel):
    fmt = col.get("format", "%Y-%m-%d")
    if col.get("serial"):
        return ["" if v == "" else date_to_excel_serial(v) for v in vals]
    if as_excel and col.get("excel_date"):
        return vals                                              # real Excel date cells
    return ["" if v == "" else v.strftime(fmt) for v in vals]


def _as_number(v):
    if isinstance(v, str) and v != "" and _is_numeric(v):
        f = float(v)
        return int(f) if f.is_integer() and "." not in v else f
    return v


def synth_table(rep, entry, synth, scale):
    """One synthetic table: {'header', 'cols' {name: values}, 'n'}."""
    header = rep.get("header") or [c["name"] for c in rep["columns"] if not c.get("helper")]
    if rep.get("verbatim_rows") is not None:
        rows = rep["verbatim_rows"]
        return {"header": header, "n": len(rows), "cols": {h: [_as_number(r[i]) for r in rows] for i, h in enumerate(header)}}
    n = int(round(rep["n_rows"] * scale))
    n = max(1, n) if rep["n_rows"] else 0
    by = {c["name"]: c for c in rep["columns"]}
    parent, link = entry.get("parent"), entry.get("link")
    parent_key = entry.get("parent_key") or link
    inherited = set(entry.get("inherited") or [])
    attach = None
    if parent is not None and parent in synth and synth[parent]["n"]:
        has = synth[parent]["cols"].get("has::%s" % rep["base"])       # only some parent rows have rows here
        elig = [i for i, v in enumerate(has) if v == "yes"] if has else []
        if elig:
            attach = [elig[i] for i in _attach_indices(n, len(elig), entry.get("fanout_grid"), entry.get("fanout_quantiles"))]
        else:
            attach = _attach_indices(n, synth[parent]["n"], entry.get("fanout_grid"), entry.get("fanout_quantiles"))
    cols, copied = {}, set()
    for col in rep["columns"]:
        name, kind = col["name"], col["kind"]
        if attach is not None and (name == link or name in inherited or col.get("helper") == "parent"):
            src = synth[parent]["cols"].get(parent_key if name == link else col.get("parent_col", name))
            if src is not None:                                   # the value of the parent row this row hangs from
                cols[name] = [src[attach[i]] for i in range(n)]
                if col.get("parent_bins"):                         # a number of the parent row, as its band
                    eb = col["parent_bins"]
                    cols[name] = ['' if to_float(v) is None else "B%d" % bisect.bisect_left(eb, to_float(v)) for v in cols[name]]
                if kind == "datetime":
                    copied.add(name)
                continue
        if kind == "datetime":
            vals = ["x"] * n                                      # filled in below, after the months are drawn
        elif kind == "integer" and col.get("value_freqs"):
            vf = col["value_freqs"]
            vals = [int(x) for x in random.choices(list(vf), weights=list(vf.values()), k=n)] if n else []
        elif kind in ("integer", "float"):
            vals = sample_numeric(col, n, inject_edges=False)
            if kind == "float":
                vals = [round(x, 4) for x in vals]
        elif kind in ("categorical", "boolean"):
            vals = sample_categorical(col, n, inject_edges=False) if n else []
        elif kind == "id_or_text":
            vals = sample_id(col, n)
        elif kind == "identifier_unique":
            vals = sample_identifier_unique(col, n)
        elif kind == "identifier_group":
            vals = sample_identifier_group(col, n) if n else []
        else:
            vals = [""] * n
        ruled = col.get("empty_when") and col["empty_when"]["column"] in by       # emptied by rule below, not at random
        cols[name] = apply_missing(vals, 0.0 if ruled else col.get("missing_rate", 0.0))
    for L in entry.get("links") or []:                          # every other link: draw from the parent's keys
        if L.get("primary") and attach is not None:
            continue
        p, lk, pk = L["parent"], L["link"], L["parent_key"]
        if p in synth and lk in by:
            pool = [v for v in synth[p]["cols"].get(pk, []) if v not in ("", None)]
            if pool:
                mr = by[lk].get("missing_rate", 0.0)
                cols[lk] = ["" if random.random() < mr else random.choice(pool) for _ in range(n)]
    apply_crosstabs(cols, rep, n)
    for col in rep["columns"]:                                   # empty exactly when another column says so
        ew = col.get("empty_when")
        if ew and ew["column"] in cols and col["name"] in cols:
            X, V, when = cols[ew["column"]], cols[col["name"]], set(ew["values"])
            for i in range(n):
                if str(X[i]) in when:
                    V[i] = ""
    for col in rep["columns"]:
        if col["kind"] == "datetime" and col["name"] not in copied:
            cols[col["name"]] = _synth_dates(col, cols.get(col["name"] + "__period"), cols[col["name"]], n)
    for col in rep["columns"]:                                   # a date = the parent row's date + a real-looking number of days
        if col.get("helper") != "pgap" or attach is None:
            continue
        b, src = col["of"], synth[parent]["cols"].get(col["parent_col"])
        if src is None or b not in cols or b in copied:
            continue
        B, G = cols[b], cols[col["name"]]
        for i in range(n):
            p = src[attach[i]]
            if B[i] != "" and G[i] != "" and isinstance(p, datetime.datetime):
                d = datetime.datetime(p.year, p.month, p.day) + datetime.timedelta(days=int(float(G[i])))
                B[i] = _rand_time(d) if by[b].get("has_time") else d
    for col in rep["columns"]:                                   # a later date = the earlier one + a real-looking wait
        if col.get("helper") != "gap":
            continue
        a, b = col["from"], col["of"]
        if a not in cols or b not in cols or b in copied:
            continue
        A, B, G = cols[a], cols[b], cols[col["name"]]
        for i in range(n):
            if A[i] != "" and B[i] != "" and G[i] != "" and isinstance(A[i], datetime.datetime):
                d = A[i] + datetime.timedelta(days=max(0, int(float(G[i]))))
                B[i] = _rand_time(datetime.datetime(d.year, d.month, d.day)) if by[b].get("has_time") else d
    for col in rep["columns"]:                                   # an age = the years between two dates of the row
        dy = col.get("derived_years")
        if dy and dy[0] in cols and dy[1] in cols:
            A, B, V = cols[dy[0]], cols[dy[1]], cols[col["name"]]
            for i in range(n):
                if V[i] != "" and isinstance(A[i], datetime.datetime) and isinstance(B[i], datetime.datetime):
                    V[i] = max(0, int((B[i] - A[i]).days // 365.25))
    for col in rep["columns"]:
        name = col["name"]
        if col.get("helper") == "period" and col["of"] in cols:    # keep the period in step with the final date
            cols[name] = [period_label(d, col["scheme"]) if isinstance(d, datetime.datetime) else "" for d in cols[col["of"]]]
        elif col["kind"] == "float":
            dec = col.get("decimals", 2)
            cols[name] = [v if v == "" else round(float(v), dec) for v in cols[name]]
        elif col["kind"] == "integer" or (col.get("all_numeric") and col["kind"] != "datetime"):
            cols[name] = [_as_number(v) for v in cols[name]]
    return {"header": header, "cols": cols, "n": n, "dates": {c["name"]: c for c in rep["columns"] if c["kind"] == "datetime"}}


def run_synth(profile_dir, out_dir, scale=1.0, seed=DEFAULT_SEED):
    """Step 2.  Returns (out_dir, [(file, table, rows, columns)])."""
    reports = load_profiles(profile_dir)
    if not reports:
        raise SystemExit("ERROR: no profile_*.json in %s" % profile_dir)
    sp = os.path.join(profile_dir, "schema.json")
    schema = {"files": {}, "order": []}
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            schema = json.load(f)
    random.seed(seed)
    by_base = {r["base"]: r for r in reports}
    order = [b for b in schema.get("order", []) if b in by_base] + [b for b in by_base if b not in schema.get("order", [])]
    synth = {}
    for base in order:
        print("  building : %s" % base, flush=True)
        synth[base] = synth_table(by_base[base], schema.get("files", {}).get(base) or {}, synth, scale)
    os.makedirs(out_dir, exist_ok=True)
    by_file, outputs = {}, []
    for r in sorted(reports, key=lambda r: (r["source_file"], r.get("sheet_index", 0))):   # sheets in their real order
        by_file.setdefault(r["source_file"], []).append(r)
    for fname, reps in by_file.items():
        stem = os.path.splitext(fname)[0]
        is_csv = reps[0].get("file_type") == "csv"
        sheets = []
        for r in reps:
            t = synth[r["base"]]
            cols = dict(t["cols"])
            for name, c in (t.get("dates") or {}).items():
                cols[name] = _format_dates(c, cols[name], as_excel=not is_csv)
            rows = [t["header"]] + [[cols[h][i] if h in cols else "" for h in t["header"]] for i in range(t["n"])]
            sheets.append((r.get("sheet") or "Sheet1", rows))
            outputs.append((fname, r["base"], t["n"], len(t["header"])))
        if is_csv:
            out = os.path.join(out_dir, "synthetic_%s.csv" % stem)
            with open(out, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(sheets[0][1])
        else:
            out = os.path.join(out_dir, "synthetic_%s.xlsx" % stem)
            write_workbook(out, sheets)
        print("  [OK] %s" % os.path.basename(out))
    with open(os.path.join(out_dir, "synthetic_manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"synthetic": True, "tool": VERSION, "made": datetime.datetime.now().isoformat(timespec="seconds"),
                   "seed": seed, "scale": scale, "note": "Every value is invented from aggregate profiles. Results on "
                   "these files test the software; they are not findings.",
                   "files": [{"file": a, "table": b, "rows": c, "columns": d} for a, b, c, d in outputs]},
                  f, ensure_ascii=False, indent=1)
    print("\nDONE. Synthetic files in: %s" % out_dir)
    print("Every value is invented. Results on these files test your script; they are not findings.")
    return out_dir, outputs


# ==============================================================================
#  Step 3 -- the toolbox for your own analysis script  (import gov_one as g)
# ==============================================================================
USING_SYNTHETIC = False


class Table(object):
    """One table: .name  .file  .sheet  .header  .rows (a list of {column: text})."""

    def __init__(self, t, synthetic):
        self.name, self.file, self.sheet = t['base'], t['file'], t['sheet']
        self.header, self.rows, self.synthetic = t['header'], t['rows'], synthetic

    def __len__(self):
        return len(self.rows)

    def __repr__(self):
        return '<Table %s: %d rows x %d columns%s>' % (self.name, len(self.rows), len(self.header),
                                                       ' SYNTHETIC' if self.synthetic else '')

    def col(self, name):
        """The column as text, row by row ('' = empty)."""
        return [r.get(name, '') for r in self.rows]

    def nums(self, name):
        """The column as numbers; empty and non-numeric cells are left out."""
        return [x for x in (to_float(v) for v in self.col(name)) if x is not None]

    def dates(self, name):
        """The column as dates; cells that are not dates are left out."""
        return [d for d in (to_date(v) for v in self.col(name)) if d is not None]


def open_tables(folder='.'):
    """{table name: Table} for every Excel / CSV file in the folder.
    Real files win.  When the folder holds no real data file, the synthetic files (in the folder or
    in its 'synthetic' sub-folder) are used under the SAME table names, and g.USING_SYNTHETIC is set,
    so one script runs unchanged at home and on the premises."""
    global USING_SYNTHETIC
    paths, _ = find_inputs(folder)
    synthetic = False
    if not paths:
        for d in (folder, os.path.join(folder, SYNTH_DIR)):
            paths = sorted(p for p in glob.glob(os.path.join(d, 'synthetic_*'))
                           if p.lower().endswith(('.xlsx', '.csv')))
            if paths:
                synthetic = True
                break
    if not paths:
        raise SystemExit('ERROR: no data file (and no synthetic_ file) in %s' % os.path.abspath(folder))
    USING_SYNTHETIC = synthetic
    out = {}
    for p in paths:
        for t in read_file_tables(p):
            if synthetic:
                t['base'] = re.sub(r'^synthetic_', '', t['base'])
            out[t['base']] = Table(t, synthetic)
    print('%s data: %d table(s) from %s' % ('SYNTHETIC' if synthetic else 'REAL', len(out), os.path.abspath(folder)))
    return out


def to_num(v):
    """Text -> number, or None."""
    return to_float(v) if not is_missing(v) else None


def to_date(v):
    """Text -> datetime, or None.  Reads 2024-03-15, 15/03/2024, 15.03.2024 and date-times."""
    return None if is_missing(v) else _to_dt(str(v).strip())


def month_key(v):
    """'YYYY-MM' of a date cell, or ''."""
    d = v if isinstance(v, datetime.datetime) else to_date(v)
    return '%04d-%02d' % (d.year, d.month) if d else ''


def count_by(rows, *cols):
    """{value (or tuple of values): number of rows}, largest first."""
    out = {}
    for r in rows:
        key = r.get(cols[0], '') if len(cols) == 1 else tuple(r.get(c, '') for c in cols)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def group_by(rows, col):
    """{value: [rows]}."""
    out = {}
    for r in rows:
        out.setdefault(r.get(col, ''), []).append(r)
    return out


def join(rows, parent_rows, on, parent_on=None, prefix=''):
    """Each row plus the columns of its parent row (matched on the key).  Rows without a parent are
    kept with nothing added.  A parent column that already exists in the row gets the prefix."""
    parent_on = parent_on or on
    index = {}
    for p in parent_rows:
        index.setdefault(p.get(parent_on, ''), p)
    out = []
    for r in rows:
        new = dict(r)
        p = index.get(r.get(on, '')) if r.get(on, '') != '' else None
        if p:
            for a, b in p.items():
                if a != parent_on:
                    new[(prefix + a) if (a in r or prefix) else a] = b
        out.append(new)
    return out


def monthly_counts(rows, date_col, by=None, value=None):
    """Rows (or the sum of a numeric column) per month: ([months in order], {group: [one number per month]}).
    Months with nothing are 0; the months run from the first to the last one seen."""
    cells, months = {}, set()
    for r in rows:
        m = month_key(r.get(date_col, ''))
        if not m:
            continue
        g = r.get(by, '') if by else 'all'
        x = 1 if value is None else (to_num(r.get(value, '')) or 0)
        months.add(m)
        cells[(g, m)] = cells.get((g, m), 0) + x
    if not months:
        return [], {}
    y, mo = [int(x) for x in min(months).split('-')]
    last, axis = max(months), []
    while '%04d-%02d' % (y, mo) <= last:
        axis.append('%04d-%02d' % (y, mo))
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    groups = sorted({g for g, _ in cells}, key=str)
    return axis, {g: [cells.get((g, m), 0) for m in axis] for g in groups}


def safe(n, k=MIN_CELL_COUNT):
    """A count for a report that may leave: '<k' instead of a number below k."""
    return ('<%d' % k) if 0 < n < k else n


# ---- statistics ---------------------------------------------------------------
def quantile(xs, p):
    """The p-th percentile (0-100) of a list of numbers."""
    return percentile(sorted(xs), p)


def describe(xs):
    """n, mean, sd (sample), min, p25, median, p75, max of a list of numbers."""
    xs = sorted(x for x in xs if x is not None)
    n = len(xs)
    if not n:
        return {'n': 0}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return {'n': n, 'mean': m, 'sd': sd, 'min': xs[0], 'p25': percentile(xs, 25), 'median': percentile(xs, 50),
            'p75': percentile(xs, 75), 'max': xs[-1]}


def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def beta_inc(a, b, x):
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def gamma_q(a, x):
    """Regularised upper incomplete gamma function Q(a, x)."""
    if x <= 0.0:
        return 1.0
    lead = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1.0:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(2000):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 3e-14:
                break
        return max(0.0, 1.0 - s * lead)
    tiny = 1e-300
    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return lead * h


def p_normal(z):
    """Two-sided p value of a z statistic."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def p_t(t, df):
    """Two-sided p value of a t statistic."""
    return beta_inc(df / 2.0, 0.5, df / (df + t * t)) if df > 0 else float('nan')


def p_chi2(x, df):
    """Upper-tail p value of a chi-square statistic."""
    return gamma_q(df / 2.0, x / 2.0) if df > 0 else float('nan')


def p_f(f, d1, d2):
    """Upper-tail p value of an F statistic."""
    return beta_inc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f)) if f > 0 else 1.0


def t_crit(df, alpha=0.05):
    """The t value with two-sided tail area alpha (1.96 for large df)."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if p_t(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def crosstab(rows, row_col, col_col):
    """(row labels, column labels, counts as a list of lists); empty cells of either column are skipped."""
    cells, rl, cl = {}, [], []
    for r in rows:
        a, b = r.get(row_col, ''), r.get(col_col, '')
        if is_missing(a) or is_missing(b):
            continue
        if a not in rl:
            rl.append(a)
        if b not in cl:
            cl.append(b)
        cells[(a, b)] = cells.get((a, b), 0) + 1
    rl.sort(key=str)
    cl.sort(key=str)
    return rl, cl, [[cells.get((a, b), 0) for b in cl] for a in rl]


def chi_square(table):
    """Chi-square test of independence on a table of counts (list of rows).
    Returns chi2, df, p, n, cramers_v and the smallest expected count (below 5 = read with care)."""
    rs = [sum(r) for r in table]
    cs = [sum(r[j] for r in table) for j in range(len(table[0]))] if table else []
    keep_r = [i for i, x in enumerate(rs) if x > 0]
    keep_c = [j for j, x in enumerate(cs) if x > 0]
    n = float(sum(rs))
    if n == 0 or len(keep_r) < 2 or len(keep_c) < 2:
        return {'chi2': float('nan'), 'df': 0, 'p': float('nan'), 'n': int(n), 'cramers_v': float('nan'), 'min_expected': float('nan')}
    chi2, min_e = 0.0, float('inf')
    for i in keep_r:
        for j in keep_c:
            e = rs[i] * cs[j] / n
            min_e = min(min_e, e)
            chi2 += (table[i][j] - e) ** 2 / e
    df = (len(keep_r) - 1) * (len(keep_c) - 1)
    return {'chi2': chi2, 'df': df, 'p': p_chi2(chi2, df), 'n': int(n),
            'cramers_v': math.sqrt(chi2 / (n * (min(len(keep_r), len(keep_c)) - 1))), 'min_expected': min_e}


def t_test(a, b):
    """Welch's t test for two groups of numbers (unequal variances).
    Returns the means, their difference (a - b) with a 95% interval, t, df and the two-sided p."""
    da, db = describe(a), describe(b)
    if da['n'] < 2 or db['n'] < 2:
        return {'n_a': da['n'], 'n_b': db['n'], 'p': float('nan')}
    va, vb = da['sd'] ** 2 / da['n'], db['sd'] ** 2 / db['n']
    se = math.sqrt(va + vb)
    diff = da['mean'] - db['mean']
    if se == 0:
        return {'n_a': da['n'], 'n_b': db['n'], 'mean_a': da['mean'], 'mean_b': db['mean'], 'diff': diff, 'p': float('nan')}
    df = (va + vb) ** 2 / (va ** 2 / (da['n'] - 1) + vb ** 2 / (db['n'] - 1))
    t = diff / se
    h = t_crit(df) * se
    return {'n_a': da['n'], 'n_b': db['n'], 'mean_a': da['mean'], 'mean_b': db['mean'], 'diff': diff,
            'ci95': (diff - h, diff + h), 't': t, 'df': df, 'p': p_t(t, df)}


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for q in range(i, j + 1):
            ranks[order[q]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def mann_whitney(a, b):
    """Mann-Whitney U test (rank test for two groups; normal approximation with tie correction)."""
    na, nb = len(a), len(b)
    if na < 1 or nb < 1:
        return {'p': float('nan')}
    ranks = _ranks(list(a) + list(b))
    u = sum(ranks[:na]) - na * (na + 1) / 2.0
    n = na + nb
    ties = {}
    for x in list(a) + list(b):
        ties[x] = ties.get(x, 0) + 1
    tie = sum(t ** 3 - t for t in ties.values())
    var = na * nb / 12.0 * ((n + 1) - tie / float(n * (n - 1))) if n > 1 else 0.0
    if var <= 0:
        return {'u': u, 'p': float('nan')}
    z = (u - na * nb / 2.0) / math.sqrt(var)
    return {'u': u, 'z': z, 'p': p_normal(z), 'n_a': na, 'n_b': nb, 'prob_a_above_b': u / float(na * nb)}


def pearson(x, y):
    """Pearson correlation of two equal-length lists: r, n and the two-sided p."""
    n = len(x)
    if n < 3 or n != len(y):
        return {'r': float('nan'), 'n': n, 'p': float('nan')}
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return {'r': float('nan'), 'n': n, 'p': float('nan')}
    r = sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    t = r * math.sqrt((n - 2) / max(1e-300, 1.0 - r * r))
    return {'r': r, 'n': n, 'p': p_t(t, n - 2)}


def spearman(x, y):
    """Spearman rank correlation: rho, n and the two-sided p."""
    out = pearson(_ranks(list(x)), _ranks(list(y)))
    return {'rho': out['r'], 'n': out['n'], 'p': out['p']}


def proportion_test(x1, n1, x2, n2):
    """Two proportions x1/n1 and x2/n2: the difference with a 95% interval, z and the two-sided p."""
    if n1 <= 0 or n2 <= 0:
        return {'p': float('nan')}
    p1, p2 = x1 / float(n1), x2 / float(n2)
    pool = (x1 + x2) / float(n1 + n2)
    se0 = math.sqrt(pool * (1 - pool) * (1.0 / n1 + 1.0 / n2))
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = (p1 - p2) / se0 if se0 > 0 else float('nan')
    return {'p1': p1, 'p2': p2, 'diff': p1 - p2, 'ci95': (p1 - p2 - 1.96 * se, p1 - p2 + 1.96 * se), 'z': z,
            'p': p_normal(z) if se0 > 0 else float('nan')}


def _solve(A, B):
    """Solve A X = B (A square, B a matrix) by Gauss-Jordan elimination; None when A is singular."""
    n = len(A)
    M = [list(map(float, A[i])) + list(map(float, B[i])) for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def ols(y, X, names=None, intercept=True, hac_lags=None):
    """Ordinary least squares.  y: list of numbers; X: list of rows of predictors (one row per y).
    Returns names, coef, se, t, p, ci95, r2, n, df, fitted, resid.
    hac_lags=None: classical standard errors and t tests.  hac_lags=k: Newey-West standard errors
    for a time series (use about 6 for monthly data); tests then use the normal distribution."""
    n = len(y)
    rows = [([1.0] if intercept else []) + [float(v) for v in r] for r in X]
    p = len(rows[0]) if rows else 0
    names = (['intercept'] if intercept else []) + list(names or ['x%d' % (i + 1) for i in range(p - (1 if intercept else 0))])
    if n <= p or p == 0:
        return {'error': 'too few rows for %d coefficients' % p, 'n': n}
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(p)] for i in range(p)]
    xty = [[sum(r[i] * yy for r, yy in zip(rows, y))] for i in range(p)]
    inv = _solve(xtx, [[1.0 if i == j else 0.0 for j in range(p)] for i in range(p)])
    if inv is None:
        return {'error': 'the predictors are linearly dependent', 'n': n}
    coef = [sum(inv[i][j] * xty[j][0] for j in range(p)) for i in range(p)]
    fitted = [sum(c * v for c, v in zip(coef, r)) for r in rows]
    resid = [yy - f for yy, f in zip(y, fitted)]
    df = n - p
    my = sum(y) / n
    sst = sum((yy - my) ** 2 for yy in y)
    sse = sum(e * e for e in resid)
    if hac_lags is None:
        s2 = sse / df
        cov = [[s2 * inv[i][j] for j in range(p)] for i in range(p)]
    else:
        L = int(hac_lags)
        S = [[sum(resid[t] ** 2 * rows[t][i] * rows[t][j] for t in range(n)) for j in range(p)] for i in range(p)]
        for lag in range(1, min(L, n - 1) + 1):
            w = 1.0 - lag / (L + 1.0)
            for i in range(p):
                for j in range(p):
                    g = sum(resid[t] * resid[t - lag] * (rows[t][i] * rows[t - lag][j] + rows[t - lag][i] * rows[t][j])
                            for t in range(lag, n))
                    S[i][j] += w * g
        tmp = [[sum(inv[i][a] * S[a][j] for a in range(p)) for j in range(p)] for i in range(p)]
        cov = [[n / float(df) * sum(tmp[i][a] * inv[a][j] for a in range(p)) for j in range(p)] for i in range(p)]
    se = [math.sqrt(max(0.0, cov[i][i])) for i in range(p)]
    tv = [(c / s if s > 0 else float('nan')) for c, s in zip(coef, se)]
    crit = t_crit(df) if hac_lags is None else 1.96
    pv = [(p_t(t, df) if hac_lags is None else p_normal(t)) if t == t else float('nan') for t in tv]
    return {'names': names, 'coef': coef, 'se': se, 't': tv, 'p': pv,
            'ci95': [(c - crit * s, c + crit * s) for c, s in zip(coef, se)],
            'r2': (1.0 - sse / sst) if sst > 0 else float('nan'), 'n': n, 'df': df, 'fitted': fitted, 'resid': resid}


def its(values, break_index, hac_lags=6, seasonal=False):
    """Interrupted time series on a list of monthly (or other equally spaced) values.
    break_index: position of the first 'after' value.  Fits level + trend before, and the change in
    level and in trend after.  seasonal=True adds a yearly sine / cosine (needs 24+ values).
    Returns the ols result plus 'level_change' and 'slope_change' as (estimate, low, high, p)."""
    n = len(values)
    X, names = [], ['trend', 'level_change', 'slope_change'] + (['sin12', 'cos12'] if seasonal else [])
    for i in range(n):
        t = i - break_index
        post = 1.0 if i >= break_index else 0.0
        row = [t, post, t * post]
        if seasonal:
            row += [math.sin(2 * math.pi * i / 12.0), math.cos(2 * math.pi * i / 12.0)]
        X.append(row)
    out = ols(values, X, names=names, hac_lags=hac_lags)
    if 'error' not in out:
        for a in ('level_change', 'slope_change'):
            j = out['names'].index(a)
            out[a] = (out['coef'][j], out['ci95'][j][0], out['ci95'][j][1], out['p'][j])
    return out


# ---- an offline HTML report -------------------------------------------------------
def fmt(x, digits=2):
    """A number for a table: 1,234 / 12.35 / 0.004 ; p values as '< .001'."""
    if x is None or (isinstance(x, float) and x != x):
        return '—'
    if isinstance(x, str):
        return x
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer() and abs(x) < 1e15):
        return '{:,}'.format(int(x))
    return '{:,.{d}f}'.format(x, d=digits) if abs(x) >= 0.01 else '{:.2g}'.format(x)


def fmt_p(p):
    if p is None or p != p:
        return '—'
    return '< .001' if p < 0.001 else ('= %.3f' % p).replace('0.', '.', 1)


class Report(object):
    """Builds one self-contained HTML page (no internet, no external file).
        rep = g.Report('Title');  rep.h('Section');  rep.p('text');  rep.table(header, rows)
        rep.line(months, {'name': [numbers]});  rep.bars({'label': number});  rep.save('results/report.html')
    The page says in a banner when it was built from synthetic files."""
    COLORS = ['#2f66a8', '#b83a48', '#12766a', '#96660a', '#6a55b0', '#1f6f9c', '#55742f', '#7a7a7a']

    def __init__(self, title, synthetic=None):
        self.title = title
        self.synthetic = USING_SYNTHETIC if synthetic is None else synthetic
        self.parts = []

    @staticmethod
    def _e(s):
        return html.escape(str(s))

    def h(self, text, level=2):
        self.parts.append('<h%d>%s</h%d>' % (level, self._e(text), level))

    def p(self, text):
        self.parts.append('<p dir="auto">%s</p>' % self._e(text))

    def note(self, text):
        self.parts.append('<p class="note" dir="auto">%s</p>' % self._e(text))

    def table(self, header, rows, caption=None):
        out = ['<div class="tw"><table>']
        if caption:
            out.append('<caption dir="auto">%s</caption>' % self._e(caption))
        out.append('<thead><tr>%s</tr></thead><tbody>' % ''.join('<th dir="auto">%s</th>' % self._e(x) for x in header))
        for r in rows:
            out.append('<tr>%s</tr>' % ''.join(
                '<td%s dir="auto">%s</td>' % (' class="n"' if isinstance(v, (int, float)) else '', self._e(fmt(v))) for v in r))
        out.append('</tbody></table></div>')
        self.parts.append(''.join(out))

    def line(self, labels, series, title=None, mark=None):
        """A line chart.  labels: x axis (e.g. months); series: {name: [numbers, None for gaps]};
        mark: a label at which to draw a vertical line (e.g. the month of a reform)."""
        W, H, L, R, T, B = 860, 300, 56, 16, 18, 42
        vals = [v for s in series.values() for v in s if v is not None]
        if not vals or not labels:
            return
        lo, hi = min(0, min(vals)), max(vals)
        hi = hi if hi > lo else lo + 1
        n = len(labels)
        X = lambda i: L + (W - L - R) * (i / float(max(1, n - 1)))
        Y = lambda v: T + (H - T - B) * (1 - (v - lo) / float(hi - lo))
        svg = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, self._e(title or 'chart'))]
        for q in range(5):
            v = lo + (hi - lo) * q / 4.0
            svg.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/><text x="%d" y="%.1f" class="ax" text-anchor="end">%s</text>'
                       % (L, W - R, Y(v), Y(v), L - 6, Y(v) + 4, self._e(fmt(v, 1))))
        step = max(1, n // 10)
        for i in range(0, n, step):
            svg.append('<text x="%.1f" y="%d" class="ax" text-anchor="middle">%s</text>' % (X(i), H - B + 16, self._e(labels[i])))
        if mark in labels:
            x = X(labels.index(mark))
            svg.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" class="mark"/><text x="%.1f" y="%d" class="ax">%s</text>'
                       % (x, x, T, H - B, x + 4, T + 10, self._e(mark)))
        legend = []
        for k, (name, s) in enumerate(series.items()):
            color = self.COLORS[k % len(self.COLORS)]
            d, pen = [], False
            for i, v in enumerate(s[:n]):
                if v is None:
                    pen = False
                    continue
                d.append('%s%.1f %.1f' % ('L' if pen else 'M', X(i), Y(v)))
                pen = True
            svg.append('<path d="%s" fill="none" stroke="%s" stroke-width="2"/>' % (' '.join(d), color))
            legend.append('<span><i style="background:%s"></i>%s</span>' % (color, self._e(name)))
        svg.append('</svg>')
        self.parts.append('<figure>%s%s<div class="lg">%s</div></figure>' % (
            '<figcaption dir="auto">%s</figcaption>' % self._e(title) if title else '', ''.join(svg), ''.join(legend)))

    def bars(self, pairs, title=None):
        """Horizontal bars.  pairs: {label: number} (or a list of pairs), drawn in the order given."""
        items = list(pairs.items()) if isinstance(pairs, dict) else list(pairs)
        items = [(a, b) for a, b in items if isinstance(b, (int, float))]
        if not items:
            return
        top = max(abs(b) for _, b in items) or 1
        rows = ''.join('<div class="br"><span dir="auto">%s</span><b style="width:%.1f%%"></b><em>%s</em></div>'
                       % (self._e(a), 100.0 * abs(b) / top, self._e(fmt(b))) for a, b in items)
        self.parts.append('<figure>%s<div class="bars">%s</div></figure>' % (
            '<figcaption dir="auto">%s</figcaption>' % self._e(title) if title else '', rows))

    def save(self, path):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        banner = ('<div class="syn"><b>Synthetic test data — not findings.</b> Every number on this page comes from '
                  'invented files. It shows that the script works; it says nothing about the real world.</div>') if self.synthetic else ''
        css = ('body{font:15px/1.5 "Segoe UI",Arial,sans-serif;color:#1d2733;background:#f5f7fa;margin:0}'
               'main{max-width:960px;margin:0 auto;padding:24px 16px 60px}h1{font-size:26px;margin:0 0 4px}'
               'h2{font-size:19px;margin:30px 0 8px;padding-top:14px;border-top:3px solid #2f66a8;color:#2f66a8}h3{font-size:16px;margin:20px 0 6px}'
               '.meta{color:#5b6877;font-size:13px}.syn{background:#fdf4dc;border:1px solid #d9b24c;border-left:6px solid #96660a;padding:10px 14px;margin:14px 0;border-radius:6px}'
               '.note{color:#5b6877;font-size:13px}.tw{overflow-x:auto}table{border-collapse:collapse;background:#fff;margin:8px 0;font-size:14px}'
               'caption{text-align:start;font-weight:600;padding:4px 0}th,td{border:1px solid #d5dce5;padding:5px 9px;text-align:start}'
               'th{background:#eaf1f9}td.n{text-align:end;font-variant-numeric:tabular-nums}figure{margin:12px 0;background:#fff;border:1px solid #d5dce5;border-radius:8px;padding:10px}'
               'figcaption{font-weight:600;margin-bottom:6px}svg{width:100%;height:auto}.grid{stroke:#e3e8ee}.ax{font-size:11px;fill:#5b6877}'
               '.mark{stroke:#b83a48;stroke-dasharray:5 4}.lg span{display:inline-flex;align-items:center;gap:6px;margin-inline-end:14px;font-size:13px}'
               '.lg i{width:12px;height:12px;border-radius:2px;display:inline-block}.br{display:grid;grid-template-columns:minmax(90px,30%) 1fr 70px;gap:8px;align-items:center;margin:3px 0;font-size:13px}'
               '.br b{background:#2f66a8;height:14px;border-radius:3px;display:block}.br em{font-style:normal;text-align:end;font-variant-numeric:tabular-nums}'
               '@media print{body{background:#fff}.tw{overflow:visible}figure{break-inside:avoid}}')
        page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>%s</title><style>%s</style></head><body><main><h1 dir="auto">%s</h1><div class="meta">built %s by %s</div>%s%s</main></body></html>'
                % (self._e(self.title), css, self._e(self.title), datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                   self._e(VERSION), banner, ''.join(self.parts)))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
        print('[OK] report: %s%s' % (os.path.abspath(path), '  (SYNTHETIC data - not findings)' if self.synthetic else ''))
        return path


# ==============================================================================
#  Command line
# ==============================================================================
def run_check(data_dir):
    """What would be read: files, sheets, header row, column names.  No data is shown."""
    std = set(getattr(sys, 'stdlib_module_names', ()))
    ext = sorted({m.split('.')[0] for m in sys.modules} - std - {'__main__', 'gov_one'}) if std else []
    ext = [m for m in ext if not m.startswith('_')]
    print('modules outside the standard library loaded: %s' % (', '.join(ext) if ext else 'none'))
    paths, bad = find_inputs(data_dir)
    for p in paths:
        name = os.path.basename(p)
        try:
            if p.lower().endswith(('.csv', '.tsv')):
                parts = [('', read_csv_rows(p)[:80])]
            else:
                parts = [(s, read_sheet(p, part, max_rows=80)[0]) for s, part in xlsx_sheets(p)]
        except Exception as e:                                       # noqa: BLE001
            print('  [!] %s: cannot be read (%s)' % (name, e))
            continue
        for sname, raw in parts:
            raw = [r for r in raw if any(str(c).strip() for c in r)]
            if not raw:
                print('  %s%s: empty' % (name, ' / ' + sname if sname else ''))
                continue
            h = find_header_row(raw)
            head = [str(c).strip() for c in raw[h] if str(c).strip()]
            print('  %s%s: header on row %d, %d columns: %s' % (name, ' / ' + sname if sname else '', h + 1, len(head),
                                                              ', '.join(head[:14]) + (' ...' if len(head) > 14 else '')))
    for b in bad:
        print('  [!] %s: %s' % b)
    if not paths:
        print('  no Excel / CSV data file in %s' % os.path.abspath(data_dir))
    profs = glob.glob(os.path.join(data_dir, 'profile_*.json')) + glob.glob(os.path.join(data_dir, SEND_DIR, 'profile_*.json'))
    print('  profile JSON files found: %d' % len(profs))


def _profile_dir(data_dir):
    for d in (data_dir, os.path.join(data_dir, SEND_DIR)):
        if glob.glob(os.path.join(d, 'profile_*.json')):
            return d
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog='gov_one.py', description='Profile Excel / CSV files into aggregate JSON, rebuild '
                                 'synthetic files from the JSON, and give your own analysis script a statistics toolbox. '
                                 'Standard library only; offline.')
    ap.add_argument('command', nargs='?', default='auto', choices=['auto', 'profile', 'synth', 'check', 'settings'])
    ap.add_argument('--data', default='.', help='folder with the data files (profile) or the JSON files (synth); default: here')
    ap.add_argument('--out', default=None, help='output folder (default: to_send for profile, synthetic for synth)')
    ap.add_argument('--k', type=int, default=None, help='minimum cell count (default %d)' % MIN_CELL_COUNT)
    ap.add_argument('--rows', type=float, default=1.0, help='synth: size of the synthetic files relative to the real ones (0.1 = a tenth)')
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED, help='synth: random seed')
    a = ap.parse_args(argv)
    data = os.path.abspath(a.data)
    if not os.path.isdir(data):
        raise SystemExit('ERROR: folder not found: %s' % data)
    print('%s | Python %s' % (VERSION, sys.version.split()[0]))
    cmd = a.command
    if cmd == 'auto':
        has_data = bool(find_inputs(data)[0])
        cmd = 'profile' if has_data else ('synth' if _profile_dir(data) else None)
        if cmd is None:
            raise SystemExit('Nothing to do in %s: no Excel / CSV data file and no profile_*.json.\n'
                             'On the premises: put gov_one.py next to the data files and run it.\n'
                             'At home: put it next to the JSON files (or the to_send folder) and run it.' % data)
        print('auto     : %s' % ('data files found -> profile' if cmd == 'profile' else 'only JSON files found -> synthetic files'))
    t0 = time.time()
    if cmd == 'check':
        run_check(data)
    elif cmd == 'settings':
        p = os.path.join(data, SETTINGS_FILE)
        if os.path.exists(p):
            raise SystemExit('%s already exists; edit it.' % p)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS_TEMPLATE, f, ensure_ascii=False, indent=2)
        print('[OK] %s written. Edit it, then run the profile again.' % p)
    elif cmd == 'profile':
        run_profile(data, a.out, a.k)
    elif cmd == 'synth':
        pd = _profile_dir(data)
        if not pd:
            raise SystemExit('ERROR: no profile_*.json in %s (or its %s folder)' % (data, SEND_DIR))
        if find_inputs(data)[0]:
            print('  [!] real data files are in this folder too; the synthetic files go to a separate folder')
        run_synth(pd, a.out or os.path.join(data, SYNTH_DIR), scale=a.rows, seed=a.seed)
    print('(%.1f s)' % (time.time() - t0))


if __name__ == '__main__':
    main()
