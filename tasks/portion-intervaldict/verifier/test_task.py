"""
Hidden verifier for the "IntervalDict single-key operations" task.

Three groups of checks, all deterministic (fixed seeds, no clock, no network):

1. ``TestDocumentedBehaviour``  - hand-written examples taken from, or directly
   implied by, the IntervalDict section of the library's README.
2. ``TestDifferential``         - long random operation sequences applied both
   to the implementation under test and to a pristine copy of the original
   implementation (the "oracle"); every observable result must be identical.
3. ``TestCost``                 - counts the comparisons performed on interval
   bounds and on stored values during single-key operations on large mappings.
   Nothing here measures wall-clock time.

Only the public API is used; no private attribute of IntervalDict is read.
"""

import hashlib
import importlib.util
import os
import random

import pytest

import portion as P
from portion import IntervalDict
from portion.interval import AbstractDiscreteInterval

# --------------------------------------------------------------------------- #
# Oracle: the original, unmodified implementation, kept outside the repository.
# --------------------------------------------------------------------------- #

ORACLE_PATH = os.environ.get("ORACLE_PATH", "/workspace/oracle/oracle_dict.py")
ORACLE_SHA256 = "339edad95f4e01c83051224303d6fcaba1a929d4975128842d2201e1784ca397"


def _load_oracle():
    with open(ORACLE_PATH, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    assert digest == ORACLE_SHA256, "the oracle implementation has been tampered with"
    spec = importlib.util.spec_from_file_location("oracle_dict", ORACLE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.IntervalDict


OracleDict = _load_oracle()


class IntInterval(AbstractDiscreteInterval):
    _step = 1


class IntDict(IntervalDict):
    _klass = IntInterval


class OracleIntDict(OracleDict):
    _klass = IntInterval


class Opaque:
    """A value that supports equality but is not hashable."""

    __hash__ = None

    def __init__(self, tag):
        self.tag = tag

    def __eq__(self, other):
        return isinstance(other, Opaque) and self.tag == other.tag

    def __add__(self, other):
        return Opaque((self.tag, other.tag))

    def __repr__(self):
        return f"Opaque({self.tag!r})"


def snapshot(d):
    """Everything observable about an IntervalDict through its public API."""
    items = list(d.items())
    return {
        "repr": repr(d),
        "len": len(d),
        "items": [(repr(k), v) for k, v in items],
        "keys": [repr(k) for k in d.keys()],
        "values": list(d.values()),
        "iter": [repr(k) for k in d],
        "domain": repr(d.domain()),
        # Plain dicts: compared as mappings, i.e. regardless of insertion order.
        "as_dict": {repr(k): v for k, v in d.as_dict().items()},
        "as_dict_atomic": {repr(k): v for k, v in d.as_dict(atomic=True).items()},
        "view_lens": (len(d.keys()), len(d.values()), len(d.items())),
    }


# --------------------------------------------------------------------------- #
# 1. Documented behaviour
# --------------------------------------------------------------------------- #


class TestDocumentedBehaviour:
    def test_readme_walkthrough(self):
        d = P.IntervalDict()
        d[P.closed(0, 3)] = "banana"
        d[4] = "apple"
        assert repr(d) == "{[0,3]: 'banana', [4]: 'apple'}"
        d[P.closed(2, 4)] = "orange"
        assert repr(d) == "{[0,2): 'banana', [2,4]: 'orange'}"
        assert d[2] == "orange"
        assert d.get(5, default=0) == 0
        with pytest.raises(KeyError):
            d[5]
        assert repr(d[~P.closed(1, 2)]) == "{[0,1): 'banana', (2,4]: 'orange'}"
        assert repr(d[P.closed(-1, 1)]) == "{[0,1]: 'banana'}"
        assert repr(d.get(P.closed(-2, 1), default="peach")) == (
            "{[-2,0): 'peach', [0,1]: 'banana'}"
        )
        assert d.find("banana") == P.closedopen(0, 2)
        assert d.find("peach") == P.empty()
        assert d.domain() == P.closed(0, 4)
        assert list(d.keys()) == [P.closedopen(0, 2), P.closed(2, 4)]
        assert list(d.values()) == ["banana", "orange"]
        assert list(d.items()) == [
            (P.closedopen(0, 2), "banana"),
            (P.closed(2, 4), "orange"),
        ]

    def test_one_element_per_stored_value(self):
        d = P.IntervalDict()
        d[P.closed(0, 1)] = d[P.closed(2, 3)] = "peach"
        assert list(d.items()) == [(P.closed(0, 1) | P.closed(2, 3), "peach")]
        assert len(d) == 1
        assert d.as_dict(atomic=True) == {
            P.closed(0, 1): "peach",
            P.closed(2, 3): "peach",
        }

    def test_interleaved_values_keep_one_key_each(self):
        d = P.IntervalDict()
        for i in range(6):
            d[P.closedopen(i, i + 1)] = "even" if i % 2 == 0 else "odd"
        assert len(d) == 2
        assert list(d.values()) == ["even", "odd"]
        assert list(d.keys()) == [
            P.closedopen(0, 1) | P.closedopen(2, 3) | P.closedopen(4, 5),
            P.closedopen(1, 2) | P.closedopen(3, 4) | P.closedopen(5, 6),
        ]
        for i in range(6):
            assert d[i] == ("even" if i % 2 == 0 else "odd")
            assert d[i + 0.5] == ("even" if i % 2 == 0 else "odd")
        with pytest.raises(KeyError):
            d[6]
        assert 5.5 in d and 6 not in d and -0.1 not in d

    def test_adjacent_intervals_with_equal_values_are_merged(self):
        d = P.IntervalDict()
        d[P.closedopen(0, 1)] = "a"
        d[P.closed(1, 2)] = "a"
        d[P.openclosed(2, 3)] = "a"
        assert repr(d) == "{[0,3]: 'a'}"
        assert d.as_dict(atomic=True) == {P.closed(0, 3): "a"}
        d[1] = "b"
        assert repr(d) == "{[0,1) | (1,3]: 'a', [1]: 'b'}"
        d[1] = "a"
        assert repr(d) == "{[0,3]: 'a'}"

    def test_values_only_need_equality(self):
        d = P.IntervalDict()
        d[P.closed(0, 1)] = [1, 2]
        d[P.closed(5, 6)] = {"k": 1}
        d[P.closed(8, 9)] = [1, 2]
        d[P.closed(11, 12)] = Opaque("x")
        d[P.closed(14, 15)] = Opaque("x")
        assert len(d) == 3
        assert list(d.values()) == [[1, 2], {"k": 1}, Opaque("x")]
        assert list(d.keys()) == [
            P.closed(0, 1) | P.closed(8, 9),
            P.closed(5, 6),
            P.closed(11, 12) | P.closed(14, 15),
        ]
        assert d.find([1, 2]) == P.closed(0, 1) | P.closed(8, 9)
        assert d[8.5] == [1, 2]
        assert d[14] == Opaque("x")
        del d[P.closed(0, 1)]
        assert list(d.items())[1] == (P.closed(8, 9), [1, 2])

    def test_bound_types_at_touching_points(self):
        d = P.IntervalDict()
        d[P.closedopen(0, 1)] = "left"
        d[P.open(1, 2)] = "right"
        with pytest.raises(KeyError):
            d[1]
        assert 1 not in d
        d[P.singleton(1)] = "point"
        assert d[1] == "point"
        assert d[0.999] == "left" and d[1.001] == "right"
        del d[1]
        assert 1 not in d
        with pytest.raises(KeyError):
            del d[1]
        with pytest.raises(KeyError):
            d.pop(1)
        assert d.pop(1, "nope") == "nope"
        assert repr(d) == "{[0,1): 'left', (1,2): 'right'}"

    def test_infinite_bounds(self):
        d = P.IntervalDict()
        d[P.open(-P.inf, P.inf)] = 0
        d[P.closed(0, 10)] = 1
        d[P.closedopen(20, P.inf)] = 2
        assert d[-(10**9)] == 0 and d[5] == 1 and d[15] == 0 and d[10**9] == 2
        assert repr(d) == "{(-inf,0) | (10,20): 0, [0,10]: 1, [20,+inf): 2}"
        del d[P.openclosed(-P.inf, 5)]
        assert repr(d) == "{(5,10]: 1, (10,20): 0, [20,+inf): 2}"
        assert -1 not in d

    def test_views_are_live(self):
        d = P.IntervalDict({P.closed(0, 2): 3, P.closed(3, 4): 2})
        k, v, i = d.keys(), d.values(), d.items()
        assert len(k) == len(v) == len(i) == len(d) == 2
        assert P.closed(0, 2) in k
        assert P.closed(0, 1) not in k
        d[5] = 4
        d[P.closed(10, 11)] = 3
        assert len(k) == len(v) == len(i) == 3
        assert list(k) == [P.closed(0, 2) | P.closed(10, 11), P.closed(3, 4), P.singleton(5)]
        assert list(v) == [3, 2, 4]
        assert list(i) == list(zip(list(k), list(v)))
        del d[P.closed(0, 100)]
        assert len(k) == len(v) == len(i) == 0
        assert list(k) == [] and list(v) == [] and list(i) == []

    def test_popitem_and_clear(self):
        d = P.IntervalDict()
        d[P.closed(0, 1)] = "a"
        d[P.closed(2, 3)] = "b"
        d[P.closed(4, 5)] = "a"
        assert d.popitem() == (P.closed(2, 3), "b")
        assert d.popitem() == (P.closed(0, 1) | P.closed(4, 5), "a")
        with pytest.raises(KeyError):
            d.popitem()
        d[1] = 2
        d.clear()
        assert len(d) == 0 and d.domain() == P.empty() and repr(d) == "{}"

    def test_copy_is_independent(self):
        d = P.IntervalDict({P.closed(0, 5): "a", P.closed(7, 9): "b"})
        c = d.copy()
        c[P.closed(1, 2)] = "c"
        del c[8]
        assert repr(d) == "{[0,5]: 'a', [7,9]: 'b'}"
        assert repr(c) == "{[0,1) | (2,5]: 'a', [1,2]: 'c', [7,8) | (8,9]: 'b'}"
        assert d != c and d == d.copy()
        sub = d[P.closed(4, 8)]
        sub[P.closed(4, 8)] = "z"
        assert repr(d) == "{[0,5]: 'a', [7,9]: 'b'}"

    def test_setdefault_and_pop_with_intervals(self):
        d = P.IntervalDict({P.closed(0, 2): "a"})
        assert d.setdefault(1, "x") == "a"
        assert d.setdefault(5, "x") == "x"
        t = d.setdefault(P.closed(1, 4), "y")
        assert repr(t) == "{[1,2]: 'a', (2,4]: 'y'}"
        assert repr(d) == "{[0,2]: 'a', (2,4]: 'y', [5]: 'x'}"
        p = d.pop(P.closed(2, 5))
        assert repr(p) == "{[2]: 'a', (2,4]: 'y', [5]: 'x'}"
        assert repr(d) == "{[0,2): 'a'}"

    def test_combine(self):
        d1 = P.IntervalDict({P.closed(0, 2): "banana"})
        d2 = P.IntervalDict({P.closed(1, 3): "orange"})
        d = d1.combine(d2, how=lambda x, y: x + "/" + y)
        assert repr(d) == "{[0,1): 'banana', [1,2]: 'banana/orange', (2,3]: 'orange'}"
        d = d1.combine(d2, how=lambda x, y: (x, y), missing=None)
        assert d[0] == ("banana", None) and d[3] == (None, "orange")

    def test_discrete_intervals(self):
        d = IntDict()
        d[IntInterval.from_atomic(P.CLOSED, 0, 1, P.CLOSED)] = "a"
        d[IntInterval.from_atomic(P.CLOSED, 2, 3, P.CLOSED)] = "a"
        d[IntInterval.from_atomic(P.OPEN, 3, 6, P.OPEN)] = "b"
        assert repr(d) == "{[0,3]: 'a', [4,5]: 'b'}"
        assert d.as_dict(atomic=True) == {
            IntInterval.from_atomic(P.CLOSED, 0, 3, P.CLOSED): "a",
            IntInterval.from_atomic(P.CLOSED, 4, 5, P.CLOSED): "b",
        }
        d[2] = "b"
        assert repr(d) == "{[0,1] | [3]: 'a', [2] | [4,5]: 'b'}"
        assert isinstance(d.domain(), IntInterval)
        assert all(isinstance(k, IntInterval) for k in d.keys())
        sub = d[IntInterval.from_atomic(P.CLOSED, 1, 4, P.CLOSED)]
        assert isinstance(sub, IntDict)
        assert repr(sub) == "{[1] | [3]: 'a', [2] | [4]: 'b'}"
        with pytest.raises(KeyError):
            d[6]


# --------------------------------------------------------------------------- #
# 2. Differential testing against the original implementation
# --------------------------------------------------------------------------- #


class Scenario:
    """Random operations applied to an implementation and to the oracle."""

    def __init__(self, seed, subject_cls, oracle_cls, klass, make_value, discrete):
        self.rng = random.Random(seed)
        self.klass = klass
        self.make_value = make_value
        self.discrete = discrete
        self.pair = (subject_cls(), oracle_cls())
        self.classes = (subject_cls, oracle_cls)

    # -- generators --------------------------------------------------------- #

    def bound(self):
        r = self.rng
        if not self.discrete and r.random() < 0.15:
            return r.randint(0, 13) + 0.5
        return r.randint(0, 13)

    def atomic(self):
        r = self.rng
        a, b = self.bound(), self.bound()
        lo, hi = min(a, b), max(a, b)
        if r.random() < 0.06:
            lo = -P.inf
        if r.random() < 0.06:
            hi = P.inf
        left = r.choice([P.CLOSED, P.OPEN])
        right = r.choice([P.CLOSED, P.OPEN])
        return self.klass.from_atomic(left, lo, hi, right)

    def interval(self):
        r = self.rng
        x = r.random()
        if x < 0.04:
            return self.klass()
        if x < 0.70:
            return self.atomic()
        return self.klass(*(self.atomic() for _ in range(r.randint(2, 3))))

    def key(self):
        if self.rng.random() < 0.45:
            return self.bound()
        return self.interval()

    def value(self):
        return self.make_value(self.rng.randint(0, 4))

    def other(self):
        """A pair of small independent mappings with identical content."""
        r = self.rng
        pairs = [(self.key(), self.value()) for _ in range(r.randint(0, 4))]
        return tuple(cls(list(pairs)) for cls in self.classes)

    # -- execution ---------------------------------------------------------- #

    def both(self, func):
        results = []
        for d in self.pair:
            try:
                out = ("ok", func(d))
            except KeyError:
                out = ("KeyError", None)
            results.append(out)
        return results

    def normalise(self, out):
        status, value = out
        if isinstance(value, (IntervalDict, OracleDict)):
            return status, "dict", snapshot(value)
        if isinstance(value, P.Interval):
            return status, "interval", repr(value)
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], P.Interval):
            return status, "item", (repr(value[0]), value[1])
        return status, "value", value

    def check(self, label, func):
        got, expected = self.both(func)
        assert self.normalise(got) == self.normalise(expected), label

    def step(self):
        r = self.rng
        op = r.choices(
            [
                "set", "del", "get_item", "get", "pop", "pop_default", "setdefault",
                "update_pairs", "update_dict", "contains", "find", "copy_swap",
                "combine", "or", "ior", "popitem", "eq", "set_many", "clear",
            ],
            weights=[26, 12, 12, 6, 5, 5, 5, 4, 4, 6, 4, 2, 3, 2, 2, 2, 2, 4, 0.3],
        )[0]

        if op == "set":
            k, v = self.key(), self.value()
            self.check(op, lambda d: d.__setitem__(k, v))
        elif op == "set_many":
            v = self.value()
            for _ in range(r.randint(2, 5)):
                k = self.atomic()
                self.check(op, lambda d, k=k: d.__setitem__(k, v))
        elif op == "del":
            k = self.key()
            self.check(op, lambda d: d.__delitem__(k))
        elif op == "get_item":
            k = self.key()
            self.check(op, lambda d: d[k])
        elif op == "get":
            k, v = self.key(), self.value()
            self.check(op, lambda d: d.get(k, v))
            self.check(op, lambda d: d.get(k))
        elif op == "pop":
            k = self.key()
            self.check(op, lambda d: d.pop(k))
        elif op == "pop_default":
            k, v = self.key(), self.value()
            self.check(op, lambda d: d.pop(k, v))
        elif op == "setdefault":
            k, v = self.key(), self.value()
            self.check(op, lambda d: d.setdefault(k, v))
        elif op == "update_pairs":
            pairs = [(self.key(), self.value()) for _ in range(r.randint(0, 5))]
            self.check(op, lambda d: d.update(list(pairs)))
        elif op == "update_dict":
            others = dict(zip(map(id, self.pair), self.other()))
            self.check(op, lambda d: d.update(others[id(d)]))
        elif op == "contains":
            k = self.key()
            self.check(op, lambda d: k in d)
        elif op == "find":
            v = self.value()
            self.check(op, lambda d: d.find(v))
        elif op == "copy_swap":
            copies = tuple(d.copy() for d in self.pair)
            assert snapshot(copies[0]) == snapshot(copies[1])
            k, v = self.key(), self.value()
            for d in self.pair:
                d[k] = v
            # The copies must not have been affected; continue with them.
            assert snapshot(copies[0]) == snapshot(copies[1])
            self.pair = copies
        elif op == "combine":
            others = dict(zip(map(id, self.pair), self.other()))
            how = lambda x, y: x + y  # noqa: E731
            self.check(op, lambda d: d.combine(others[id(d)], how))
            missing = self.value()
            self.check(op, lambda d: d.combine(others[id(d)], how, missing=missing))
            self.check(
                op,
                lambda d: d.combine(
                    others[id(d)], lambda x, y, i: (repr(i), x + y), pass_interval=True
                ),
            )
        elif op == "or":
            others = dict(zip(map(id, self.pair), self.other()))
            self.check(op, lambda d: d | others[id(d)])
        elif op == "ior":
            others = dict(zip(map(id, self.pair), self.other()))
            self.check(op, lambda d: d.__ior__(others[id(d)]) is d)
        elif op == "popitem":
            self.check(op, lambda d: d.popitem())
        elif op == "eq":
            others = dict(zip(map(id, self.pair), self.other()))
            self.check(op, lambda d: d == others[id(d)])
            self.check(op, lambda d: d == d.copy())
        elif op == "clear":
            self.check(op, lambda d: d.clear())

        assert snapshot(self.pair[0]) == snapshot(self.pair[1]), f"state after {op}"

    def run(self, steps):
        for _ in range(steps):
            self.step()


