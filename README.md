# swe-eval-task

[![Self-check](https://github.com/LevManzhai/swe-eval-task/actions/workflows/selfcheck.yml/badge.svg)](https://github.com/LevManzhai/swe-eval-task/actions/workflows/selfcheck.yml)
**[▶ Run a task's self-check](https://github.com/LevManzhai/swe-eval-task/actions/workflows/selfcheck.yml)**: open the page and press *Run workflow* (repository owner only; anyone can open past runs and their logs).

I build coding tasks for evaluating AI agents. Each one comes from a real
open-source repository and has the same pieces: a problem statement, a
Docker environment, a reference solution, and a hidden test suite that
grades the agent's patch.

Building the task is the easy half. The hard half is finding out whether the
task is actually hard, and in my experience most candidates are not. This
repo keeps the candidates that failed as well, with notes on why they failed,
because those notes are where most of what I learned ended up.

## What's here

Two tasks passed:

- [`tasks/tomlkit-conformance`](tasks/tomlkit-conformance): two independent
  attempts each fixed 14 of its 15 bugs and missed a different one.
- [`tasks/anyio-cancellation-safety`](tasks/anyio-cancellation-safety).

The rest are earlier candidates that turned out easy, kept with notes on why,
because that's how I got to the ones that work.

| Task | Repo | Type | Result |
|---|---|---|---|
| [`tasks/msw-reset-subscriptions`](tasks/msw-reset-subscriptions) | [msw](https://github.com/mswjs/msw) | Distant-symptom debugging in TypeScript: one bug, the symptom two layers from the cause, no oracle | In progress: 1 of 1 attempts passed (12 / 12) |
| [`tasks/yarl-url-standards`](tasks/yarl-url-standards) | [yarl](https://github.com/aio-libs/yarl) | Bug hunt: ten WHATWG URL Standard and RFC 3986 conformance bugs, graded on the standard's own test data | **Accepted**: 0 of 3 attempts passed (353, 351, 357 / 375) |
| [`tasks/dateutil-tz-edge-cases`](tasks/dateutil-tz-edge-cases) | [dateutil](https://github.com/dateutil/dateutil) | Bug hunt: twelve time zone, TZ string, parser and recurrence bugs, no oracle | **Accepted**: 0 of 3 attempts passed (108, 109, 109 / 115) |
| [`tasks/more-itertools-edge-cases`](tasks/more-itertools-edge-cases) | [more-itertools](https://github.com/more-itertools/more-itertools) | Bug hunt: sixteen size, argument, error, `numeric_range` and laziness bugs, no oracle | **Accepted**: 0 of 3 attempts passed (549, 549, 554 / 558) |
| [`tasks/click-cli-edge-cases`](tasks/click-cli-edge-cases) | [click](https://github.com/pallets/click) | Bug hunt: thirteen help, value-source, terminal and strict-flag bugs, no oracle | **Accepted**: 0 of 3 attempts passed (60, 60, 60 / 64) |
| [`tasks/starlette-spec-edge-cases`](tasks/starlette-spec-edge-cases) | [starlette](https://github.com/Kludex/starlette) | Bug hunt: seventeen RFC 9110, ASGI and documented-API bugs, no oracle | **Accepted**: 0 of 3 attempts passed (40, 43, 42 / 44) |
| [`tasks/urllib3-response-edge-cases`](tasks/urllib3-response-edge-cases) | [urllib3](https://github.com/urllib3/urllib3) | Bug hunt: thirteen response, retry and redirect bugs, no oracle | **Accepted**: 0 of 3 attempts passed (90, 89, 88 / 92) |
| [`tasks/packaging-spec-edge-cases`](tasks/packaging-spec-edge-cases) | [packaging](https://github.com/pypa/packaging) | Bug hunt: nine spec edge cases (PEP 440/508, wheel tags, metadata), no oracle | **Accepted**: 0 of 3 attempts passed (47 / 48 each) |
| [`tasks/flask-werkzeug-rare-inputs`](tasks/flask-werkzeug-rare-inputs) | [flask](https://github.com/pallets/flask) + [werkzeug](https://github.com/pallets/werkzeug) | Bug hunt across two repos: thirteen rare-input bugs, no oracle | **Accepted**: 0 of 3 attempts passed (66 / 68 each) |
| [`tasks/aiohttp-http-edge-cases`](tasks/aiohttp-http-edge-cases) | [aiohttp](https://github.com/aio-libs/aiohttp) | Bug hunt: nine HTTP edge cases with unusual triggers, client and server, no oracle | **Accepted**: 0 of 2 attempts passed (87 / 90, 89 / 90) |
| [`tasks/tomlkit-conformance`](tasks/tomlkit-conformance) | [tomlkit](https://github.com/python-poetry/tomlkit) | Bug hunt, v3: fifteen bugs with rare triggers, one symptom in the report | **Accepted: 0 of 2 attempts solved it** |
| [`tasks/anyio-cancellation-safety`](tasks/anyio-cancellation-safety) | [anyio](https://github.com/agronholm/anyio) | Bug hunt: eleven cancellation-safety bugs in seven files, no oracle | **Accepted**: 0 of 2 attempts passed (34 / 36 each) |
| [`tasks/tomlkit-table-structure`](tasks/tomlkit-table-structure) | [tomlkit](https://github.com/python-poetry/tomlkit) | Bug hunt, v2: eight bugs, one symptom in the report | Easy (first attempt solved it, 100 / 100) |
| [`tasks/tomlkit-out-of-order-tables`](tasks/tomlkit-out-of-order-tables) | [tomlkit](https://github.com/python-poetry/tomlkit) | Bug hunt: five bugs, one symptom in the report | Rejected, but close: 2 of 3 solved it, each with a ~1,000-line rewrite |
| [`tasks/portion-intervaldict`](tasks/portion-intervaldict) | [portion](https://github.com/AlexandreDecan/portion) | Performance, behaviour must not change | Easy (2 of 2 attempts solved it) |
| [`tasks/flask-blueprint-prefix`](tasks/flask-blueprint-prefix) | [flask](https://github.com/pallets/flask) | Bug fix | Easy (3 of 3 attempts solved it) |

Two earlier candidates (jsonschema, tenacity) were rejected the same way. They
aren't in the repo, but [`REJECTED.md`](REJECTED.md) mentions them.

## Running the checks on GitHub

Any task's self-check can be run without installing anything. Open the
**Actions** tab, pick **Self-check a task**, press **Run workflow** and choose
the task. It builds the Docker image and runs that task's `run.sh`. The log
shows a `PASS`/`FAIL` line for every expectation and finishes with
`ALL EXPECTATIONS MET`.

## How each task is laid out

```
task/PROBLEM.md        what the agent gets to read
environment/           Dockerfile, every version pinned
solution/              my reference patch
verifier/test_task.py  the hidden tests
verifier/alt_fixes/    other correct patches; these must pass
verifier/wrong_fixes/  plausible wrong patches; these must fail
run.sh                 builds the image and checks all of the above
NOTES.md               the reasoning behind the task, and what happened
```

`alt_fixes/` and `wrong_fixes/` are there to test the tests. If a correct
solution written a different way fails, the verifier is checking my
implementation instead of the behaviour. If a plausible wrong solution
passes, the verifier has a hole in it. `run.sh` checks both, every time.

## My bar for "hard"

Before calling a task done I check four things:

1. `run.sh` passes from a clean checkout. Tests run with the network off.
2. Every hidden test can be traced back to the problem statement, the
   library's docs, or what the original code already does. I don't test
   anything that's just a quirk of my own solution.
3. At least two correct solutions that differ in structure both pass.
4. I give a strong coding agent only `PROBLEM.md` and the repo, one try, and
   do that three times. I keep the task only if at most one of the three
   passes.

When a task fails step 4 I don't make the statement vaguer to rescue it. A
task that is hard only because nobody can tell what it's asking is a bad
task. It goes in `REJECTED.md` instead.
