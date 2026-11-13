"""demo_analysis.py -- an example of "my own script" for the pretend welfare office.

    python demo/demo_analysis.py demo/home        (synthetic files: rehearsal)
    python demo/demo_analysis.py demo/premises    (the "real" files)

It asks four questions with gov_one's statistics and writes results/demo_report.html in that folder.
The same file runs in both places; only the data differ.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gov_one as g

FOLDER = sys.argv[1] if len(sys.argv) > 1 else '.'
T = g.open_tables(FOLDER)
clients, cases, payments = T['לקוחות'].rows, T['תיקים'].rows, T['תשלומים'].rows
rep = g.Report('Welfare office (demo): four questions')

# every case row gets the columns of its client; every payment row the columns of its case
cases = g.join(cases, clients, on='מספר לקוח')
payments = g.join(payments, cases, on='מספר תיק')
rep.h('Data')
rep.table(['Table', 'Rows'], [['clients', len(clients)], ['cases', len(cases)], ['payments', len(payments)]])
matched = sum(1 for r in cases if r.get('מחוז'))
rep.p('%s of %s cases were matched to a client; %s of %s payments were matched to a case.' % (
    g.fmt(matched), g.fmt(len(cases)), g.fmt(sum(1 for r in payments if r.get('סוג תיק'))), g.fmt(len(payments))))

# ---- 1. is the type of case related to the client's district? (two tables, chi-square) -----------
rl, cl, counts = g.crosstab(cases, 'מחוז', 'סוג תיק')
test = g.chi_square(counts)
rep.h('1. Case type by district')
rep.table(['district'] + cl + ['all'], [[a] + [g.safe(x) for x in row] + [sum(row)] for a, row in zip(rl, counts)])
rep.p('chi-square = %s, df = %d, p %s, Cramer V = %s.' % (g.fmt(test['chi2']), test['df'], g.fmt_p(test['p']), g.fmt(test['cramers_v'])))

# ---- 2. how long does a case stay open, by type? (durations) ------------------------------------
rep.h('2. Days from opening to closing, by case type')
lines, waits = [], {}
for ctype, rows in sorted(g.group_by(cases, 'סוג תיק').items()):
    days = [(g.to_date(r['תאריך סגירה']) - g.to_date(r['תאריך פתיחה'])).days for r in rows
            if g.to_date(r['תאריך סגירה']) and g.to_date(r['תאריך פתיחה'])]
    waits[ctype] = days
    d = g.describe(days)
    lines.append([ctype, d['n'], d.get('mean'), d.get('median'), d.get('p25'), d.get('p75')])
rep.table(['case type', 'closed cases', 'mean days', 'median', '25%', '75%'], lines)
rep.bars({a: g.describe(b).get('median', 0) for a, b in waits.items()}, title='Median days open')

# ---- 3. did the wait for youth-at-risk cases change in January 2024? (two groups + time series) --
rep.h('3. Youth-at-risk cases before and after 2024-01')
youth = [r for r in cases if r['סוג תיק'] == 'נוער בסיכון' and g.to_date(r['תאריך סגירה'])]
before = [(g.to_date(r['תאריך סגירה']) - g.to_date(r['תאריך פתיחה'])).days for r in youth if g.month_key(r['תאריך פתיחה']) < '2024-01']
after = [(g.to_date(r['תאריך סגירה']) - g.to_date(r['תאריך פתיחה'])).days for r in youth if g.month_key(r['תאריך פתיחה']) >= '2024-01']
tt, mw = g.t_test(after, before), g.mann_whitney(after, before)
rep.table(['opened', 'cases', 'mean days', 'median days'],
          [['before 2024-01', len(before), g.describe(before).get('mean'), g.describe(before).get('median')],
           ['from 2024-01', len(after), g.describe(after).get('mean'), g.describe(after).get('median')]])
if 'ci95' in tt:
    rep.p('Difference in mean days: %s (95%% interval %s to %s); Welch t = %s, p %s; Mann-Whitney p %s.' % (
        g.fmt(tt['diff']), g.fmt(tt['ci95'][0]), g.fmt(tt['ci95'][1]), g.fmt(tt['t']), g.fmt_p(tt['p']), g.fmt_p(mw['p'])))
months, series = g.monthly_counts([r for r in cases if r['סוג תיק'] == 'נוער בסיכון'], 'תאריך פתיחה')
if '2024-01' in months and len(months) >= 24:
    fit = g.its(series['all'], months.index('2024-01'), hac_lags=6)
    if 'error' not in fit:
        est, low, high, p = fit['level_change']
        rep.line(months, {'cases opened': series['all'], 'fitted': fit['fitted']}, title='Youth-at-risk cases opened per month', mark='2024-01')
        rep.p('Interrupted time series: change in monthly level at 2024-01 = %s (95%% interval %s to %s), p %s.' % (
            g.fmt(est), g.fmt(low), g.fmt(high), g.fmt_p(p)))

# ---- 4. what explains the amount of a payment? (three tables, regression) -----------------------
rep.h('4. Payment amount')
y, X = [], []
for r in payments:
    amount, kids = g.to_num(r['סכום']), g.to_num(r.get('מספר ילדים', ''))
    if amount is None or kids is None or not r.get('סוג תיק'):
        continue
    y.append(amount)
    X.append([1.0 if r['סוג תיק'] == 'סיוע כלכלי' else 0.0, 1.0 if r['סוג תשלום'] == 'חירום' else 0.0, kids])
fit = g.ols(y, X, names=['case type = financial aid', 'payment type = emergency', 'number of children'])
if 'error' not in fit:
    rep.table(['term', 'b', 'se', 't', 'p'], [[n, b, s, t, g.fmt_p(p)] for n, b, s, t, p in
                                                zip(fit['names'], fit['coef'], fit['se'], fit['t'], fit['p'])],
              caption='Linear regression of the amount, n = %s, R² = %s' % (g.fmt(fit['n']), g.fmt(fit['r2'])))
kids = [g.to_num(r['מספר ילדים']) for r in clients]
income = [g.to_num(r['הכנסה חודשית']) for r in clients]
pairs = [(a, b) for a, b in zip(kids, income) if a is not None and b is not None]
sp = g.spearman([a for a, _ in pairs], [b for _, b in pairs])
rep.p('Clients: rank correlation between number of children and monthly income = %s (n = %s, p %s).' % (
    g.fmt(sp['rho']), g.fmt(sp['n']), g.fmt_p(sp['p'])))

rep.save(os.path.join(FOLDER, 'results', 'demo_report.html'))