SEEDS = list(range(40))


class TestDifferential:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_hashable_values(self, seed):
        Scenario(seed, IntervalDict, OracleDict, P.Interval, lambda n: n * 10, False).run(250)

    @pytest.mark.parametrize("seed", SEEDS)
    def test_unhashable_values(self, seed):
        Scenario(
            1000 + seed, IntervalDict, OracleDict, P.Interval, lambda n: [n], False
        ).run(250)

    @pytest.mark.parametrize("seed", SEEDS[:20])
    def test_opaque_values(self, seed):
        Scenario(2000 + seed, IntervalDict, OracleDict, P.Interval, Opaque, False).run(250)

    @pytest.mark.parametrize("seed", SEEDS)
    def test_discrete_intervals(self, seed):
        Scenario(
            3000 + seed, IntDict, OracleIntDict, IntInterval, lambda n: "v%d" % n, True
        ).run(250)

    def test_many_fragments(self):
        """A wider domain, so that mappings hold a few hundred fragments."""
        rng = random.Random(4242)
        subject, oracle = IntervalDict(), OracleDict()
        for step in range(1500):
            lo = rng.randint(0, 2000)
            hi = lo + rng.choice([0, 0, 1, 2, 5, 40])
            left, right = rng.choice([P.CLOSED, P.OPEN]), rng.choice([P.CLOSED, P.OPEN])
            key = P.Interval.from_atomic(left, lo, hi, right)
            if rng.random() < 0.8:
                value = rng.randint(0, 60)
                subject[key] = value
                oracle[key] = value
            else:
                del subject[key]
                del oracle[key]
            if step % 100 == 99:
                assert snapshot(subject) == snapshot(oracle)
        assert snapshot(subject) == snapshot(oracle)
        for x in range(-1, 2050):
            for probe in (x, x + 0.5):
                assert (probe in subject) == (probe in oracle)
                assert subject.get(probe, "missing") == oracle.get(probe, "missing")


