# oissyntheticdata (gov_one)

One file, `gov_one.py`. Python standard library only: no other package, no internet.
Tested on Python 3.15 (Windows), on invented data only.

It follows one flow, for any office whose data is a folder of Excel / CSV files:
profile the folder on the premises → aggregate-only JSON leaves → synthetic files are rebuilt at home →
you write your statistics script on them → the same script runs on the real files on the premises.

## Install (at home)

```
pip install oissyntheticdata
```

This gives the module `gov_one`, the same module under the name `oissyntheticdata`, and the commands
`oissyntheticdata`, `oissd` and `gov_one` (all three are `python gov_one.py`).

On the premises nothing is installed. Copy the two files you need out of the installation:

```
oissyntheticdata export my_usb_folder
```

It writes `gov_one.py` and `analysis_template.py` there. Carry those in.

**Version 3 is a different tool from 2.x.** The four-stage commands of 2.2.0 (`add-month`, `profile`,
`synthesize`, `compare`) and its `profile()` / `synthesize()` / `compare()` functions are gone, and
profiles written by 2.x are not read. To keep them: `pip install "oissyntheticdata<3"`.

## The flow

### 1. On the premises: profile the folder

Copy `gov_one.py` into the folder with the Excel / CSV files and run:

```
python gov_one.py
```

It reads every `.xlsx` / `.xlsm` / `.csv` file (every sheet), finds how the tables link to each other, and
writes a `to_send` folder: one `profile_<table>.json` per table, `schema.json` (the links) and
`profile_summary.md`.

**Read `profile_summary.md` before anything is sent.** It lists, column by column, what leaves.

To look first without writing anything: `python gov_one.py check`

### 2. The office e-mails you the `to_send` folder

### 3. At home: build synthetic files and write your script

Put `gov_one.py` next to the `to_send` folder and run the same command (or run `oissyntheticdata` there):

```
python gov_one.py
```

It finds only JSON, so it writes `synthetic\synthetic_<file>.xlsx / .csv`: same file names, sheets, headers,
row counts, links between tables, and similar distributions. Every value is invented.

Copy `analysis_template.py`, write your statistics in part 4, and run it on the folder:

```
python analysis_template.py .
```

It writes `results\report.html` (one offline page, stamped "Synthetic test data — not findings").

Write `import gov_one as g` in your script, not `import oissyntheticdata`: that line works in both places.

### 4. Back on the premises: run the same script on the real files

Bring `gov_one.py` and your script, put them in the folder with the real files, and run the script.
Real files win over synthetic ones automatically; the report loses the synthetic stamp.

## What leaves the premises, and what does not

| In the data | In the JSON |
|---|---|
| Id numbers, names, phones, addresses, e-mail, free text (by header) | shape only: length and letters / digits |
| Key columns (case number, client number) | counts only: how many, how many rows per key |
| Categories (district, status, type) | labels + counts; a label seen fewer than 5 times loses its name |
| Numbers | 9 rounded quantiles, mean, spread |
| Dates | counts per month and per day of the week; never the day itself |
| Two columns together | joint counts for pairs that pass a significance test; a cell below 5 is dropped, and one more cell is dropped when the hidden remainder could be found by subtraction |
| Two dates (opened → closed; a date in a linked table) | rounded quantiles of the days between them |
| Linked tables | how many rows per key, and what share of the parent rows have any |
| Rules | "column A is empty when column B is X"; "age = years between two dates" |
| A table with fewer than 20 rows | shape only |

No row is copied. The minimum count is 5; change it with `--k 10`.

A column that is **labels + counts** sends its values as written. If such a column holds names of people
under a header the tool did not recognise, hide it (next section). This is the one thing to check by eye.
The summary marks columns whose labels look like names of people, but that mark is a guess, not a guarantee.

## Settings (optional)

`python gov_one.py settings` writes `gov_one_settings.json` next to the data. Edit it and profile again.

| Key | Use |
|---|---|
| `hide` | headers to describe by shape only |
| `show` | headers the tool hid that are safe to summarise |
| `public_tables` | small lookup tables (e.g. list of districts) to copy as they are |
| `links` | a link the tool missed: `"payments::client = clients::client_id"` |
| `no_links` | a link the tool found that is not one |
| `skip_files` | files to leave out |
| `min_cell` | the minimum count |

## The toolbox for your script (`import gov_one as g`)

