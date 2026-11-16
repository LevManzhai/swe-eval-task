# Notes

## Why there's a second version

The first version ([`../tomlkit-out-of-order-tables`](../tomlkit-out-of-order-tables))
ended at 2 passes out of 3. The attempt that failed was a serious one; it
missed exactly one bug, an indented header four levels deep, because its random
generator never produced that shape. The other two were luckier with their
generators.

From that I concluded the task design works: one symptom in the report, a
clear contract, and several hidden bugs in one area. What it needs is more
bugs whose triggers are unusual shapes or operations, so that there are more
of them for a fuzzer to miss.

## Where the bugs come from

- Repo: https://github.com/python-poetry/tomlkit, base commit `7bf7284`
  (13 November 2026).
- Eight fixes are reverted (code, the tests they added, and their changelog
  lines). They're listed in the [README](README.md). I picked them by one
  rule: they had to touch the same area (document structure: split tables,
  arrays of tables, dotted keys, inline tables) and they had to revert
  cleanly together. Three more that I wanted (`6b5f079`, `495a42e`,
  `e23a254`) conflict with code that changed afterwards, so I left them out.
- After the revert, the library's whole suite passes (1,389 tests), so it
  doesn't hint at anything.

## What changed compared with the first version

- The statement covers the whole structure area, not just split tables, and
  explicitly includes the list-like interface of arrays of tables (slices,
  `del`, `append()`, `insert()`). Without that, bug 6 wouldn't be covered by
  the contract.
- The rule for validity and data is now worded through the TOML 1.0
  specification rather than "what `tomllib` does". In these cases the two are
  the same, and the hidden tests still use `tomllib` as the oracle.
- It includes the sentence added after the first version's first attempt:
  where the existing tests pin down behaviour, keep it.

**One thing I tried and dropped.** I wanted to run the task on Python 3.10,
which has no `tomllib`, to take away the oracle all the attempts were using.
It doesn't work. On 3.10, pytest itself depends on `tomli` (the package
`tomllib` came from), and two more copies are vendored inside pip and
setuptools. So the oracle would still be within reach, and saying it wasn't
would be misleading. The environment stays on 3.12.

## The hidden tests

There are 100 tests in `verifier/test_task.py`: the 77 from the first version
plus 23 new ones. They come in three groups:

- **AoT slices**: slice assignment on an array of tables, including extended
  slices, empty replacements, `tomlkit.table()` items, nesting, and slices
  followed by more edits;
- **inline dotted keys**: emptying a dotted prefix inside an inline table, at
  the start, middle and end, nested, and inside a section;
- **AoT over a dotted key**: replacing a dotted key with an array of tables,
  with different siblings after it, and inside a table.

Every check compares the data and the text with what `tomllib` says. The exact
spelling of the output is never checked, so `b = {}` and other valid forms are
all accepted.

## Correct and wrong solutions

- `solution/reference.patch`: the eight upstream fixes, code only.
- `alt_fixes/`: the two alternatives from the first version plus the three new
  upstream fixes. Both pass 100 / 100.
- `wrong_fixes/`: these must fail.

| Patch | What it does | Hidden tests failed |
|---|---|---|
| 01 | only the bug from the statement | 66 |
| 02 | all except the indented header | 6 |
| 03 | all except AoT slice assignment | 6 |
| 04 | all except the emptied inline dotted key | 7 |
| 05 | all except AoT over a dotted key | 5 |
| 06 | all, but deletes the "Redefinition" check outright | 2 |
| 07 | all, but `update()` clears later parts | 18 |

Every one of them except 06 passes the library's whole suite.

How much each fix is worth on its own (the starting state fails 69 of 100):

| Only this fix | Still failing |
|---|---|
| `29c31d2` (statement) | 66 |
| `55d0768` | 51 |
| `bb7cdd5` | 53 |
| `398c53e` | 63 |
| `229ee86` | 61 |
| `d41d237` | 63 |
| `85d391e` | 62 |
| `67d3e86` | 64 |

## Difficulty check

The setup is the same as before: a folder with `PROBLEM.md`, the repo without
history, and a virtualenv. No network, one try each. I run attempts one at a
time and stop as soon as the result is decided: two passes means rejected, two
fails means accepted.

_In progress._
