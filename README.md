# swe-eval-task

I build coding tasks for evaluating AI agents. Each one comes from a real
open-source repository and has the same pieces: a problem statement, a
Docker environment, a reference solution, and a hidden test suite that
grades the agent's patch.

Building the task is the easy half. The hard half is finding out whether the
task is actually hard, and in my experience most candidates are not. This
repo keeps the candidates that failed as well, with notes on why they failed,
because those notes are where most of what I learned ended up.

## What's here

| Task | Repo | Type | Result |
|---|---|---|---|
| [`tasks/anyio-cancellation-safety`](tasks/anyio-cancellation-safety) | [anyio](https://github.com/agronholm/anyio) | Bug hunt: eleven cancellation-safety bugs in seven files, no oracle | In progress |
| [`tasks/croniter-expand-from-start-time`](tasks/croniter-expand-from-start-time) | [croniter](https://github.com/pallets-eco/croniter) | Implement documented behaviour | Easy (first attempt solved it in ~2 minutes) |
| [`tasks/tomlkit-table-structure`](tasks/tomlkit-table-structure) | [tomlkit](https://github.com/python-poetry/tomlkit) | Bug hunt, v2: eight bugs, one symptom in the report | Easy (first attempt solved it, 100 / 100) |
| [`tasks/tomlkit-out-of-order-tables`](tasks/tomlkit-out-of-order-tables) | [tomlkit](https://github.com/python-poetry/tomlkit) | Bug hunt: five bugs, one symptom in the report | Rejected, but close: 2 of 3 solved it, each with a ~1,000-line rewrite |
| [`tasks/portion-intervaldict`](tasks/portion-intervaldict) | [portion](https://github.com/AlexandreDecan/portion) | Performance, behaviour must not change | Easy (2 of 2 attempts solved it) |
| [`tasks/flask-blueprint-prefix`](tasks/flask-blueprint-prefix) | [flask](https://github.com/pallets/flask) | Bug fix | Easy (3 of 3 attempts solved it) |

Two earlier candidates (jsonschema, tenacity) were rejected the same way. They
aren't in the repo, but [`REJECTED.md`](REJECTED.md) mentions them.

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
