# Notes

## Where the bugs come from

- Repo: https://github.com/Kludex/starlette
- Base commit: `271c277da0ff64e2048a4d46ecc812b9d61db5f6`

| Commit | What it fixed |
|---|---|
| `0a15da3` | `StaticFiles` answers `405` with an `Allow` header |
| `a579222` | `HTTPEndpoint` lists `HEAD` in `Allow` when it has `get()` |
| `dc20b21` | `Range` is honoured only for `GET` and `HEAD` |
| `1766228` | `TrustedHostMiddleware` / host routing compare host names case-insensitively |
| `750dc33` | `MutableHeaders` merges `Vary` instead of overwriting it |
| `96d5023` | `SessionMiddleware(max_age=0)` sends `Max-Age=0` |
| `4114432` | `http.response.start` without `headers` (optional in ASGI) is accepted |
| `b7901fb` | a `memoryview` body's `Content-Length` is its byte length |
| `3bc0e61` | a typed `memoryview` streamed chunk is sent as bytes of the right length |
| `a85a5c3` | `url_path_for` substitutes parameters in one pass |
| `3214cd0` | path parameters and request paths escape `?`, `#`, `\` and a leading `//` |
| `438cbed` | the WSGI adapter strips `root_path` only at a segment boundary |
| `271c277` | `Config` handles casts that have no `__name__` |
| `8ec9638` | `.env` values lose only matching outer quotes |
| `6b8b612` | URL-encoded form parsing is finalised at the end of the stream |
| `d7731e0` | `FormData` equality works with repeated uploads |
| `5b544ce` | `GZipMiddleware` sends `http.response.start` at once for responses it doesn't compress |

Source changes only were reverted; changelog entries were removed. `61123a5`
from the same period changes an error message only and stays fixed. Two
asserts in `tests/test_endpoints.py` that pinned the old `Allow` value were
removed from the starting state; no other upstream test changes.

## The hidden tests

`verifier/test_task.py`, 44 tests, all through the public API: the
`TestClient`, routers, middleware driven directly as ASGI apps with recorded
`send` messages, `URL`, `Config`, `FormParser`, `FormData`, `MutableHeaders`
and `build_environ`.

Before any attempt ran, the `Config` tests were narrowed to the cases where
the documented behaviour is unambiguous: a matching pair of outer quotes is
stripped, nested quotes are kept, and quote characters that are data
(`PASSWORD=abc"`, `TOKEN='xyz`, `NAME=it's`) are kept.

During the difficulty check three tests turned out to be stricter than the
statement, and every attempt was re-graded after the changes:

- `test_url_from_scope_with_double_slash_path` demanded that `str(URL)` for a
  request path `//example.org/a` doesn't start with `//`. Attempt 1 writes an
  empty authority in front (`////example.org/a`), which RFC 3986 reads as a
  path with no authority. The test now checks that the URL, read back from
  its string, has no authority.
- `test_parameter_value_that_looks_like_a_placeholder` demanded literal
  braces in `url_path_for("u", a="{b}", b="zz")`. Attempt 2 percent-encodes
  them (`/u/%7Bb%7D/zz`), which RFC 3986 prefers and which still round-trips.
  The test now compares the percent-decoded path.
- `test_path_parameter_never_becomes_an_authority` compared with one exact
  escaped string. It now also accepts any URL that decodes back to the value,
  doesn't start with `//` and has no raw backslash.

Kept as they are: the backslash tests. RFC 3986 doesn't allow a raw `\` in a
URI, and the WHATWG URL parser that browsers use reads `/\example.org/a` as
`//example.org/a`, an authority. A path that keeps a raw backslash therefore
does end up read as an authority, which point 3 of the statement rules out.

## Checking the checker

`run.sh` runs the starting state, the reference, one alternative and
seventeen wrong solutions against the upstream suite (1,380 tests; one
permission test is deselected because the container runs as root) and the
hidden tests.

- `verifier/alt_fixes/01_vary_and_quote_variants.patch` merges `Vary` and
  strips `.env` quotes with different code from upstream.
- each wrong solution fixes everything except one bug.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 17 min, 113 tool calls | **failed**, 40 / 44 | `url_path_for` substitutes a `{b}` value again; raw `\` in route and request paths |
| 2 | 17 min, 85 tool calls | **failed**, 43 / 44 | raw `\` in a request path |
| 3 | 16 min, 87 tool calls | **failed**, 42 / 44 | raw `\` in route and request paths |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 18 files, +363 / −96) fixed the
HTTP, ASGI, form, `Config`, WSGI and gzip bugs, and kept `//` request paths as
paths by writing an empty authority in front. It still substitutes route
parameters one after another, so a value `{b}` is replaced by the value of
`b`, and it leaves backslashes alone.

**Attempt 2** (`difficulty/attempt-2.patch`, 18 files, +335 / −104)
percent-encodes route parameters (so `\` there is escaped), substitutes in one
pass, and escapes `%`, `?`, `#` and a leading `//` in `URL(scope=...)`. A
request path `/\example.org/a` keeps its raw backslash.

**Attempt 3** (`difficulty/attempt-3.patch`, 18 files, +378 / −104) is like
attempt 2 but escapes only `%`, `?` and `#` in route parameters, so a
backslash stays raw in both places.

### What I make of it

- After the three test fixes above, every attempt fails on the same case: a
  raw backslash at the start of a path. All three knew about `//` and
  handled it; none treated `\` as the same thing, which is how browsers
  read it (this is the open-redirect pattern upstream's `3214cd0` closes).
- This is the most debatable point of the task. The statement says a path
  must never "end up read as an authority"; it doesn't name browsers or the
  WHATWG parser. My reasons for keeping it are above (a raw `\` isn't valid
  in a URI at all, and the parser real clients use reads `/\host` as an
  authority), and I decided to keep it before attempts 2 and 3 ran. A
  reviewer who disagrees would score attempt 2 as a pass, which still leaves
  the task at 1 of 3.
- The other sixteen bugs were found by every attempt, except the
  placeholder substitution, which attempt 1 missed.
