"""Hidden tests for the more-itertools edge-cases task.

Only the public API of ``more_itertools`` is used.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from fractions import Fraction
from itertools import islice

import pytest

import more_itertools as mi


class Counting:
    """An iterator over 0, 1, 2, ... that records how many items it gave."""

    def __init__(self, limit: int = 10**6) -> None:
        self.given = 0
        self.limit = limit

    def __iter__(self):
        return self

    def __next__(self) -> int:
        if self.given >= self.limit:
            raise AssertionError("read far more of the iterable than needed")
        value = self.given
        self.given += 1
        return value


class Falsy:
    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# (1) Sizes and counts
# ---------------------------------------------------------------------------


class TestNegativeSizes:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: list(mi.chunked([1, 2, 3], -1)),
            lambda: list(mi.chunked([1, 2, 3], -2, strict=True)),
            lambda: [list(c) for c in mi.ichunked([1, 2, 3], -1)],
            lambda: list(mi.chunked_even([1, 2, 3], -1)),
            lambda: list(mi.sliced([1, 2, 3], -1)),
            lambda: list(mi.sliced("abcdef", -2)),
        ],
        ids=["chunked", "chunked-strict", "ichunked", "chunked_even", "sliced", "sliced-str"],
    )
    def test_negative_size_raises_value_error(self, call) -> None:
        with pytest.raises(ValueError):
            call()

    def test_negative_size_on_empty_input_raises_too(self) -> None:
        for call in (
            lambda: list(mi.chunked([], -1)),
            lambda: list(mi.ichunked([], -1)),
            lambda: list(mi.chunked_even([], -1)),
            lambda: list(mi.sliced([], -1)),
        ):
            with pytest.raises(ValueError):
                call()


class TestZeroSizeAgrees:
    def test_chunked_zero(self) -> None:
        assert list(mi.chunked([1, 2, 3], 0)) == []

    def test_ichunked_zero_matches_chunked(self) -> None:
        assert [list(c) for c in mi.ichunked([1, 2, 3], 0)] == list(mi.chunked([1, 2, 3], 0))

    def test_chunked_even_zero_matches_chunked(self) -> None:
        assert list(mi.chunked_even([1, 2, 3], 0)) == list(mi.chunked([1, 2, 3], 0))

    def test_positive_sizes_unchanged(self) -> None:
        assert [list(c) for c in mi.ichunked(range(7), 3)] == [[0, 1, 2], [3, 4, 5], [6]]
        assert list(mi.chunked_even(range(7), 3)) == [[0, 1, 2], [3, 4], [5, 6]]
        assert list(mi.sliced("abcde", 2)) == ["ab", "cd", "e"]


class TestConstrainedBatchesCount:
    @pytest.mark.parametrize("max_count", [0, -1])
    @pytest.mark.parametrize("items", [[], [b"a", b"b"]])
    def test_nonpositive_max_count_raises(self, max_count: int, items: list) -> None:
        with pytest.raises(ValueError):
            list(mi.constrained_batches(items, 10, max_count=max_count))

    def test_max_count_one_and_none_unchanged(self) -> None:
        items = [b"a", b"b", b"c"]
        assert list(mi.constrained_batches(items, 10, max_count=1)) == [(b"a",), (b"b",), (b"c",)]
        assert list(mi.constrained_batches(items, 10)) == [(b"a", b"b", b"c")]


RUNNING = [mi.running_min, mi.running_max, mi.running_mean, mi.running_statistics]


class WindowSize:
    def __init__(self, n: int) -> None:
        self.n = n

    def __index__(self) -> int:
        return self.n


class TestRunningWindowSize:
    @pytest.mark.parametrize("function", RUNNING, ids=lambda f: f.__name__)
    @pytest.mark.parametrize("maxlen", [2.5, float("nan"), float("inf")], ids=["2.5", "nan", "inf"])
    def test_non_integer_window_is_rejected(self, function, maxlen: float) -> None:
        with pytest.raises((TypeError, ValueError)):
            list(function([1, 2, 3, 4], maxlen=maxlen))

    @pytest.mark.parametrize("function", RUNNING, ids=lambda f: f.__name__)
    def test_index_protocol_window(self, function) -> None:
        assert list(function([1, 2, 3, 4], maxlen=WindowSize(2))) == list(function([1, 2, 3, 4], maxlen=2))

    @pytest.mark.parametrize("function", RUNNING, ids=lambda f: f.__name__)
    def test_nonpositive_index_window(self, function) -> None:
        with pytest.raises(ValueError):
            list(function([1, 2, 3], maxlen=WindowSize(-1)))


# ---------------------------------------------------------------------------
# (2) Arguments the caller supplies are used as given
# ---------------------------------------------------------------------------


class FalsyKey(Falsy):
    def __call__(self, value: str) -> str:
        return value.lower()


class FalsyValidator(Falsy):
    def __call__(self, value: str) -> bool:
        return value != "b"


class FalsyError(Exception):
    def __bool__(self) -> bool:
        return False


class TestFalsyArguments:
    def test_all_unique_uses_a_falsy_key(self) -> None:
        assert mi.all_unique(["a", "A"], key=FalsyKey()) is False
        assert mi.all_unique(["a", "b"], key=FalsyKey()) is True

    def test_bucket_uses_a_falsy_validator(self) -> None:
        b = mi.bucket(["a1", "b1", "a2"], key=lambda s: s[0], validator=FalsyValidator())
        assert "b" not in b
        assert list(b["a"]) == ["a1", "a2"]
        assert list(b["b"]) == []

    def test_bucket_iteration_respects_a_falsy_validator(self) -> None:
        b = mi.bucket(["a1", "b1"], key=lambda s: s[0], validator=FalsyValidator())
        assert sorted(b) == ["a"]

    def test_one_raises_a_falsy_too_short(self) -> None:
        with pytest.raises(FalsyError):
            mi.one([], too_short=FalsyError("short"))

    def test_one_raises_a_falsy_too_long(self) -> None:
        with pytest.raises(FalsyError):
            mi.one([1, 2], too_long=FalsyError("long"))

    def test_only_raises_a_falsy_too_long(self) -> None:
        with pytest.raises(FalsyError):
            mi.only([1, 2], too_long=FalsyError("long"))

    def test_default_errors_unchanged(self) -> None:
        with pytest.raises(ValueError):
            mi.one([])
        with pytest.raises(ValueError):
            mi.one([1, 2])
        assert mi.only([], default="d") == "d"


# ---------------------------------------------------------------------------
# (3) Errors from the caller's code propagate
# ---------------------------------------------------------------------------


class TestErrorsPropagate:
    def test_value_chain_does_not_swallow_a_type_error_while_iterating(self) -> None:
        def items():
            yield 1
            raise TypeError("boom")

        out = []
        with pytest.raises(TypeError, match="boom"):
            for value in mi.value_chain(0, items()):
                out.append(value)
        assert out == [0, 1]

    def test_value_chain_type_error_from_a_class_iterator(self) -> None:
        class Broken:
            def __iter__(self):
                return self

            def __next__(self):
                raise TypeError("inside")

        with pytest.raises(TypeError, match="inside"):
            list(mi.value_chain(Broken()))

    def test_value_chain_still_treats_non_iterables_as_values(self) -> None:
        assert list(mi.value_chain(1, [2, 3], "ab", b"cd", 4.5)) == [1, 2, 3, "ab", b"cd", 4.5]


# ---------------------------------------------------------------------------
# (4) numeric_range behaves like range
# ---------------------------------------------------------------------------


INEXACT = [
    (0.0, 1.0, 0.1),
    (0.0, 3.0, 0.7),
    (1.0, 0.0, -0.1),
    (2.1, 5.1, 0.5),
    (-1.0, 1.0, 0.25),
    (10.0, -10.0, -0.7),
    (-8.732, -13.532, -2.4),
    (4.51, 10.375, 0.255),
    (-69.37276490678778, -29.8339073344664, 4.942357196540172),
    (32.50227965239458, 9.003418351482358, -1.9582384417426848),
]


class TestNumericRangeAgreesWithItsItems:
    @pytest.mark.parametrize("args", INEXACT)
    def test_len_matches_iteration(self, args) -> None:
        r = mi.numeric_range(*args)
        items = list(r)
        assert len(r) == len(items)
        if items:
            assert r[len(r) - 1] == items[-1]
            assert r[-1] == items[-1]

    @pytest.mark.parametrize("args", INEXACT)
    def test_every_item_is_contained_and_indexed(self, args) -> None:
        r = mi.numeric_range(*args)
        for i, v in enumerate(r):
            assert v in r
            assert r.index(v) == i
            assert r.count(v) == 1

    def test_values_it_does_not_produce_are_not_contained(self) -> None:
        r = mi.numeric_range(0.0, 1.0, 0.1)
        items = set(r)
        for i in range(1000):
            v = i / 1000
            if v not in items:
                assert v not in r
                with pytest.raises(ValueError):
                    r.index(v)

    def test_exact_types_unchanged(self) -> None:
        r = mi.numeric_range(Fraction(1), Fraction(5), Fraction(3, 2))
        assert list(r) == [Fraction(1), Fraction(5, 2), Fraction(4)]
        assert Fraction(5, 2) in r and Fraction(3) not in r
        d = mi.numeric_range(Decimal("1.0"), Decimal("2.0"), Decimal("0.3"))
        assert Decimal("1.9") in d and d.index(Decimal("1.6")) == 2


INT_ARGS = [
    (0, 5, 2), (0, 6, 2), (0, 7, 2), (2, 3, 1), (2, 3, 5), (2, 4, 5), (5, 0, -1),
    (5, 4, -3), (5, 4, -1), (3, 3, 1), (4, 1, 1), (0, 1, 1), (0, 1, 7), (1, 10, 3),
]


class TestNumericRangeEquality:
    @pytest.mark.parametrize("a", INT_ARGS)
    @pytest.mark.parametrize("b", INT_ARGS)
    def test_equality_matches_range(self, a, b) -> None:
        assert (mi.numeric_range(*a) == mi.numeric_range(*b)) == (range(*a) == range(*b))

    @pytest.mark.parametrize("a", INT_ARGS)
    @pytest.mark.parametrize("b", INT_ARGS)
    def test_equal_ranges_hash_equal(self, a, b) -> None:
        ra, rb = mi.numeric_range(*a), mi.numeric_range(*b)
        if ra == rb:
            assert hash(ra) == hash(rb)

    def test_single_float_items_with_different_steps(self) -> None:
        r1 = mi.numeric_range(1.5, 2.0, 1.0)
        r2 = mi.numeric_range(1.5, 2.0, 0.75)
        assert list(r1) == list(r2) == [1.5]
        assert r1 == r2 and hash(r1) == hash(r2)

    def test_not_equal_to_other_types(self) -> None:
        assert mi.numeric_range(3) != range(3)
        assert mi.numeric_range(7.0) != "abc"


BIG = 10**30


class TestNumericRangeAboveMaxsize:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ((0, BIG, 1), (0, BIG, 1)),
            ((0, BIG, 2), (0, BIG - 1, 2)),
            ((BIG, 0, -2), (BIG, 1, -2)),
            ((0, BIG, 1), (0, BIG + 1, 1)),
            ((0, BIG, 1), (1, BIG + 1, 1)),
            ((0, BIG, 1), (0, BIG * 2, 2)),
        ],
    )
    def test_equality_matches_range(self, a, b) -> None:
        assert (mi.numeric_range(*a) == mi.numeric_range(*b)) == (range(*a) == range(*b))

    @pytest.mark.parametrize("args", [(0, BIG, 1), (0, BIG, 2), (BIG, 0, -2)])
    def test_hashable_and_usable_as_a_key(self, args) -> None:
        r = mi.numeric_range(*args)
        assert {r: "v"}[mi.numeric_range(*args)] == "v"


SLICES = [
    slice(None, None, -1), slice(None, None, -2), slice(None, 2, -1), slice(8, None, -1),
    slice(8, 2, -2), slice(-1, None, -3), slice(None, -8, -1), slice(100, None, -1),
    slice(None, None, 2), slice(1, -1), slice(-100, 100, 3),
]


class TestNumericRangeSlicing:
    @pytest.mark.parametrize("sl", SLICES, ids=str)
    @pytest.mark.parametrize("args", [(0, 10, 1), (0, 10, 3), (10, 0, -2), (10.0, 0.0, -2.0), (1.0, 9.0, 1.5)])
    def test_slice_matches_slicing_the_items(self, args, sl: slice) -> None:
        r = mi.numeric_range(*args)
        assert list(r[sl]) == list(r)[sl]

    def test_slice_of_an_int_range_matches_range(self) -> None:
        for sl in SLICES:
            assert list(mi.numeric_range(0, 10, 3)[sl]) == list(range(0, 10, 3)[sl])


# ---------------------------------------------------------------------------
# (5) Laziness and empty input
# ---------------------------------------------------------------------------


class TestPeekableReadsOnlyWhatItNeeds:
    @pytest.mark.parametrize("start", [0, 3, 5, 20])
    def test_negative_step_with_omitted_stop(self, start: int) -> None:
        source = Counting(limit=1000)
        p = mi.peekable(source)
        assert p[start::-1] == list(range(start, -1, -1))
        assert source.given <= start + 1
        assert next(p) == 0

    def test_negative_step_with_omitted_stop_on_a_long_iterator(self) -> None:
        # Stands in for an infinite iterator: reading it to the end fails.
        p = mi.peekable(Counting(limit=10**5))
        assert p[4::-2] == [4, 2, 0]
        assert list(islice(p, 3)) == [0, 1, 2]

    def test_other_slices_unchanged(self) -> None:
        p = mi.peekable(iter(range(10)))
        assert p[2:8:2] == [2, 4, 6]
        assert p[::-3] == [9, 6, 3, 0]
        assert p[-2:] == [8, 9]


class TestEmptyInput:
    def test_interleave_evenly_with_no_iterables(self) -> None:
        assert list(mi.interleave_evenly([])) == []
        assert list(mi.interleave_evenly([], lengths=[])) == []

    def test_interleave_evenly_unchanged(self) -> None:
        assert list(mi.interleave_evenly([[1, 2, 3, 4], ["a", "b"]])) == [1, 2, "a", 3, 4, "b"]

    @pytest.mark.parametrize("function", [mi.split_before, mi.split_after, mi.split_when], ids=lambda f: f.__name__)
    def test_maxsplit_zero_on_empty_input(self, function) -> None:
        pred = (lambda a, b: True) if function is mi.split_when else bool
        assert list(function([], pred, maxsplit=0)) == list(function([], pred))

    @pytest.mark.parametrize("function", [mi.split_before, mi.split_after, mi.split_when], ids=lambda f: f.__name__)
    def test_maxsplit_zero_on_nonempty_input_unchanged(self, function) -> None:
        pred = (lambda a, b: True) if function is mi.split_when else bool
        assert list(function([0, 1, 2], pred, maxsplit=0)) == [[0, 1, 2]]


# ---------------------------------------------------------------------------
# (6) running_min / running_max agree with min() / max()
# ---------------------------------------------------------------------------


def windows(values: list, maxlen: int) -> list[list]:
    return [values[max(0, i + 1 - maxlen) : i + 1] for i in range(len(values))]


EQUAL_VALUES = [
    [1.0, 1, Decimal(1), Fraction(1)],
    [3, 1.0, 1, 2, 1, Fraction(1)],
    [Decimal("2.0"), Decimal("2.00"), Decimal("2"), 5, Decimal("2.000")],
    [0, 0.0, -1, -1.0, -1, 3],
]


class TestRunningMinMaxPickTheSameItemAsMinMax:
    @pytest.mark.parametrize("values", EQUAL_VALUES)
    @pytest.mark.parametrize("maxlen", [2, 3])
    def test_running_min(self, values: list, maxlen: int) -> None:
        got = list(mi.running_min(values, maxlen=maxlen))
        expected = [min(w) for w in windows(values, maxlen)]
        assert [repr(x) for x in got] == [repr(x) for x in expected]

    @pytest.mark.parametrize("values", EQUAL_VALUES)
    @pytest.mark.parametrize("maxlen", [2, 3])
    def test_running_max(self, values: list, maxlen: int) -> None:
        got = list(mi.running_max(values, maxlen=maxlen))
        expected = [max(w) for w in windows(values, maxlen)]
        assert [repr(x) for x in got] == [repr(x) for x in expected]

    def test_unbounded_unchanged(self) -> None:
        values = [1.0, 1, 0, 0.0]
        assert [repr(x) for x in mi.running_min(values)] == ["1.0", "1.0", "0", "0"]
