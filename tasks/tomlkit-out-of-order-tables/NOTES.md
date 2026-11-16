# Notes

## Where the bugs come from

- Repo: https://github.com/python-poetry/tomlkit
- Base commit: `7bf7284dbd622557d9909f8fee017a4cb169a139` (13 November 2026)
- Reverted, in the order they landed:

| Commit | PR | What it fixed | Lines |
|---|---|---|---|
| `229ee86` | #565 | `[a.b.c]` then `[a]` with `b.z = 1` rejected as "Redefinition", although it's valid TOML | 3 |
| `398c53e` | #663 | `AttributeError: 'OutOfOrderTableProxy' object has no attribute 'trivia'` when a table is defined out of order under an indented header four or more levels deep | 2 |
| `bb7cdd5` | #699 | adding a key through the proxy for a split table didn't record which part it went into, so deleting or replacing it afterwards crashed | 15 |
| `55d0768` | #677 | `update()` on a split table dropped whole later parts, and the unrelated keys in them | 6 |
| `29c31d2` | #702 | a table split around an `[[array]]` was written back in a different order | 1 |

`environment/starting_state.patch` reverts all of it: the code, the tests those
PRs added, and their two changelog lines. After that, the library's whole suite
(1,407 tests) still passes. So the solver's own test suite doesn't give
anything away.

The Dockerfile deletes `.git` after applying the patch, so the history with
these commits can't be read from the sandbox.

## Why I picked it

After four rejected candidates I had a rule: a task is easy if the agent can
check its own answer mechanically. Here the rule in the statement is
completely clear ("behave like `tomllib`"), and `tomllib` ships with Python, so
in principle the agent can check itself. But checking requires *inputs*, and
each of these bugs needs its own particular document shape:

- an `[[array]]` between two parts of a table;
- an implicit super-table extended by a dotted key;
- an indented header nested at least four levels deep;
- adding a new key and then deleting it through the same proxy;
- `update()` with two keys that each live in different parts.

To find these, you have to understand how `OutOfOrderTableProxy` works and
which code paths it has. Fixing the one example from the statement isn't
enough, and random generation rarely produces shapes like these.

The second difference from my earlier tasks: the statement names one symptom,
not five, and it doesn't enumerate cases. It does say that there are more bugs
and gives the contract they all violate. I think that's fair. It's how a real
bug report reads ("this broke, and other odd things keep happening"), and
every hidden test checks one of the four points of that contract.

## The hidden tests

`verifier/test_task.py`, 77 tests. The oracle is `tomllib` everywhere: for any
document, parsing and the result of edits are compared with what `tomllib`
says. Nothing depends on how the reference solution is written.

- **Parsing and round trip.** 15 valid documents covering all three parsing
  bugs, plus shapes that already worked. For each one, `unwrap()` must equal
  `tomllib.loads()` and `as_string()` must give back the input.
- **Invalid documents.** 4 documents that `tomllib` rejects, which tomlkit must
  reject too. This catches a lazy fix that just deletes the check.
- **Editing.** For every bug there are edits that afterwards check the data,
  the text, and that the text parses with `tomllib` to the same data. That
  covers new keys of different types (number, string, list, table, array of
  tables), replacing a value with one of a different type, and `update()` in
  both key orders.
- **Mixed sequences.** Add a key, remove it again, and the data has to match
  the original.

One thing I deliberately don't test. The old proxy object you got from
`doc["a"]` isn't required to see changes made through a new `doc["a"]`.
Upstream doesn't do that either, and the statement doesn't promise it.

## Correct and wrong solutions

`solution/reference.patch` is the five upstream fixes, code only, +18 / −13 lines in
two files.

Alternatives in `verifier/alt_fixes/`. Both pass the hidden tests and the
library's suite:

- `01_alternative_checks`: different checks for the same things (`hasattr` in
  place of `isinstance`, a different condition structure);
- `02_restructured_proxy`: a rewrite of the key-placement logic in the proxy,
  plus removing a key from later parts in a different way.

