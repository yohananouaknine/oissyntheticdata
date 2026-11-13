"""make_suicide_data.py -- INVENTED files of a pretend welfare unit that follows suicide cases.

    python demo_suicide/make_suicide_data.py      ->  demo_suicide/premises/   (3 files, 5 tables)

EVERY ROW IS INVENTED.  No person, id number, name, date or note here is real.

Only the PROPORTIONS follow published national statistics, so the test looks like the real thing:
  Ministry of Health, "Suicidality in Israel: suicides 2000-2023" (January 2026), which is built on the
  cause-of-death files of the Central Bureau of Statistics (CBS), ICD-10 codes X60-X84 and Y87.0.
  https://www.gov.il/BlobFolder/reports/suicides-2023/he/files_publications_units_info_suicides_2000-2023.pdf
  CBS Statistical Abstract, table 3.10, mortality rates by cause: "Intentional self-harm" 5-6 per 100,000.

Taken from the report:
  * suicides per year and sex, 2014-2023 (exact numbers, table "all suicides")
  * age: about 14-15% under 25, a third 25-44, 26-28% 45-64, a quarter 65+ (2021-2023)
  * population group: 388 Jews and others, 45 Arabs in 2023; Arab cases are younger (72% under 45)
  * marital status 2023: men 143 single / 106 married / 66 divorced / 16 widowed; women 42 / 33 / 21 / 6
  * method 2021-2023: men 55% hanging, 20% jumping, 13% firearm, 5% poisoning;
                      women 46% hanging, 29% jumping, 17% poisoning, 2% firearm
  * month: counts per month 2004-2023 (May and June high, October to December low); fewer on Friday / Saturday
  * about 16% had a suicide attempt in the five years before
My own assumptions (not in the report): the split inside 65+, country-of-birth shares, district weights
(population share x published district rate), towns, everything about the welfare contacts.
"""
import os
import sys
import csv
import random
import datetime
import calendar

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gov_one as g

random.seed(7801)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'premises')
os.makedirs(OUT, exist_ok=True)

# ---- published: suicides per year (men, women) --------------------------------------------------
PER_YEAR = {2014: (301, 89), 2015: (283, 80), 2016: (329, 71), 2017: (309, 100), 2018: (360, 97),
            2019: (340, 96), 2020: (351, 100), 2021: (321, 106), 2022: (330, 99), 2023: (331, 102)}
# published: counts per month 2004-2023, standardised to 31 days
MONTH_W = [695, 669, 718, 712, 761, 748, 681, 713, 735, 657, 654, 624]
DAY_W = {4: 0.82, 5: 0.80}                                 # Friday, Saturday (Monday = 0)

AGE_GROUPS = [(15, 24), (25, 44), (45, 64), (65, 74), (75, 97)]
AGE_W = {('יהודים ואחרים', 'זכר'): [12, 31, 29, 13, 15], ('יהודים ואחרים', 'נקבה'): [13, 31, 27, 14, 15],
         ('ערבים', 'זכר'): [24, 48, 23, 3, 2], ('ערבים', 'נקבה'): [26, 46, 22, 4, 2]}
MARITAL = ['רווק/ה', 'נשוי/אה', 'גרוש/ה', 'אלמן/ה']
MARITAL_W = [[97, 3, 0, 0], [55, 30, 15, 0], [22, 42, 33, 3], [8, 52, 20, 20], [6, 44, 12, 38]]
METHODS = ['תלייה או חנק', 'קפיצה מגובה', 'נשק', 'הרעלה', 'אחר']
METHOD_W = {'זכר': [55, 20, 13, 5, 7], 'נקבה': [46, 29, 2, 17, 6]}
ICD = {'תלייה או חנק': ['X70'], 'קפיצה מגובה': ['X80'], 'נשק': ['X72', 'X73', 'X74', 'X74'],
       'הרעלה': ['X61', 'X61', 'X62', 'X64', 'X64', 'X65', 'X68', 'X69'],
       'אחר': ['X71', 'X76', 'X78', 'X78', 'X81', 'X82', 'X83', 'X84', 'Y87.0']}
