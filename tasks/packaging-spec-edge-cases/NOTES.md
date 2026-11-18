# Notes

## Where the bugs come from

- Repo: https://github.com/pypa/packaging
- Base commit: `6a69a83d8d89c6a01d554a8ad1b420cbb45fb4bc` (17 November 2026)

| Commit | PR | What it fixed |
|---|---|---|
| `189a76d` | #1345 | the parser's end-of-input rule used `$`, so a trailing `\n` was accepted |
| `5a7d338` | #1531 | `===` followed by another, spaced specifier was rejected |
| `2602dd0` | #1379 | the URL token allowed whitespace other than space and tab |
| `4d7875f` | #1450 | deeply nested markers exhausted the recursion limit |
| `5b583e3` | #1213 | marker values containing `"` serialized to a string that doesn't parse |
| `f0620a9` | #1238 | `parse_tag` with the wrong number of fields raised a plain `ValueError` |
| `8af7590` | #1341 | a wheel project name could end in `\n` |
| `0625596` | #1427 | a wheel build tag could end in `\n` |
| `2d873eb` | #1356 | the metadata writer only folded `\n`, not the other line boundaries |

All revert cleanly except `f0620a9`, whose code was later extended by
`26fa1d4`; I removed only the lines `f0620a9` added and left `26fa1d4` in
place. Its docstrings mention the three-component rule, so I took that
phrase out of them in the starting state, the same way changelog entries are
removed. The fixes' own tests are removed too, and three later tests that
would have given bugs away.

Two candidates I built and then took out again, because the statement couldn't
fairly require them:

- `9afc187`, `SpecifierSet` accepting plain strings in its iterable form. The
  starting state's documentation only promises `Specifier` objects there.
- `26fa1d4`, rejecting a tag whose interpreter isn't a Python identifier. The
  platform tag specification doesn't say that in so many words.

### Oracle check

pytest depends on packaging, so the image first gets packaging 26.3 from PyPI.
26.3 already contains six of these fixes, which would have made it a perfect
reference. The editable install of the repository replaces it, and the
Dockerfile asserts that the importable `packaging` is the one under
`/workspace/repo`. pip's vendored copy is an older release that has the same
bugs.

## The problem statement

One user report (a requirements line with a trailing newline), then four
points: valid if and only if the grammar says so, only documented exceptions,
`str()` round-trips, metadata stays well formed. The first draft said
"whitespace inside a URL" as an example, which pointed straight at one of the
bugs; I replaced it with a neutral wording before any attempt ran.

## The hidden tests

`verifier/test_task.py`, 48 tests on the public API: trailing newlines in
requirements, markers and wheel filenames; Unicode whitespace in URLs;
markers nested 5,000 and 20,000 deep (either a clean parse or
`InvalidMarker` is accepted; `RecursionError` isn't); quote characters in
marker values round-tripping; `===` next to other specifiers; tag field counts;
and for the metadata writer, ten different line-boundary characters inside a
summary. The output is read back with packaging's own `parse_email` and the
standard library's email parser, and neither may see a header besides the
expected ones.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and nine
wrong solutions against the upstream suite (64,129 tests) and the hidden
tests. All 24 expectations are met.

- `verifier/alt_fixes/01_recursion_guard_and_splitlines.patch` catches
  `RecursionError` at the two parse entry points instead of counting depth, and
  folds metadata lines with `str.splitlines()` instead of a regular expression.
- `verifier/wrong_fixes/` each fix everything except one of the nine bugs.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 12 min, 59 tool calls | **failed**, 47 / 48 | `foo===1.0, >= 2` |
| 2 | 13 min, 67 tool calls | **failed**, 47 / 48 | `foo===1.0, >= 2` |
| 3 | 18 min, 83 tool calls | **failed**, 47 / 48 | `foo===1.0, >= 2` |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 7 files, +120 / −21) wrote a
300,000-string round-trip fuzzer and fixed eight of the nine bugs, plus things
outside the task (names ending in `_`, licence expressions, `direct_url`
credentials). It missed the one bug where the starting state rejects valid
input rather than accepting invalid input: a requirement with `===1.0`
followed by a comma and a spaced specifier. Its fuzzer only checked that what
parses round-trips, not that everything valid parses.

**Attempt 2** (`difficulty/attempt-2.patch`, 8 files, +196 / −34) went the
same way: eight of nine, many extras (escape sequences in marker strings,
licence tokens, an iterative fallback for `dependency_groups`), and the same
miss. Its report says it left "`===` versions may contain anything, including
commas" alone because existing tests require it. They don't: the visible
tests require `foo===arbitrarystring,>=1` to parse as two specifiers and
`demo===x,y` to fail on the specifier `y`, so the comma separates specifiers.
I checked this before counting the failure.

It also showed a mistake in my verifier. The first version of the metadata
test split the output with `str.splitlines()`, which treats `\u2028`, `\x85`
and similar characters as line breaks. The email parser in this Python
(3.12.16, which has the CVE-2024-6923 fix) doesn't, so attempt 2's output,
which leaves those characters alone, is read back exactly, with no extra
header. On this interpreter only `\r` actually lets a value break out. The
test now reads the output back with `parse_email` and `email` instead, and I
re-graded both attempts: attempt 1 is unaffected, attempt 2 went from 39/48 to
47/48. Both still fail on `===`.

**Attempt 3** (`difficulty/attempt-3.patch`, 11 files, +334 / −98) was the
most ambitious: it rewrote the marker parser, `str()` and `evaluate()` to use
an explicit stack so any nesting depth works, and fixed a character-class bug
in `direct_url.py` (`0-9-_` includes the range `9` to `_`). It still missed
the same bug as the other two.

### What I make of it

- All three attempts found the eight bugs where packaging accepts or mangles
  bad input, and all three missed the one where it rejects good input. Each
  attempt's own checking (fuzzers, round-trip tests) asked "does what parses
  behave?", never "does everything valid parse?".
- As with anyio and the Flask/Werkzeug task, the difficulty rests mostly on
  one bug. I'd describe the task that way.
- Two of my own tests needed fixing during the check (the metadata reading
  and, in the Flask task, an exception type). Both were too strict, both were
  found by reading attempts' failures, and both were fixed before scores were
  recorded.

