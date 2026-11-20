# dateutil: rare dates, time zones and recurrences handled wrongly

The repository in `/workspace/repo` is
[dateutil](https://github.com/dateutil/dateutil), the extensions to Python's
`datetime` that pandas, botocore and many other projects depend on.

## What a user reported

> We compute "the last day of the year" with
> `date(year, 1, 1) + relativedelta(yearday=366)` for leap years. For 2024 it
> gives December 30th, the same as `yearday=365`.

## What we want

Fix that, and treat it as one example of a wider problem: dateutil handles
some rare but valid input in ways that don't match the standards it
implements, Python's `tzinfo` protocol, or its own documentation. We want the
following to hold across the library:

1. **Time zone files and TZ strings are read as their specifications say.**
   `tz.tzfile` follows RFC 8536 for TZif data and POSIX for the TZ string in
   its footer, every rule form included. The explicit transitions and the TZ
   string that follows them describe one consistent zone: every local time
   gets the right offset, DST and abbreviation, and converting to and from UTC
   round-trips, folds (PEP 495) included, however few transitions a zone has.
   Data that isn't valid TZif, including data that ends early, is rejected
   with `ValueError`.
2. **dateutil's `tzinfo` objects follow Python's `tzinfo` protocol.** That
   includes being called with `None` (as `datetime.time` does), and
   documented singletons and cached instances keep that identity when they
   are copied or pickled.
3. **Parsers accept exactly their grammar.** `isoparse` (ISO 8601) and
   `tzical` (RFC 5545) accept only what their formats allow, numeric fields
   included, and raise `ValueError` for anything else. `rrulestr` accepts
   everything RFC 5545 allows in the lines it reads.
4. **Documented APIs behave as documented for every valid input.** This
   covers `relativedelta`'s absolute fields and recurrence rules, including
   cached rules and rule sets used in every supported way.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is, apart from three tests that depend on the
  system time zone data in this sandbox. It doesn't cover these cases.
- Your changes are graded by hidden tests that use dateutil's public API:
  `tz.tzfile` over TZif data built by the tests, `tz.gettz`, `tz.tzlocal`
  (with `TZ` set in a separate process), `tz.tzutc`, `tz.tzoffset`,
  `tz.tzical`, `parser.isoparse` and `isoparser`, `relativedelta`, and
  `rrule`, `rruleset` and `rrulestr`.
