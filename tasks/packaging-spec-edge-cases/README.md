# packaging: inputs the specifications reject, accepted anyway

> **Status: accepted.** Three of three one-shot attempts failed (47 / 48
> each). All three fixed eight of the nine bugs and missed the same one.
> `run.sh` passes all 24 of its checks. Details at the end of
> [`NOTES.md`](NOTES.md).

[packaging](https://github.com/pypa/packaging) is the reference
implementation of Python's packaging specifications, and pip, setuptools,
Poetry and many other tools build on it. Between July and November 2026
upstream fixed a long run of edge cases. I took packaging as of 17 November
2026 and reverted nine of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| requirement / marker parser | `Requirement("requests>=2\n")` | accepted; the regex end anchor `$` matches before a trailing newline |
| requirement parser | `foo===1.0, >= 2` | a valid requirement is rejected |
| requirement tokenizer | a form feed or non-breaking space inside a URL | accepted as part of the URL |
| marker parser | a marker nested a few thousand parentheses deep | `RecursionError` |
| marker serialization | a marker value containing `"` | `str(marker)` no longer parses |
| `parse_tag` | `py3-none` or four fields | plain `ValueError` instead of `InvalidTag` |
| `parse_wheel_filename` | a project name ending in `\n` | accepted |
| `parse_wheel_filename` | a build tag `1\n` | accepted |
| metadata writer | a `\r` inside a value | the writer raises `HeaderWriteError`: only `\n` is folded (older Pythons also split headers on `\u2028`, `\x85` and similar) |

The problem statement shows **only the first row** and a four-point contract.

## Why this one

It's the recipe that worked for anyio, aiohttp and Flask/Werkzeug: many
small bugs, each with its own odd trigger, in a library whose own suite (over
64,000 tests, much of it property-based) passes without noticing any of them.
There is no executable oracle in the sandbox: git history is gone, the
released copy of packaging that pytest pulls in is replaced by the editable
install, and pip's vendored copy is an older release with the same bugs.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | packaging at commit `6a69a83`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the nine upstream fixes, source only |
| `verifier/test_task.py` | 48 hidden tests on the public API |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | nine "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. packaging is dual-licensed Apache-2.0 / BSD-2-Clause; the
Dockerfile clones it from GitHub.
