# markdown-it-py: Markdown not rendered per CommonMark, or not in linear time

> **Status: accepted.** Three of three one-shot attempts failed (60, 58 and
> 56 of 67). All three missed the same bug. `run.sh` passes all 24 of its
> checks. Details at the end of [`NOTES.md`](NOTES.md).

[markdown-it-py](https://github.com/executablebooks/markdown-it-py) is the
Markdown parser behind Jupyter, MyST, mdformat and many documentation tools.
Its 4.3.0 release (10 November 2026) aligned several rules with
CommonMark 0.31.2 and fixed two quadratic-time parsing paths. I took the
release commit and reverted ten of those fixes (plus one that later commits
build on):

| Area | Trigger | What goes wrong |
|---|---|---|
| HTML blocks | `para\n<!doctype html>` | the declaration ends up inside the paragraph |
| HTML blocks | `<ſcript>`, `<dİv>` (Unicode lookalikes) | treated as `<script>`, `<div>` |
| HTML blocks | an HTML comment spanning a blank line in a list item | the block ends at the blank line |
| code spans | `` [foo `bar` baz` `` | no code span, because of the unclosed `[` |
| code spans | `` ` \t ` ``, `` `   ` `` | padding not stripped (only U+0020 is a space) |
| task lists | `-     [x] literal` (an indented code block) | rendered as a checkbox |
| URLs | `[x](http://[::1]:8000/)` | brackets encoded to `%5B`/`%5D` |
| image alt | `![foo\\\nbar](/u)`, `![a<b>c](/u)` | hard break and inline HTML dropped |
| end of input | a table in a block quote ending on `>` | `IndexError` |
| API | `md.enable(name for name in [...])` | applied to the core chain only |
| speed | `"x" + "<!--" * 30000` | 13 s instead of 0.1 s |
| speed | `"&" * 1_200_000` | about a minute instead of 2 s |

The problem statement shows **only the first row** and a four-point
contract.

## Why this one

Same recipe as the other tasks in this repository, with a standard
(CommonMark 0.31.2) behind most of the cases and a red-team angle: two of
the bugs are denial-of-service issues on crafted input, checked with hard
time limits.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | markdown-it-py at commit `d504583`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 67 hidden tests: rendering cases, API cases, timing cases |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | nine "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. markdown-it-py is MIT-licensed; the Dockerfile clones it
from GitHub.