# --------------------------------------------------------------------------- #
# 3. Cost of single-key operations
# --------------------------------------------------------------------------- #


class Budget(Exception):
    pass


class Counter:
    def __init__(self):
        self.count = 0
        self.limit = None

    def tick(self):
        self.count += 1
        if self.limit is not None and self.count > self.limit:
            self.limit = None
            raise Budget()


COUNTER = Counter()


class K:
    """An interval bound that counts every comparison it takes part in."""

    __slots__ = ("x",)

    def __init__(self, x):
        self.x = x

    def __hash__(self):
        return hash(self.x)

    def __repr__(self):
        return f"K({self.x})"

    def __eq__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x == other.x

    def __ne__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x != other.x

    def __lt__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x < other.x

    def __le__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x <= other.x

    def __gt__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x > other.x

    def __ge__(self, other):
        if not isinstance(other, K):
            return NotImplemented
        COUNTER.tick()
        return self.x >= other.x


class V:
    """A hashable stored value that counts every equality test."""

    __slots__ = ("x",)

    def __init__(self, x):
        self.x = x

    def __hash__(self):
        return hash(("V", self.x))

    def __repr__(self):
        return f"V({self.x})"

    def __eq__(self, other):
        COUNTER.tick()
        return isinstance(other, V) and self.x == other.x

    def __ne__(self, other):
        COUNTER.tick()
        return not (isinstance(other, V) and self.x == other.x)


