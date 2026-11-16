# Notes

## The idea

What decides whether an attempt passes on a bug hunt like this is whether its
own testing reaches every bug. All the strong attempts so far wrote a random
tester against `tomllib`. A random tester only covers what its author thought
to generate. The one failed attempt, on the first version, missed a single
bug: an indented header, a shape its generator never produced.

If each bug with a rare trigger has some chance of being missed, then the more
of them there are, the lower the chance an attempt catches them all. So this
version has fifteen bugs, and most of their triggers are not about table
structure at all:

- a time offset in seconds;
- uppercase `NaN`;
- `0E5`;
- a control character in a comment;
- `+` on a string;
- a negative slice in `del`;
- a dotted entry on the last line with no newline.

## Where the bugs come from

- Repo: https://github.com/python-poetry/tomlkit, base commit `7bf7284`
  (13 November 2026).
- Fifteen upstream fixes are reverted: their code, their tests, and their
  changelog lines. They're listed in the [README](README.md). I picked them by
  three criteria:
  - they revert cleanly together;
  - after the revert the library's whole suite (1,228 tests) passes, so
    nothing in it gives a bug away;
  - every bug violates one point of the contract in `PROBLEM.md`.

  I didn't take fixes that only change formatting (spaces, quote style) or
  only reorder dict keys. They don't follow from the contract, so asking for
  them would be unfair.
- The git history is removed.

## The statement

It shows **one** symptom, the pyproject example, and then gives the contract:

1. valid TOML is parsed and invalid TOML is rejected;
2. an unmodified document round-trips byte for byte;
3. after any change through the public API, the document is valid and holds
   exactly the data written. If a change isn't possible, it raises an
   exception, and the document is still valid.

The statement says in plain words that there are other bugs and that they
"don't seem to come from one place". I think that's fair: every hidden test
checks one point of the contract, and that's how real bug reports are written.

To keep it unambiguous, two clarifications are written out explicitly:

- an aware datetime counts as the same data if it denotes the same instant;
- where the existing tests pin down different behaviour, keep it.

## The hidden tests

There are 172 tests in `verifier/test_task.py`: the 100 from the second
version plus 72 new ones. Every check compares the result with what `tomllib`
says. I removed two cases after writing them, because upstream doesn't pass
them either:

- `+ "\x7f"` on a *literal* string;
- a dotted key three levels deep on the last line without a newline.

Those are remaining upstream bugs, and I can't ask for more than the reference
does.

## Correct and wrong solutions

All checked in Docker by `run.sh`; every expectation holds.

- `solution/reference.patch`: the fifteen upstream fixes. 172 / 172.
- `alt_fixes/01`, `02`: the alternatives from the earlier versions plus the
  new upstream fixes. 172 / 172 each.
- `wrong_fixes/01`: only the bug from the statement. Fails 108.
- `wrong_fixes/02`–`10`: every bug fixed except one. Each fails 2 to 10
  tests, and each passes the library's whole suite.
- `wrong_fixes/11`: deletes the "Redefinition" check outright instead of
  narrowing it.

Each of the fifteen fixes on its own leaves 97 to 113 of the 172 failing, so
every bug is checked independently of the others.

## Difficulty check

The setup is the same as before: a folder with `PROBLEM.md`, the repo without
history, and a virtualenv. No network, one try each. Attempts run one at a
time, and I stop as soon as the result is decided: two passes means rejected,
two fails means accepted.

### Attempt 1: failed (162 / 172)

Patch: `difficulty/attempt-1.patch`. The library's suite passed (1,299,
including 71 tests of its own), and the hidden tests passed **162 of 172**.

All 10 failures are the same bug: `+NaN`, `-Inf` and other *signed*
uppercase special floats are still accepted. (An unsigned `NaN` was already
rejected before, so a quick check with no sign shows nothing wrong.) Its
version still parses `v = +NaN` as `nan`, and `tomllib` rejects that. So it's
a real missed bug, not a disagreement about the statement.

It was a very large attempt: about 1,750 changed lines in five files of the
library, a new module `tomlkit/_semantics.py` with a TOML rule checker, a
rewritten proxy for split tables, and fuzzers against `tomllib` for parsing,
round trips and edits. It also hit my usage limit once and was resumed from
where it stopped, with no extra information. It found and fixed 14 of the 15
bugs, including every one that was missed or nearly missed in earlier versions
(the indented header, a time offset in seconds, `0E5`, `+` on a string,
control characters in comments, a negative `del` slice, a dotted key at the
end of the file).

What it reported as ambiguous was the same as in the first version: the
existing tests pin down a few non-conforming behaviours (AoT merging,
`\r\n` in multiline strings). It kept them, as the statement asks. None of
that touches the hidden tests.

### Attempt 2: failed (166 / 172)

Patch: `difficulty/attempt-2.patch`. The library's suite passed (1,261,
including 33 tests of its own), and the hidden tests passed **166 of 172**.

All 6 failures are the same bug, and it's the one the failed attempt on the
first version also missed: a table defined out of order under an **indented**
header four levels deep (` [a.b.c.d]`, then `[a.b.c]`). On its version that
file still fails to parse with
`'OutOfOrderTableProxy' object has no attribute 'trivia'`, even though
`tomllib` accepts it.

It was the longest attempt of all: about 49 minutes and 229 tool calls, about
1,650 changed lines in six files, a new module `tomlkit/_namespace.py`, and
fuzzers against `tomllib` over random documents, mutated toml-test files and
edit sequences. In its own words: "A fuzzer only covers what it generates, so
the hidden suite may still find cases it missed." It found and fixed 14 of the
15 bugs, including the signed uppercase `+NaN` that attempt 1 missed.

What it reported as ambiguous was the same as attempt 1: the existing tests pin
down some non-conforming behaviours, and it kept them. None of that touches
the hidden tests.

## Verdict: accepted, 0 of 2

| Attempt | Hidden tests | Bug it missed | Size of solution |
|---|---|---|---|
| 1 | 162 / 172 | signed uppercase `+NaN` / `-Inf` accepted | ~1,750 lines |
| 2 | 166 / 172 | crash on an indented out-of-order header | ~1,650 lines, 49 min |
| 3 | not run | the result was already decided: at most 1 of 3 can pass | |

My bar is at most one pass in three. Two fails already meet it, so I didn't
run the third attempt.

### Why it worked this time

- **Many independent bugs, each with a rare trigger.** Both attempts got 14 of
  15. Each missed a different bug: a different blind spot in its own testing.
  That's what I was counting on. The chance of fixing *all* fifteen is the
  product of the chances of fixing each one, and with fifteen it drops fast.
- **The contract is fair, but finding the cases is up to the solver.** Both
  attempts said in their reports that they understood the contract and had
  nothing to dispute in the statement. They failed on a real bug that they
  didn't find, not on how something was worded.
- **Upstream fixes are tiny.** Both missed bugs are fixed upstream in 2–4
  lines (`398c53e`, `446d6fa`). This isn't about the volume of work. It's
  about whether you know to look in that particular place.
