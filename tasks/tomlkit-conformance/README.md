# tomlkit: fifteen conformance bugs, one symptom in the report

> **Status: difficulty check in progress, 0 of 1 attempts passed so far.** See the end of
> [`NOTES.md`](NOTES.md).

This is the third version of the tomlkit task, and it's built around what I
learned from the first two:

- In [the first version](../tomlkit-out-of-order-tables), the one attempt that
  failed missed a bug with a **rare trigger**: a table header indented four
  levels deep. Its random tester never generated that shape.
- In [the second version](../tomlkit-table-structure), I added more bugs, but
  their triggers were ordinary operations, and I had to list those operations
  in the statement. The attempt's fuzzer covered them and it passed.

So this version keeps the contract-based statement and adds more bugs whose
triggers are rare, spread across the whole library instead of one area:

| # | Upstream fix | Rare trigger |
|---|---|---|
| 1 | `29c31d2` #702 | a table split around `[[array]]` (the only bug shown in the statement) |
| 2 | `229ee86` #565 | `[a.b.c]`, then `[a]` with `b.z = 1` |
| 3 | `398c53e` #663 | an out-of-order table under an **indented** header four levels deep |
| 4 | `bb7cdd5` #699 | add a key through a split-table proxy, then delete or replace it |
| 5 | `55d0768` #677 | `update()` with two keys living in different parts |
| 6 | `d41d237` #631 | slice assignment on an array of tables |
| 7 | `85d391e` #664 | empty a dotted prefix inside an inline table |
| 8 | `67d3e86` #549 | replace a dotted key with an array of tables |
| 9 | `0666206` #701 | a `datetime` whose UTC offset has **seconds** (`zoneinfo` gives these for old dates) |
| 10 | `446d6fa` #628 | `+NaN` / `-Inf` with uppercase letters is accepted |
| 11 | `61941de` #612 | `+` on a string item doesn't escape `"` or `\` |
| 12 | `8c30fc1` #599 | `del arr[-2:]` or another negative or open slice on an array |
| 13 | `669d4d6` #705 | a comment containing a control character |
| 14 | `7ab7469` #586 | `0E5` (uppercase `E` after a zero) is rejected |
| 15 | `43668dd` #533 | add a key after a dotted entry on the **last line, with no newline** |

All of these were fixed upstream between June and November 2026.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees: one symptom and the contract |
| `environment/` | pinned Dockerfile plus `starting_state.patch`; the git history is removed |
| `solution/reference.patch` | the fifteen upstream fixes, code only |
| `verifier/test_task.py` | 172 hidden tests, with `tomllib` as the oracle |
| `verifier/alt_fixes/` | two correct solutions written differently; must pass |
| `verifier/wrong_fixes/` | eleven patches that must fail: ten each miss one bug, and one deletes a check |
| `run.sh` | builds the image and checks all of the above |

## Running it

You need Docker.

```bash
./run.sh
```
