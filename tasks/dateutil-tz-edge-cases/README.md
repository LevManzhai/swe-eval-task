# dateutil: rare dates, time zones and recurrences handled wrongly

> **Status: accepted.** Three of three one-shot attempts failed (108, 109 and
> 109 of 115). All three missed the same time zone case. `run.sh` passes all
> 30 of its checks. Details at the end of [`NOTES.md`](NOTES.md).

[dateutil](https://github.com/dateutil/dateutil) extends Python's `datetime`
and sits under pandas, botocore and many other projects. In autumn 2026
upstream rewrote `tz.tzfile` and fixed a run of bugs where dateutil didn't
follow the standards it implements (RFC 8536, POSIX TZ strings, ISO 8601,
RFC 5545) or Python's `tzinfo` protocol. I took dateutil as of 17 November
2026 and reverted twelve of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| `relativedelta` | `yearday=366` in a leap year | December 30, the same as 365 |
| `tzfile` TZ string | an `n` or `Jn` day-of-year rule | DST starts and ends a day off |
| `tzfile` | a zone with one transition that moves the clock back | wrong UTC time and fold in the fold |
| `tzfile` | the last explicit transition moves the clock back, a TZ string follows | the fold isn't detected |
| `tzfile` | the last transition falls inside the TZ string's DST period | times just after it get the TZ string's DST offset |
| `tzfile` | transitions end in DST, TZ string is zic's permanent negative DST | `dst()` is negative |
| `tzfile` | TZif data that ends early | `struct.error` instead of `ValueError` |
| `tzlocal` | `tzname(None)` (e.g. from a `datetime.time`) in a zone with DST | `AttributeError` |
| pickling | a `tzutc()` or `tzoffset(...)` | a new object instead of the cached one |
| `isoparse` | `2014- 4-21`, `2_14-04-21`, `+-1:00`, non-ASCII digits | accepted, because `int()` accepts them |
| `tzical` | `TZOFFSETFROM:+0_00` | accepted |
| `rrulestr` | `RRULE;X-EVOLUTION-ENDDATE=...:FREQ=...` | `ValueError` |
| cached `rrule` | the same rule twice in an `rruleset` | iteration hangs forever |

The problem statement shows **only the first row** and a four-point contract.

## Why this one

Same recipe as the other tasks in this repository: many bugs, each with an
unusual trigger, in a widely used library whose own suite passes without
noticing them, and no oracle in the sandbox apart from the standard library's
`zoneinfo` (see NOTES for what it can and can't tell a solver).

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | dateutil at commit `261e291`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 115 hidden tests through the public API, with a small TZif writer |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | twelve "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. dateutil is dual-licensed (Apache 2.0 / BSD); the Dockerfile
clones it from GitHub.
