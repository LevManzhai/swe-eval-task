"""Hidden tests for the dateutil edge-cases task.

Only dateutil's public API is used: ``tz.tzfile`` over TZif data built here (version 3, since some
TZ strings use transition hours outside 0-24),
``tz.gettz``, ``tz.tzlocal``, ``tz.tzutc``/``tz.tzoffset``, ``tz.tzical``,
``parser.isoparse``/``isoparser``, ``relativedelta``, ``rrule``/``rruleset``/
``rrulestr``.
"""

from __future__ import annotations

import io
import os
import pickle
import struct
import subprocess
import sys
import textwrap
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytest

from dateutil import parser, relativedelta as rd, rrule, tz

ZERO = timedelta(0)
ONE_H = timedelta(hours=1)
UTC = tz.UTC


# ---------------------------------------------------------------------------
# A small TZif (RFC 8536, version 3) writer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Offset:
    name: str
    utcoffset: timedelta
    dst: timedelta = ZERO


@dataclass(frozen=True)
class Transition:
    """A transition at local wall time ``when`` (in the offset before it)."""

    when: datetime
    before: Offset
    after: Offset

    @property
    def utc_ts(self) -> int:
        return int((self.when - self.before.utcoffset).replace(tzinfo=UTC).timestamp())


def tzif(transitions: list[Transition], footer: str) -> io.BytesIO:
    offsets: list[Offset] = []
    times: list[int] = []
    idxs: list[int] = []
    for t in sorted(transitions, key=lambda t: t.utc_ts):
        for o in (t.before, t.after):
            if o not in offsets:
                offsets.append(o)
        times.append(t.utc_ts)
        idxs.append(offsets.index(t.after))
    if not offsets:
        offsets.append(Offset("UTC", ZERO))

    abbrs = bytearray()
    ttinfos = []
    for o in offsets:
        ttinfos.append((int(o.utcoffset.total_seconds()), bool(o.dst), len(abbrs)))
        abbrs += o.name.encode("ascii") + b"\0"

    out = io.BytesIO()
    for time_type, limit in (("l", 2**31), ("q", 2**63)):
        # The version 1 section only holds 32-bit times.
        kept = [(t, i) for t, i in zip(times, idxs) if -limit <= t < limit]
        out.write(b"TZif3" + b"\0" * 15)
        out.write(struct.pack(">6l", 0, 0, 0, len(kept), len(ttinfos), len(abbrs)))
        out.write(struct.pack(f">{len(kept)}{time_type}", *(t for t, _ in kept)))
        out.write(struct.pack(f">{len(kept)}B", *(i for _, i in kept)))
        for ttinfo in ttinfos:
            out.write(struct.pack(">lbb", *ttinfo))
        out.write(bytes(abbrs))
    out.write(b"\n" + footer.encode("ascii") + b"\n")
    out.seek(0)
    return out


def zone(transitions: list[Transition], footer: str) -> tz.tzfile:
    return tz.tzfile(tzif(transitions, footer))


def at(dt: datetime, z, fold: int = 0) -> datetime:
    return tz.enfold(dt.replace(tzinfo=z), fold=fold)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---------------------------------------------------------------------------
# (1) TZif data and TZ strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("footer", "std_dts", "dst_dts"),
    [
        # "n" counts from 0: day 10 is January 11th
        ("STD0DST-1,10/0,J100/0", [datetime(2021, 1, 10, 12)], [datetime(2021, 1, 11, 12)]),
        # ... and includes February 29th
        (
            "STD0DST-1,59/0,300/0",
            [datetime(2024, 2, 28, 12), datetime(2023, 2, 28, 12)],
            [datetime(2024, 2, 29, 12), datetime(2023, 3, 1, 12)],
        ),
        # "Jn" counts from 1 and never counts February 29th
        (
            "STD0DST-1,J59/0,J300/0",
            [datetime(2024, 2, 27, 12), datetime(2023, 2, 27, 12)],
            [datetime(2024, 2, 28, 12), datetime(2023, 2, 28, 12)],
        ),
        (
            "STD0DST-1,J60/0,J300/0",
            [datetime(2024, 2, 29, 12), datetime(2023, 2, 28, 12)],
            [datetime(2024, 3, 1, 12), datetime(2023, 3, 1, 12)],
        ),
        # The end of the period: J300 is October 27th, day 300 is October 28th
        # in common years
        (
            "STD0DST-1,J60/0,J300/0",
            [datetime(2023, 10, 27, 12)],
            [datetime(2023, 10, 26, 12)],
        ),
        (
            "STD0DST-1,J60/0,300/0",
            [datetime(2023, 10, 28, 12)],
            [datetime(2023, 10, 27, 12)],
        ),
    ],
)
def test_tz_string_day_of_year_rules(footer, std_dts, dst_dts) -> None:
    z = zone([], footer)
    for dts, name in ((std_dts, "STD"), (dst_dts, "DST")):
        for dt in dts:
            assert dt.replace(tzinfo=z).tzname() == name, dt
            assert dt.replace(tzinfo=UTC).astimezone(z).tzname() == name, dt


