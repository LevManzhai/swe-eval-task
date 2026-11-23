# Notes

## Where the bug comes from

- Repo: https://github.com/mswjs/msw (MIT, TypeScript)
- Fix commit: `3818a81` "fix(HandlersController): dispose of reset handlers"
  (9 October 2026, msw 3.0.2)
- Starting state: that commit with its source changes reverted and the tests
  it added removed (`environment/starting_state.patch`). Nothing else differs
  from upstream.

The reference solution (`solution/reference.patch`) is the source part of the
upstream commit: 3 files, about 80 changed lines.

## The cause → symptom chain

The user sees the symptom in the GraphQL subscription layer: a subscription on
a long-lived WebSocket client gets "no matching subscription handler" after
the first test. The cause is in the generic handler bookkeeping, two layers
away, plus a hidden sibling handler the user never registered.

1. `graphql.link()` creates a hidden **transport** handler for the endpoint
   (the `graphql-transport-ws` protocol session). Every `api.subscription()`
   handler carries it as a *sibling*, so it ends up in the handler list, but
   `listHandlers()` doesn't show it.
2. When a client connects, each matching subscription handler registers
   itself as a **subscriber** of that connection's session, in a
   module-level registry shared by all transports. This only happens at
   connect time.
3. `server.resetHandlers()` goes through the network to the
   `HandlersController`. Its `reset()` calls `reset()` on **every** current
   handler, including the hidden transport.
4. The transport's `reset()` ends the active subscriptions and also **drops
   all of its subscribers** from every open session: the handlers that stay
   registered as well as the ones the reset removes.
5. The client stays connected, so nothing registers again (step 2 runs only
   on connect). The next `subscribe` message finds an empty subscriber list
   and msw warns that nothing matches. A `server.use()` of the same handler
   doesn't help, for the same reason.

The obvious fix is to stop step 4 from dropping subscribers. Then the second
half shows up: the handlers that the reset *did* remove are still subscribed,
and they keep answering on the open connection (runtime handlers from the
previous test take precedence). Until now step 4 was the only thing that
unbound them. A correct fix has to do both:

- keep the subscribers of handlers that stay registered, and
- unbind the handlers that leave the network, which needs a "this handler was
  removed" event. The controller didn't have one: `Handler.dispose()` existed
  but was only called by `server.close()`.

Upstream computes kept vs. removed handlers in the controller, calls
`reset()` on the kept ones and `dispose()` on the removed ones (errors
reported, not thrown), adds `dispose()` to the subscription handler to
unsubscribe itself, and changes the transport's `reset()` to only end
subscriptions.

Hops from symptom to cause: the warning in the transport's subscribe
handling → the subscriber registry → the transport's `reset()` → the
controller's `reset()` that calls it on a hidden sibling, and, for the second
half, the missing disposal of removed handlers in the controller.

## Why there's no oracle

There's no second implementation of msw in the sandbox, and the expected
behaviour is not something the current code does on any path. It comes from
what `resetHandlers()` means for HTTP handlers and from msw's documentation.
A differential fuzzer has nothing to compare against. The solver has to
write scenario tests, and the important ones (a connection that outlives a
reset; a removed handler on that connection; the same handler object reused
in the next test) only come up if they understand *when* handlers are bound
to a connection.

## The hidden tests

`verifier/task.node.test.ts`, 12 tests, all through the public API:
`setupServer`, `graphql.link(...).subscription()`, `server.use()`,
`server.resetHandlers()` with and without arguments, and a real `graphql-ws`
client. Each test maps to a point of the statement:

| Statement point | Tests |
|---|---|
| 1. kept handlers keep working | initial handler after one and after several resets; a handler passed to `resetHandlers()` again; two links to one endpoint |
| 2. removed handlers are gone | runtime handler replaced on an open connection; its resolver is never called again; a runtime handler for another operation; handlers replaced by `resetHandlers(next)` |
| 3. existing behaviour kept | `{ once: true }` matches again; active subscriptions end with their `finalize()` cleanups; the same handler object used again in a later test; a handler added after a reset serves new connections |

The tests don't pin down whether handlers passed as the *new* initial
handlers in `resetHandlers(next)` serve connections that were already open:
upstream doesn't, and the statement doesn't ask for it.

The starting state fails 7 of the 12 (`run.sh` checks that it fails).

## Checking the checker

`run.sh` builds the image and runs the starting state, the reference, one
alternative and four wrong solutions against the upstream suite and the
hidden tests.

The upstream suite is the `unit` and `node` Vitest projects (810 tests).
Four files are deleted inside the throwaway container before it runs: three
Node.js scenarios resolve `test.mswjs.io`, and the Vite plugin test launches
Chromium. Neither works offline. The browser projects need Playwright
browsers and aren't run.

Every hidden test run starts with `pnpm build`, because msw's Node.js tests
import the built `lib/`, not `src/`. Without it every patch would be graded
against the starting state's build. I found this the hard way: my first run
had the starting state passing all hidden tests.

**Alternative (must pass).** `alt_fixes/01_detach_flag_cleared_on_connect.patch`
leaves the subscriber registry alone. A removed subscription handler marks
itself detached and refuses to match; connecting again clears the flag. The
controller finds removed handlers with a list filter instead of set
operations.

**Wrong solutions (must fail, all pass the upstream suite):**

| Patch | Why it's tempting | Hidden tests failed |
|---|---|---|
| `01_stop_dropping_subscribers_only` | It's the fix at the place the symptom points to: the transport drops the subscribers, so stop doing that. The report's test passes. | 6: every "removed handler" test, because removed handlers keep answering |
| `02_dispose_only_on_reset_without_arguments` | Correct for the `resetHandlers()` call in the report, but only on that path. `resetHandlers(next)` still resets everything. | 2 |
| `03_disposed_handler_never_matches_again` | A guard that turns removed handlers off for good. It passes every scenario with fresh handler objects. | 1: the same handler object reused in a later test stays dead |
| `04_dispose_every_websocket_handler` | "Release WebSocket handlers on reset" applied to all of them, kept ones included. | 9 |

## What I expect a strong agent to try first

Search for the warning text and find the subscriber list empty. From there,
find that the transport's `reset()` clears it and patch that: wrong solution
01. Whether it then fails depends on whether it writes a test where a
runtime handler and a kept handler share a connection across a reset. A
second likely trap is the guard in wrong solution 03, if it doesn't test
reusing handler objects, which is how a lot of test suites are written.

## Difficulty check

<!-- Left empty on purpose: attempts are run in separate fresh sessions. -->
