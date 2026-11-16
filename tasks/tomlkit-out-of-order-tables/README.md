# tomlkit: several bugs in tables that are split across a document

> **Status: rejected, but close.** One of three one-shot attempts failed on a
> real bug. The other two passed, but each needed about half an hour and a
> rewrite of around a thousand lines, where upstream's fix is 31. My bar is
> at most one pass in three. Details at the end of [`NOTES.md`](NOTES.md).

[tomlkit](https://github.com/python-poetry/tomlkit) is the library Poetry uses
to edit `pyproject.toml` without losing formatting. TOML lets you write one
table in several places in a file, for example `[tool.poetry]` near the top and
`[tool.other]` further down with an `[[plugins]]` array in between. tomlkit
handles that case with a fairly involved proxy object, and that's where the
bugs in this task are.

I took tomlkit as of November 2026 and reverted five fixes that went into this
area between 12 October and 7 November 2026. That brings back five separate
bugs:

- the document comes out in a different order after a round trip;
- a valid file gets rejected;
- parsing crashes with an `AttributeError`;
- deleting or replacing a key that was just added crashes;
- `update()` silently throws away unrelated keys.

The problem statement shows **only the first one**. It says plainly that we
think there are more, and it gives the rule a correct library has to follow.
Finding the rest is up to the solver.

## Why this setup

My earlier candidates were too easy for three reasons:

- the agent could check its own answer against a ready-made oracle;
- the problem statement listed every case;
- the fix was on the internet years before the model was trained.

This one is meant to close all three:

- **Hunting is required.** The statement shows one bug out of five, and the
  other four sit in different methods of a 1,300-line file.
- **The rule is clear, but the inputs aren't given.** The rule is "behave like
  `tomllib`, and round-trip byte for byte". To find the bugs you have to come
  up with the specific document shapes that trigger them.
- **Fresh fixes.** All five came out after mid-2026 and none of them is
  reachable from the solver's sandbox, since the repo is given without its git
  history.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | tomlkit at commit `7bf7284`, plus `starting_state.patch`, git history removed |
| `environment/starting_state.patch` | reverts the five fixes, their tests and their changelog lines |
| `solution/reference.patch` | the five upstream fixes, source code only |
| `verifier/test_task.py` | 77 hidden tests, using `tomllib` as the oracle |
| `verifier/alt_fixes/` | two correct solutions written differently; must pass |
| `verifier/wrong_fixes/` | five wrong or incomplete solutions; must fail |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker.

tomlkit is MIT-licensed. The Dockerfile clones it from GitHub.
