# mistune: rare Markdown parsed or re-rendered wrongly

> **Status: accepted.** Three of three one-shot attempts failed (80, 95 and
> 86 of 97). The closest one missed only the abbreviation case. `run.sh`
> passes all 42 of its checks. Details at the end of [`NOTES.md`](NOTES.md).

[mistune](https://github.com/lepture/mistune) is a fast Markdown parser with
HTML, reStructuredText and Markdown renderers; the Markdown renderer is used
to reformat and normalize documents. Over summer and autumn 2026 upstream
fixed a long run of edge cases in parsing and in the renderers. I took
mistune as of 24 October 2026 and reverted 21 of them:

| Area | Trigger | What goes wrong |
|---|---|---|
| lists | `-\nfoo` | `foo` becomes the empty item's text |
| lists | `1. a\n. b` | `. b` starts a second item |
| definition lists | `Term\n:\tdef` | a code block instead of a definition |
| tables | `Name \| Age\nJohn \| 30` | the second row is taken as a delimiter row |
| task lists | `- # [ ] heading` | a checkbox in a heading |
| footnotes | a reference definition inside a footnote | ignored |
| abbreviations | `HTML` and `HTML5` both defined | `HTML5` matched as `HTML` + `5` |
| directives | `- item\n:{note}` | a one-colon run starts a directive in a list |
| Markdown output | `[x](/u 'say "hi"')`, `` `  x  ` ``, `# Issue \#` | the output parses to something else |
| Markdown output | `~~gone~~`, `==hl==`, `^^ins^^` | the markup is dropped |
| Markdown output | `![https://e.com](https://e.com)` | turned into an autolink |
| Markdown output | a multi-line setext heading, `> <https://x>` | the heading or the `>` breaks |
| Markdown output | `` `a\|b` `` in a table cell | the escape count changes the table |
| RST output | a hard break in a tight list item | lost |
| all renderers | `\x85` or `\x1e` inside a list item | treated as a line break |

The problem statement shows **only the first row** and a four-point
contract.

## Why this one

Same recipe as the other tasks in this repository. Many of the checks are
round trips, Markdown → Markdown → HTML compared with Markdown → HTML, so
any correct renderer output is accepted.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | mistune at commit `f7ec702`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 97 hidden tests: HTML and RST cases, Markdown round trips, directives |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | eighteen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. mistune is BSD-licensed; the Dockerfile clones it from
GitHub.