| Need | Call |
|---|---|
| Open the folder | `T = g.open_tables(folder)` → `T['name'].rows`, `.col(c)`, `.nums(c)`, `.dates(c)` |
| Convert a cell | `g.to_num(v)`, `g.to_date(v)`, `g.month_key(v)` |
| Group and link | `g.count_by`, `g.group_by`, `g.join(rows, parent_rows, on=...)`, `g.monthly_counts` |
| Describe | `g.describe`, `g.quantile`, `g.crosstab` |
| Tests | `g.chi_square`, `g.t_test` (Welch), `g.mann_whitney`, `g.proportion_test`, `g.pearson`, `g.spearman` |
| Models | `g.ols` (classical or Newey-West errors), `g.its` (interrupted time series) |
| Report | `rep = g.Report(title)`; `rep.h`, `rep.p`, `rep.note`, `rep.table`, `rep.line`, `rep.bars`, `rep.save` |
| Small cells in your own output | `g.safe(n)` shows `<5` instead of a small count |

Anything else you need, write in plain Python in your script. Do not import another package.

## How the synthetic files keep their shape

Each column is drawn given one other column it depends on most (a tree over the columns), and, where a
second column still tells something once the first is accounted for, given that one too. The two joint
tables are combined so that the synthetic file agrees with both. Nothing beyond two-column counts is
ever written to the JSON.

## The demos

Both demos are invented from the first row to the last. The scripts that invent the data and analyse it
are in the source archive (`demo\`, `demo_suicide\`); the data folders are made by running them.
A synthetic result tells you the script runs and the output looks right. It is never a finding.

### An invented welfare office

`demo\make_demo_data.py` writes 3 files (4 tables) into `demo\premises`. `demo\demo_analysis.py` asks four
questions. The same script on both sides:

| Question | Synthetic | "Real" |
|---|---|---|
| Case type by district (two tables joined) | Cramér V 0.11, p < .001 | Cramér V 0.10, p < .001 |
| Median days open, youth-at-risk cases | 48 | 47 |
| Jump in monthly youth-at-risk cases at 2024-01 | +18.9 a month | +17.9 a month |
| Extra amount for financial-aid payments | +575 | +613 |
| Days open before vs after 2024-01, youth-at-risk only | +0.1 (not significant) | −42.9 (p < .001) |

The last line is the limit to remember: an effect that exists in one sub-group only is not reproduced.

### Invented suicide cases followed by a welfare unit

`demo_suicide\make_suicide_data.py` invents 4,195 cases for 2014-2023, their welfare contacts and earlier
attempts (3 files, 4 tables). Only the proportions follow the Ministry of Health report "Suicidality in
Israel, suicides 2000-2023", which is built on the CBS cause-of-death files (ICD-10 X60-X84, Y87.0):
cases per year and sex, age, population group, marital status, method, month.
`demo_suicide\suicide_analysis.py` asks eight questions.

| Question | Synthetic | Invented "real" |
|---|---|---|
| Cases in 2014 / 2018 / 2023 | 402 / 458 / 424 | 390 / 457 / 433 |
| Method by sex | Cramér V 0.23 | Cramér V 0.25 |
| Friday and Saturday share of cases | 25.9% | 24.6% |
| Known to welfare, age 15-24 / 75+ | 25.3% / 51.5% | 24.6% / 46.0% |
| Earlier attempt, men / women | 11.7% / 29.1% | 12.7% / 25.1% |
| Median days from last contact to death, high / low risk | 77 / 160 | 54 / 177 |
| Contacts or attempts dated after the death | 0 | 0 |
| Arab cases under 45 | 65.0% | 73.1% |
| Known to welfare: divorced minus others | +7.0 points (p < .001) | +8.6 points (p < .001) |

The last two lines are what the second column buys: when each column followed one other column only, they
were 51.6% and +1.9 points (not significant).

## The same tool in R

`gov_one.R` is the R twin, in base R only. It writes the same JSON files: a profile made with R can be
turned into synthetic files with Python, and the other way round. It is the R package `oissyntheticdata`,
at <https://github.com/yohananouaknine/oissyntheticdata-r>.

## Limits

- An effect that exists in one sub-group only (a three-way pattern) is not reproduced. See the welfare demo.
- A column follows two other columns at most, and the second is added only when a test finds it. A weak
  pattern spread over many values can be missed.
- Synthetic distributions are close, not equal: see the tables above for how far they sit from the "real" side.
- Links between tables are found by matching values. Check the list in `profile_summary.md`; fix it with `links` / `no_links`.
- Hiding personal columns relies on the header. A names column under an unusual header must be added to `hide`.
- The header must be one row. Titles above it are skipped; merged or two-level headers and total rows are not handled.
- `.xls` and `.xlsb` are not read: save them as `.xlsx` first.
- The synthetic `.xlsx` files were read back by the tool itself; they were not opened in Excel during testing.
- Not yet run on real ministry files, and only on Python 3.15.
