# Notes

## Where the bugs come from

- Repo: https://github.com/aio-libs/aiohttp
- Base commit: `b2350c3d330608165c9b51c3d291a5123c4364b9` (16 November 2026)
- Reverted (source only; their tests and changelog entries are removed from
  the starting state too):

| Commit | PR | File | What it fixed |
|---|---|---|---|
| `b2b2bce` | #13229 | `web_request.py` | infinite loop in `BaseRequest.forwarded` on a trailing malformed value such as `Forwarded: a` |
| `5789546` | #13671 | `http_parser.py` | the pure-Python request parser treated `HEAD` like a response to `HEAD` and didn't read the request's body |
| `18b49f3` | #13983 | `web_request.py`, `web_urldispatcher.py` | absolute-form targets: `request.host` without the port, `Domain` matching the `Host` header instead of the target |
| `a6306fc` | #13870 | `streams.py` | `StreamReader.readuntil()` missing a multi-byte separator split across chunks |
| `ced8133` | #13760 | `multipart.py` | `BodyPartReader.read_chunk()` crashing on `Content-Length: 0` |
| `2d9c5c1` | #13509 | `multipart.py` | base64 parts: `read_chunk()` returning chunks that end mid-quartet when the length is known |
| `e07684e` | #13681 | `web_protocol.py` | the server not closing connections that never send a request |
| `48f7b3d` | #13757 | `connector.py` | `keepalive_timeout=None` crashing on connection reuse |
| `a5e3747` | #13841 | `connector.py` | the proxy connection left open when sending `CONNECT` fails |

All nine reverse cleanly on the base commit, except `2d9c5c1` when it's
reverted on its own for a wrong fix (see below). `CHANGES.rst` lost the eight
matching entries and two unreleased fragments were deleted.

Five old tests in the starting state pinned the behaviour these fixes changed
(two base64 decode tests, one CONNECT authority-form test, two proxy raw-path
tests). Upstream rewrote them together with the fixes. Keeping the old
versions would have told the solver to preserve the bugs, and the new
versions would have revealed them, so I removed them. Everything else in the
upstream suite for the touched modules passes in the starting state.

Left out: `26fde21` (the parser paused at the end of a content-length body).
Its Python half reverts cleanly, but its Cython half doesn't, and leaving the
fixed Cython code in the repository would have shown the solver the answer.

## Why I picked it

It's the anyio lesson made deliberate. In anyio both attempts found ten of the
eleven bugs by auditing, and missed the one whose trigger was strange. In
redis-py (an earlier candidate, not kept in this repo) every bug was on the main
path, and the attempt found them all.
Here each of the nine bugs needs its own unusual input or situation, and they
sit in six different files across client and server.

There is also no oracle in the sandbox. aiohttp is installed with
`AIOHTTP_NO_EXTENSIONS=1`, so the C parser (which would have handled `HEAD`
correctly) isn't built; there's no `h11`, no `llhttp` build, no git history.

## The problem statement

It shows one bug, as a user report: the `Forwarded: a` hang. Then a
four-point contract:

1. chunking doesn't change what is parsed or read, and pieces handed out to be
   processed one at a time can be processed on their own;
2. HTTP/1.1 framing and request-target semantics per RFC 9112;
3. no input or documented configuration makes aiohttp hang, spin or crash;
4. connections don't outlive their use, client and server.

Every hidden test checks one of these. The statement doesn't name the other
eight places.

## The hidden tests

`verifier/test_task.py`, 90 tests (most of them parametrised cuts and sizes).

- **Server tests run a real aiohttp server** and talk to it over raw sockets:
  a `HEAD` request with a body followed by a pipelined `GET`, absolute-form
  targets with a conflicting `Host`, a connection that sends nothing.
- **`readuntil()`** is tested at every cut point of a short payload, one byte
  per chunk, and with a separator split three ways.
- **Base64 multipart** is read with `read_chunk()` at several sizes, with and
  without line wrapping and a known length. Every chunk must decode on its own,
  and the pieces together must give the original bytes. Sizes below 7 bytes
  aren't tested: with a line break inside, such a chunk can't hold a whole
  quartet, and neither upstream nor the contract promises it.
- **The `Forwarded` loop** runs in a daemon thread with a deadline, so a hang
  fails the test instead of the run.
- **The proxy test** uses a real listening socket as the proxy and patches the
  method that writes the client request so that sending `CONNECT` fails. With
  the garbage collector disabled and the exception still referenced, the proxy
  side must see the connection closed.
- **Regression checks** for nearby behaviour that already worked: the client
  still ignores the body of a `HEAD` response, origin-form requests still use
  `Host`, an active connection isn't cut off by `keepalive_timeout`,
  `force_close` with `keepalive_timeout` is still rejected.

## Checking the checker

`run.sh` runs everything with `--network none`:

- the starting state passes the upstream tests for the touched modules (1,377
  tests) and fails 28 of the 90 hidden tests, at least one for each bug;
- `solution/reference.patch` passes both;
- `verifier/alt_fixes/01_window_search_readuntil.patch` passes both. It
  finds a split separator differently from upstream, by searching a window of
  the last `len(separator) - 1` bytes already taken plus the unread data;
- each of the nine `verifier/wrong_fixes/` (everything fixed except one bug)
  passes the upstream tests and fails the hidden ones.

Mistakes in my own work that the self-check caught before any attempt ran:

- the stub protocol used by the `StreamReader` tests didn't accept the keyword
  argument `resume_reading()` gets in this version, so every reader test
  failed with `TypeError` on the reference too;
- the server helper passed `keepalive_timeout` to the runner instead of the
  `Server`, where it's ignored, so the idle-connection tests failed on the
  reference;
- the base64 test included sizes too small for any chunk to hold a whole
  quartet, which the reference doesn't handle either (see above).

## Difficulty check

Same bar as every task here: a strong coding agent gets `PROBLEM.md` and the
repository, one try. Accepted if at most one attempt in three passes. Attempts
run one at a time, stopping as soon as the outcome is decided.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 22 min, 120 tool calls | **failed**, 87 / 90 | `read_chunk()` on a part with `Content-Length: 0` |

**Attempt 1** (`difficulty/attempt-1.patch`, 9 files, +192 / −63). It found
eight of the nine bugs: the `Forwarded` loop, `HEAD` request bodies,
absolute-form targets, the split separator, base64 alignment, idle server
connections, `keepalive_timeout=None` and the proxy `CONNECT` leak. It also
fixed a handful of things beyond the task (a `Range: bytes=-0` edge case,
non-ASCII `Sec-WebSocket-Key`, `read_bufsize=None`, quoted-printable chunk
alignment). It wrote its own split-point tester, as earlier attempts on other
tasks did.

What it missed: a multipart part with an explicit `Content-Length: 0` is
treated as a part of unknown length, because the code tests `if
self._length:` rather than `is not None`. Read with `read_chunk()` and a size
smaller than the boundary, it then trips an internal assertion
(`Chunk size must be greater or equal than boundary length + 2`). The same call
works on a part with any other `Content-Length`. The documentation for
`read_chunk()` sets no minimum size, so I count this as point 3 of the
contract (an unexpected exception), as upstream did when it fixed it.

To be precise about the edge of the contract: a part *without* a length still
has that minimum size in both the starting state and upstream. The hidden
tests don't touch that case.
