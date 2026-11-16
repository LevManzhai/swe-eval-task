# anyio: operations are not safe to cancel

The repository in `/workspace/repo` is [anyio](https://github.com/agronholm/anyio),
the async I/O library used underneath httpx, Starlette and many others. Only
the asyncio backend is installed.

## What a user reported

An HTTP client built on anyio wraps each request in a timeout:

```python
with anyio.move_on_after(timeout):
    stream = await anyio.connect_tcp(host, port)
    ...
```

Under load the process slowly runs out of file descriptors, and with
`-W always::ResourceWarning` it prints `unclosed <socket.socket ...>` warnings.
The user tracked it down to this: if the timeout fires at the moment one of
`connect_tcp()`'s connection attempts has just succeeded, `connect_tcp()`
raises the cancellation, and the socket that did connect is never closed.

## What we want

Fix that, but don't stop there. The reporter's case is one instance of a
general problem: parts of anyio do not behave correctly when the task calling
them is cancelled. We want anyio to honour the following contract **everywhere
in the library** (asyncio backend), not just in `connect_tcp()`.

**Cancellation contract**

1. **Nothing leaks.** If an operation is cancelled, every resource it had
   already acquired by then (sockets, files, temporary files and directories,
   limiter tokens, and so on) is released, or ends up owned by an object the
   caller can still clean up.
2. **Cleanup always happens.** Operations whose job is to release something
   (`aclose()`, `cleanup()`, the exit of an async context manager) actually
   release it, even if the calling task is already cancelled when it calls
   them or is cancelled while they run. They may let the cancellation
   propagate once the cleanup is done.
3. **No silent corruption.** After a cancelled call, the object it was called
   on keeps behaving as if the call had not been made (or as if it had
   completed). If that is impossible, every further use of the object must
   raise `anyio.BrokenResourceError`. It must never go on quietly misbehaving,
   for example by producing output the other side can't make sense of, or by
   no longer applying limits it applied before.
4. **Cancelling from another thread is safe.** Cancelling a
   `concurrent.futures.Future` that anyio handed to a worker thread must never
   raise an exception inside the event loop, whatever the event loop is doing
   at that moment.

Behaviour that does not involve cancellation must not change. If an existing
test in `tests/` pins down a behaviour, keep it.

## Notes

- The existing test suite passes as it is. It doesn't cover these cases.
- You don't need to support the Trio backend, and it isn't installed.
- Your patch is graded by hidden tests that cancel anyio operations at
  specific points and check the contract above. They only use anyio's public
  API, plus `unittest.mock`-style patching of standard library classes and
  functions (as seen from the anyio module that uses them) and of public
  backend methods, to choose the moment a cancellation happens.
