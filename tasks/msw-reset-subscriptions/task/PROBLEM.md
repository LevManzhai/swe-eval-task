# msw: GraphQL subscriptions stop working after `resetHandlers()`

The repository in `/workspace/repo` is [msw](https://github.com/mswjs/msw)
(Mock Service Worker), at version 3.0.2. Its dependencies are installed.

## What a user reported

> We mock our GraphQL API with `setupServer()` and `graphql.link()`, including
> subscriptions over WebSocket. Our app keeps one `graphql-ws` client for its
> whole lifetime, so in tests the client is created once in `beforeAll` and
> stays connected, and `afterEach` calls `server.resetHandlers()` as the docs
> recommend.
>
> The first test passes. In every later test, subscriptions on that client
> never get any data. msw prints that the subscription "has no matching
> subscription handler", even though the handler is one of the handlers we
> passed to `setupServer()` and nothing removed it. If a test opens a new
> client instead, it works. HTTP handlers are fine.
>
> ```ts
> const api = graphql.link('https://api.example.com/graphql')
>
> const server = setupServer(
>   api.subscription('OnTick', ({ subscription }) => {
>     subscription.publish({ data: { tick: 1 } })
>   }),
> )
>
> let client: Client
> beforeAll(() => {
>   server.listen()
>   client = createClient({ url: 'wss://api.example.com/graphql', lazy: false })
> })
> afterEach(() => server.resetHandlers())
>
> test('first', async () => { /* subscribe to OnTick: gets { tick: 1 } */ })
> test('second', async () => { /* subscribe to OnTick: never resolves */ })
> ```
>
> Registering the same handler again with `server.use()` at the start of each
> test doesn't help either. Whatever the fix is, we also rely on handlers we
> add with `server.use()` in one test not leaking into the next one.

## What we want

`server.resetHandlers()` has to mean the same thing for a WebSocket connection
that is already open as it does for HTTP. After any reset, with or without
arguments, and whichever `graphql.link()` the handlers come from:

1. **Handlers that stay active keep working on open connections.** A handler
   that is still registered after the reset handles subscriptions on a
   connection that was opened before the reset, just as it did before.
2. **Handlers that the reset removed are gone for good.** A handler that was
   registered before the reset and is no longer registered after it never
   handles a subscription again, on any connection, and its resolver is not
   called.
3. **Everything the reset already does keeps working.** Handlers marked
   `{ once: true }` can match again after a reset, active subscriptions are
   still ended with their `finalize()` cleanups run, and a handler object can
   be registered again later (with `server.use()` or `server.resetHandlers()`)
   and work as before.

Behaviour that has nothing to do with this must not change. If an existing
test in the repository pins down a behaviour, keep it.

## Notes

- The existing test suite passes as it is. It doesn't cover this.
- The Node.js tests (`pnpm vitest run --project=node`) import msw from the
  built `lib/` directory, so run `pnpm build` after changing `src/`. There is
  no network access, and the browser test projects can't run here.
- Your change is graded by hidden tests that use msw's public API only:
  `setupServer` from `msw/node`, `graphql.link` and its `subscription()`
  handlers from `msw/graphql`, `server.use()` and `server.resetHandlers()`,
  with a real `graphql-ws` client connected to the mocked endpoint.
