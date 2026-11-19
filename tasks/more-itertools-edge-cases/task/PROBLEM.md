# more-itertools: edge cases handled inconsistently

The repository in `/workspace/repo` is
[more-itertools](https://github.com/more-itertools/more-itertools), the
library of iterator building blocks that pip, setuptools and many other
projects depend on.

## What a user reported

> ```python
> >>> r = numeric_range(0.0, 1.0, 0.1)
> >>> list(r)[3]
> 0.30000000000000004
> >>> 0.30000000000000004 in r
> False
> ```
>
> The range says it doesn't contain a value it just gave us. Our code checks
> membership before looking values up, so it skips them.

## What we want

Fix that, and treat it as one example of a wider problem: many functions in
the library handle rare but legitimate input in ways that don't match their
documentation, their siblings, or the built-ins they are modelled on. We want
the following to hold across the library:

1. **Sizes and counts are validated consistently.** A size, count or window
   that makes no sense raises `ValueError` (or `TypeError` for a value that
   isn't an integer at all; whatever Python accepts as an integer index
   counts as one), before anything is produced, the way the library's other
   size arguments already do. Functions that do the same job
   with different strategies (eager or lazy, even or uneven) agree on every
   size, zero included.
2. **What the caller passes is used as passed.** `None` means "not given".
   Any other value, such as a key function, a validator or an exception to
   raise, is used even if it happens to be falsy.
3. **Errors from the caller's code propagate.** An exception raised by the
   caller's iterable or callable reaches the caller unchanged; the library
   doesn't swallow it or reinterpret it.
4. **`numeric_range` behaves like `range`.** Its length, membership, `index`,
   `count`, equality, hashing and slicing agree with the items it actually
   produces, for every numeric type it supports and for ranges of any size.
5. **Iteration is lazy and empty input gives empty output.** No function reads
   more of an iterable than it needs, and no function invents items when
   given nothing.
6. **`running_min` and `running_max` agree with `min` and `max`.** Each value
   they produce is the item that `min` or `max` would return for the same
   window.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is (`python -m unittest`). It doesn't cover
  these cases.
- Your changes are graded by hidden tests that use the public API of
  `more_itertools` only.
