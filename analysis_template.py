"""analysis_template.py -- the starting point for YOUR analysis script.

    python analysis_template.py [folder]

The same script runs unchanged in both places:
  * at home, the folder holds only synthetic files  -> it uses them and stamps the report "synthetic";
  * on the premises, the folder holds the real files -> it uses those.
It needs only gov_one.py next to it.  No other package, no internet.

Parts 1-3 work on any folder and give a first look.  Part 4 is where you write your own statistics;
the examples there show every tool in gov_one (g.describe, g.crosstab, g.chi_square, g.t_test,
g.mann_whitney, g.pearson, g.spearman, g.proportion_test, g.ols, g.its, g.monthly_counts, g.join).
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gov_one as g

FOLDER = sys.argv[1] if len(sys.argv) > 1 else '.'
T = g.open_tables(FOLDER)                      # {table name: Table}; real files win over synthetic ones
rep = g.Report('First look at the data')

# ---- 1. what is there ---------------------------------------------------------------------------
rep.h('Tables')
rep.table(['Table', 'File', 'Rows', 'Columns'], [[t.name, t.file, len(t), len(t.header)] for t in T.values()])

# ---- 2. every column of every table -------------------------------------------------------------
# Values are listed only for columns with few distinct values, and never below 5 rows, so this
# page does not show a person even when it is built from real files.
for t in T.values():
    rep.h(t.name)
    lines = []
    for c in t.header:
        vals = [v for v in t.col(c) if not g.is_missing(v)]
        nums, dates = t.nums(c), t.dates(c)
        miss = '%.0f%%' % (100.0 * (len(t) - len(vals)) / len(t)) if len(t) else ''
        distinct = len(set(vals))
        if not vals:
            kind, detail = 'empty', ''
        elif len(dates) >= 0.9 * len(vals):
            kind, detail = 'date', '%s to %s' % (min(dates).strftime('%Y-%m'), max(dates).strftime('%Y-%m'))
        elif len(nums) >= 0.9 * len(vals) and distinct > 12:
            d = g.describe(nums)
            kind, detail = 'number', 'mean %s, median %s, middle half %s to %s' % (
                g.fmt(d['mean']), g.fmt(d['median']), g.fmt(d['p25']), g.fmt(d['p75']))
        elif distinct <= 12:
            top = [(a, n) for a, n in g.count_by([{'v': v} for v in vals], 'v').items() if n >= 5][:6]
            kind, detail = 'category', ', '.join('%s (%s)' % (a, g.fmt(n)) for a, n in top)
        else:
            kind, detail = 'text / id', '%s distinct values' % g.fmt(distinct)
        lines.append([c, kind, miss, detail])
    rep.table(['Column', 'Kind', 'Empty', 'Summary'], lines)

    # ---- 3. rows per month for the first date column ------------------------------------------
    for c in t.header:
        vals = [v for v in t.col(c) if not g.is_missing(v)]
        if vals and len(t.dates(c)) >= 0.9 * len(vals):
            months, series = g.monthly_counts(t.rows, c)
            if len(months) >= 6:
                rep.line(months, {'rows per month': series['all']}, title='%s: rows per month by %s' % (t.name, c))
            break

# ---- 4. YOUR ANALYSIS ---------------------------------------------------------------------------
# Replace the names in capitals with your own table and column names, and delete what you do not need.
#
#   cases = T['CASES'].rows                                     # a list of rows; row['COLUMN'] is text
#
#   # join a table to its parent (the link is listed in to_send/profile_summary.md)
#   cases = g.join(cases, T['CLIENTS'].rows, on='CLIENT ID')    # now every case row also has the client's columns
#
#   # two categories: are they related?
#   rl, cl, counts = g.crosstab(cases, 'DISTRICT', 'CASE TYPE')
#   test = g.chi_square(counts)
#   rep.h('Case type by district')
#   rep.table(['district'] + cl, [[a] + row for a, row in zip(rl, counts)])
#   rep.p('chi-square = %s, df = %d, p %s, Cramer V = %s' % (g.fmt(test['chi2']), test['df'], g.fmt_p(test['p']), g.fmt(test['cramers_v'])))
#
#   # a number in two groups
#   a = [g.to_num(r['AMOUNT']) for r in cases if r['GENDER'] == 'A' and g.to_num(r['AMOUNT']) is not None]
#   b = [g.to_num(r['AMOUNT']) for r in cases if r['GENDER'] == 'B' and g.to_num(r['AMOUNT']) is not None]
#   test = g.t_test(a, b)            # or g.mann_whitney(a, b) when the numbers are very skewed
#   rep.p('difference %s (95%% interval %s to %s), p %s' % (g.fmt(test['diff']), g.fmt(test['ci95'][0]), g.fmt(test['ci95'][1]), g.fmt_p(test['p'])))
#
#   # before / after a date, month by month (interrupted time series)
#   months, series = g.monthly_counts(cases, 'OPENED')
#   k = months.index('2024-01')                                 # the first month "after"
#   fit = g.its(series['all'], k, hac_lags=6)
#   rep.line(months, {'cases': series['all'], 'model': fit['fitted']}, title='Cases per month', mark='2024-01')
#   est, low, high, p = fit['level_change']
#   rep.p('change in level at 2024-01: %s (95%% interval %s to %s), p %s' % (g.fmt(est), g.fmt(low), g.fmt(high), g.fmt_p(p)))
#
#   # a regression with several predictors
#   y = [...]; X = [[x1, x2], ...]                              # one row of predictors per value of y
#   fit = g.ols(y, X, names=['x1', 'x2'])
#   rep.table(['term', 'b', 'se', 't', 'p'], [[n, b, s, t, g.fmt_p(p)] for n, b, s, t, p in zip(fit['names'], fit['coef'], fit['se'], fit['t'], fit['p'])])

rep.save(os.path.join(FOLDER, 'results', 'report.html'))
