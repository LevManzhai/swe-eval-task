# Notes

## Where the bugs come from

- Repo: https://github.com/executablebooks/markdown-it-py
- Base commit: `d504583a458edfa399ee800074244fceec288862` (10 November 2026, release 4.3.0)

| Commit | Date | What it fixed |
|---|---|---|
| `2542e66` | 2026-11-09 | HTML block start per CommonMark 0.31.2: lowercase `<!doctype>` starts a block; tag names match case-insensitively in ASCII only |
| `cb36d3a` | 2026-11-09 | HTML blocks of types 1–5 inside list items and block quotes don't end at a blank line |
| `f5af61f` | 2026-11-10 | code spans after an unclosed link or image label; only U+0020 counts when stripping a code span's padding |
| `01d077a` | 2026-11-10 | a `[x]` at the start of an indented code block in a list item isn't a task marker |
| `a852307` | 2026-11-09 | `enable()`/`disable()` apply a generator of rule names to every chain |
| `d774374` | 2026-11-10 | IPv6 host brackets survive URL normalization |
| `be6367a` | 2026-09-17 | unterminated inline HTML (`<!--`, `<?`, `<![CDATA[`) rejected in constant time (was quadratic) |
| `8501cf3` | 2026-09-08 | hard breaks and inline HTML kept in image `alt` text |
| `1b7ef65` | 2026-09-08 | `IndexError` at end of input (table in a block quote ending on `>`) |
| `997232e` | 2026-09-08 | runs of characters that start an inline rule (`&`, `<a`, ...) parsed in linear time (was quadratic) |
| `9aa1aae` | 2026-11-09 | rendering joins fragments once (quadratic on PyPy; not measurable on CPython, so untested) |

All of them reverse cleanly at the base commit. The
reference patch is 338 changed lines. `9aa1aae` is reverted because later
commits build on it; on the default CPython build it changes nothing
observable, so no hidden test covers it and there is no wrong solution for
it.

The 4.3.0 release notes in `CHANGELOG.md` describe these fixes; their
bullets, the empty "Security" section and the matching upgrade notes are
removed, and the release summary is cut down to what remains. Tests added by
the fixes are removed, tests they changed are put back as they were. Also
removed from the starting state because they fail on it: two image-alt-text
cases in `tests/test_port/fixtures/commonmark_extras.md` and six tests in
`tests/test_api/test_main.py` whose fix commits didn't revert cleanly.

## The hidden tests

`verifier/test_task.py`, 67 tests.

- 38 rendering cases (input, preset, expected HTML). The inputs are the
  upstream fixture cases for these fixes plus variants; the expected HTML is
  the reference's output, which for the CommonMark preset is what
  CommonMark 0.31.2 specifies. 13 of them are guards the starting state
  already renders correctly.
- `enable()`/`disable()` with lists, tuples, iterators and generators.
- end-of-input cases with tables in block quotes, with and without HTML.
- timing: eight hostile inputs (unterminated inline HTML, runs of `&`, `&#`,
  `<a`) rendered in a child process with a limit (8 or 15 seconds). The
  reference needs at most 2.8 seconds; the starting state needs 13 seconds
  to well over a minute.

One case was dropped after grading, and every attempt was re-graded:
`- <!--\n\n- b` (an HTML comment and a blank line in a list item, then a
second item). The reference keeps the blank line in the HTML block, as
markdown-it 14.2 does; commonmark.js trims trailing blank lines from an HTML
block, and two attempts did the same. CommonMark doesn't settle it, so the
case isn't a fair test.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and nine
wrong solutions against the upstream suite (1,098 tests) and the hidden
tests.

- `verifier/alt_fixes/01_rule_names_and_alt_text_variants.patch` writes the
  rule-name normalization and the `alt` text branches differently.
- each wrong solution fixes everything except one bug. There is none for
  `997232e` (seven files, rewritten by later commits) or `9aa1aae`
  (untested).

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes. Attempts 1
and 2 were cut off by an API rate limit partway through and resumed with
their work intact.

| Attempt | Result | What it missed |
|---|---|---|
| 1 | **failed**, 60 / 67 | IPv6 brackets in link destinations; code spans after an unclosed `[` or `![` |
| 2 | **failed**, 58 / 67 | IPv6 brackets in link destinations; `IndexError` at end of input with tables |
| 3 | **failed**, 56 / 67 | IPv6 brackets in link destinations; code spans after an unclosed label; `IndexError` at end of input |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 21 files, +589 / −205),
**attempt 2** (`difficulty/attempt-2.patch`, 20 files, +537 / −209) and
**attempt 3** (`difficulty/attempt-3.patch`, 17 files, +507 / −131) each
fixed the reported HTML block start, ASCII-only case-insensitivity, HTML
blocks in containers, code span padding, task markers in indented code,
image `alt` text, `enable()`/`disable()` with generators, and both
quadratic-time paths (all eight timing tests pass for all three). Each went
further: linear smartquotes and linkify, label case folding and length
limits, stricter raw-HTML whitespace.

What none of them fixed:

- **IPv6 hosts in link destinations.** `[x](http://[::1]:8000/)` renders
  `href="http://%5B::1%5D:8000/"`, which is no longer a valid URL. All three
  looked at normalization and left it: attempt 1 says it compared it with
  markdown-it 15 and found no difference; attempt 2 noticed the brackets
  being encoded and assumed the JavaScript library does the same (it did
  before 15.0.1).

Also missed by two of the three:

- **Code spans after an unclosed link or image label** (attempts 1 and 3):
  `` [foo `bar` baz` `` keeps the backticks literal.
- **`IndexError` at end of input** (attempts 2 and 3): a table in a block
  quote that ends on `>`, with the `table` rule enabled. Attempt 2 fuzzed
  random presets and rule sets and found no exception even on the original
  code; the crash needs `table` enabled on top of `commonmark`.

### What I make of it

- As with yarl, the common miss is a place where the solver's memory of the
  reference implementation is out of date: markdown-it changed IPv6
  handling in a recent release.
- Both denial-of-service bugs were found and fixed by all three, by timing
  inputs of growing size, which the statement invites.
