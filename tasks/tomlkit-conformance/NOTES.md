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

_In progress._
