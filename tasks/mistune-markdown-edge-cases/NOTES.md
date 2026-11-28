# Notes

## Where the bugs come from

- Repo: https://github.com/lepture/mistune
- Base commit: `f7ec702edfc1ad5579a76f881238841af266d93c` (24 October 2026, after release 3.4.0)

| Commit | Date | What it fixed |
|---|---|---|
| `847d51a` | 2026-10-23 | end an empty list item at an unindented line |
| `b3aa5b9` | 2026-10-18 | Fix ReST hard breaks in tight list items |
| `15ad4b0` | 2026-10-18 | Preserve reference definitions parsed inside footnotes |
| `18af19b` | 2026-10-17 | Fix indented definition-list markers |
| `129f63a` | 2026-10-16 | Preserve non-line-break characters in list rendering |
| `592a70d` | 2026-10-14 | Render strikethrough, mark and insert in MarkdownRenderer |
| `f6a0767` | 2026-10-13 | Preserve escaped pipes in Markdown table code spans |
| `41af9a7` | 2026-10-12 | Only parse task markers in leading paragraphs |
| `0634fa2` | 2026-10-11 | Prefer longer registered abbreviation matches |
| `1b1e0ed` | 2026-10-01 | list: require a digit on an ordered list marker |
| `aa5f0ac` | 2026-09-09 | preserve empty reference destinations in MarkdownRenderer |
| `c439fd5` | 2026-09-08 | Preserve literal hashes at the end of headings |
| `8d77817` | 2026-09-07 | Keep images with URL alt text out of autolink rendering |
| `c3e832c` | 2026-09-07 | Preserve meaningful edge spaces in Markdown code spans |
| `278640e` | 2026-08-21 | preserve leading blank lines in MarkdownRenderer |
| `14ececa` | 2026-07-20 | Keep multi-line setext headings intact in MarkdownRenderer |
| `7aa49ec` | 2026-07-19 | def_list: a tab after the ':' marker no longer makes the definition a code block |
| `86f9fd1` | 2026-07-19 | table: reject a non-delimiter second row instead of eating it |
| `03eacc5` | 2026-07-17 | Only relax the indent bound when recompiling list break rules |
| `cff35d5` | 2026-06-27 | Keep a trailing '>' when reformatting block quotes |
| `2c1a518` | 2026-06-27 | Escape quotes in MarkdownRenderer link and image titles |

All 21 reverse cleanly at the base commit, newest first; the reference patch
is 120 changed lines. Seven more fixes from the same months were tried and
left fixed because later refactors of the inline parser rewrote their code
(CommonMark inline HTML comments, literal inline syntax in Markdown output,
full reference labels, indented fence lines, backslashes in link
destinations, emphasis markers in Markdown output, the emphasis
multiple-of-3 rule).

`278640e` (leading blank lines in `MarkdownRenderer` output) is reverted but
not tested: blank lines at the start of a document don't change what it
parses to, so the round-trip property in the statement doesn't cover it,
and requiring them would test a formatting choice. There is no wrong
solution for it.

Most of these fixes are listed in the 3.4.0 entry of `docs/changes.rst`;
those bullets are removed. Tests added by the fixes are removed, tests they
changed are put back as they were. Also removed because they fail on the
starting state: the "Leading headings are not task list paragraphs" section
of `tests/fixtures/task_lists.txt` and eight test methods in
`tests/test_renderers.py` whose fix commits didn't revert cleanly (task
markers, formatting plugins, table pipes, code span spaces, image alt text,
leading blank lines, link titles, list line separators).

## The hidden tests

`verifier/test_task.py`, 97 tests.

- 25 HTML cases and 6 RST cases with the expected output (the reference's;
  for core Markdown it is what CommonMark specifies). The inputs are
  upstream's test inputs for these fixes plus variants; 7 of them are
  guards the starting state already gets right.
- 30 Markdown round trips, each checked twice: the Markdown that
  `MarkdownRenderer` writes must render to the same HTML as the source, and
  so must rendering it a second time. Any output with that property is
  accepted, so no particular formatting is required.
- fenced directives inside list items (`03eacc5`).

Five cases were dropped after grading, and every attempt was re-graded:
definition-list markers indented by one to three spaces (`18af19b`).
mistune's documentation for the `def_list` plugin shows only unindented
markers, so the statement's "documented syntax" doesn't promise them.
`18af19b` stays in the reference; its tab case is still checked through
`7aa49ec`'s case.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and
eighteen wrong solutions against the upstream suite (1,239 tests) and the
hidden tests.

- `verifier/alt_fixes/01_abbr_list_marker_and_title_variants.patch` writes
  the abbreviation ordering, the ordered-marker digits and the title
  escaping differently.
- each wrong solution fixes everything except one bug. There is none for
  `7aa49ec` (a tab after a definition-list marker: `18af19b` rewrote the same
  lines, so it can't be reverted on its own), `18af19b` (its cases were
  dropped, see below) or `278640e` (untested).

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes. All three
were cut off by an API rate limit partway through and resumed with their
work intact.

| Attempt | Result | What it missed |
|---|---|---|
| 1 | **failed**, 80 / 97 | tables without a delimiter row; task markers in headings; footnote reference definitions; abbreviations; image alt = URL in Markdown output; directives in lists |
| 2 | **failed**, 95 / 97 | the longest registered abbreviation |
| 3 | **failed**, 86 / 97 | tables without a delimiter row; task markers in headings; footnote reference definitions; a tab after a definition marker; directives in lists |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 17 files, +1,176 / −198),
**attempt 2** (`difficulty/attempt-2.patch`, 17 files, +1,029 / −151) and
**attempt 3** (`difficulty/attempt-3.patch`, 19 files, +1,246 / −202) each
rewrote most of `MarkdownRenderer` and `RSTRenderer`, fixed the reported
empty list item and the ordered-marker digits, and replaced Python's
`splitlines()`/`strip()` with LF-only handling. All three keep the upstream
suite green. Attempts 1 and 3 round-tripped every CommonMark example and
plugin fixture with their own scripts, and passed all or nearly all hidden
round-trip checks; they missed parsing fixes in plugins (tables, task
lists, footnotes, directives).

**Attempt 2** came closest. It fixed tables, task lists, footnotes and
directives too, and fails only the two abbreviation cases: with `HTML` and
`HTML5` both defined, `HTML5` is marked up as the `HTML` abbreviation
followed by "5" (or is left alone, depending on definition order), so the
`HTML5` definition is never used.

### What I make of it

- The deciding check for attempt 2 is the abbreviation one. The `abbr`
  documentation doesn't spell out longest-match, but a defined abbreviation
  that can never apply is hard to call documented behaviour. A reviewer who
  disagreed would score attempt 2 as a pass; the task would still be
  accepted at 1 of 3.
- The two attempts that put their effort into round-tripping (1 and 3)
  missed plugin parsing bugs that the round-trip checks can't see, because
  the same wrong parse happens on both sides.
