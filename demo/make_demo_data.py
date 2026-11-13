"""make_demo_data.py -- invents the files of a pretend welfare office, to rehearse the whole flow.

    python demo/make_demo_data.py            ->  demo/premises/  (3 files, 4 tables)

Nothing here is real: names, id numbers, phones, dates and amounts are random.  The folder plays
the role of the "real" files on the premises, so you can run   profile -> synth -> your script
and compare what the script finds on the synthetic files with what it finds on the "real" ones.
"""
import os
import sys
import random
import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gov_one as g

random.seed(2026)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'premises')
os.makedirs(OUT, exist_ok=True)

FIRST = ['דוד', 'משה', 'יוסף', 'אברהם', 'שרה', 'רחל', 'מרים', 'לאה', 'אחמד', 'מוחמד', 'פאטמה', 'נועה', 'יעל', 'איתי', 'עומר', 'תמר']
LAST = ['כהן', 'לוי', 'מזרחי', 'פרץ', 'ביטון', 'דהן', 'אברהם', 'פרידמן', 'אגבאריה', 'חורי', 'גבאי', 'שפירא', 'אזולאי', 'מלכה']
DISTRICTS = {'צפון': ['חיפה', 'נצרת', 'עכו', 'צפת', 'טבריה', 'כרמיאל'], 'מרכז': ['פתח תקווה', 'רמלה', 'לוד', 'נתניה', 'כפר סבא'],
             'תל אביב': ['תל אביב', 'בת ים', 'חולון', 'בני ברק'], 'ירושלים': ['ירושלים', 'בית שמש', 'מעלה אדומים'],
             'דרום': ['באר שבע', 'אשדוד', 'אשקלון', 'דימונה', 'רהט', 'אילת']}
DW = {'צפון': 22, 'מרכז': 25, 'תל אביב': 18, 'ירושלים': 15, 'דרום': 20}
CASE_TYPES = ['סיוע כלכלי', 'אלימות במשפחה', 'קשישים', 'נוער בסיכון', 'מוגבלות']
REFORM = datetime.datetime(2024, 1, 1)                   # a pretend reform: faster handling of 'נוער בסיכון' from 2024


def pick(d):
    return random.choices(list(d), weights=list(d.values()))[0]


def day(a, b):
    return a + datetime.timedelta(days=random.randint(0, (b - a).days))


# ---- clients (a title and a date sit above the header, as ministry exports often do) -------------
clients, ids = [], random.sample(range(200000000, 399999999), 3000)
for i in range(3000):
    dist = pick(DW)
    town = random.choice(DISTRICTS[dist])
    kids = random.choices(range(0, 9), weights=[18, 16, 22, 18, 10, 6, 5, 3, 2])[0]
    income = max(0, round(random.lognormvariate(8.6, 0.5) - (600 if dist == 'דרום' else 0)))
    clients.append([100001 + i, ids[i], random.choice(FIRST), random.choice(LAST),
                    '05%d-%07d' % (random.randint(0, 8), random.randint(0, 9999999)),
                    day(datetime.datetime(1940, 1, 1), datetime.datetime(2006, 12, 31)),
                    random.choice(['זכר', 'נקבה']), dist, town,
                    random.choices(['נשוי', 'רווק', 'גרוש', 'אלמן'], weights=[45, 25, 20, 10])[0],
                    kids, income if random.random() > 0.08 else ''])
for row, town in zip(clients[:7], ['מצפה רמון'] * 3 + ['ירוחם'] * 4):      # two rare towns (3 and 4 clients): their
    row[7], row[8] = 'דרום', town                                           # names must not leave the premises
client_sheet = [['משרד הרווחה - דוח לקוחות'], ['הופק בתאריך 01/11/2026'],
                ['מספר לקוח', 'תעודת זהות', 'שם פרטי', 'שם משפחה', 'טלפון', 'תאריך לידה', 'מגדר', 'מחוז', 'יישוב',
                 'מצב משפחתי', 'מספר ילדים', 'הכנסה חודשית']] + clients
