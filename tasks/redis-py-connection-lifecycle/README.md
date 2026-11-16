# redis-py: pooled connections that go missing or come back wrong

> **Status: built and self-checked; difficulty check in progress.** Details at
> the end of [`NOTES.md`](NOTES.md).

[redis-py](https://github.com/redis/redis-py) is the standard Python client for
Redis. Almost everything it does goes through a connection pool: a command
takes a connection, runs, and gives it back. In October and November 2026
upstream fixed a series of places where that life cycle broke. I took
redis-py as of 16 November 2026 and reverted seven of those fixes:

| Where | What goes wrong |
|---|---|
| `PubSub.aclose()` | cancelled while closing (e.g. by a timeout around `async with r.pubsub()`), the connection is never returned; the pool eventually raises `MaxConnectionsError` |
| `ConnectionPool.release()` | cancelled while waiting for the pool lock, the connection stays "in use" forever |
| connection handshake | if a credential provider raises, or the task is cancelled during `AUTH`, the socket is left open and looks connected, so the next command runs **unauthenticated and on the wrong database** (sync and asyncio) |
| `PubSub` push handler | a closed PubSub's RESP3 push handler stays on the pooled connection, and the next PubSub's messages go to it (sync and asyncio) |
| `Monitor` | if entering `MONITOR` fails (e.g. no ACL permission) or is cancelled, the connection leaks (sync and asyncio) |
| `Pipeline.reset()` | after a dropped connection, opens a brand new connection just to send `UNWATCH` (sync and asyncio) |
| `async with Redis()` | a cancelled entry leaves the usage counter off by one, so the client is never closed; a new context can start using a client that is still being closed |

The problem statement shows **only the first row**, as a user would report
it, and then states the connection life-cycle contract that all of them
break.

## Same strategy as the anyio task

This follows [`tasks/anyio-cancellation-safety`](../anyio-cancellation-safety),
the first task here to pass the difficulty bar:

- **No oracle.** Whether a connection is returned after a cancellation at a
  particular `await` isn't visible in any output the agent could diff. The git
  history, the upstream regression tests and one later test that depended on
  a fix are removed.
- **Several subsystems, sync and asyncio.** The bugs are spread over the pool,
  the connection handshake, PubSub, Monitor, Pipeline and the client's own
  context manager, in `redis/asyncio/{client,connection,cluster}.py`,
  `redis/client.py`, `redis/connection.py` and `redis/cluster.py`.
- **Each bug has its own trigger.** A cancel while a release waits for a lock,
  a credential provider that raises a non-Redis exception, RESP3 with a
  custom push handler, an ACL user without `+monitor`, a dropped connection
  under `WATCH`, two tasks sharing one client.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | redis-py at commit `09c5cbf`, Redis 7.4.12 from the official image, plus `starting_state.patch`; git history removed |
| `environment/starting_state.patch` | reverts the seven fixes and removes their tests |
| `solution/reference.patch` | the seven upstream fixes, source code only |
| `verifier/test_task.py` | 29 hidden tests, run against a real Redis server |
| `verifier/alt_fixes/` | a correct solution with a different design for the pool; must pass |
| `verifier/wrong_fixes/` | eight wrong or incomplete solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. To build from a registry mirror:

```bash
DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=<mirror>/python:3.12.16-bookworm --build-arg REDIS_IMAGE=<mirror>/redis:7.4.12-bookworm" ./run.sh
```

redis-py is MIT-licensed. The Dockerfile clones it from GitHub.
