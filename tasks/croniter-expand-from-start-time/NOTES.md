# Notes

## Where it comes from

- Repo: https://github.com/pallets-eco/croniter, base commit `ddb3495`
  (9 November 2026, `7.0.1.dev`).
- I reverted the **code only** (`src/croniter/croniter.py`) of four upstream
  commits that changed `expand_from_start_time`:

| Commit | PR | What it changed |
|---|---|---|
| `f329964` | #235 | the month phase was off by one |
| `44e3090` | #239 | the day-of-week phase didn't wrap Sunday |
| `269121b` | #254 | the flag raised `ValueError` for the seconds and years fields |
| `ba58c3d` | #255 | the main change: the start time sets only the *phase*, and a range keeps its bounds (`10-50/15` from minute 7 gives `22,37`, not `7,22,37`); equal ranges are the whole cycle; a range with no phase inside it is left as written; hashed `H/…` takes its phase from the start time |

A fifth commit, `f1f3b2e` (#256, phase in the start time's own timezone), was
left in place because it conflicts with later code. Its tests stay in the
visible suite.

- The README and `CHANGELOG.rst` are **unchanged**. They describe the new
  rules in detail, with examples, and they're the specification for the
  task.
- From the visible test file (`src/croniter/tests/test_croniter.py`) I removed
  the 16 tests that fail on the old code. All the others pass, so the visible
  suite doesn't hint at anything.
- The Dockerfile deletes the git history.

## Why I picked it

After six candidates the lesson was clear: if the solver can check its own
answer mechanically, it gets through by brute force. Every earlier task had
such an oracle: `tomllib` for tomlkit, the original code for portion, worked
examples in the statement for Flask.

This is a different type of task. It asks the solver to implement documented
behaviour, and there's nothing to compare against: croniter *is* the
reference. The docs give the rules and a handful of examples. Everything else
has to be derived:

- the phase for each field. Minutes, hours and seconds start at 0; days and
  months at 1; years at 1970, with the phase taken from the field minimum;
  day of week wraps Sunday as `0` or `7`;
- how to move the phase into a declared range without going past it;
- what to do when no value of the phase fits ("honoured as written");
- wrapping ranges (`6-0`, Saturday and Sunday) are left alone;
- equal ranges (`1-1/3`) are the whole cycle, but `59/15` (start at the field
  maximum) isn't an equal range;
- a start at the Unix epoch (timestamp `0`) must be re-based too, which
  catches a common `if from_timestamp:` slip.

## The hidden tests

`verifier/test_task.py` is croniter's upstream test file at `ddb3495`, in
full: 179 tests, with 870 subtests among them. The 16 that the solver doesn't
see are all about `expand_from_start_time`:

- invariants ("an expansion never leaves the declared range", "never fires
  more often than without the flag", "never empty");
- a seeded fuzz over 500 random expressions;
- exact expansions for the seconds and years fields, a start at the epoch, and
  `59/15`;
- "a range doesn't turn into another kind".

The other 163 make sure nothing else broke.

I didn't write these tests myself. They were written upstream together with
the documentation that serves as the specification here. The difficulty check
should show whether the docs pin down everything they check: each attempt
reports what it found ambiguous.

## Correct and wrong solutions

| Patch | Hidden tests |
|---|---|
| `solution/reference.patch` (upstream) | all 179 pass |
| `alt_fixes/01_modular_phase` (different arithmetic for moving the phase into the range) | all 179 pass |
| `wrong_fixes/01_only_month_and_weekday_phase` (only the two small fixes) | fails |
| `wrong_fixes/02_phase_ignores_declared_range` (phase from the start time, range bounds ignored) | 3 fail |
| `wrong_fixes/03_epoch_start_not_rebased` (`if from_timestamp:`) | 1 fails |
| `wrong_fixes/05_equal_range_not_widened` | 3 fail (and 3 visible) |

I also tried one more wrong fix, "year phase taken from the value instead of
the field minimum", and dropped it. It turns out to be equivalent: both give
the same residue modulo the step, and moving the phase into the range then
produces the same values.

## Difficulty check

The setup is the same as before: a folder with `PROBLEM.md`, the repo without
history, and a virtualenv. No network, one try each. Attempts run one at a
time, and I stop as soon as the result is decided.

### Attempt 1: passed (179 / 179), in about 2 minutes

Patch: `difficulty/attempt-1.patch`. The visible suite passed (253, including
2 tests of its own), and the hidden tests passed **179 of 179**, all 870
subtests included. It took about **2 minutes, 13 tool calls and 128 changed
lines**. That's the fastest solve of any candidate so far.

It got every trap right, including the ones I considered hard: the start at
the Unix epoch (`is not None`), `59/15` at the field maximum, equal ranges,
wrapping ranges, seconds and years, and hashed `H/15`. In its own words, it
derived the rules "from every documented example and the changelog fixes".

I stopped after this attempt. The task is rejected.

### Why it was easy

I was wrong about the oracle. I thought "the docs are prose, so there's
nothing to compare against". But croniter's 7.0 changelog notes and README
are written so thoroughly that they amount to the spec *and* the test suite:
the rules, the edge cases (an empty phase, wrapping ranges, `59/15`, equal
ranges), concrete examples with exact outputs, and even the "old → new"
behaviour for each case. The CHANGELOG even contains the history of the
earlier fixes (#235 month, #239 Sunday), with a description of the exact
formula.

So "implement from documentation" is only hard when the documentation leaves
real gaps. Here, upstream wrote it after the fact, from the finished
implementation and with every edge case in mind, which made the task
almost a transcription.