Wrong solutions in `verifier/wrong_fixes/`. All fail the hidden tests and all
pass the library's suite, except the fourth:

| Patch | What it does | Hidden tests failed |
|---|---|---|
| 01 | fixes only the bug from the statement | 48 |
| 02 | everything except the indented-header crash | 6 |
| 03 | everything except key tracking in the proxy | 16 |
| 04 | everything, but deletes the "Redefinition" check outright instead of narrowing it, so invalid TOML gets through | 2 (also fails 4 of the library's tests) |
| 05 | everything, but `update()` clears later parts instead of removing one key | 18 |

How much each upstream fix is worth on its own (starting state is 51 of 77
failing):

| Only this fix | Still failing |
|---|---|
| `29c31d2` (the bug from the statement) | 48 |
| `398c53e` | 45 |
| `229ee86` | 43 |
| `bb7cdd5` | 35 |
| `55d0768` | 33 |

So fixing what the statement shows gets you almost nothing. You have to find
all five.

## Difficulty check

To save my usage limit I run attempts one at a time. If the first one solves
the task, it's rejected straight away. If it doesn't, I run one or two more.

### Attempt 1: failed (73 / 77)

The setup is the same as for my other tasks: a folder with `PROBLEM.md`, the
repo without git history, and a virtualenv. No network, no access to this
repo, one try. I graded the patch in Docker with the hidden tests. The patch
is saved in `difficulty/attempt-1.patch`.

- The library's suite: 1,417 passed (its own 1,407 plus 10 tests it added).
- Hidden tests: **73 of 77**. All 4 failures are the same bug: the
  `AttributeError` on an out-of-order table under an indented header
  (` [a.b.c.d]` then `[a.b.c]`). On those files its version still crashes
  while parsing.

It was a serious attempt: 15 minutes, about 880 lines changed across three
files, and its own random tester run against `tomllib` "on hundreds of
thousands of documents". It found and fixed four of the five bugs, and fixed
the update and new-key problems with a much bigger rewrite than upstream did.
But its generator never produced an indented header, and nothing in the
statement points to one. That's exactly the kind of failure I wanted: the
bug is covered by rule 1 of the statement ("`tomllib` accepts it, so tomlkit
must too"), but you only find it if you read the code paths around indentation
in `Table.append`.

The attempt also hit my usage limit once and was resumed from where it stopped,
with no extra information.

### What the attempt flagged as ambiguous, and what I changed

It reported two conflicts between the statement and the library's existing
tests:

- an array of tables split by other tables (`[[products]]` … `[foo]` …
  `[[products]]`) is written back reordered, and an existing test requires it;
- when a split table becomes empty, an existing test expects it to disappear
  from the output instead of staying as `{}`.

Both points are fair. The statement promised a byte-for-byte round trip and
exact data for *any* document, and the existing tests pin down different
behaviour in these two corner cases. Neither is covered by my hidden tests, so
the score isn't affected. I still added one sentence to `PROBLEM.md`: when the
existing tests pin down behaviour that conflicts with the list, keep the tested
behaviour. This was the only change made after the attempt, and it doesn't
change what the hidden tests check.

### Attempt 2: passed (77 / 77)

This one got the statement with the added sentence. Patch:
`difficulty/attempt-2.patch`.

- The library's suite: 1,423 passed (plus 16 of its own tests).
- Hidden tests: **77 of 77**.

It took about 34 minutes, roughly 150 tool calls, and about 940 changed lines
in three files. Like the first attempt, it wrote its own random tester against
`tomllib`, but it also generated the cases that the first one missed. In the
end it put a separate checker into the parser that follows `tomllib`'s rules,
and rewrote the split-table proxy. That's a much bigger rewrite than the five
upstream fixes, which come to 31 changed lines.

### Score so far

1 passed out of 2. The bar is at most 1 of 3, so the third attempt decides:
if it fails, the task is accepted (1 of 3); if it passes, it's rejected.
