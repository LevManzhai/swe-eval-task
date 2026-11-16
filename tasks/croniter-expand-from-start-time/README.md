# croniter: make `expand_from_start_time` do what its documentation says

> **Status: rejected.** The first attempt solved it in about two minutes
> (179 / 179). Reasons are at the end of [`NOTES.md`](NOTES.md).

[croniter](https://github.com/pallets-eco/croniter) computes when a cron
expression fires. With `expand_from_start_time=True`, a step like `*/15`
counts from the start time instead of from zero. In autumn 2026 upstream
rewrote how this flag works and documented the new rules in detail, in the
README and the 7.0 changelog notes.

This task keeps that documentation and takes the implementation back to the
old code. The solver has to make the code do what the docs say.

## Why this kind of task

All my earlier candidates had an automatic oracle for the solver: `tomllib`,
the old implementation, or examples spelled out in the statement. The solver
wrote a random tester against it and got through by brute force.

Here there is no oracle. croniter is itself the reference implementation, and
the docs describe the rules in prose. The solver has to read them, turn them
into code for seven fields with different minimums (`0` for minutes, `1` for
days and months, `1970` for years, wrapping Sunday for day of week), and get
the edge cases right without being able to check against anything:

- a range with no in-range phase;
- wrapping ranges;
- equal ranges like `1-1/3`;
- `59/15` at the field maximum;
- a start time at the Unix epoch;
- timezone-aware start times.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/` | pinned Dockerfile plus `starting_state.patch`; the git history is removed |
| `solution/reference.patch` | upstream code from commits `f329964`, `44e3090`, `269121b`, `ba58c3d` |
| `verifier/test_task.py` | croniter's upstream test file at `ddb3495`; 16 of its tests are hidden from the solver |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | four wrong or incomplete solutions; must fail |
| `run.sh` | builds the image and checks all of the above |

## Running it

You need Docker.

```bash
./run.sh
```
