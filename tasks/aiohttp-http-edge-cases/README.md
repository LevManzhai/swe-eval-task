# aiohttp: HTTP edge cases that ordinary traffic never hits

> **Status: accepted.** Two of two one-shot attempts failed (87 / 90 and
> 89 / 90). Each found eight of the nine bugs, and they missed different ones.
> `run.sh` passes all 24 of its checks. Details at the end of
> [`NOTES.md`](NOTES.md).

[aiohttp](https://github.com/aio-libs/aiohttp) is one of the most used async
HTTP libraries in Python, client and server. Between August and October 2026
upstream fixed a run of bugs that share one property: each needs an input or a
situation that ordinary traffic never produces. I took aiohttp as of 16
November 2026 and reverted nine of them, spread over six files:

| Where | Trigger | What goes wrong |
|---|---|---|
| `web_request.py` | `Forwarded: a` | `request.forwarded` loops forever; one request takes a worker down |
| `http_parser.py` | a `HEAD` request with a body | the body isn't consumed, so it's parsed as the next request (request smuggling on a keep-alive connection) |
| `web_request.py`, `web_urldispatcher.py` | an absolute-form target, `GET http://example.com:8080/ HTTP/1.1` | `request.host` drops the port, domain sub-apps match the `Host` header instead of the target (RFC 9112 §3.2.2) |
| `streams.py` | a multi-byte separator split across two chunks | `readuntil()` misses it and returns data past it |
| `multipart.py` | a part with `Content-Length: 0` | `read_chunk()` crashes with an `AssertionError` |
| `multipart.py` | a base64 part read with `read_chunk()` and a known length | chunks end mid-quartet and can't be decoded one by one |
| `web_protocol.py` | a client that connects and sends nothing | the server holds the connection forever; `keepalive_timeout` only starts after a first request |
| `connector.py` | `TCPConnector(keepalive_timeout=None)` | the second request to the same host crashes with `TypeError` |
| `connector.py` | sending `CONNECT` to a proxy fails | the proxy connection stays open until garbage collection |

The problem statement shows **only the first row**, as a user report, and
then states a four-point contract that all nine violate.

## Why this one

Two earlier tasks here used the same approach, and I learned from both:

- **anyio** (accepted, 0 of 2 attempts passed): both attempts audited the
  library and found ten of eleven bugs. They missed the one whose trigger was
  exotic.
- **redis-py** (an earlier candidate, rejected and not kept here): every bug sat on the main path of a connection's
  life cycle, so a systematic walk through that path found them all.

So this task is built from bugs whose triggers are each unusual in their own
way, in a large codebase, with no oracle in the sandbox: the C parser isn't
built, `h11`/`llhttp` aren't available, git history is gone, and the upstream
regression tests and changelog entries are removed.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | aiohttp at commit `b2350c3`, without C extensions, plus `starting_state.patch`; git history removed |
| `environment/starting_state.patch` | reverts the nine fixes, their tests and changelog entries |
| `solution/reference.patch` | the nine upstream fixes, source code only |
| `verifier/test_task.py` | 90 hidden tests, mostly against a real server over raw sockets |
| `verifier/alt_fixes/` | a correct solution with a different `readuntil()`; must pass |
| `verifier/wrong_fixes/` | nine "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. `DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=<mirror>/python:3.12.16-bookworm"`
builds from a registry mirror.

aiohttp is Apache-2.0 licensed. The Dockerfile clones it from GitHub.
