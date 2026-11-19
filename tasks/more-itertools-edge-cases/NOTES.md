# Notes

## Where the bugs come from

- Repo: https://github.com/more-itertools/more-itertools
- Base commit: `c0ede7fcd50340170bc7f428b7b658f6e767a34c` (17 November 2026)

| Commit | Date | What it fixed |
|---|---|---|
| `fbd5513` | 2026-10-26 | `chunked_even` rejects a negative size and returns nothing for 0, like `chunked` |
| `e6ce1b0` | 2026-10-11 | `peekable[i::-1]` reads only up to `i`, not the whole iterable |
| `71e070b` | 2026-10-07 | `all_unique` uses a key function that is falsy |
| `67fcf64` | 2026-10-06 | `bucket` uses a validator that is falsy |
| `f89d7a3` | 2026-09-29 | `ichunked` agrees with `chunked` for 0 and rejects negative sizes |
| `d032cab` | 2026-09-09 | `constrained_batches` rejects `max_count <= 0` |
| `670b715` | 2026-09-07 | `running_min/max/mean/statistics` validate `maxlen` through `__index__` |
| `ce676d2` | 2026-09-04 | `split_before/after/when(maxsplit=0)` give nothing for empty input |
| `7847d43` | 2026-09-03 | `value_chain` lets a `TypeError` from iteration through |
| `dc2664b` | 2026-09-02 | `numeric_range` length, membership and `index` agree with its float items |
| `def2dab` | 2026-08-30 | `one`/`only` raise a user exception that is falsy |
| `069b300`, `c629214` | 2026-07-16, 2026-10-31 | `numeric_range` equality and hashing follow `range`, also above `sys.maxsize` |
| `d992be0` | 2026-07-12 | windowed `running_min`/`running_max` return the same item as `min`/`max` |
| `958990e` | 2026-07-02 | `sliced` rejects a negative size |
| `f51a53b` | 2026-06-29 | `interleave_evenly([])` returns nothing instead of raising `IndexError` |
| `a51da82` | 2026-02-20 | `numeric_range` slices with a negative step are correct |

Fourteen reverse cleanly. `71e070b` and `d992be0` were reverted by hand,
because later commits rewrote the same lines. `069b300` and `c629214` touch
the same methods and count as one bug: in the starting state the second has
nothing left to fix on its own.

Tried and taken back out:

- `0e6acdf` (`chunked` rejects a negative size): with the other fixes reverted,
  `chunked` already raises `ValueError` for a negative size, from `islice`.
  There is nothing to test, so it stays fixed.
- `71b46b0` (`windowed(n=0)` raises): this changes documented behaviour (it
  used to yield one empty tuple) rather than fixing a bug, so it stays.
- The `seekable(maxlen=0)` fixes, `combination_with_replacement_index`, and
  the `numeric_range` reverse-iteration fixes: they don't revert onto the
  current code without rewriting it.

The starting state keeps upstream's suite. Tests that the fixes added are
removed, and tests they changed are put back as they were before the fix.
Three more removals: two test cases that pin a fixed behaviour
(`numeric_range` single-item equality, negative-step slicing), and five test
methods whose fix commits didn't revert cleanly. The 11.2.0 entries in
`docs/versions.rst` that describe these fixes are removed. Fixed docstrings
are reverted with the code.

## The hidden tests

`verifier/test_task.py`, 558 tests (most are parametrized `numeric_range`
cases, compared with `range` or with the range's own items). Only the public
API is used. The laziness tests feed `peekable` an iterator that fails after a
fixed number of items, so a wrong solution fails instead of filling memory;
`run.sh` also caps containers at 2 GB.

Before any attempt ran, I loosened two tests so they don't depend on choices
the statement leaves open:

- a non-integer window size may raise `TypeError` or `ValueError`;
- hashing is checked as "equal ranges hash equal", not against `range`'s hash
  values.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and
sixteen wrong solutions against the upstream suite (`python -m unittest`,
909 tests) and the hidden tests.

- `verifier/alt_fixes/01_split_validator_and_empty_variants.patch` writes the
  `split_*` fix, the `bucket` validator default and the empty
  `interleave_evenly` check differently.
- each wrong solution fixes everything except one bug.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 23 min, 70 tool calls | **failed**, 549 / 558 | `split_*(maxsplit=0)` on empty input; `peekable[i::-1]` reads everything; `running_statistics` window `size` |
| 2 | 21 min, 73 tool calls | **failed**, 549 / 558 | the same three |
| 3 | 26 min, 103 tool calls | **failed**, 554 / 558 | `split_*(maxsplit=0)` on empty input; `running_statistics` window `size` |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 2 files, +563 / −199),
**attempt 2** (`difficulty/attempt-2.patch`, 2 files, +556 / −167) and
**attempt 3** (`difficulty/attempt-3.patch`, 2 files, +487 / −182) each
rewrote `numeric_range` (all of its hidden tests pass for all three),
validated size arguments across dozens of functions, and fixed the falsy
arguments, the swallowed errors, `interleave_evenly([])` and the
`running_min`/`running_max` ties. What they missed:

- `split_before([], pred, maxsplit=0)` gives `[[]]` while
  `split_before([], pred)` gives `[]`. Attempt 1 says it left the `split_*`
  family alone because a test pins `split_at([]) == [[]]`; that test is about
  `split_at` without `maxsplit` and is unchanged by the fix.
- `running_statistics([1, 2, 3, 4], maxlen=WindowSize(2))`, with an object
  whose `__index__` returns 2, reports `size=<WindowSize object>` in every
  `Stats` instead of `size=2`. All three converted `maxlen` with
  `operator.index` in `running_mean`, `running_min` and `running_max` but not
  in `running_statistics`, which passes `maxlen` through to its result.
- Attempts 1 and 2: `peekable(it)[5::-1]` still reads the whole iterator
  (attempt 1 changed `peekable` slicing to read one item less, but not for an
  omitted stop with a negative step).

### What I make of it

- Unlike the other tasks, no single bug carries the result: every attempt
  fails on two separate bugs, and two attempts on three.
- The `running_statistics` case is the narrowest of the three. The statement
  says "whatever Python accepts as an integer index counts as one", and the
  same window given as `2` and as an index object gives different results.
  Without that test every attempt still fails on `split_*`.
- All three changed 650 to 760 lines where upstream's fixes change about 190.
