# NOTES

## Upstream reference

- Repository: https://github.com/AlexandreDecan/portion
- Starting commit: `2c34f2830bef51b7bba3dd52e18b95daaf9de248` (26 October 2026,
  version `2.7.0-pre2`).
- This task is **not** derived from an upstream issue or pull request. Upstream
  has never changed the representation of `IntervalDict`; the class docstring
  says in so many words that it "does not aim to have the best performance".
  There is therefore no upstream fix to look up or to remember: the reference
  solution was written for this task.

## The starting point

`IntervalDict` keeps a `SortedDict` that maps **one key per distinct value** to
that value. When two intervals hold equal values, their keys are merged into a
single non-atomic `Interval` (a union). The dict is sorted by the lower bound
of each key.

Consequences for single-key operations:

| Operation | What the code does | Cost |
|---|---|---|
| `d[x]` | walks the keys in order until `x < key.lower` | linear in the number of values |
| `x in d` | builds `d.domain()` (union of all keys), then tests | linear, always |
| `d[k] = v` | walks **all** keys: compares `v` with each value, and subtracts `k` from each overlapping key | linear, always |
| `del d[k]` | walks the keys until `k.upper < key.lower` | linear |

With thousands of distinct values these are thousands of comparisons each.
With only two values alternating over thousands of ranges, the dict has two
keys, but each key is a union of thousands of atomic intervals, and
`key | interval` / `key - interval` rebuild that union on every write.

## Why this is hard

The statement is short and the goal is obvious. The difficulty is that the
current representation is *also the documented public behaviour*, so it cannot
simply be replaced:

1. **The inviting fix is wrong.** The storage is already sorted by lower bound,
   so a binary search looks like a five-line change. It is incorrect: keys are
   unions and they interleave. With `even = [0,1) | [2,3) | [4,5)` and
   `odd = [1,2) | [3,4)`, the key with the greatest lower bound not above `3.5`
   is `odd`, and `3.5 in odd` happens to be true — but for `4.5` the same search
   also lands on `odd`, which does not contain it. The existing test suite does
   not catch this (`wrong_fixes/01` passes all 233 upstream tests).

2. **Writes are the real problem, and they force a new representation.** Making
   reads fast with an auxiliary index is easy; `d[k] = v` still has to find
   "the key that already holds `v`" and rebuild a union. Getting writes under
   the budget requires storing disjoint *atomic* intervals and dropping the
   per-value key from the write path altogether.