DISTRICTS = {'ירושלים': 61, 'הצפון': 107, 'חיפה': 101, 'המרכז': 162, 'תל אביב': 112, 'הדרום': 112, 'יהודה ושומרון': 28}
ARAB_DISTRICT_W = {'ירושלים': 13, 'הצפון': 55, 'חיפה': 12, 'המרכז': 10, 'תל אביב': 0, 'הדרום': 10, 'יהודה ושומרון': 0}
TOWNS = {'ירושלים': ['ירושלים'] * 8 + ['בית שמש', 'מבשרת ציון'],
         'הצפון': ['נצרת', 'נוף הגליל', 'עפולה', 'טבריה', 'צפת', 'כרמיאל', 'עכו', 'נהריה', 'קריית שמונה', 'שפרעם', 'סחנין', 'מגדל העמק'],
         'חיפה': ['חיפה'] * 5 + ['קריית ים', 'קריית אתא', 'קריית מוצקין', 'קריית ביאליק', 'חדרה', 'אום אל-פחם', 'טירת כרמל'],
         'המרכז': ['ראשון לציון', 'ראשון לציון', 'פתח תקווה', 'פתח תקווה', 'נתניה', 'נתניה', 'רחובות', 'כפר סבא', 'רעננה',
                   'הוד השרון', 'לוד', 'רמלה', 'יבנה', 'נס ציונה', 'ראש העין', 'מודיעין', 'טייבה'],
         'תל אביב': ['תל אביב-יפו'] * 6 + ['בת ים', 'בת ים', 'חולון', 'חולון', 'רמת גן', 'רמת גן', 'גבעתיים', 'בני ברק', 'הרצליה'],
         'הדרום': ['באר שבע'] * 3 + ['אשדוד'] * 3 + ['אשקלון', 'אשקלון', 'אילת', 'דימונה', 'קריית גת', 'נתיבות', 'אופקים', 'רהט', 'ערד'],
         'יהודה ושומרון': ['מעלה אדומים', 'אריאל', 'ביתר עילית', 'מודיעין עילית']}
RARE_TOWNS = ['מצפה רמון', 'ירוחם', 'מטולה', 'קצרין', 'שלומי']               # 1-3 cases each: must not leave
FIRST = ['דוד', 'משה', 'יוסף', 'אברהם', 'יעקב', 'שרה', 'רחל', 'מרים', 'לאה', 'אחמד', 'מוחמד', 'פאטמה', 'נועה', 'יעל',
         'איתי', 'עומר', 'תמר', 'סרגיי', 'אולגה', 'ולדימיר', 'טטיאנה', 'אברה', 'טגסט']
LAST = ['כהן', 'לוי', 'מזרחי', 'פרץ', 'ביטון', 'דהן', 'אברהם', 'פרידמן', 'אגבאריה', 'חורי', 'גבאי', 'שפירא', 'אזולאי',
        'מלכה', 'איבנוב', 'קוזנצוב', 'טספאי', 'מנגיסטו']
NOTES = ['המשפחה פנתה לסיוע לאחר האירוע', 'אחיו %s נמצא בטיפול', 'גרה לבד, השכן %s הודיע', 'פוטר מעבודתו חודש לפני',
         'בתהליך גירושין מ%s', 'שוחרר מאשפוז פסיכיאטרי', 'חובות כבדים, הוצאה לפועל', 'אמו %s מבקשת ליווי']


def pick(names, weights):
    return random.choices(names, weights=weights)[0]


def death_date(year):
    month = pick(range(1, 13), [w * calendar.monthrange(year, m + 1)[1] / 31.0 for m, w in enumerate(MONTH_W)])
    days = range(1, calendar.monthrange(year, month)[1] + 1)
    day = pick(days, [DAY_W.get(datetime.date(year, month, d).weekday(), 1.0) for d in days])
    return datetime.datetime(year, month, day)