def test_tz_string_month_rules_unchanged() -> None:
    z = zone([], "EST5EDT,M3.2.0,M11.1.0")
    assert datetime(2024, 7, 1, tzinfo=z).utcoffset() == -4 * ONE_H
    assert datetime(2024, 1, 1, tzinfo=z).utcoffset() == -5 * ONE_H


class TestOneTransitionFold:
    # A zone whose only transition moves the clock back three hours
    AAA = Offset("AAA", ZERO)
    BBB = Offset("BBB", -3 * ONE_H)

    @pytest.fixture
    def z(self):
        return zone([Transition(datetime(1976, 12, 1), self.AAA, self.BBB)], "BBB3")

    @pytest.mark.parametrize(
        ("local", "fold", "expected_utc"),
        [
            (datetime(1976, 11, 30, 20), 0, utc(1976, 11, 30, 20)),
            (datetime(1976, 11, 30, 22), 0, utc(1976, 11, 30, 22)),
            (datetime(1976, 11, 30, 21), 1, utc(1976, 12, 1, 0)),
            (datetime(1976, 11, 30, 22), 1, utc(1976, 12, 1, 1)),
            (datetime(1976, 11, 30, 23, 59), 1, utc(1976, 12, 1, 2, 59)),
            (datetime(1976, 12, 1), 0, utc(1976, 12, 1, 3)),
        ],
    )
    def test_round_trip(self, z, local, fold, expected_utc) -> None:
        dt = at(local, z, fold)
        assert dt.astimezone(UTC) == expected_utc
        back = expected_utc.astimezone(z)
        assert back.replace(tzinfo=None) == local
        assert back.fold == fold
        assert back.astimezone(UTC) == expected_utc


class TestFoldAtLastTransitionBeforeTzString:
    # The last explicit transition moves the clock back an hour; a TZ string
    # with its own DST rule takes over after it.
    LMT = Offset("LMT", -7 * ONE_H)
    CST = Offset("CST", -6 * ONE_H)
    MST = Offset("MST", -7 * ONE_H)

    @pytest.fixture
    def z(self):
        return zone(
            [
                Transition(datetime(2000, 1, 1), self.LMT, self.CST),
                Transition(datetime(2022, 11, 30), self.CST, self.MST),
            ],
            "MST7MDT,M3.2.0,M11.1.0",
        )

    @pytest.mark.parametrize(
        ("local", "fold", "expected_utc"),
        [
            (datetime(2022, 11, 29, 23, 30), 0, utc(2022, 11, 30, 5, 30)),
            (datetime(2022, 11, 29, 23), 1, utc(2022, 11, 30, 6)),
            (datetime(2022, 11, 29, 23, 30), 1, utc(2022, 11, 30, 6, 30)),
            (datetime(2022, 11, 30, 0, 30), 0, utc(2022, 11, 30, 7, 30)),
            (datetime(2023, 7, 1, 12), 0, utc(2023, 7, 1, 18)),
        ],
    )
    def test_round_trip(self, z, local, fold, expected_utc) -> None:
        assert at(local, z, fold).astimezone(UTC) == expected_utc
        back = expected_utc.astimezone(z)
        assert back.replace(tzinfo=None) == local
        assert back.fold == fold


