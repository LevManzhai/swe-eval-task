# `portion.IntervalDict`: logarithmic single-key operations

A performance task on a real library:
[`portion`](https://github.com/AlexandreDecan/portion), a Python library for
interval arithmetic. Its `IntervalDict` (a mapping from intervals to values)
scans its whole content on every lookup, assignment and deletion. The task is
to make single-key operations logarithmic **without changing anything that is
observable through the public API**.

The solver gets the repository at a pinned commit and
[`task/PROBLEM.md`](task/PROBLEM.md). The patch is graded by a hidden test
suite that counts comparisons instead of measuring time, and that compares the
behaviour of the patched class with the original one on long random operation
sequences.

## Why it is not a one-line change

The class stores one key per *distinct value*: when two intervals share a
value they are merged into a single, non-atomic key (a union of intervals).
This is documented, and it is visible everywhere: `len()`, `keys()`,
`items()`, `repr()`, `as_dict()`, `popitem()`.

That representation is exactly what makes the obvious optimisation wrong. The
storage is a sorted dict ordered by the lower bound of each key, which invites
a binary search — but the keys interleave (`even` covers `[0,1) | [2,3) | …`,
`odd` covers `[1,2) | [3,4) | …`), so being sorted by lower bound says nothing
about which key contains a given point. A correct solution has to change the
internal representation to disjoint atomic intervals and then *reconstruct*
the documented per-value view on demand, while preserving:

- grouping by **equality**, not by hash (values only need to support `==`;
  lists and dicts are valid values);
- the order of keys, and the merging of adjacent intervals inside a key;
- live `keys()` / `values()` / `items()` views;
- support for `Interval` subclasses (discrete intervals merge `[0,1]` and
  `[2,3]` into `[0,3]`);
- open/closed bounds at touching points, infinities, non-atomic keys.

See [`NOTES.md`](NOTES.md) for the full analysis, the wrong solutions the
verifier is built to reject, and the result of the difficulty check.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | The problem statement given to the solver. |
| `environment/Dockerfile` | Starting environment: pinned Python, `portion` at the pinned commit, pinned dependencies, plus a pristine copy of the original class used as the oracle. |
| `environment/requirements.txt` | Exact `==` pins. |
| `solution/reference.patch` | Reference solution (unified diff against the starting commit). |
| `verifier/test_task.py` | Hidden test suite: documented behaviour, differential tests, comparison budgets. |
| `verifier/alt_fixes/` | Two structurally different correct solutions; both must pass. |
| `verifier/wrong_fixes/` | Seven plausible but wrong or incomplete solutions; all must fail. |
| `run.sh` | Builds the image and checks the whole matrix above. |
| `NOTES.md` | Design notes, justification of every hidden check, difficulty check. |

## Running the self-check

Requires Docker.

```bash
./run.sh
```

It builds the image, then verifies that the starting state passes the upstream
tests but fails the hidden verifier, that the reference and both alternative
solutions pass both, and that every wrong solution fails the hidden verifier.
All test runs happen with networking disabled. The script exits non-zero if
any expectation is violated.

## Grading a candidate patch

```bash
docker build -t portion-intervaldict-task environment
docker run --rm --network none \
    -v "$PWD/verifier/test_task.py:/workspace/verifier/test_task.py:ro" \
    -v "/path/to/candidate.patch:/workspace/candidate.patch:ro" \
    portion-intervaldict-task \
    bash -c "git apply /workspace/candidate.patch \
             && cd /workspace/verifier \
             && python -m pytest test_task.py -q -p no:cacheprovider -p no:benchmark"
```

## Licence

`portion` is distributed under the LGPL-3.0-or-later licence. The patches in
this directory are derivative works of `portion/dict.py` and are provided under
the same licence. This repository does not redistribute the library itself:
the Dockerfile fetches it from upstream.