# ---- table 1: the cases -------------------------------------------------------------------------
cases, ids, serial = [], random.sample(range(200000000, 399999999), 5000), 0
for year, (men, women) in PER_YEAR.items():
    people = ['זכר'] * men + ['נקבה'] * women
    random.shuffle(people)
    for n, sex in enumerate(people, start=1):
        serial += 1
        group = 'ערבים' if random.random() < 0.104 else 'יהודים ואחרים'
        gi = pick(range(5), AGE_W[(group, sex)])
        lo, hi = AGE_GROUPS[gi]
        age = random.randint(lo, hi) if gi < 4 else min(97, 75 + int(random.expovariate(1 / 7.0)))
        died = death_date(year)
        born = died - datetime.timedelta(days=int(age * 365.25) + random.randint(0, 364))
        if group == 'ערבים':
            birth, district = 'ישראל', pick(list(ARAB_DISTRICT_W), list(ARAB_DISTRICT_W.values()))
        else:
            district = pick(list(DISTRICTS), list(DISTRICTS.values()))
            fsu = 0.10 if age < 25 else (0.20 if age < 45 else (0.27 if age < 65 else 0.34))     # older immigrants
            eth = 0.05 if age < 35 else 0.012
            birth = pick(['ישראל', 'בריה"מ לשעבר', 'אתיופיה', 'אחר'], [1 - fsu - eth - 0.07, fsu, eth, 0.07])
        aliyah = ''
        if birth != 'ישראל':
            first_year = 1984 if birth == 'אתיופיה' else 1990
            aliyah = random.randint(max(first_year, born.year), max(first_year, min(year, 2020)))
        town = random.choice(TOWNS[district])
        marital = pick(MARITAL, MARITAL_W[gi])
        mw = list(METHOD_W[sex])
        if sex == 'זכר':
            mw[2] = 27 if age < 25 else (14 if age < 45 else 9)                                  # firearm: young men
        method = pick(METHODS, mw)
        prior = random.random() < (0.25 if sex == 'נקבה' else 0.13)
        known = random.random() < ({0: 0.24, 1: 0.26, 2: 0.30, 3: 0.40, 4: 0.46}[gi] + (0.12 if marital == 'גרוש/ה' else 0))
        note = ''
        if random.random() < 0.15:
            note = random.choice(NOTES)
            note = note % random.choice(FIRST) if '%s' in note else note
        cases.append({'key': '%d/%04d' % (year, n), 'id': ids[serial], 'first': random.choice(FIRST), 'last': random.choice(LAST),
                      'sex': sex, 'born': born, 'died': died, 'age': age, 'group': group, 'birth': birth, 'aliyah': aliyah,
                      'marital': marital, 'district': district, 'town': town, 'method': method,
                      'icd': random.choice(ICD[method]), 'prior': prior, 'known': known, 'note': note, 'gi': gi})
for c, town in zip(random.sample([c for c in cases if c['district'] in ('הדרום', 'הצפון')], 10),
                   ['מצפה רמון', 'מצפה רמון', 'ירוחם', 'ירוחם', 'ירוחם', 'מטולה', 'קצרין', 'קצרין', 'שלומי', 'שלומי']):
    c['town'] = town

head = ['מספר מקרה', 'תעודת זהות', 'שם פרטי', 'שם משפחה', 'מגדר', 'תאריך לידה', 'תאריך פטירה', 'גיל', 'קבוצת אוכלוסייה',
        'ארץ לידה', 'שנת עלייה', 'מצב משפחתי', 'מחוז', 'יישוב', 'אופן ביצוע', 'קוד ICD-10', 'ניסיון קודם', 'מוכר לרווחה', 'הערות']
rows = [[c['key'], c['id'], c['first'], c['last'], c['sex'], c['born'], c['died'], c['age'], c['group'], c['birth'], c['aliyah'],
         c['marital'], c['district'], c['town'], c['method'], c['icd'], 'כן' if c['prior'] else 'לא',
         'כן' if c['known'] else 'לא', c['note']] for c in cases]
random.shuffle(rows)
case_sheet = [['משרד הרווחה - מעקב מקרי התאבדות 2014-2023 (נתונים מומצאים לבדיקת תוכנה)'], ['הופק: 11/11/2026'], [], head] + rows
icd_sheet = [['קוד', 'תיאור'], ['X60-X69', 'הרעלה עצמית מכוונת'], ['X70', 'תלייה, חנק'], ['X71', 'טביעה'],
             ['X72-X74', 'נשק חם'], ['X76', 'אש ולהבות'], ['X78', 'חפץ חד'], ['X80', 'קפיצה מגובה'],
             ['X81-X84', 'אמצעים אחרים'], ['Y87.0', 'תוצאה מאוחרת של פגיעה עצמית']]
g.write_workbook(os.path.join(OUT, 'מקרי התאבדות.xlsx'), [('מקרים', case_sheet), ('קודי ICD', icd_sheet)])

