# aiohttp: edge cases in HTTP handling

The repository in `/workspace/repo` is [aiohttp](https://github.com/aio-libs/aiohttp),
the asyncio HTTP client and server. It is installed without its C extensions
(`AIOHTTP_NO_EXTENSIONS=1`), so the pure-Python HTTP parser and helpers are
the ones in use. Treat them as the implementation to fix; the Cython sources
are not built and don't need changing.

## What a user reported

> One of our aiohttp workers went to 100% CPU and stopped answering. We
> traced it to a single request from a misconfigured load balancer that sent
> `Forwarded: a`. Our access-log middleware reads `request.forwarded`, and
> that call never returns. One request like that takes a whole worker down.

## What we want

Fix that, and treat it as a sign that aiohttp's HTTP handling has more edge
cases of the same kind: inputs or situations that are legal (or at least
possible), that a test with ordinary traffic never produces, and that make
aiohttp misbehave. We want the following to hold across the library, client
and server:

1. **Chunking doesn't matter.** What aiohttp parses or returns from a read
   (`StreamReader`, multipart readers, the HTTP parser) never depends on how
   the incoming bytes happened to be split into chunks. Where an API hands out
   data in pieces that callers are expected to process one at a time, every
   piece can be processed on its own.
2. **HTTP/1.1 semantics are respected.** Messages are framed exactly as RFC
   9112 says: a request's body is read according to its framing headers,
   whatever its method, so that the next request on the connection starts
   where it should. The request target means what RFC 9112 section 3.2 says it
   means, including the host it designates.
3. **Nothing hangs, spins or crashes.** No header value, body or other input,
   and no documented value of a configuration option, makes aiohttp loop
   forever or fail with an unexpected exception.
4. **Connections don't outlive their use.** On the server, a connection that is
   idle for longer than `keepalive_timeout` is closed, whatever state it is
   in. On the client, a connection that can no longer be used is closed when
   that becomes clear, not later by the garbage collector.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The existing tests for the relevant modules pass as they are. They don't
  cover these cases.
- Your patch is graded by hidden tests. Most of them talk to a real aiohttp
  server over raw sockets, or call public APIs (`StreamReader`,
  `BodyPartReader`, `web.Request`, `ClientSession`, connectors). To simulate a
  network failure at a precise point, a test may patch the method that writes
  a client request to the connection.
