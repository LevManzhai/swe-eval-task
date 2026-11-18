# urllib3: rare responses and redirects handled wrongly

> **Status: accepted.** Three of three one-shot attempts failed (90, 89 and
> 88 of 92). All three missed the same bug. `run.sh` passes all 32 of its
> checks. Details at the end of [`NOTES.md`](NOTES.md).

[urllib3](https://github.com/urllib3/urllib3) is the HTTP client underneath
requests, botocore and pip. Between August and November 2026 upstream fixed a
run of bugs in how it reads responses, retries and follows redirects. I took
urllib3 as of 14 November 2026 and reverted thirteen of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| response headers | a header continued on the next line (obsolete folding) | the value contains a raw `\r\n` |
| response headers | a bare `\n`, or a NUL, inside a value | passed through as-is |
| response body | two gzip members, read in reads that end exactly at the boundary | the second member is lost |
| response body | raw deflate over the wire, read in small pieces | the tail of the body is lost |
| response body | `deflate, gzip` read one byte at a time | `read()` returns `b""` before the end |
| response body | a truncated zstd body read with `read(64)` | looks like a clean end of body |
| response body | `read(decode_content=False)` after a decoded read | refused only after a chunk has been consumed |
| framing | `Content-Length: +5` or `5_0`, chunk size `0x5` or `+5` | accepted, because `int()` accepts them |
| `Retry` | thousands of retries with a backoff factor | `OverflowError` |
| `Retry` | `Retry-After: Fri, 31 Dec 99999 ...` | `OverflowError` or `ValueError` |
| `PoolManager` redirect | a 3xx with `Retry-After` | the wait is ignored |
| `ProxyManager` redirect | a cross-host redirect through an HTTP proxy | `Authorization` and `Cookie` go to the new host |
| 303 redirect | a chunked request body | the follow-up `GET` still says `Transfer-Encoding: chunked` |
| body rewind | a body with `tell()` but no `seek()` | `ValueError` instead of `UnrewindableBodyError` |
| `assert_fingerprint` | a fingerprint with non-hex characters | `binascii.Error` instead of `SSLError` |

The problem statement shows **only the first row** and a five-point contract.

## Why this one

Same recipe as the accepted anyio, aiohttp, Flask/Werkzeug and packaging
tasks: many bugs, each with an unusual trigger, in a widely used library whose
own suite passes without noticing them, and no oracle in the sandbox.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | urllib3 at commit `d9f9b0a`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 92 hidden tests: in-memory responses plus small local HTTP servers and a fake proxy |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | thirteen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. urllib3 is MIT-licensed; the Dockerfile clones it from GitHub.