N = 4096

# Fragment i of the large mappings is [10*i, 10*i + 5); the gaps in between
# are left unmapped.
#
# Limits, in number of counted comparisons (bounds + values). For reference,
# on a mapping of N fragments the original implementation needs between a few
# thousand and several hundred thousand comparisons for a single one of the
# operations below, while a logarithmic implementation needs roughly 30-150.
BUILD_LIMIT = 1000 * N
SINGLE_OP_LIMIT = 1000


def frag(i):
    return P.closedopen(K(10 * i), K(10 * i + 5))


def build(value_of):
    """Build a mapping of N fragments, in a fixed pseudo-random order."""
    order = list(range(N))
    random.Random(7).shuffle(order)
    d = IntervalDict()
    COUNTER.count, COUNTER.limit = 0, BUILD_LIMIT
    try:
        for i in order:
            d[frag(i)] = value_of(i)
    except Budget:
        pytest.fail(
            f"building a mapping of {N} intervals one assignment at a time "
            f"needed more than {BUILD_LIMIT} comparisons"
        )
    finally:
        COUNTER.limit = None
    return d


def distinct(i):
    return V(i)


def striped(i):
    return V(i % 2)


SHAPES = {"distinct_values": distinct, "two_values": striped}


def cost(func):
    COUNTER.count, COUNTER.limit = 0, 50 * SINGLE_OP_LIMIT
    try:
        result = func()
    except Budget:
        return None, 50 * SINGLE_OP_LIMIT + 1
    finally:
        COUNTER.limit = None
    return result, COUNTER.count