class TestLastTransitionInsideTzStringDst:
    # The last explicit transition is a change from DST to standard time at
    # the same offset, inside a period that the TZ string would call DST.
    STD3 = Offset("-03", -3 * ONE_H)
    DST2 = Offset("-02", -2 * ONE_H, ONE_H)
    STD2 = Offset("-02", -2 * ONE_H)

    @pytest.fixture
    def z(self):
        return zone(
            [
                Transition(datetime(2023, 3, 25, 22), self.STD3, self.DST2),
                Transition(datetime(2023, 10, 28, 23), self.DST2, self.STD2),
            ],
            "<-02>2<-01>,M3.5.0/-1,M10.5.0/0",
        )

    @pytest.mark.parametrize(
        ("local", "expected"),
        [
            (datetime(2023, 10, 28, 22, 30), DST2),
            (datetime(2023, 10, 28, 23), STD2),
            (datetime(2023, 10, 28, 23, 30), STD2),
            (datetime(2023, 10, 29, 1), STD2),
        ],
    )
    @pytest.mark.parametrize("fold", [0, 1])
    def test_offsets(self, z, local, expected, fold) -> None:
        dt = at(local, z, fold)
        assert dt.utcoffset() == expected.utcoffset
        assert dt.dst() == expected.dst
        assert dt.tzname() == expected.name

    @pytest.mark.parametrize(
        ("local", "expected_utc"),
        [
            (datetime(2023, 10, 28, 23), utc(2023, 10, 29, 1)),
            (datetime(2023, 10, 28, 23, 30), utc(2023, 10, 29, 1, 30)),
            (datetime(2023, 10, 29, 1), utc(2023, 10, 29, 3)),
            (datetime(2024, 7, 1, 12), utc(2024, 7, 1, 13)),
        ],
    )
    def test_round_trip(self, z, local, expected_utc) -> None:
        assert local.replace(tzinfo=z).astimezone(UTC) == expected_utc
        assert expected_utc.astimezone(z).replace(tzinfo=None) == local


class TestPermanentDstAtTheEnd:
    # The explicit transitions end in +01 as DST; the TZ string after them
    # writes +01 as DST all year from a made-up standard offset of +02, the
    # way zic writes it.
    STD = Offset("+00", ZERO)
    DST = Offset("+01", ONE_H, ONE_H)

    @pytest.fixture
    def z(self):
        return zone(
            [
                Transition(datetime(2087, 3, 1, 3), self.DST, self.STD),
                Transition(datetime(2087, 5, 11, 2), self.STD, self.DST),
            ],
            "XXX-2<+01>-1,0/0,J365/23",
        )

    @pytest.mark.parametrize(
        "local", [datetime(2087, 5, 11, 3, 30), datetime(2100, 1, 1), datetime(2100, 7, 1), datetime(2400, 12, 31, 12)]
    )
    def test_dst_is_the_explicit_transitions_dst(self, z, local) -> None:
        dt = local.replace(tzinfo=z)
        assert dt.utcoffset() == ONE_H
        assert dt.dst() == ONE_H
        assert dt.tzname() == "+01"

    def test_dst_all_year_without_explicit_transitions_unchanged(self) -> None:
        z = zone([], "EST5EDT,0/0,J365/25")
        assert datetime(2024, 7, 1, tzinfo=z).utcoffset() == -4 * ONE_H
        assert datetime(2024, 1, 1, 0, 30, tzinfo=z).utcoffset() == -4 * ONE_H


def _valid_file() -> bytes:
    return zone_bytes(
        [
            Transition(datetime(2000, 3, 26, 2), Offset("STD", ONE_H), Offset("DST", 2 * ONE_H, ONE_H)),
            Transition(datetime(2000, 10, 29, 3), Offset("DST", 2 * ONE_H, ONE_H), Offset("STD", ONE_H)),
        ],
        "STD-1DST,M3.5.0,M10.5.0/3",
    )


def zone_bytes(transitions, footer) -> bytes:
    return tzif(transitions, footer).getvalue()


class TestTruncatedFiles:
    def test_every_truncation_raises_value_error(self) -> None:
        data = _valid_file()
        # Cut anywhere before the footer: the file is incomplete.
        footer_start = data.rindex(b"\nSTD")
        for n in range(footer_start):
            with pytest.raises(ValueError):
                tz.tzfile(io.BytesIO(data[:n]))

    def test_the_whole_file_still_loads(self) -> None:
        z = tz.tzfile(io.BytesIO(_valid_file()))
        assert datetime(2024, 7, 1, tzinfo=z).utcoffset() == 2 * ONE_H

    def test_gettz_skips_a_truncated_file_on_tzpath(self, tmp_path) -> None:
        bad = tmp_path / "bad" / "Fictional"
        good = tmp_path / "good" / "Fictional"
        bad.mkdir(parents=True)
        good.mkdir(parents=True)
        (bad / "Zone").write_bytes(_valid_file()[:30])
        (good / "Zone").write_bytes(_valid_file())
        tz.reset_tzpath([str(tmp_path / "bad"), str(tmp_path / "good")])
        try:
            tz.gettz.nocache()
            z = tz.gettz.nocache("Fictional/Zone")
        finally:
            tz.reset_tzpath()
        assert z is not None
        assert datetime(2024, 7, 1, tzinfo=z).utcoffset() == 2 * ONE_H