# ---- table 2: welfare contacts before the death (only for cases known to the welfare office) ----
SERVICES = ['טיפול משפחתי', 'סיוע כלכלי', 'התמכרויות', 'קשישים', 'נוער וצעירים', 'אלימות במשפחה', 'בריאות הנפש בקהילה']
SERVICE_W = [[14, 10, 14, 0, 46, 8, 8], [26, 22, 18, 0, 6, 14, 14], [22, 28, 16, 2, 0, 12, 20], [10, 16, 4, 52, 0, 4, 14],
             [6, 10, 1, 70, 0, 2, 11]]
workers = [random.choice(FIRST) + ' ' + random.choice(LAST) for _ in range(60)]
liaisons = [random.choice(FIRST) + ' ' + random.choice(LAST) for _ in range(25)]       # header 'איש קשר': NOT caught by the header rules
contacts, cno = [], 700000
for c in cases:
    if not c['known']:
        continue
    risk = pick(['נמוכה', 'בינונית', 'גבוהה'], [50, 33, 17])
    last_gap = random.gammavariate(1.6, {'נמוכה': 150, 'בינונית': 90, 'גבוהה': 35}[risk])   # high risk: seen closer to the death
    service = pick(SERVICES, SERVICE_W[c['gi']])
    when = c['died'] - datetime.timedelta(days=int(last_gap) + 1)
    for i in range(random.choices([1, 2, 3, 5, 8, 12], weights=[22, 24, 20, 18, 11, 5])[0]):
        cno += 1
        contacts.append([cno, c['key'], when, service if random.random() < 0.8 else pick(SERVICES, SERVICE_W[c['gi']]),
                         'לשכת רווחה ' + c['district'], random.choice(workers), random.choice(liaisons),
                         risk if random.random() < 0.85 else pick(['נמוכה', 'בינונית', 'גבוהה'], [50, 33, 17]),
                         random.choice(['פגישה', 'פגישה', 'שיחת טלפון', 'ביקור בית', 'ועדה'])])
        when = when - datetime.timedelta(days=int(random.gammavariate(1.5, 60)) + 1)
random.shuffle(contacts)
g.write_workbook(os.path.join(OUT, 'פניות לרווחה.xlsx'),
                 [('פניות', [['מספר פנייה', 'מספר מקרה', 'תאריך פנייה', 'סוג שירות', 'מחלקה', 'עובד סוציאלי', 'איש קשר',
                              'רמת סיכון', 'סוג מגע']] + contacts)])

# ---- table 3: earlier attempts treated in an emergency room (CSV, text dates) --------------------
HOSPITALS = ['איכילוב', 'שיבא', 'רמב"ם', 'סורוקה', 'הדסה עין כרם', 'שערי צדק', 'בילינסון', 'וולפסון', 'ברזילי', 'העמק',
             'זיו', 'הלל יפה', 'מאיר', 'קפלן', 'פוריה']
n_att = 0
with open(os.path.join(OUT, 'ניסיונות קודמים.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['מספר מקרה', 'תאריך ניסיון', 'אופן', 'בית חולים', 'אושפז'])
    for c in cases:
        if not c['prior']:
            continue
        for _ in range(random.choices([1, 2, 3, 4], weights=[62, 23, 10, 5])[0]):
            n_att += 1
            when = c['died'] - datetime.timedelta(days=random.randint(10, 5 * 365))
            how = pick(['הרעלה', 'חתך', 'תלייה או חנק', 'קפיצה מגובה', 'אחר'], [80, 6, 8, 4, 2] if c['sex'] == 'זכר' else [89, 4, 4, 2, 1])
            w.writerow([c['key'], when.strftime('%d/%m/%Y'), how, random.choice(HOSPITALS),
                        'כן' if random.random() < (0.72 if c['age'] >= 65 else 0.48) else 'לא'])

print('INVENTED "premises" folder: %s' % OUT)
print('  מקרי התאבדות.xlsx    : %d cases (2014-2023, yearly totals by sex as published) + a small ICD sheet' % len(cases))
print('  פניות לרווחה.xlsx    : %d welfare contacts of %d cases' % (len(contacts), sum(1 for c in cases if c['known'])))
print('  ניסיונות קודמים.csv  : %d earlier attempts of %d cases' % (n_att, sum(1 for c in cases if c['prior'])))
