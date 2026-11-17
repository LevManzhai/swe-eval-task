# Notes

## Where the bugs come from

- Werkzeug: https://github.com/pallets/werkzeug at
  `0f43c6ebd426039e4b99ec22535c2c8a2ec2f69f` (9 November 2026)
- Flask: https://github.com/pallets/flask at
  `49943b5a94413a530761350f04e896f76e8d620e` (30 October 2026)

| Repo | Commit | Date | What it fixed |
|---|---|---|---|
| Werkzeug | `c678a231` | 19 Aug | `int`/`float` converters: non-ASCII digits, validating values when building, overflow to `inf`, scientific notation in built URLs |
| Werkzeug | `594452f6` | 1 Oct | `float` converter: sign position for small negative numbers |
| Werkzeug | `ab16e62d` | 13 Aug | `int` segments longer than `sys.get_int_max_str_digits()` give 404, not 500 |
| Werkzeug | `6d7c0b4e` | 21 Aug | converter matches sorted numerically, so rules with 10+ converters in one part assign values correctly |
| Werkzeug | `1b8bc581` | 19 Aug | `Basic` auth rejects non-base64 characters |
| Werkzeug | `658bf5ed` | 12 Aug | `Host` port must be 1–65535 |
| Werkzeug | `4da3786f` | 30 Jul | `iri_to_uri` / `uri_to_iri` keep empty user, password and port 0 |
| Werkzeug | `ea77c357` | 21 Aug | `LimitedStream.readinto` doesn't resize the caller's buffer on a short read |
| Werkzeug | `f85f3807` | 17 Sep | a header property whose dump function returns nothing removes the header |
| Werkzeug | `0ac9f126` | 11 Aug | `parse_options_header` stops at an unterminated quoted string |
| Werkzeug | `b71ddc61` | 14 Oct | the development server closes the response iterable even if draining the request fails |
| Flask | `7203feab` | 14 Jul | `app.run()` parses an IPv6 `SERVER_NAME` |
| Flask | `de8429ff` | 14 Jul | `session_transaction()` sets the cookie for an IPv6 host |

Most revert as patches. Three needed care because Werkzeug was refactored
after them:

- `658bf5ed` and `f85f3807`: the code they changed has since moved
  (`sansio/utils.py` was reworked, `header_property` now lives in
  `_header_property.py`). I removed exactly the lines each fix added, at the
  new location.
- `b71ddc61`: only its `serving.py` part is reverted; its other change (a type
  variable in `_internal.py`) is used elsewhere.

Changelog entries for all of them are removed, and so are the regression
tests they added. Both upstream suites pass in the starting state (968
Werkzeug tests, 492 Flask tests).

## Why this version

A first Flask/Werkzeug candidate (nine bugs: Range requests, empty
`If-Range`, IPv6 and similar) was solved on its first attempt, 42/42. Every one
of those bugs sat in an area an HTTP-minded audit checks first. I didn't add
it to the repository.

This version follows what made anyio and aiohttp hold up: more bugs, each with
its own trigger, mostly in places an HTTP audit doesn't look. Number parsing in
URL converters, the order in which converter matches are read back, URL
round-tripping through IRI/URI conversion, a stream's buffer handling. Four of
the thirteen (the header property, the unterminated quote, the development
server, the two Flask IPv6 fixes) are carried over from the first candidate.

## The problem statement

One user report (`GET /invoice/٣` reaching the view as invoice 3), then a
seven-point contract: values follow their grammar, bad input is the client's
error, URL building inverts matching, conversions keep information, header
grammar, IPv6 literals, response iterables are always closed.

## The hidden tests

`verifier/test_task.py`, 68 tests, mostly through a Flask app and its test
client. Points worth noting:

- **Leaks of the wrong value are checked end to end:** a path with
  Arabic-Indic or full-width digits must 404; a 4,310-digit `int` segment must
  404, not 500; a float segment too large for a float must 404, not reach the
  view as `inf`.
- **Round trips:** `url_for` then a request with the result, for small, large,
  positive and negative floats, and for a rule with twelve converters in one
  segment (and eleven untyped ones separated by dots).
- **The short read:** a stream that hands out at most 3 bytes per call, behind
  a `LimitedStream` with 5 bytes left, read into a 10-byte `bytearray` and a
  `memoryview`. The buffer's size must not change.
- **`TRUSTED_HOSTS`** with a port out of range must give 400.

One test I wrote and then dropped: that `fixed_digits` doesn't count the minus
sign (upstream changed this in `c678a231`). The starting state is consistent
with itself there (it builds and matches `-05` for three digits), and nothing
in the statement settles whether the sign is a digit, so a test for it
wouldn't have been fair.

## Checking the checker

`run.sh` applies each solution's two patches and checks the starting state,
the reference, one alternative solution and twelve wrong ones against both
upstream suites and the hidden tests. All 30 expectations are met.

- `verifier/alt_fixes/01_direct_slice_and_port_parse` reads straight into a
  slice of the caller's buffer instead of using a temporary one, validates the
  `Host` port with its own parsing instead of upstream's regex group, and
  parses the test client's host with `urlsplit("//" + host)`.
- `verifier/wrong_fixes/01`–`12` each fix everything except one bug (the two
  float commits count as one, since one builds on the other).

## Difficulty check

Same bar as every task here: a strong coding agent gets `PROBLEM.md` and both
repositories, one try. Accepted if at most one attempt in three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 18 min, 124 tool calls | **failed**, 66 / 68 | rules with 10+ converters in one segment |
| 2 | 15 min, 99 tool calls | **failed**, 66 / 68 | rules with 10+ converters in one segment |

**Result: accepted.** Two of two attempts failed, so even a pass on a third
would leave it at one in three. I didn't run the third.

**Attempt 1** (`difficulty/attempt-1/`, 24 files across both repositories,
+558 / −123) fixed twelve of the thirteen bugs and a long list of things beyond
the task (`Retry-After` read as days, `parse_date` edge cases, unsigned number
fields, cookie parsing, building validation for every converter). It never
looked at how the matcher reads converter values back: they're sorted as
strings, so with ten or more converters `10` comes before `2` and values go
to the wrong names. A URL built for one set of values matches with another,
which is point 3 of the contract.

**Attempt 2** (`difficulty/attempt-2/`, 18 files, +630 / −120) went the same
way: twelve of thirteen fixed, many extras (a new RFC 3986 splitter for IRI
conversion, `path` converter matching newlines, `DechunkedInput.readinto`),
and its report says in so many words "`matcher` untouched". Same failure as
attempt 1.

### What I make of it

- Unlike aiohttp, where the two attempts missed different bugs, both missed
  the same one here, as in anyio. The trigger needs ten converters in a
  single path segment, and nothing about the reported symptom points at the
  matcher.
- That makes this task's difficulty rest mostly on one bug out of thirteen,
  and I'd describe it that way rather than as thirteen hard bugs. The other
  twelve are found, and fixed well.
- Both attempts changed far more than the task asked for; a reviewer would
  want those split into separate changes.
