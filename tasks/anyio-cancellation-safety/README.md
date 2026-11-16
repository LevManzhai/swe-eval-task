# anyio: operations that aren't safe to cancel

> **Status: accepted.** Two of two one-shot attempts failed (34 / 36 each).
> Both fixed ten of the eleven bugs and missed the same one. `run.sh` passes all
> 34 of its checks. Details at the end of [`NOTES.md`](NOTES.md).

[anyio](https://github.com/agronholm/anyio) is the async I/O layer underneath
httpx, Starlette/FastAPI and a lot of other Python networking code. Its whole
model is built around *cancellation*: any `await` can be interrupted by a
timeout or a cancelled task group, and the library promises that this is safe.

In September and October 2026 upstream fixed a long series of places where it
wasn't. I took anyio as of 16 November 2026 and reverted eleven of those fixes.
They are spread over seven files in five subsystems:

| Subsystem | What goes wrong when the caller is cancelled at the wrong moment |
|---|---|
| `connect_tcp()` | the connection that won the race is never closed (fd leak) |
| TLS streams | a send cancelled after encryption loses a record; every later record is garbage to the peer |
| asyncio TCP streams | a cancelled `receive()` leaves the transport reading, so incoming data piles up in memory with no limit |
| thread portal | a future cancelled just as the call finishes crashes the event loop side with `InvalidStateError` |
| `CapacityLimiter` | `acquire_on_behalf_of()` cancelled at the wrong point releases the *current task's* token instead of the borrower's |
| temporary files and directories | the directory isn't removed (three separate code paths), and a cancelled rollover loses buffered data |
| file streams, `AsyncFile` | `aclose()` returns without closing the file |

The problem statement shows **only the first row**, as a user would report it.
It then states the cancellation contract that all of these violate, and asks
for the contract to hold across the library.

## Why this one should be harder than my earlier tasks

Every earlier candidate was solved because the agent could check its own
answer mechanically: against the old code, against `tomllib`, or against
documentation that already spelled out every case. Here there's nothing to
check against:

- **No oracle.** There is no reference implementation in the sandbox. Trio is
  deliberately not installed, so the agent can't diff the asyncio backend
  against it. The upstream regression tests and changelog entries for these
  fixes are removed.
- **Hunting across subsystems.** The bugs sit in seven files, and finding them
  means asking, at every `await` in the library, "what if cancellation lands
  exactly here?"
- **Each bug needs its own way of reproducing it.** Pre-cancelled scope,
  cancellation while blocked in a transport, cancellation delivered from a
  worker thread, a native `Task.cancel()` at a precise checkpoint, a
  `concurrent.futures.Future` cancelled between two lines. A generic fuzzer
  doesn't reach most of them.
- **Tempting fixes are wrong.** Adding a `checkpoint_if_cancelled()` at the top
  of `TLSStream.send()` or `SocketStream.receive()` passes the obvious test and
  misses the real window where cancellation lands. Both are in
  `verifier/wrong_fixes/`.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | anyio at commit `9df02f0`, plus `starting_state.patch`, git history removed |
| `environment/starting_state.patch` | reverts the eleven fixes, their tests and their changelog lines |
| `solution/reference.patch` | the eleven upstream fixes, source code only |
| `verifier/test_task.py` | the hidden tests |
| `verifier/alt_fixes/` | two correct solutions written differently from upstream; must pass |
| `verifier/wrong_fixes/` | thirteen wrong or incomplete solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. If Docker Hub is not reachable directly, point the build at a
mirror of the same image:

```bash
DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=<mirror>/python:3.12.16-bookworm" ./run.sh
```

anyio is MIT-licensed. The Dockerfile clones it from GitHub.
