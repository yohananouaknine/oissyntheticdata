"""suicide_analysis.py -- "my own script" for the INVENTED suicide-cases folder.

    python demo_suicide/suicide_analysis.py demo_suicide/home        (synthetic files: rehearsal)
    python demo_suicide/suicide_analysis.py demo_suicide/premises    (the invented "real" files)

Standard library + gov_one.py only.  Writes results/suicide_report.html in that folder.
Counts below 5 are shown as "<5", so the page itself could leave the premises.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gov_one as g

FOLDER = sys.argv[1] if len(sys.argv) > 1 else '.'
T = g.open_tables(FOLDER)
cases, contacts, attempts = T['מקרי התאבדות'].rows, T['פניות לרווחה'].rows, T['ניסיונות קודמים'].rows
rep = g.Report('Suicide cases followed by a welfare unit (invented data): eight questions')

# Published: Ministry of Health, "Suicidality in Israel, suicides 2000-2023", from the CBS cause-of-death files
PUBLISHED = {2014: (301, 89), 2015: (283, 80), 2016: (329, 71), 2017: (309, 100), 2018: (360, 97),
             2019: (340, 96), 2020: (351, 100), 2021: (321, 106), 2022: (330, 99), 2023: (331, 102)}
BANDS = [(15, 24, '15-24'), (25, 44, '25-44'), (45, 64, '45-64'), (65, 74, '65-74'), (75, 200, '75+')]


def band(row):
    age = g.to_num(row.get('גיל', ''))
    for lo, hi, name in BANDS:
        if age is not None and lo <= age <= hi:
            return name
    return ''


def pct(a, b):
    return '%.1f%%' % (100.0 * a / b) if b else ''


def days(row, later, earlier):
    a, b = g.to_date(row.get(later, '')), g.to_date(row.get(earlier, ''))
    return (a - b).days if a and b else None


for r in cases:
    r['קבוצת גיל'] = band(r)
    r['שנה'] = g.month_key(r['תאריך פטירה'])[:4]

# ---- 0. the data and its links -------------------------------------------------------------------
case_of = {r['מספר מקרה']: r for r in cases}
contacts = g.join(contacts, cases, on='מספר מקרה')
attempts = g.join(attempts, cases, on='מספר מקרה')
rep.h('0. Data')
late_c = sum(1 for r in contacts if (days(r, 'תאריך פנייה', 'תאריך פטירה') or 0) > 0)
late_a = sum(1 for r in attempts if (days(r, 'תאריך ניסיון', 'תאריך פטירה') or 0) > 0)
rep.table(['Table', 'Rows', 'Linked to a case', 'Dated after the death'],
          [['cases', len(cases), '', ''],
           ['welfare contacts', len(contacts), sum(1 for r in contacts if r['מספר מקרה'] in case_of), late_c],
           ['earlier attempts', len(attempts), sum(1 for r in attempts if r['מספר מקרה'] in case_of), late_a]])

# ---- 1. cases per year and sex, next to the published national numbers ---------------------------
rep.h('1. Cases per year and sex')
rl, cl, counts = g.crosstab(cases, 'שנה', 'מגדר')
by_year = {y: dict(zip(cl, row)) for y, row in zip(rl, counts)}
lines = []
for y in sorted(by_year):
    m, f = by_year[y].get('זכר', 0), by_year[y].get('נקבה', 0)
    pub = PUBLISHED.get(int(y)) if y.isdigit() else None
    lines.append([y, m, f, m + f, pct(m, m + f), sum(pub) if pub else '', pct(pub[0], sum(pub)) if pub else ''])
rep.table(['year', 'men', 'women', 'all', 'men %', 'published: all', 'published: men %'], lines)
years = [l[0] for l in lines]
rep.line(years, {'this file': [l[3] for l in lines], 'published': [l[5] if l[5] != '' else None for l in lines]},
         title='Cases per year: this file and the published national count')

# ---- 2. age and sex ------------------------------------------------------------------------------
rep.h('2. Age band by sex')
names = [b[2] for b in BANDS]
rows2 = []
for sex in ('זכר', 'נקבה'):
    grp = [r for r in cases if r['מגדר'] == sex]
    rows2.append([sex, len(grp)] + [pct(sum(1 for r in grp if r['קבוצת גיל'] == n), len(grp)) for n in names])
rep.table(['sex', 'cases'] + names, rows2)
rep.note('Published for 2021-2023: 14-15% under 25, about a third aged 25-44, 26-28% aged 45-64, about a quarter 65 and over.')

# ---- 3. method by sex ----------------------------------------------------------------------------
rep.h('3. Method by sex')
rl, cl, counts = g.crosstab(cases, 'אופן ביצוע', 'מגדר')
tot = [sum(row[j] for row in counts) for j in range(len(cl))]
rep.table(['method'] + ['%s: n' % c for c in cl] + ['%s: %%' % c for c in cl],
          [[a] + [g.safe(x) for x in row] + [pct(x, t) for x, t in zip(row, tot)] for a, row in zip(rl, counts)])
t3 = g.chi_square(counts)
rep.p('chi-square = %s, df = %d, p %s, Cramer V = %s.' % (g.fmt(t3['chi2']), t3['df'], g.fmt_p(t3['p']), g.fmt(t3['cramers_v'])))
rep.note('Published for 2021-2023: men 55% hanging, 20% jumping, 13% firearm, 5% poisoning; women 46%, 29%, 2%, 17%.')
young = [r for r in cases if r['מגדר'] == 'זכר' and r['קבוצת גיל'] == '15-24']
older = [r for r in cases if r['מגדר'] == 'זכר' and r['קבוצת גיל'] not in ('15-24', '')]
t3b = g.proportion_test(sum(1 for r in young if r['אופן ביצוע'] == 'נשק'), len(young),
                        sum(1 for r in older if r['אופן ביצוע'] == 'נשק'), len(older))
if 'ci95' in t3b:
    rep.p('Firearm among men: %s aged 15-24 against %s of older men; difference %s (95%% interval %s to %s), p %s.' % (
        pct(t3b['p1'], 1), pct(t3b['p2'], 1), pct(t3b['diff'], 1), pct(t3b['ci95'][0], 1), pct(t3b['ci95'][1], 1), g.fmt_p(t3b['p'])))

# ---- 4. population group and age -----------------------------------------------------------------
rep.h('4. Population group: share of cases under 45')
grp4 = {}
for r in cases:
    if r['קבוצת גיל']:
        d = grp4.setdefault(r['קבוצת אוכלוסייה'], [0, 0])
        d[0] += r['קבוצת גיל'] in ('15-24', '25-44')
        d[1] += 1
rep.table(['group', 'cases', 'under 45', '%'], [[a, d[1], d[0], pct(d[0], d[1])] for a, d in grp4.items()])
if 'ערבים' in grp4 and 'יהודים ואחרים' in grp4:
    t4 = g.proportion_test(grp4['ערבים'][0], grp4['ערבים'][1], grp4['יהודים ואחרים'][0], grp4['יהודים ואחרים'][1])
    rep.p('Difference %s (95%% interval %s to %s), p %s.  Published: 72%% against 46%%.' % (
        pct(t4['diff'], 1), pct(t4['ci95'][0], 1), pct(t4['ci95'][1], 1), g.fmt_p(t4['p'])))

# ---- 5. month of the year and day of the week ----------------------------------------------------
rep.h('5. Season and day of the week')
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
LENGTH = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
per_month, weekend, dated = [0] * 12, 0, 0
for r in cases:
    d = g.to_date(r['תאריך פטירה'])
    if d:
        per_month[d.month - 1] += 1
        weekend += d.weekday() in (4, 5)
        dated += 1
expected = [dated * L / sum(LENGTH) for L in LENGTH]
chi5 = sum((o - e) ** 2 / e for o, e in zip(per_month, expected)) if dated else 0.0
rep.bars({m: round(o * 31.0 / L) for m, o, L in zip(MONTHS, per_month, LENGTH)}, title='Cases per month of the year, as if every month had 31 days')
rep.p('Against an even spread over the year: chi-square = %s, df = 11, p %s.' % (g.fmt(chi5), g.fmt_p(g.p_chi2(chi5, 11))))
if dated:
    p0, ph = 2 / 7.0, weekend / float(dated)
    z = (ph - p0) / (p0 * (1 - p0) / dated) ** 0.5
    rep.p('Friday and Saturday hold %s of the cases (an even spread would give 28.6%%); z = %s, p %s.' % (pct(weekend, dated), g.fmt(z), g.fmt_p(g.p_normal(z))))

# ---- 6. who was known to the welfare office? ------------------------------------------------------
rep.h('6. Known to the welfare office before the death')
rows6 = []
for n in names:
    grp = [r for r in cases if r['קבוצת גיל'] == n]
    rows6.append([n, len(grp), pct(sum(1 for r in grp if r['מוכר לרווחה'] == 'כן'), len(grp))])
rep.table(['age band', 'cases', 'known to welfare'], rows6)
div = [r for r in cases if r['מצב משפחתי'] == 'גרוש/ה']
oth = [r for r in cases if r['מצב משפחתי'] not in ('גרוש/ה', '')]
t6 = g.proportion_test(sum(1 for r in div if r['מוכר לרווחה'] == 'כן'), len(div), sum(1 for r in oth if r['מוכר לרווחה'] == 'כן'), len(oth))
if 'ci95' in t6:
    rep.p('Divorced: %s known, others: %s; difference %s (95%% interval %s to %s), p %s.' % (
        pct(t6['p1'], 1), pct(t6['p2'], 1), pct(t6['diff'], 1), pct(t6['ci95'][0], 1), pct(t6['ci95'][1], 1), g.fmt_p(t6['p'])))
prior = {s: [r for r in cases if r['מגדר'] == s] for s in ('זכר', 'נקבה')}
rep.p('An attempt in the five years before: %s of the men, %s of the women.  Published: about 16%% of all cases.' % (
    pct(sum(1 for r in prior['זכר'] if r['ניסיון קודם'] == 'כן'), len(prior['זכר'])),
    pct(sum(1 for r in prior['נקבה'] if r['ניסיון קודם'] == 'כן'), len(prior['נקבה']))))

# ---- 7. the welfare contacts: how long before the death was the last one? ------------------------
rep.h('7. Days from the last welfare contact to the death, by risk level')
last = {}
for r in contacts:
    d = days(r, 'תאריך פטירה', 'תאריך פנייה')
    if d is not None and d >= 0 and (r['מספר מקרה'] not in last or d < last[r['מספר מקרה']][0]):
        last[r['מספר מקרה']] = (d, r['רמת סיכון'])
by_risk = {}
for d, risk in last.values():
    by_risk.setdefault(risk, []).append(d)
rows7 = []
for risk in ('נמוכה', 'בינונית', 'גבוהה'):
    d = g.describe(by_risk.get(risk, []))
    rows7.append([risk, d['n'], d.get('median'), d.get('p25'), d.get('p75')])
rep.table(['risk level at the last contact', 'cases', 'median days', '25%', '75%'], rows7)
if by_risk.get('גבוהה') and by_risk.get('נמוכה'):
    t7 = g.mann_whitney(by_risk['גבוהה'], by_risk['נמוכה'])
    rep.p('High against low risk (Mann-Whitney): p %s; a high-risk case was seen closer to the death in %s of the pairs.' % (
        g.fmt_p(t7['p']), pct(1 - t7['prob_a_above_b'], 1)))
for r in contacts:
    r['קבוצת גיל'] = band(r)
rl, cl, counts = g.crosstab(contacts, 'קבוצת גיל', 'סוג שירות')
t7b = g.chi_square(counts)
rep.table(['age band'] + cl, [[a] + [g.safe(x) for x in row] for a, row in sorted(zip(rl, counts))],
          caption='Welfare contacts: type of service by age band of the case')
rep.p('chi-square = %s, df = %d, p %s, Cramer V = %s.' % (g.fmt(t7b['chi2']), t7b['df'], g.fmt_p(t7b['p']), g.fmt(t7b['cramers_v'])))

# ---- 8. month by month: did the level change in March 2020? --------------------------------------
rep.h('8. Cases per month, with a break at 2020-03')
months, series = g.monthly_counts(cases, 'תאריך פטירה')
if '2020-03' in months and len(months) >= 36:
    fit = g.its(series['all'], months.index('2020-03'), hac_lags=6)
    if 'error' not in fit:
        est, low, high, p = fit['level_change']
        rep.line(months, {'cases': series['all'], 'fitted': fit['fitted']}, title='Cases per month', mark='2020-03')
        rep.p('Change in the monthly level at 2020-03: %s (95%% interval %s to %s), p %s.' % (g.fmt(est), g.fmt(low), g.fmt(high), g.fmt_p(p)))

rep.save(os.path.join(FOLDER, 'results', 'suicide_report.html'))