district_sheet = [['קוד מחוז', 'מחוז', 'מנהל מחוז']] + [[i + 1, d, random.choice(FIRST) + ' ' + random.choice(LAST)]
                                                      for i, d in enumerate(DISTRICTS)]
g.write_workbook(os.path.join(OUT, 'לקוחות.xlsx'), [('לקוחות', client_sheet), ('מחוזות', district_sheet)])

# ---- cases: several per client; the reform shortens the wait for one case type -------------------
workers = [random.choice(FIRST) + ' ' + random.choice(LAST) for _ in range(40)]
cases, case_no = [], 500000
dist_of = {c[0]: c[7] for c in clients}
for c in clients:
    for _ in range(random.choices([1, 2, 3, 4, 6], weights=[35, 30, 20, 10, 5])[0]):
        case_no += 1
        d = dist_of[c[0]]
        w = [30, 14, 20, 16, 20]
        if d == 'דרום':
            w = [42, 14, 12, 20, 12]
        if d == 'תל אביב':
            w = [22, 12, 34, 12, 20]
        ctype = random.choices(CASE_TYPES, weights=w)[0]
        opened = day(datetime.datetime(2021, 1, 1), datetime.datetime(2026, 9, 30))
        if ctype == 'נוער בסיכון' and opened < REFORM and random.random() < 0.45:
            opened = day(REFORM, datetime.datetime(2026, 9, 30))             # more such cases after the reform
        wait = random.gammavariate(2.0, 45)
        if ctype == 'נוער בסיכון' and opened >= REFORM:
            wait *= 0.55                                                     # ... and they close faster
        closed = opened + datetime.timedelta(days=int(wait))
        is_open = closed > datetime.datetime(2026, 10, 31) or random.random() < 0.12
        cases.append([case_no, c[0], ctype, opened, '' if is_open else closed, 'פתוח' if is_open else 'סגור',
                      random.choice(workers), random.choice(['עירייה', 'משטרה', 'בית חולים', 'פנייה עצמית', 'בית ספר'])])
cases[10][7] = cases[11][7] = 'שגרירות'                                    # a referral source seen only twice
random.shuffle(cases)
g.write_workbook(os.path.join(OUT, 'תיקים.xlsx'), [('תיקים', [['מספר תיק', 'מספר לקוח', 'סוג תיק', 'תאריך פתיחה', 'תאריך סגירה',
                                                              'סטטוס', 'עובד סוציאלי', 'גורם מפנה']] + cases)])

# ---- payments: a CSV with text dates (day/month/year), linked to the cases -------------------------
import csv
pay_no = 9000000
with open(os.path.join(OUT, 'תשלומים.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['מספר תשלום', 'מספר תיק', 'תאריך תשלום', 'סכום', 'סוג תשלום'])
    n = 0
    for cs in cases:
        if cs[2] not in ('סיוע כלכלי', 'קשישים', 'מוגבלות'):
            continue
        for _ in range(random.choices([0, 1, 2, 4, 8], weights=[20, 30, 25, 15, 10])[0]):
            pay_no += 1
            n += 1
            when = cs[3] + datetime.timedelta(days=random.randint(5, 400))
            amount = round(random.lognormvariate(7.0 if cs[2] == 'סיוע כלכלי' else 6.4, 0.6), 2)
            w.writerow([pay_no, cs[0], when.strftime('%d/%m/%Y'), amount,
                        random.choices(['חד פעמי', 'חודשי', 'חירום'], weights=[50, 40, 10])[0]])

print('demo "premises" folder: %s' % OUT)
print('  לקוחות.xlsx  : %d clients + a small districts sheet' % len(clients))
print('  תיקים.xlsx   : %d cases' % len(cases))
print('  תשלומים.csv  : %d payments' % n)
