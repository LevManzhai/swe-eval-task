# redis-py: pooled connections go missing or come back wrong

The repository in `/workspace/repo` is [redis-py](https://github.com/redis/redis-py),
the Python client for Redis, with both its synchronous (`redis`) and its asyncio
(`redis.asyncio`) API. A Redis 7.4 server is installed in the environment;
start one with `redis-server --daemonize yes` (it listens on
`localhost:6379`).

## What a user reported

A Starlette service reads from Redis pub/sub inside a request-scoped timeout:

```python
pool = redis.asyncio.ConnectionPool(max_connections=20)
client = redis.asyncio.Redis(connection_pool=pool)

async def handler():
    with anyio.move_on_after(5):
        async with client.pubsub() as p:
            await p.subscribe("events")
            ...
```

After a few hours under load, every request fails with
`redis.exceptions.MaxConnectionsError: Too many connections`, although the
server shows only a handful of clients. The reporter found that when the
timeout fires while the `async with client.pubsub()` block is closing, the
pubsub's connection is never given back to the pool. The pool keeps counting
it as in use, forever.

## What we want

Fix that, but treat it as one symptom of a broader problem. Connections taken
from a pool have a life cycle — checked out, set up (handshake: `HELLO`/`AUTH`,
`SELECT`, ...), used, given back — and that life cycle has to hold no matter
how the code using the connection ends. We want the following contract to hold
**throughout the client, sync and asyncio**, not just in `PubSub`:

**Connection life-cycle contract**

1. **Every checkout is returned, exactly once.** A connection taken from a pool
   goes back to that pool when its user is done with it, whether that user
   finishes normally, raises, or is cancelled (asyncio cancellation, timeouts,
   anyio cancel scopes) at any point, including while it is cleaning up.
2. **No half-set-up connections.** A connection that a pool hands out, or that
   a command runs on, is either connected *and* fully set up, or not connected
   at all, so that it will be set up from scratch before use. If the handshake
   fails or is interrupted for any reason, the connection must not look
   connected afterwards.
3. **Nothing is inherited.** A connection carries nothing over from its
   previous user into its next one.
4. **No pointless reconnects.** Server-side state that dies with a connection
   (`WATCH`, subscriptions, `MONITOR`) does not need undoing once the
   connection has been dropped. Cleanup must not open a new connection just
   to undo it.

The same applies to client objects that manage their own resources, for
example a `redis.asyncio.Redis` used as `async with client:`. Its last exit
closes it and nothing else does. That stays true when an entry or an exit is
cancelled, and when several tasks enter and leave it concurrently.

Behaviour that has nothing to do with these situations must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The existing tests for the touched modules pass as they are; they don't
  cover these cases. Many other test files need a Redis cluster, Redis
  modules or TLS, which aren't available here.
- You don't need to change the cluster clients beyond what the contract
  implies for code they share with the standalone clients.
- Your patch is graded by hidden tests that run against the local Redis
  server. They use the public API, and check for leaks through the pool's
  observable behaviour and its `_in_use_connections` / `_available_connections`
  bookkeeping, which has existed for many releases. To pick the moment
  something goes wrong, they patch public methods (a connection's or a pool's
  methods, a client's `initialize()` / `aclose()`, a credential provider) or
  pause the server with `CLIENT PAUSE`, and they may hold a pool's internal
  lock (`pool._lock`) to keep a release waiting.
