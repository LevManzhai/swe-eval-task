# Notes

## Where the bugs come from

- Repo: https://github.com/redis/redis-py
- Base commit: `09c5cbfbfe593b5e4527a002acb94ffdaeed4ded` (16 November 2026)
- Reverted (source only; the tests they added are removed from the starting
  state too):

| Commit | PR | Files | What it fixed |
|---|---|---|---|
| `36f2f8c` | #4510 | `asyncio/client.py`, `asyncio/cluster.py` | `async with` on a client: a cancelled `initialize()` didn't undo the usage count, and a new context could enter while the previous one was still closing |
| `be1af1d` | #4557 | `asyncio/client.py` | `PubSub.aclose()` cancelled while waiting for its lock, disconnecting or releasing never returned the connection |
| `d9fede6` | #4550 | `asyncio/client.py`, `client.py` | `Monitor` entry that failed (e.g. `NoPermissionError`) or was cancelled leaked the connection |
| `30bd3cf` | #4559 | `asyncio/connection.py`, `asyncio/client.py` | `ConnectionPool.release()` / `BlockingConnectionPool.release()` cancelled while waiting for the pool lock left the connection counted as in use |
| `5306ac6` | #4546 | `asyncio/connection.py`, `connection.py` | a handshake failure that wasn't a `RedisError` (a credential provider's own exception, a cancellation) left the socket open, so the next command ran without `AUTH` / `SELECT` |
| `9d06bb9` | #4588 | `asyncio/client.py`, `client.py` | a closed PubSub's RESP3 push handler stayed on the pooled connection's parser and swallowed the next PubSub's messages |
| `eaba199` | #4631 | `asyncio/client.py`, `client.py`, both `cluster.py` | `Pipeline.reset()` reconnected a dropped connection just to send `UNWATCH` |

All of them landed between 28 October and 13 November 2026. Two reverts
overlapped with later upstream refactors of the same lines (`5a3cb83` rewrote
`disconnect()`, a later commit added a module `__getattr__` after
`BlockingConnectionPool.release()`). In both places I kept the later code and
only restored what the reverted commit had changed. Nothing in the starting
state is code I wrote.

One later upstream test,
`test_release_records_connection_closed_once_when_disconnect_cancelled`, only
passes with the pool fix in place, so it would have given the bug away. It's
removed from the starting state along with the fixes' own tests.

I left out `5a3cb83` (connection-closed metrics on a cancelled disconnect):
what it fixes is only visible through OpenTelemetry metrics, which would have
meant testing an observability detail rather than behaviour a user sees.

## Why this one

It uses the same idea as the anyio task, which passed the gate: the bugs are
about what happens when code is interrupted at a particular point, so there is
no output the agent can compare against a reference. What's new compared with
anyio:

- **Sync and asyncio.** Four of the seven bugs exist in both APIs, and the
  statement says the contract holds in both.
- **A real server.** The hidden tests run against Redis 7.4 inside the
  container. Leaks are detected the way a user would hit them: a pool with
  `max_connections=1` whose next command fails with `MaxConnectionsError`,
  `ACL WHOAMI` returning the wrong user, the server's own
  `total_connections_received` counter.
- **One of the bugs is a security issue.** After a failed credential fetch,
  the next command runs on an unauthenticated connection, as the default
  user.

## The problem statement

One realistic report (the `PubSub` leak under a Starlette timeout), then a
four-point contract:

1. every checkout is returned, exactly once, however its user ends;
2. no half-set-up connections;
3. nothing is inherited from the previous user;
4. no reconnecting just to undo state that died with the connection;

plus one paragraph on clients used as `async with`. Every hidden test checks
one of these. The statement doesn't list the other six places.

It does say which internals the tests touch: the pool's
`_in_use_connections` / `_available_connections`, and holding `pool._lock` to
keep a release waiting. Those have been part of redis-py's pool for years and
its own tests rely on them. I'd rather say so up front than have a correct
solution fail because it renamed them.

## The hidden tests

`verifier/test_task.py`, 29 tests in seven groups, one per bug. Points worth
noting:

- **Black-box where possible.** `ACL WHOAMI` after a failed handshake; a
  one-connection pool that must still answer `PING`; the server's connection
  counter around `Pipeline.reset()`; `CLIENT PAUSE` to make `EXEC` or
  `MONITOR` hang so they can be cancelled without patching anything.
- **Leniency where the contract allows it.** `PubSub.aclose()` may return
  before or after its teardown finishes, as long as the connection comes back.
  The pool may return a connection from a background task, as upstream does,
  or by any other means.
- **Regression checks** for behaviour that already worked (a nested failed
  entry must not close an active client, a cancelled exit still closes it, a
  cancel during a shielded `Pipeline.reset()`).

## Checking the checker

`run.sh` runs everything with `--network none`, starting a Redis server inside
each container:

- the starting state passes the upstream tests for the touched modules (about
  1,450 tests) and fails 20 of the 29 hidden tests;
- `solution/reference.patch` passes both;
- `verifier/alt_fixes/01_shielded_release_task.patch` passes both. It fixes
  the pool differently from upstream: `release()` runs the bookkeeping as its
  own task under `asyncio.shield()` and lets it finish if the caller is
  cancelled, instead of upstream's explicit background-release machinery;
- each of the eight `verifier/wrong_fixes/` passes the upstream tests and fails
  the hidden ones:
  - `01`–`07`: everything fixed except one of the seven bugs;
  - `08`: the handshake fixed for cancellation only. A credential provider
    raising its own exception still leaves an unauthenticated socket behind.

The upstream-test check skips one test that expects Redis 8 behaviour
(`test_subscriber_mode_rejects_regular_command_after_ssubscribe`). It fails the
same way on the reference solution and on untouched upstream code against a
7.4 server.

Mistakes in my own work that the self-check caught before any attempt ran:

- the async push-handler test passed a plain function as the handler; the
  asyncio client awaits it, so the test failed even on the reference. It now
  uses a coroutine, as redis-py's own tests do.

## Difficulty check

Same bar as every task here: a strong coding agent gets `PROBLEM.md` and the
repository, one try. Accepted if at most one attempt in three passes. Attempts
run one at a time, stopping as soon as the outcome is decided.

Results are added below as they come in.
