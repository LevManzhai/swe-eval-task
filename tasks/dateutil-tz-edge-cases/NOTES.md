# Notes

## Where the bugs come from

- Repo: https://github.com/dateutil/dateutil
- Base commit: `261e2913961865300032cf30df1d59f4f0ff6f1a` (17 November 2026)

| Commit | Date | What it fixed |
|---|---|---|
| `261e291` | 2026-11-17 | `tzlocal().tzname(None)` in a zone with DST no longer raises |
| `2283058` | 2026-11-07 | `dst()` for zones whose explicit transitions end in permanent DST (zic's negative-DST TZ string) |
| `d23ff76` | 2026-11-01 | `relativedelta(yearday=366)` gives December 31 in leap years |
| `5391455` | 2026-11-01 | unpickling `tzutc`/`tzoffset` gives the cached instances |
| `6f13622` | 2026-10-19 | `isoparse` and `tzical` reject non-digit characters in numeric fields |
| `6e1864c` | 2026-10-31 | the `rrule` cache lock is released on every exit from a refill (no hang) |
| `950abb6` | 2026-10-20 | `rrulestr` ignores `X-` parameters on an `RRULE` line, as RFC 5545 allows |
| `6ba0156` | 2026-09-27 | the TZ string isn't applied to local times before the last explicit transition |
| `99f6653` | 2026-09-27 | `n` and `Jn` day-of-year rules in TZ strings give the POSIX dates |
| `7afd204` | 2026-09-27 | a TZif file truncated anywhere raises `ValueError`, not `struct.error` |
| `80b2405` | 2026-09-26 | folds at the last explicit transition are detected when a TZ string follows |
| `393c770` | 2026-09-26 | fold in `fromutc` for zones with exactly one transition |

Ten reverse cleanly. `99f6653` and `7afd204` were reverted by hand, because the
later removal of `six` changed the lines around them. Source changes only.
Tests the fixes added are removed, tests they changed are put back as they
were, and their entries in `NEWS` (3.0.0 and 4.0.0) and `changelog.d/` are
removed.

Also removed from the starting state's suite, because they fail on it and
would point straight at the time zone bugs:

- in `tests/test_tzpath_data.py`, the three tests that compare every
  installed zone against the standard library's `zoneinfo`
  (`test_matches_zoneinfo`, `test_utc_round_trip`,
  `test_ambiguous_and_imaginary`), with the helper, import and comment that
  only they used;
- in `tests/test_tzfile.py`, the one-transition-fold zone in the "weird
  zones" cases, the truncated-file tests and the `truncated` case of the
  invalid-TZPATH-file tests, and `test_sub_minute_offset_round_trip` (a one
  transition zone as well).

Tried and taken back out:

- `9e07c44` (`gettz` returns `None` for names with a NUL byte): on Linux with
  Python 3.12 every branch already returns `None`, so there's nothing to test.
  It stays fixed, and a hidden test keeps it that way.
- `df91cdd` and `208f587` (DST inference per transition, TZ strings near the
  new year): too large to revert onto the current code.

The time zone bugs live in `tz.tzfile`, which is a backport of the standard
library's pure-Python `zoneinfo`. A solver can compare against `zoneinfo`,
and the visible suite's TZif builder makes that easy. That doesn't give away
the `n`/`Jn` rules, the permanent-DST `dst()` value, or anything outside
`tz.tzfile`.

The image installs every package with `--no-deps`: `freezegun` depends on
`python-dateutil`, and the released 4.0.0 contains most of these fixes. The
Dockerfile checks that the editable install is the only `dateutil` on the
machine. `AUTHORS.md` is kept at the root because the build needs it.

## The hidden tests

`verifier/test_task.py`, 115 tests. The time zone tests write TZif files with
a small writer in the test file (version 3, a 32-bit and a 64-bit section and
a footer) and check offsets, abbreviations, DST and UTC round trips, folds
included. `tzlocal` is checked in a child process with `TZ` set to a POSIX
string. The `rrule` cache tests run in a thread with a timeout, so a hang
fails the test instead of the run.

One test was loosened before any attempt ran: `tzlocal().tzname(None)` may
return `None` or a name, as the `tzinfo` protocol allows; it must not raise.

Two mistakes in the tests were found while grading the attempts, and every
attempt was re-graded after fixing them:

- a test required `rrulestr` to reject `RRULE;FOO=1:...`. RFC 5545 allows any
  IANA parameter there, not only `X-` ones, and attempt 2 accepted it. The
  test is removed.
- the TZif writer labelled its files version 2, but some of the TZ strings use
  transition hours of -1 and 25, which RFC 8536 only allows from version 3.
  Attempt 1 rejected those files, correctly. The writer now writes version 3.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and
twelve wrong solutions against the upstream suite (4,965 tests; three that
depend on the image's system time zone data are deselected, and they fail the
same way on the unmodified upstream commit) and the hidden tests.

- `verifier/alt_fixes/01_tzlocal_yearday_and_rrulestr_variants.patch` writes
  the `tzlocal.tzname` check, the `yearday` bound and the `X-` filter
  differently.
- each wrong solution fixes everything except one bug.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 25 min, 101 tool calls | **failed**, 108 / 115 | last transition inside the TZ string's DST; fold at the last transition; permanent-DST `dst()` |
| 2 | 23 min, 74 tool calls | **failed**, 109 / 115 | last transition inside the TZ string's DST; permanent-DST `dst()` |
| 3 | 27 min, 111 tool calls | **failed**, 109 / 115 | last transition inside the TZ string's DST; permanent-DST `dst()` |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 6 files, +849 / −250),
**attempt 2** (`difficulty/attempt-2.patch`, 6 files, +644 / −229) and
**attempt 3** (`difficulty/attempt-3.patch`, 5 files, +553 / −188) all fixed
`yearday=366`, the `n`/`Jn` rules, the one-transition fold, truncated files,
`tzlocal().tzname(None)`, pickling identity, strict `isoparse` and `tzical`
numbers, `X-` parameters in `rrulestr` and the cached `rrule` hang, and went
well beyond (BYWEEKNO, BYEASTER, `tzical` grammar, TZif validation, a new
`tzlocal`). Attempt 3 says it compared its `tzfile` against a brute-force
implementation of its own over random TZ strings and zones with 0 to 3
transitions, and against `zoneinfo` for every installed zone.

What none of them fixed:

- **The last explicit transition inside the TZ string's DST period** (like
  America/Nuuk in slim builds). The transition at 23:00 local on 28 October
  2023 switches from DST to standard time at the same offset, -02; the TZ
  string that follows says DST (-01) until midnight. For local 23:30, all
  three return the TZ string's -01, which corresponds to 00:30 UTC, before
  the last transition, where RFC 8536 says the TZ string doesn't apply. The
  right answer is -02, the offset of the last transition.
- **`dst()` after transitions that end in DST, followed by zic's permanent
  negative-DST TZ string** (`XXX-2<+01>-1,0/0,J365/23`, like
  Africa/Casablanca in the rearguard format). All three return -1 h, the TZ
  string's literal reading; upstream returns +1 h, the DST amount of the
  explicit transitions. This is the most debatable check in the task: the
  statement asks for "one consistent zone" and the right DST, but a solver
  could argue for the literal reading. Without it the result is the same,
  because every attempt also fails the case above.
- Attempt 1 also gets `fold` wrong for one time in the fold at the last
  explicit transition when a TZ string with its own DST follows.

### What I make of it

- As in the other accepted tasks, the difficulty sits in the time zone
  corner cases. Everything outside `tz.tzfile` was fixed by every attempt.
- The common miss is a case where the explicit transitions and the TZ string
  disagree. Differential testing against `zoneinfo` over the installed zones
  doesn't reveal it, and a brute-force reimplementation built from the TZ
  string alone makes the same mistake.
- All three changed 740 to 1,100 lines where upstream's fixes change about
  150.
