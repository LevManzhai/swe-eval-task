# portion: make `IntervalDict` fast without changing what it does

> **Status: rejected.** The task builds and the verifier works, but two
> separate one-shot attempts both solved it, so it didn't clear my difficulty
> bar. The reasons are in [`NOTES.md`](NOTES.md).

[portion](https://github.com/AlexandreDecan/portion) is a Python library for
working with intervals. One of its classes, `IntervalDict`, maps intervals to
values. Every lookup or write goes through the entire mapping, so with a few
thousand intervals stored, a single `d[x]` costs thousands of comparisons.

The task: make single-key operations logarithmic, and keep every result the
public API returns exactly the same as before.

## Why I expected it to be hard

`IntervalDict` keeps one key per distinct value. When two ranges hold the same
value, their keys get merged into one union. The README documents this, and
it shows up in `len()`, `keys()`, `items()` and `repr()`.

The storage is already sorted, so the obvious move is a binary search. That
answer is wrong, because the merged keys interleave: `"even"` covers
`[0,1) | [2,3) | [4,5)` and `"odd"` covers `[1,2) | [3,4)`, so finding the
nearest key tells you nothing about which key actually contains your point.
That broken version still passes all 233 of the library's own tests.

To do it properly you have to store the data a different way, then rebuild the
documented "one key per value" view out of it, without breaking any of these:

- values only need `==` to be stored, so lists have to work and you can't
  group values by hash alone;
- `keys()`, `values()` and `items()` are live views;
- subclasses of `Interval`, like integer intervals where `[0,1]` and `[2,3]`
  merge into `[0,3]`, must keep working;
- open and closed bounds where two intervals touch.

## How it's checked

The hidden tests use three methods:

- examples taken directly from the library's README;
- random sequences of operations run on both the new class and an untouched
  copy of the original, comparing every result;
- counting comparisons, not timing anything. Interval bounds are a small class
  that increments a counter every time it is compared. Each operation on a
  4096-interval mapping is allowed at most 1000 comparisons. The original code
  needs up to about 20,000, and my solution about 200.

## Running it

You need Docker.

```bash
./run.sh
```

It builds the image and then confirms that:

- the original code fails the hidden tests;
- my solution and two alternative ones pass;
- all seven wrong solutions fail.

To grade a patch of your own:

```bash
docker build -t portion-task environment
docker run --rm --network none \
    -v "$PWD/verifier/test_task.py:/workspace/verifier/test_task.py:ro" \
    -v "/path/to/your.patch:/workspace/candidate.patch:ro" \
    portion-task \
    bash -c "git apply /workspace/candidate.patch && cd /workspace/verifier && python -m pytest test_task.py -q -p no:benchmark"
```

portion is LGPL-3.0. The Dockerfile clones it from GitHub; this repo doesn't
include the library itself.
