# Notes

## Where the bugs come from

- Repo: https://github.com/agronholm/anyio
- Base commit: `9df02f0b8362e9f4a1fc3a4404052d0d7016e4f0` (16 November 2026)
- Reverted (source code only; the tests and changelog lines they added are
  removed from the starting state too):

| Commit | PR | File | What it fixed |
|---|---|---|---|
| `c7b992c` | #1367 | `_core/_sockets.py` | `connect_tcp()` leaked the winning connection when an enclosing scope was cancelled before the happy-eyeballs task group exited |
| `031412d` | #1386 | `streams/tls.py` | a `send()` cancelled after `SSLObject.write()` lost an encrypted record, so the peer could not decrypt anything sent afterwards; the stream now reports itself broken |
| `6219807` | #1424 | `_backends/_asyncio.py` | a cancelled TCP `receive()` left `resume_reading()` in effect, so data kept being read into memory with nobody receiving |
| `633965b` | #1410 | `from_thread.py` | `BlockingPortal` crashed with `InvalidStateError` when its future was cancelled just as the call completed |
| `9e6b71e` | — | `_backends/_asyncio.py` | `CapacityLimiter.acquire_on_behalf_of()` released the current task instead of the borrower when cancelled in its shielded checkpoint |
| `033fc52` | #1304 | `_core/_tempfile.py` | `TemporaryDirectory.__aexit__` skipped the cleanup if the task was already cancelled |
| `f6a15f6` | #1316 | `_core/_tempfile.py` | the same bug in `TemporaryDirectory.cleanup()`, which #1304 had missed |
| `fc141a7` | #1403 | `_core/_tempfile.py` | a cancellation checkpoint between creating the directory and returning from `__aenter__` leaked the directory |
| `46b9422` | #1404 | `_core/_tempfile.py` | cancellation in the middle of `SpooledTemporaryFile.rollover()` lost the buffered contents |
| `ecd9b2a` | #1318 | `streams/file.py` | `FileReadStream` / `FileWriteStream` `aclose()` didn't close the file when cancelled |
| `5172506` | #1314 | `_core/_fileio.py` | `AsyncFile.aclose()` didn't close the file when cancelled |

All eleven reverse cleanly on top of the base commit. With them reverted the
library's own suite still passes (about 2,100 tests on the asyncio backend),
so the visible tests give nothing away.

I left out two fixes from the same series that I'd have liked to include:
`a87a823` (cancelled `send()` on a paused transport) and `5d3830d`
(`CancelScope` swallowing a native `Task.cancel()`). Later refactors touched
the same code, and reverting them would have meant writing the "old" code
myself instead of restoring what upstream actually had.

## Why I picked it

Every rejected candidate in this repo (see [`REJECTED.md`](../../REJECTED.md))
went the same way: the agent built itself an oracle and ground through the
task. With `portion` the oracle was the original class, with `tomlkit` it was
`tomllib`, with `croniter` it was documentation that listed every case.

Cancellation bugs are different in three ways that matter for this:

1. **Nothing to compare against.** Whether an operation is cancellation-safe
   isn't a property of its output. There's no second implementation in the
   sandbox: Trio isn't installed, git history is gone, and the regression tests
   and changelog entries are removed.
2. **Every bug has its own trigger.** Some fire only with a scope that was
   cancelled before the call, some only when cancellation lands while a
   transport is blocked, one only when a worker thread cancels a
   `concurrent.futures.Future` between two specific lines, one only when a
   native `Task.cancel()` arrives inside a shielded checkpoint. Finding them
   means reading each `await` in the library and asking what happens if
   cancellation lands right there.
3. **The cause is far from the symptom.** The statement's example is in
   `_core/_sockets.py`. The other ten bugs are in six other files.

## The problem statement

It describes one real-looking user report (the `connect_tcp()` leak) and then
a four-point contract:

1. a cancelled operation releases what it had acquired;
2. cleanup operations finish their cleanup even if cancelled;
3. after a cancelled call an object behaves as if the call hadn't happened, or
   raises `BrokenResourceError` from then on;
4. cancelling a future given to a worker thread never crashes the event loop.