3. **The per-value view then has to be reconstructed exactly.** `len(d)`,
   iteration, `keys()`, `values()`, `items()`, `repr()`, `as_dict()`,
   `popitem()`, `find()`, `==` all expose one entry per distinct value, sorted
   by the lower bound of the merged key, with adjacent pieces merged inside a
   key. All of this is described in the README ("return exactly one element for
   each stored value (i.e., if two intervals share a value, they are merged into
   a disjunction)").

4. **Values are grouped by equality, not by hash.** The README states that "any
   value can be stored […] as long as it supports equality". Lists and dicts
   are valid values. The natural way to regroup atomic pieces by value is a
   `dict` keyed by value, which raises `TypeError` on the first list.

5. **Views are live.** `keys()`, `values()` and `items()` currently return
   views of the internal `SortedDict`; the existing test `test_views` checks
   that a view obtained before a mutation reflects it afterwards. Once the
   internal storage is no longer per-value, these views have to be written.

6. **`Interval` subclasses.** `IntervalDict._klass` selects the interval class;
   `portion.create_api` relies on it. With a discrete integer interval class,
   `[0,1]` and `[2,3]` are adjacent and merge into `[0,3]`, and open bounds are
   normalised to closed ones. A solution that builds keys with the base
   `Interval` class silently loses this.

7. **Boundary cases of the search itself.** `[0,1)` followed by `(1,2)` leaves
   the single point `1` unmapped; `[0,1]` followed by `(1,2)` does not. The
   sort key has to distinguish closed from open lower bounds, and the search has
   to pick the right side.

None of these is exotic on its own. The task is hard because a solution has to
get all of them right simultaneously, in a single shot, against a verifier that
compares every observable result with the original implementation.

## The reference solution

`solution/reference.patch` (one file, `portion/dict.py`, about 290 changed
lines):

- storage becomes a `SortedDict` from `(lower, is_open)` to
  `(atomic interval, value)`, with pairwise disjoint intervals;
- a point lookup is one `bisect_right` plus one containment test;
- writes locate the overlapping pieces with one bisect, replace them by what
  remains after subtracting the key, insert the new piece, and merge it with
  its two neighbours when they hold an equal value;
- `_grouped()` rebuilds the per-value view on demand (hash lookup first,
  falling back to equality comparisons for unhashable values) and caches it
  until the next write;
- three small view classes provide live `keys()`, `values()`, `items()`.

Measured on a mapping of 4096 intervals (comparisons on bounds + equality tests
on values, worst case over the sampled keys):

| Operation | Original | Reference |
|---|---|---|
| `d[x]` | up to 8 197 | 32 |
| `x in d` | about 20 500 | 32 |
| `d[x] = v` | 8 220 – 12 466 | 194 |
| `del d[x]` | up to 8 314 | 178 |
| `d[small interval]` | up to 12 308 | 70 |
| building, per assignment | about 5 166 | 76 |

The limit enforced by the verifier is 1000 per operation: more than four times
what the reference needs, and eight times less than the original.

The reference changes a single file. The task was selected for the density of
invariants rather than for the number of files touched; this is a deliberate
deviation from the "at least three files" rule of thumb used when screening
candidates, and is recorded here as such.

## The verifier

`verifier/test_task.py`, 179 test cases, three groups. Only the public API is
used; no private attribute is read.

### 1. `TestDocumentedBehaviour` (13 tests)

Hand-written examples. Each one is taken from the README, or follows from it.
All of them pass on the unmodified code.

| Test | Justified by |
|---|---|
| `test_readme_walkthrough` | README, "Map intervals to data" (copied examples) |
| `test_one_element_per_stored_value` | README: "exactly one element for each stored value" |
| `test_interleaved_values_keep_one_key_each` | same sentence, applied to alternating values |
| `test_adjacent_intervals_with_equal_values_are_merged` | keys are `Interval`s, which are "automatically simplified" unions |
| `test_values_only_need_equality` | README: "as long as it supports equality" |
| `test_bound_types_at_touching_points` | `dict`-like `KeyError` semantics for single values (README) |
| `test_infinite_bounds` | README, "Interval creation" (`P.inf` and `-P.inf` are valid bounds) |
| `test_views_are_live` | docstrings of `keys`/`values`/`items` ("a view object", with a link to the dict-view documentation), existing test `test_views` |
| `test_popitem_and_clear`, `test_copy_is_independent`, `test_setdefault_and_pop_with_intervals`, `test_combine` | README: "also supports `len`, `in` and `del`, and defines `.clear`, `.copy`, `.update`, `.pop`, `.popitem`, and `.setdefault`", and the `.combine` section |
| `test_discrete_intervals` | README, "Specialize & customize intervals": `create_api` returns an `IntervalDict` "configured to use the subclass"; it does so by setting the `_klass` class attribute (see `portion/api.py` and the existing `test_discrete.py`) |

### 2. `TestDifferential` (141 tests)

Random sequences of 250 operations are applied both to the class under test
and to the **original implementation**, which the Dockerfile copies out of the
repository at build time (`/workspace/oracle/oracle_dict.py`, checksum
verified by the verifier). After every operation the full observable state is
compared: `repr`, `len`, ordered `items`/`keys`/`values`, iteration order,
`domain`, both forms of `as_dict`, view lengths; return values and `KeyError`s
are compared as well.

Four families, each with fixed seeds: hashable values, unhashable values
(lists), values that define only `__eq__`, and a discrete interval subclass.
The key generator uses a small domain (integers and half-integers in 0..13,
plus infinities) so that touching bounds, overlaps, empty intervals and
non-atomic keys all occur constantly. A fifth test builds a mapping of a few
hundred fragments on a wider domain.

Because the oracle is the unmodified code, this group cannot encode an opinion
of the task author: whatever it checks is, by construction, "what the library
does today". Three behaviours of the original are nevertheless **deliberately
not exercised**, because they are accidents rather than documented behaviour
and a reasonable correct solution may differ:

- *Which of two equal objects is kept* (`1` vs `1.0`, or two equal lists).
  Values in the generators are never equal across types, and results are
  compared with `==`, never with `is`.
- *Values that are not equal to themselves* (`float("nan")`).
- *Insertion order of the plain `dict`s returned by `as_dict()`*: they are
  compared as mappings.

Also not exercised: keys whose `Interval` class differs from the mapping's
`_klass`, pickling, and extra, undocumented methods of the `SortedDict` views
(indexing, `bisect`).

### 3. `TestCost` (25 tests)

No clock is involved. Interval bounds are instances of a class that counts
every comparison it takes part in; stored values are instances of a hashable
class that counts every equality test. The mapping holds 4096 fragments
`[10i, 10i+5)`, in two shapes: 4096 distinct values, and two alternating
values. For each of lookup (hit and miss), membership, `get`, assignment (new
value, value already stored far away, small interval), deletion, `pop`,
`setdefault` and small range queries, the **worst** count over about thirty
positions (both ends, the middle, and seeded random ones) must not exceed 1000.
The mapping is built one assignment at a time under a global budget, so a
linear implementation fails immediately instead of running for minutes.

The protocol, the size, the two shapes and the limit are all stated in
`PROBLEM.md`; nothing about the budget is hidden.

Robustness against shortcuts:

- every measured key is used for the first time, so memoising results does not
  help (`wrong_fixes/05`);
- `test_operations_stay_cheap_while_mutating` interleaves writes and reads, so
  an index that is rebuilt lazily after a write is caught (`wrong_fixes/04`);
- values are hashable *in this group only*, so that a solution is free to index
  values by hash on the fast path; unhashable values are covered by the
  differential group, where no budget applies.

## Correct solutions that must pass

| Patch | How it differs from the reference |
|---|---|
| `solution/reference.patch` | `SortedDict` of atomic pieces, neighbour merging, cached grouping with a hash fast path |
| `alt_fixes/01_parallel_lists_bisect.patch` | no `sortedcontainers` at all: two parallel Python lists and the `bisect` module, slice assignment for writes, no neighbour merging, no cache, grouping by equality only |
| `alt_fixes/02_sorted_key_list.patch` | a `SortedKeyList` of `(interval, value)` pairs with a key function, no neighbour merging, no cache |

## Wrong solutions that must fail

| Patch | What it does | Passes upstream tests? | Caught by |
|---|---|---|---|
| `01_bisect_on_merged_keys` | binary search on the existing per-value keys | yes, all 233 | differential tests (wrong results as soon as values interleave), cost tests (writes untouched) |
| `02_values_grouped_by_hash` | reference, but regroups values with a `dict` only | no (4 fail) | `test_values_only_need_equality`, unhashable and opaque differential tests |
| `03_ungrouped_pieces` | reference, but exposes the atomic pieces instead of one entry per value | no (14 fail) | most of groups 1 and 2 |
| `04_read_index_only` | original storage plus a sorted index for reads, rebuilt lazily after each write | yes, all 233 | every cost test: writes stay linear, and the first read after a write rebuilds the index |
| `05_memoised_lookups` | original code plus a cache of previous lookups | yes, all 233 | every cost test |
| `06_ignores_interval_class` | reference, but builds keys with the base `Interval` class | no (1 fails) | `test_discrete_intervals`, discrete differential tests |
| `07_touching_bounds` | reference, with the lookup bisecting on the wrong side of an open bound | yes, all 233 | `test_bound_types_at_touching_points`, differential tests |

Four of the seven pass the complete upstream test suite, which is what a solver
can run locally.

## Difficulty check

**Result: rejected. The first two attempts both passed (179/179), so the gate
(at most 1 of 3) cannot be met whatever the third one does.**

Protocol: each attempt is a fresh agent instance given a directory with
`PROBLEM.md`, the repository at the starting commit (no upstream history) and a
virtualenv; no network, no access to this repository, its notes, the verifier
or the solutions; one shot, no feedback from the hidden tests. The resulting
diff was then applied to the task image and graded with `verifier/test_task.py`
with networking disabled, exactly as `run.sh` does.

| Attempt | Upstream tests | Hidden verifier | Diff |
|---|---|---|---|
| 1 | 233 passed | **179 / 179** | `portion/dict.py` +390 / −74, changelog entry |
| 2 | 233 passed | **179 / 179** | `portion/dict.py` +513 / −77, changelog entry |
| 3 | — | — | still running when the verdict was already settled |

Attempt 1 was interrupted once by an API usage limit and resumed from where it
had stopped; it received no additional information.

### How the attempts solved it

Both arrived at the same architecture, which is neither the reference nor one
of the two alternative solutions: a sorted list of disjoint atomic intervals as
primary storage, a hash index to find an already stored equal value (with an
equality scan for unhashable values), and the original per-value `SortedDict`
kept as a lazily rebuilt, cached *view* for whole-mapping operations. Keeping
the old structure as a derived view is a neat way to make most of the
"reconstruct the documented behaviour" problem disappear: `keys()`, `items()`,
`repr()`, `as_dict()` and the views keep running on the very same code as
before.

Both were also stricter than the verifier: they preserved which of two equal
objects is kept (`1` vs `1.0`), the non-merging of NaN values, and pickling —
three things the verifier deliberately does not test.

### Why it was not hard enough

The decisive factor was not any single trap; all seven were avoided. It is that
**this kind of task lets the solver rebuild the hidden verifier**:

1. *The oracle ships with the task.* "Keep every observable behaviour" means the
   unmodified class is a complete executable specification. Both attempts
   copied it aside and wrote their own differential fuzzer before finishing
   (3 000 seeds × 4 modes in one case, 60 000 operation sequences in the other),
   covering discrete subclasses, unhashable values and open/closed bounds. Every
   trap listed above is exactly the kind of thing a fuzzer finds in seconds.
2. *The performance criterion is fully measurable by the solver.* To be fair,
   the statement gives the counting protocol, the size and the limit. Both
   attempts re-implemented the counter and measured every listed operation
   (worst case 259 and 158 comparisons against a limit of 1000).
3. *Everything is in one file.* There was nothing to locate.

So the task did require real work — a 400–500 line rewrite — but none of the
risk was hidden from the solver. A long task is not the same as a hard one.

### Was the statement ambiguous?

Each attempt was asked to report what it found underspecified. Both raised the
same substantive point: with *unhashable* values, deciding whether an assigned
value is already stored needs one equality test per distinct stored value, so
the comparison limit cannot be met there. They resolved it the way the verifier
does (budgets are measured with hashable values only; unhashable ones are only
checked for correctness), but the statement does not say so. Had the task been
accepted, `PROBLEM.md` would have needed one sentence to that effect. The other
points raised (mixed interval classes in one mapping, private `_storage`) are
outside what the verifier exercises.

### What this says about the verifier

The verifier itself held up: it accepted a fourth and a fifth implementation
that were written independently of it, with a different architecture from the
three it was developed against, and it still rejects all seven wrong ones.

