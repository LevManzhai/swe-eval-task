# `IntervalDict` gets slower with every interval it holds

## Observed behaviour

We use `portion.IntervalDict` as a lookup table from ranges to records: a few
thousand disjoint ranges, queried and updated one key at a time. Every one of
these single-key operations walks through the content of the mapping, so the
cost of *one* lookup or *one* assignment grows with the number of intervals
already stored. Filling the table one assignment at a time is quadratic, and
it is the hot spot of our service.

The effect is easy to see without a clock, by counting how many comparisons
the library performs on our keys:

```python
import portion as P

COMPARISONS = 0


class Key:
    """An integer-like bound that counts the comparisons it takes part in."""

    def __init__(self, x):
        self.x = x

    def __hash__(self):
        return hash(self.x)

    def _cmp(self, other, op):
        global COMPARISONS
        if not isinstance(other, Key):
            return NotImplemented
        COMPARISONS += 1
        return op(self.x, other.x)

    def __eq__(self, other): return self._cmp(other, lambda a, b: a == b)
    def __ne__(self, other): return self._cmp(other, lambda a, b: a != b)
    def __lt__(self, other): return self._cmp(other, lambda a, b: a < b)
    def __le__(self, other): return self._cmp(other, lambda a, b: a <= b)
    def __gt__(self, other): return self._cmp(other, lambda a, b: a > b)
    def __ge__(self, other): return self._cmp(other, lambda a, b: a >= b)


d = P.IntervalDict()
for i in range(4096):
    d[P.closedopen(Key(10 * i), Key(10 * i + 5))] = f"record-{i}"

for label, operation in [
    ("lookup", lambda: d[Key(40_002)]),
    ("membership", lambda: Key(40_002) in d),
    ("assignment", lambda: d.__setitem__(Key(40_007), "new")),
    ("deletion", lambda: d.__delitem__(Key(40_002))),
]:
    COMPARISONS = 0
    operation()
    print(label, COMPARISONS)
```

Each of the four lines printed at the end is in the thousands or tens of
thousands, and the numbers double when the table is twice as large. The same
happens when the table holds only a couple of distinct values spread over
thousands of ranges (e.g. `"free"` / `"busy"` alternating): the mapping then
has few keys, but each operation still has to go through all the ranges.

## Expected behaviour

Operations on a single key should only look at the part of the mapping that
is near that key, the way a search tree or a sorted array would.

Concretely, on an `IntervalDict` holding about 4000 disjoint intervals,
**each** of the following must perform **at most 1000 comparisons**, counting
both the comparisons on interval bounds (as in the script above) and the
equality tests on stored values:

- with a single value as key: `d[x]`, `x in d`, `d.get(x)`, `d[x] = v`,
  `del d[x]`, `d.pop(x)`, `d.setdefault(x, v)` — whether or not the key is
  present, and whether the assigned value is new or already stored somewhere
  else in the mapping;
- with an interval as key, when that interval overlaps only a handful of the
  stored intervals: `d[i]`, `d[i] = v`, `del d[i]`.

This must hold for every such operation individually (not on average, and not
only for keys that were queried before), including right after the mapping
was modified, and regardless of how many distinct values the mapping holds
(thousands of distinct values, or two). Building such a mapping one
assignment at a time must stay under 1000 comparisons per assignment on
average.

Operations that inherently involve the whole mapping (iteration, `keys()`,
`values()`, `items()`, `len()`, `domain()`, `find()`, `as_dict()`,
`combine()`, `==`, `repr()`, `copy()`, ...) are not subject to this limit.

## Constraints

- This is a pure performance change. Everything that can be observed through
  the public API of `IntervalDict` — as described in the README and the
  docstrings, and as exercised by the existing test suite — must stay exactly
  as it is today, for every kind of key, bound, value and `Interval` subclass
  that is supported today.
- No new dependency. The existing ones may be used.
- The existing test suite (`pytest` at the root of the repository) must keep
  passing.