It doesn't list the other ten places. Every hidden test checks one of these
four points, so a solver who takes the contract seriously and audits the
library has everything they need. I wrote the contract so that more than one
design satisfies it. For TLS, for example, "mark the stream broken" (what
upstream did) and "keep the lost ciphertext and send it first next time" are
both accepted.

## The hidden tests

`verifier/test_task.py`, one class per subsystem. They use the public API and
only reach inside anyio in three places, each a public seam rather than a
private helper:

- the backend's `connect_tcp()` class method, to cancel right after a
  connection succeeds;
- `tempfile.TemporaryDirectory` / `tempfile.TemporaryFile`, to cancel while a
  directory or file is being created in a worker thread;
- `anyio.from_thread.Future`, to cancel a future exactly as its result arrives.

Points worth noting:

- **Backpressure is measured from outside.** Instead of checking the
  transport's private state, a peer thread pushes data at the connection until
  it stalls. With reading paused the kernel buffers fill up after a few
  megabytes; with reading stuck on, anyio keeps draining the socket and the
  peer gets 96 MB through. A baseline test checks that an unread connection
  does stall, so the threshold isn't arbitrary.
- **Two cancellation timings for each stateful bug.** For TLS and for
  `receive()` there is a pre-cancelled variant and a "cancelled while blocked"
  variant. The second exists to reject the shallow fix of adding a
  `checkpoint_if_cancelled()` at the top of the method.
- **Leniency where the contract allows it.** TLS accepts both "broken" and
  "still intact". The rollover test accepts the file in either its rolled-over
  or its in-memory state, as long as contents and position are right.
  `cleanup()` may or may not re-raise the cancellation.
- **Behaviour without cancellation is checked as well**, so a fix that, say,
  breaks normal TLS sends fails.

## Checking the checker

`run.sh` builds the image and runs everything with `--network none`:

- the starting state passes the upstream suite and fails the hidden tests;
- `solution/reference.patch` passes both;
- `verifier/alt_fixes/01_resend_tls_and_thread_side_rollover.patch` passes
  both. It is deliberately built differently from upstream: TLS keeps the
  unsent ciphertext instead of breaking the stream, the rollover runs entirely
  in the worker thread and only switches the object over at the end,
  `connect_tcp()` uses a hand-over flag in a `finally`, the temporary-directory
  creation keeps its checkpoint but cleans up on failure;
- each of the fourteen `verifier/wrong_fixes/` passes the upstream suite and
  fails the hidden tests:
  - `01`–`11`: everything fixed except one of the eleven bugs;
  - `12`: the portal "fixed" by catching `InvalidStateError`. This was my own
    first attempt at the alternative solution, and the hidden tests caught it.
    A `concurrent.futures.Future` that has been cancelled but not yet notified
    accepts `set_result()` without complaint and stops being cancelled, so the
    exception you expect to catch never comes;
  - `13`, `14`: `checkpoint_if_cancelled()` added at the top of
    `SocketStream.receive()` / `TLSStream.send()` instead of handling
    cancellation where it can actually land.

Two things the self-check found in my own work while I was building this, both
fixed before any difficulty attempt ran:

- the TLS "cancelled while blocked" test deadlocked even on the reference
  solution, because both directions of the in-memory transport were
  unbuffered and the server's post-handshake messages had nowhere to go;
- the alternative solution's portal fix was wrong (now wrong fix `12`).

### Environment notes

- The image is `python:3.12.16-bookworm` (the full one, not slim). It already
  has git, so nothing is installed with apt.
- Only the asyncio backend is installed. Trio and uvloop are left out so that
  there is no second implementation to compare against, and because several
  of these bugs are asyncio-only.
- The upstream-suite check in `run.sh` skips tests marked `network`, plus five
  tests that need an IPv6 loopback interface, which some Docker setups don't
  provide under `--network none`. They fail identically with and without any
  patch.

## Difficulty check

Same bar as for every task here: a strong coding agent gets `PROBLEM.md` and
the repository, one try, no hints. I accept the task if at most one attempt
in three passes the hidden tests. Attempts run one at a time, and I stop as
soon as the outcome is decided.

Results are added below as they come in.