def positions(seed, count=24):
    rng = random.Random(seed)
    return [0, 1, N // 2, N - 2, N - 1] + [rng.randrange(N) for _ in range(count)]


def assert_cheap(label, worst):
    assert worst <= SINGLE_OP_LIMIT, (
        f"{label}: {worst} comparisons for a single operation on a mapping of "
        f"{N} intervals (limit: {SINGLE_OP_LIMIT})"
    )


@pytest.fixture(params=sorted(SHAPES))
def shape(request):
    return SHAPES[request.param]


class TestCost:
    def test_lookup_hit(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(1):
            value, c = cost(lambda: d[K(10 * i + 2)])
            assert value == shape(i)
            worst = max(worst, c)
        assert_cheap("d[x]", worst)

    def test_lookup_miss(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(2):
            def lookup():
                try:
                    return d[K(10 * i + 7)]
                except KeyError:
                    return "missing"

            value, c = cost(lookup)
            assert value == "missing"
            worst = max(worst, c)
        _, c = cost(lambda: d.get(K(-5), "nothing"))
        worst = max(worst, c)
        _, c = cost(lambda: d.get(K(10 * N + 50), "nothing"))
        worst = max(worst, c)
        assert_cheap("d[x] (missing key)", worst)

    def test_membership(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(3):
            found, c = cost(lambda: K(10 * i) in d)
            assert found is True
            worst = max(worst, c)
            found, c = cost(lambda: K(10 * i + 5) in d)
            assert found is False
            worst = max(worst, c)
        assert_cheap("x in d", worst)

    def test_get(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(4):
            value, c = cost(lambda: d.get(K(10 * i + 4)))
            assert value == shape(i)
            worst = max(worst, c)
            value, c = cost(lambda: d.get(K(10 * i + 9), "default"))
            assert value == "default"
            worst = max(worst, c)
        assert_cheap("d.get(x)", worst)

    def test_assign_new_value(self, shape):
        d = build(shape)
        worst = 0
        for n, i in enumerate(positions(5)):
            # Inside an existing fragment (splits it), then inside a gap.
            _, c = cost(lambda: d.__setitem__(K(10 * i + 2), V(-1 - n)))
            worst = max(worst, c)
            _, c = cost(lambda: d.__setitem__(K(10 * i + 7), V(-100 - n)))
            worst = max(worst, c)
        assert_cheap("d[x] = new value", worst)
        for n, i in enumerate(positions(5)):
            assert d[K(10 * i + 7)] == V(-100 - n)
            assert d[K(10 * i + 1)] == shape(i)

    def test_assign_existing_value(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(6):
            # The value is already stored for a far away fragment.
            far = (i + N // 2 + 1) % N
            _, c = cost(lambda: d.__setitem__(K(10 * i + 2), shape(far)))
            worst = max(worst, c)
            _, c = cost(lambda: d.__setitem__(K(10 * i + 8), shape(far)))
            worst = max(worst, c)
        assert_cheap("d[x] = value already stored elsewhere", worst)
        for i in positions(6):
            far = (i + N // 2 + 1) % N
            assert d[K(10 * i + 8)] == shape(far)
            assert d.find(shape(far)).contains(K(10 * i + 2))

    def test_assign_small_interval(self, shape):
        d = build(shape)
        worst = 0
        for n, i in enumerate(positions(7)):
            # Overlaps two neighbouring fragments and the gap in between.
            j = min(i, N - 2)
            key = P.closed(K(10 * j + 3), K(10 * j + 12))
            _, c = cost(lambda: d.__setitem__(key, V(-1 - n)))
            worst = max(worst, c)
        assert_cheap("d[small interval] = value", worst)

    def test_delete(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(8):
            _, c = cost(lambda: d.__delitem__(K(10 * i + 3)))
            worst = max(worst, c)

            def delete_missing():
                try:
                    del d[K(10 * i + 6)]
                except KeyError:
                    return "missing"

            value, c = cost(delete_missing)
            assert value == "missing"
            worst = max(worst, c)
            j = min(i, N - 2)
            _, c = cost(lambda: d.__delitem__(P.open(K(10 * j + 4), K(10 * j + 11))))
            worst = max(worst, c)
        assert_cheap("del d[x]", worst)
        for i in positions(8):
            assert K(10 * i + 3) not in d

    def test_pop(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(9):
            if K(10 * i + 1) in d:
                value, c = cost(lambda: d.pop(K(10 * i + 1)))
                assert value == shape(i)
                worst = max(worst, c)
            value, c = cost(lambda: d.pop(K(10 * i + 1), "gone"))
            assert value == "gone"
            worst = max(worst, c)
        assert_cheap("d.pop(x)", worst)

    def test_setdefault(self, shape):
        d = build(shape)
        worst = 0
        for n, i in enumerate(positions(10)):
            value, c = cost(lambda: d.setdefault(K(10 * i + 3), V(-1)))
            assert value == shape(i)
            worst = max(worst, c)
            value, c = cost(lambda: d.setdefault(K(10 * i + 8), V(-100 - n)))
            worst = max(worst, c)
        assert_cheap("d.setdefault(x)", worst)
        for i in positions(10):
            assert K(10 * i + 8) in d

    def test_small_range_query(self, shape):
        d = build(shape)
        worst = 0
        for i in positions(11):
            j = min(i, N - 2)
            key = P.closed(K(10 * j + 3), K(10 * j + 12))
            sub, c = cost(lambda: d[key])
            worst = max(worst, c)
            assert sub is not None and sub.domain() == (
                P.closedopen(K(10 * j + 3), K(10 * j + 5))
                | P.closed(K(10 * j + 10), K(10 * j + 12))
            )
        assert_cheap("d[small interval]", worst)

    def test_operations_stay_cheap_while_mutating(self, shape):
        """Interleaves writes with reads: no operation may hide a rebuild."""
        d = build(shape)
        rng = random.Random(99)
        worst = 0
        for n in range(300):
            i = rng.randrange(N)
            op = rng.randrange(4)
            if op == 0:
                _, c = cost(lambda: d.__setitem__(K(10 * i + rng.randrange(10)), V(-1 - n)))
            elif op == 1:
                _, c = cost(lambda: d.pop(K(10 * i + rng.randrange(10)), None))
            elif op == 2:
                _, c = cost(lambda: d.get(K(10 * i + rng.randrange(10))))
            else:
                _, c = cost(lambda: (K(10 * i + rng.randrange(10)) in d))
            worst = max(worst, c)
        assert_cheap("mixed single-key operations", worst)

    def test_large_mapping_content(self):
        """The large mappings must of course still hold the right content."""
        for name in sorted(SHAPES):
            shape = SHAPES[name]
            d = build(shape)
            assert len(d) == (N if name == "distinct_values" else 2)
            assert len(d.as_dict(atomic=True)) == N
            keys = list(d.keys())
            if name == "two_values":
                assert len(keys[0]) == len(keys[1]) == N // 2
                assert keys[0].lower == K(0) and keys[1].lower == K(10)
            else:
                assert keys[0] == frag(0) and keys[-1] == frag(N - 1)
            assert d.domain().lower == K(0) and len(d.domain()) == N
