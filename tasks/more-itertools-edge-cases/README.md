# more-itertools: edge cases handled inconsistently

> **Status: accepted.** Three of three one-shot attempts failed (549, 549 and
> 554 of 558). Each missed at least two bugs. `run.sh` passes all 38 of its
> checks. Details at the end of [`NOTES.md`](NOTES.md).

[more-itertools](https://github.com/more-itertools/more-itertools) is the
library of iterator building blocks that pip, setuptools and many other
projects depend on. During 2026 upstream fixed a run of bugs where functions
handled rare input differently from their documentation, their siblings or
the built-ins they mirror. I took more-itertools as of 17 November 2026 and
reverted sixteen of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| `numeric_range` | `0.30000000000000004 in numeric_range(0.0, 1.0, 0.1)` | `False`, though the range yields it |
| `numeric_range` | float ranges whose division and items disagree | `len()` counts an item it never yields, or misses one |
| `numeric_range` | `numeric_range(2, 3, 1) == numeric_range(2, 3, 5)` | `False`, where `range` says `True` |
| `numeric_range` | slicing with a negative step | an empty range |
| `peekable` | `p[5::-1]` on a long or infinite iterator | reads the whole iterator |
| `ichunked`, `chunked_even` | size 0 | an `islice` error, where `chunked` returns nothing |
| `sliced` | a negative size | returns wrong slices |
| `constrained_batches` | `max_count=0` or negative | ignored |
| `running_min/max/mean/statistics` | `maxlen=2.5`, or an `__index__` object | accepted, or rejected |
| `running_min`, `running_max` | equal values in a window (`1.0` and `1`) | returns a different item than `min`/`max` |
| `all_unique` | a key function that is falsy | the key is ignored |
| `bucket` | a validator that is falsy | the validator is ignored |
| `one`, `only` | a `too_short`/`too_long` exception that is falsy | a generic `ValueError` instead |
| `value_chain` | an iterable that raises `TypeError` midway | the error is swallowed and the object is yielded |
| `interleave_evenly` | no iterables | `IndexError` |
| `split_before/after/when` | `maxsplit=0` on empty input | yields `[[]]` instead of nothing |

The problem statement shows **only the first row** and a six-point contract.

## Why this one

Same recipe as the other tasks in this repository: many bugs, each with an
unusual trigger, in a widely used library whose own suite passes without
noticing them, and no oracle in the sandbox.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | more-itertools at commit `c0ede7f`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 558 hidden tests through the public API |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | sixteen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. more-itertools is MIT-licensed; the Dockerfile clones it
from GitHub.