class TestGettzNames:
    @pytest.mark.parametrize("name", ["\x00", "Europe/Paris\x00", "UTC\x00junk", "/etc/\x00localtime"])
    def test_name_with_nul_byte_is_not_a_zone(self, name: str) -> None:
        assert tz.gettz.nocache(name) is None
        assert tz.gettz(name) is None

    def test_real_names_unchanged(self) -> None:
        assert tz.gettz("UTC") is not None
        assert tz.gettz("Not/AZone") is None


# ---------------------------------------------------------------------------
# (2) tzinfo protocol: None, pickling
# ---------------------------------------------------------------------------


TZLOCAL_SCRIPT = textwrap.dedent(
    """
    import time
    from datetime import time as dtime
    from dateutil import tz
    time.tzset()
    z = tz.tzlocal()
    print(repr(z.tzname(None)), repr(z.utcoffset(None)), repr(z.dst(None)))
    print(repr(dtime(12, tzinfo=z).tzname()))
    """
)


def _run_tzlocal(tz_env: str) -> list[str]:
    env = dict(os.environ, TZ=tz_env)
    out = subprocess.run(
        [sys.executable, "-c", TZLOCAL_SCRIPT], env=env, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.splitlines()


class TestTzlocalNone:
    def test_zone_with_dst(self) -> None:
        # utcoffset(None) and dst(None) are None in a zone with DST; tzname(None)
        # must not fail. The protocol allows None or a name.
        lines = _run_tzlocal("EST+05EDT,M3.2.0,M11.1.0")
        name, utcoffset, dst = lines[0].split(" ", 2)
        assert (utcoffset, dst) == ("None", "None")
        assert name == "None" or name.startswith("'")
        assert lines[1] == "None" or lines[1].startswith("'")

    def test_zone_without_dst_unchanged(self) -> None:
        lines = _run_tzlocal("JST-9")
        assert lines[0].startswith("'JST' ")


class TestPicklingKeepsSingletons:
    @pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
    def test_tzutc(self, protocol: int) -> None:
        assert pickle.loads(pickle.dumps(tz.tzutc(), protocol)) is tz.UTC
        assert pickle.loads(pickle.dumps(tz.UTC, protocol)) is tz.tzutc()

    @pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
    @pytest.mark.parametrize(("name", "offset"), [("EST", -18000), ("XYZ", 3600), (None, 0)])
    def test_tzoffset(self, protocol: int, name, offset: int) -> None:
        z = tz.tzoffset(name, offset)
        assert pickle.loads(pickle.dumps(z, protocol)) is tz.tzoffset(name, offset)

    def test_unpickled_values_still_compare_equal(self) -> None:
        dt = datetime(2024, 1, 1, tzinfo=tz.tzoffset("EST", -18000))
        assert pickle.loads(pickle.dumps(dt)) == dt


# ---------------------------------------------------------------------------
# (3) Strict ISO 8601 and iCalendar numbers
# ---------------------------------------------------------------------------


class TestIsoparseRejectsNonDigits:
    @pytest.mark.parametrize(
        "s",
        [
            "2014- 4-21",
            "2_14-04-21",
            "2014-0_-21",
            "2014-04-2_",
            "20200728121240",
            "2014-04-21T1_:00",
            "2014-04-21T12:3 ",
            "2014-04-21T12:30:4_",
            "2014-04-21T12:30+-1:00",
            "2014-04-21T12:30+01:0_",
            "2014-04-21T12:30+0130x",
            "2014-W1_",
            "2014-W10-_",
            "2014-1_0",
            "２０１４-04-21",
            "2014-04-21T１２:00",
        ],
    )
    def test_isoparse(self, s: str) -> None:
        with pytest.raises(ValueError):
            parser.isoparse(s)

    @pytest.mark.parametrize("s", ["+-1:00", "+0_:00", "+01:_0", "+1:00", "+01:000"])
    def test_parse_tzstr(self, s: str) -> None:
        with pytest.raises(ValueError):
            parser.isoparser().parse_tzstr(s)

    @pytest.mark.parametrize("s", ["2014- 4", "2_14", " 2014"])
    def test_parse_isodate(self, s: str) -> None:
        with pytest.raises(ValueError):
            parser.isoparser().parse_isodate(s)

    @pytest.mark.parametrize(
        ("s", "expected"),
        [
            ("2014-04-21", datetime(2014, 4, 21)),
            ("20140421T123015", datetime(2014, 4, 21, 12, 30, 15)),
            ("2014-W17-1", datetime(2014, 4, 21)),
            ("2014-111", datetime(2014, 4, 21)),
            ("2014-04-21T12:30:15.25+01:30", datetime(2014, 4, 21, 12, 30, 15, 250000, tzinfo=tz.tzoffset(None, 5400))),
            ("2014-04-21T12:30-05", datetime(2014, 4, 21, 12, 30, tzinfo=tz.tzoffset(None, -18000))),
        ],
    )
    def test_valid_strings_unchanged(self, s: str, expected: datetime) -> None:
        assert parser.isoparse(s) == expected


ICAL = """BEGIN:VCALENDAR
BEGIN:VTIMEZONE
TZID:Test
BEGIN:STANDARD
DTSTART:19701025T030000
TZOFFSETFROM:{frm}
TZOFFSETTO:{to}
TZNAME:TST
END:STANDARD
END:VTIMEZONE
END:VCALENDAR
"""


class TestTzicalOffsets:
    @pytest.mark.parametrize("bad", ["+0_00", "+01 0", "-1:00", "+０１００", "+01000_"])
    def test_non_digit_offset_raises_value_error(self, bad: str) -> None:
        with pytest.raises(ValueError):
            tz.tzical(io.StringIO(ICAL.format(frm=bad, to="+0100")))

    def test_valid_offsets_unchanged(self) -> None:
        cal = tz.tzical(io.StringIO(ICAL.format(frm="+0200", to="+0100")))
        z = cal.get("Test")
        assert datetime(2024, 1, 1, tzinfo=z).utcoffset() == ONE_H


# ---------------------------------------------------------------------------
# (4) relativedelta and rrule
# ---------------------------------------------------------------------------


class TestYearday:
    def test_yearday_366_in_a_leap_year(self) -> None:
        assert date(2024, 1, 1) + rd.relativedelta(yearday=366) == date(2024, 12, 31)

    def test_every_yearday_of_a_leap_year(self) -> None:
        start = date(2024, 1, 1)
        for n in range(1, 367):
            assert start + rd.relativedelta(yearday=n) == start + timedelta(days=n - 1), n

    def test_every_yearday_of_a_common_year(self) -> None:
        start = date(2023, 1, 1)
        for n in range(1, 366):
            assert start + rd.relativedelta(yearday=n) == start + timedelta(days=n - 1), n

    def test_nlyearday_unchanged(self) -> None:
        assert date(2024, 1, 1) + rd.relativedelta(nlyearday=365) == date(2024, 12, 31)
        assert date(2024, 1, 1) + rd.relativedelta(nlyearday=60) == date(2024, 3, 1)


def _with_timeout(fn, seconds: float = 10):
    result: list = []
    errors: list = []

    def run() -> None:
        try:
            result.append(fn())
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    assert not t.is_alive(), "did not finish"
    if errors:
        raise errors[0]
    return result[0]


class TestCachedRrule:
    START = datetime(2024, 1, 1)

    def test_cached_rule_included_twice_in_a_set(self) -> None:
        r = rrule.rrule(rrule.DAILY, count=25, dtstart=self.START, cache=True)
        s = rrule.rruleset()
        s.rrule(r)
        s.rrule(r)
        got = _with_timeout(lambda: list(s))
        assert got == [self.START + timedelta(days=i) for i in range(25)]

    def test_iterators_started_before_the_cache_is_complete(self) -> None:
        r = rrule.rrule(rrule.DAILY, count=25, dtstart=self.START, cache=True)
        a, b = iter(r), iter(r)
        first = [next(a) for _ in range(3)]
        rest_b = _with_timeout(lambda: list(b))
        rest_a = _with_timeout(lambda: list(a))
        assert first + rest_a == rest_b == [self.START + timedelta(days=i) for i in range(25)]

    def test_iterating_again_after_completion(self) -> None:
        r = rrule.rrule(rrule.DAILY, count=12, dtstart=self.START, cache=True)
        assert len(_with_timeout(lambda: list(r))) == 12
        assert len(_with_timeout(lambda: list(r))) == 12
        assert _with_timeout(lambda: r.count()) == 12


class TestRrulestrExperimentalParameters:
    def test_x_parameter_on_rrule_line_is_ignored(self) -> None:
        text = "DTSTART:20240101T090000\nRRULE;X-EVOLUTION-ENDDATE=20240103T090000Z:FREQ=DAILY;COUNT=3"
        assert list(rrule.rrulestr(text)) == [datetime(2024, 1, d, 9) for d in (1, 2, 3)]

    def test_several_x_parameters(self) -> None:
        text = "DTSTART:20240101T090000\nRRULE;X-A=1;X-B=2:FREQ=WEEKLY;COUNT=2"
        assert list(rrule.rrulestr(text)) == [datetime(2024, 1, 1, 9), datetime(2024, 1, 8, 9)]
