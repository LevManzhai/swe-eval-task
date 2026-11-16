"""
Hidden verifier for the "anyio cancellation safety" task.

Every test checks one clause of the cancellation contract in task/PROBLEM.md:

  (1) a cancelled operation releases whatever it had already acquired;
  (2) cleanup operations finish their cleanup even when the caller is
      cancelled;
  (3) after a cancelled call, an object behaves as if the call had not been
      made, or fails loudly with BrokenResourceError -- it never misbehaves
      silently;
  (4) cancelling a future handed to a worker thread never crashes anything.

The tests look at observable behaviour wherever that is possible. Where a race
has to be forced, they patch a public seam (a backend class method, a stdlib
constructor, the Future class used by the portal) rather than anyio's private
helpers, so that a correct fix written differently from upstream still passes.
"""

from __future__ import annotations

import asyncio
import gc
import os
import pathlib
import socket
import ssl
import tempfile
import threading
import time
import warnings
from concurrent.futures import Future
from typing import Any

import pytest
import trustme

import anyio
from anyio import (
    BrokenResourceError,
    CancelScope,
    CapacityLimiter,
    ClosedResourceError,
    EndOfStream,
    NamedTemporaryFile,
    SpooledTemporaryFile,
    TemporaryDirectory,
    TemporaryFile,
    connect_tcp,
    create_memory_object_stream,
    create_task_group,
    fail_after,
    from_thread,
    open_file,
    to_thread,
    wrap_file,
)
from anyio._core._eventloop import get_async_backend
from anyio.from_thread import BlockingPortal
from anyio.streams.file import FileReadStream, FileStreamAttribute, FileWriteStream
from anyio.streams.stapled import StapledObjectStream
from anyio.streams.tls import TLSStream
from anyio import wait_all_tasks_blocked
from anyio.lowlevel import checkpoint

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ca() -> trustme.CA:
    return trustme.CA()


@pytest.fixture(scope="module")
def server_context(ca: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("localhost").configure_cert(context)
    return context


@pytest.fixture(scope="module")
def client_context(ca: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ca.configure_trust(context)
    return context


@pytest.fixture
def server_sock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    yield sock
    sock.close()


@pytest.fixture
def private_tmpdir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A directory that only one test creates temporary files in."""
    path = tmp_path / "scratch"
    path.mkdir()
    return path


# ---------------------------------------------------------------------------
# connect_tcp(): a winning connection must not leak on outer cancellation
# ---------------------------------------------------------------------------


class TestConnectTCP:
    async def test_connected_stream_closed_when_outer_scope_cancelled(
        self, server_sock: socket.socket, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = get_async_backend()
        original = backend.connect_tcp
        streams: list[Any] = []

        async def connect_then_cancel(*args: Any, **kwargs: Any) -> Any:
            stream = await original(*args, **kwargs)
            streams.append(stream)
            scope.cancel()
            return stream

        monkeypatch.setattr(backend, "connect_tcp", connect_then_cancel)
        with CancelScope() as scope:
            await connect_tcp(*server_sock.getsockname())

        assert scope.cancelled_caught
        assert len(streams) == 1
        with pytest.raises(ClosedResourceError):
            await streams[0].send(b"x")

    async def test_peer_sees_the_connection_closed(
        self, server_sock: socket.socket, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = get_async_backend()
        original = backend.connect_tcp

        async def connect_then_cancel(*args: Any, **kwargs: Any) -> Any:
            stream = await original(*args, **kwargs)
            scope.cancel()
            return stream

        monkeypatch.setattr(backend, "connect_tcp", connect_then_cancel)
        with CancelScope() as scope:
            await connect_tcp(*server_sock.getsockname())

        accepted, _ = server_sock.accept()
        with accepted:
            accepted.settimeout(5)
            # EOF (or a reset) means the client closed its end
            try:
                assert accepted.recv(1) == b""
            except ConnectionResetError:
                pass


# ---------------------------------------------------------------------------
# SocketStream.receive(): read flow control must survive cancellation
# ---------------------------------------------------------------------------


def _push_until_stalled(sock: socket.socket, budget: int) -> int:
    """
    Send from a non-blocking socket until the peer stops accepting data for a
    full second, or until ``budget`` bytes went through. Returns the number of
    bytes the peer accepted.
    """
    chunk = b"\0" * 65536
    sent = 0
    sock.setblocking(False)
    stalled_since: float | None = None
    while sent < budget:
        try:
            sent += sock.send(chunk)
            stalled_since = None
        except BlockingIOError:
            now = time.monotonic()
            if stalled_since is None:
                stalled_since = now
            elif now - stalled_since > 1.0:
                break
            time.sleep(0.01)

    return sent


# Far more than the kernel will buffer on a loopback connection, and far less
# than a reader that keeps draining the socket lets through.
_BUDGET = 96 * 1024 * 1024
_LIMIT = 48 * 1024 * 1024


class TestReceiveBackpressure:
    async def test_baseline_unread_connection_applies_backpressure(
        self, server_sock: socket.socket
    ) -> None:
        async with await connect_tcp(*server_sock.getsockname()):
            peer, _ = server_sock.accept()
            with peer:
                sent = await to_thread.run_sync(_push_until_stalled, peer, _BUDGET)

        assert sent < _LIMIT

    async def test_precancelled_receive_restores_backpressure(
        self, server_sock: socket.socket
    ) -> None:
        async with await connect_tcp(*server_sock.getsockname()) as stream:
            peer, _ = server_sock.accept()
            with peer:
                with CancelScope() as scope:
                    scope.cancel()
                    await stream.receive()

                sent = await to_thread.run_sync(_push_until_stalled, peer, _BUDGET)

        assert sent < _LIMIT, (
            f"{sent} bytes were read off the socket while nobody was receiving"
        )

    async def test_receive_cancelled_while_waiting_restores_backpressure(
        self, server_sock: socket.socket
    ) -> None:
        async with await connect_tcp(*server_sock.getsockname()) as stream:
            peer, _ = server_sock.accept()
            with peer:
                async with create_task_group() as tg:
                    tg.start_soon(stream.receive)
                    await wait_all_tasks_blocked()
                    tg.cancel_scope.cancel()

                sent = await to_thread.run_sync(_push_until_stalled, peer, _BUDGET)

        assert sent < _LIMIT, (
            f"{sent} bytes were read off the socket while nobody was receiving"
        )

    async def test_stream_still_delivers_data_after_cancelled_receive(
        self, server_sock: socket.socket
    ) -> None:
        async with await connect_tcp(*server_sock.getsockname()) as stream:
            peer, _ = server_sock.accept()
            with peer:
                async with create_task_group() as tg:
                    tg.start_soon(stream.receive)
                    await wait_all_tasks_blocked()
                    tg.cancel_scope.cancel()

                peer.sendall(b"hello")
                with fail_after(5):
                    assert await stream.receive() == b"hello"


# ---------------------------------------------------------------------------
# TLSStream: a send() cancelled after encryption must not corrupt the session
# ---------------------------------------------------------------------------


async def _tls_pair(
    server_context: ssl.SSLContext, client_context: ssl.SSLContext, buffer: int
) -> tuple[TLSStream, TLSStream, StapledObjectStream, StapledObjectStream]:
    # ``buffer`` applies to the client-to-server direction only. The other
    # direction is always buffered, so the server can flush its post-handshake
    # messages without waiting for the client to read them.
    c2s_send, c2s_receive = create_memory_object_stream[bytes](buffer)
    s2c_send, s2c_receive = create_memory_object_stream[bytes](10)
    client_transport = StapledObjectStream(c2s_send, s2c_receive)
    server_transport = StapledObjectStream(s2c_send, c2s_receive)
    result: dict[str, TLSStream] = {}

    async def wrap_server() -> None:
        result["server"] = await TLSStream.wrap(
            server_transport, server_side=True, ssl_context=server_context
        )

    async with create_task_group() as tg:
        tg.start_soon(wrap_server)
        result["client"] = await TLSStream.wrap(
            client_transport, hostname="localhost", ssl_context=client_context
        )

    return result["client"], result["server"], client_transport, server_transport


async def _check_after_lost_record(
    client: TLSStream, server: TLSStream, server_transport: StapledObjectStream
) -> None:
    """
    After a cancelled send, the client must either refuse to be used any more
    (BrokenResourceError), or keep the session intact so that the server can
    still decrypt what is sent next.
    """
    received = bytearray()

    async def serve() -> None:
        try:
            while True:
                received.extend(await server.receive())
        except EndOfStream:
            # The client closed its side; answer its closing handshake, if any
            try:
                await server.aclose()
            except Exception:
                pass
        except (BrokenResourceError, ssl.SSLError):
            received.extend(b"<server-error>")

    with fail_after(10):
        async with create_task_group() as tg:
            tg.start_soon(serve)
            try:
                await client.send(b"second")
            except BrokenResourceError:
                with pytest.raises(BrokenResourceError):
                    await client.send(b"third")
                with pytest.raises(BrokenResourceError):
                    await client.receive()
            else:
                # The session survived; the peer must be able to read on
                while not received.endswith(b"second"):
                    assert b"<server-error>" not in received, (
                        "the peer could not decrypt data sent after a cancelled "
                        "send(), but the client did not report the stream as broken"
                    )
                    await wait_all_tasks_blocked()
                    await anyio.sleep(0.01)

            # Closing must not hang or blow up, whatever state the stream is in
            with fail_after(5):
                try:
                    await client.aclose()
                except BrokenResourceError:
                    pass

            tg.cancel_scope.cancel()

    await server_transport.aclose()


class TestTLSCancelledSend:
    async def test_precancelled_send(
        self, server_context: ssl.SSLContext, client_context: ssl.SSLContext
    ) -> None:
        client, server, _, server_transport = await _tls_pair(
            server_context, client_context, buffer=10
        )
        await client.send(b"first")
        assert await server.receive() == b"first"
        with CancelScope() as scope:
            scope.cancel()
            await client.send(b"cancelled")

        await _check_after_lost_record(client, server, server_transport)

    async def test_send_cancelled_while_transport_blocks(
        self, server_context: ssl.SSLContext, client_context: ssl.SSLContext
    ) -> None:
        # With an unbuffered transport, send() blocks after encrypting until
        # the server side takes the record. Cancel it right there.
        client, server, _, server_transport = await _tls_pair(
            server_context, client_context, buffer=0
        )
        async with create_task_group() as tg:
            tg.start_soon(server.receive)
            await client.send(b"first")

        async with create_task_group() as tg:
            tg.start_soon(client.send, b"cancelled")
            await wait_all_tasks_blocked()
            tg.cancel_scope.cancel()

        await _check_after_lost_record(client, server, server_transport)

    async def test_uncancelled_sends_unaffected(
        self, server_context: ssl.SSLContext, client_context: ssl.SSLContext
    ) -> None:
        client, server, _, server_transport = await _tls_pair(
            server_context, client_context, buffer=10
        )
        for i in range(5):
            await client.send(b"msg%d" % i)
            assert await server.receive() == b"msg%d" % i

        await server_transport.aclose()


# ---------------------------------------------------------------------------
# BlockingPortal: a future cancelled while the call completes
# ---------------------------------------------------------------------------


class _RacingFuture(Future):
    """A future that the waiting thread cancels just as the result arrives."""

    def set_result(self, result: Any) -> None:
        self.cancel()
        super().set_result(result)

    def set_exception(self, exception: BaseException | None) -> None:
        self.cancel()
        super().set_exception(exception)


class TestPortalCompletionRace:
    @pytest.mark.parametrize("raises", [False, True], ids=["result", "exception"])
    async def test_cancel_during_completion_does_not_crash_the_portal(
        self, monkeypatch: pytest.MonkeyPatch, raises: bool
    ) -> None:
        async def func() -> str:
            if raises:
                raise ValueError("boom")

            return "ok"

        monkeypatch.setattr(from_thread, "Future", _RacingFuture)
        async with BlockingPortal() as portal:
            if raises:
                with pytest.raises(ValueError, match="boom"):
                    await to_thread.run_sync(portal.call, func)
            else:
                assert await to_thread.run_sync(portal.call, func) == "ok"

            # The portal is still alive and serving calls
            monkeypatch.undo()
            assert await to_thread.run_sync(portal.call, _answer) == 42

    @pytest.mark.parametrize("raises", [False, True], ids=["result", "exception"])
    def test_cancel_during_completion_with_start_blocking_portal(
        self, monkeypatch: pytest.MonkeyPatch, raises: bool
    ) -> None:
        async def func() -> str:
            if raises:
                raise ValueError("boom")

            return "ok"

        with from_thread.start_blocking_portal("asyncio") as portal:
            monkeypatch.setattr(from_thread, "Future", _RacingFuture)
            future = portal.start_task_soon(func)
            done = threading.Event()
            future.add_done_callback(lambda f: done.set())
            assert done.wait(5)
            monkeypatch.undo()
            assert portal.call(_answer) == 42


async def _answer() -> int:
    return 42


# ---------------------------------------------------------------------------
# CapacityLimiter.acquire_on_behalf_of(): cancellation releases the borrower
# ---------------------------------------------------------------------------


class TestCapacityLimiterOnBehalfOf:
    @pytest.mark.parametrize("delay", [0, 1, 2, 3])
    async def test_cancelled_acquire_on_behalf_of(self, delay: int) -> None:
        borrower = object()
        limiter = CapacityLimiter(1)
        task = asyncio.create_task(limiter.acquire_on_behalf_of(borrower))
        for _ in range(delay):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            # It finished before the cancellation landed; give the token back
            limiter.release_on_behalf_of(borrower)

        assert limiter.borrowed_tokens == 0
        assert limiter.statistics().borrowers == ()
        # The limiter is still usable by the same borrower and by others
        limiter.acquire_on_behalf_of_nowait(borrower)
        limiter.release_on_behalf_of(borrower)
        async with limiter:
            pass

    async def test_cancelled_acquire_does_not_touch_current_task_tokens(
        self,
    ) -> None:
        borrower = object()
        limiter = CapacityLimiter(2)
        await limiter.acquire()  # the current task holds one token
        try:
            task = asyncio.create_task(limiter.acquire_on_behalf_of(borrower))
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            else:
                limiter.release_on_behalf_of(borrower)

            stats = limiter.statistics()
            assert stats.borrowed_tokens == 1
            assert stats.borrowers == (asyncio.current_task(),)
        finally:
            limiter.release()

        assert limiter.borrowed_tokens == 0


# ---------------------------------------------------------------------------
# Temporary directories
# ---------------------------------------------------------------------------


class TestTemporaryDirectory:
    async def test_exit_while_cancelled_removes_directory(
        self, private_tmpdir: pathlib.Path
    ) -> None:
        with CancelScope() as scope:
            async with TemporaryDirectory(dir=private_tmpdir) as name:
                path = pathlib.Path(name)
                assert path.is_dir()
                scope.cancel()

        assert not path.exists()
        assert list(private_tmpdir.iterdir()) == []

    async def test_exit_with_cancellation_in_body_removes_directory(
        self, private_tmpdir: pathlib.Path
    ) -> None:
        with CancelScope() as scope:
            async with TemporaryDirectory(dir=private_tmpdir) as name:
                path = pathlib.Path(name)
                scope.cancel()
                await checkpoint()

        assert scope.cancelled_caught
        assert not path.exists()

    async def test_cleanup_while_cancelled_removes_directory(
        self, private_tmpdir: pathlib.Path
    ) -> None:
        manager = TemporaryDirectory(dir=private_tmpdir)
        name = await manager.__aenter__()
        path = pathlib.Path(name)
        try:
            with CancelScope() as scope:
                scope.cancel()
                await manager.cleanup()
                await checkpoint()

            assert not path.exists()
        finally:
            await manager.__aexit__(None, None, None)

        assert list(private_tmpdir.iterdir()) == []

    async def test_cancellation_during_creation_leaves_nothing_behind(
        self, private_tmpdir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = tempfile.TemporaryDirectory
        created: list[pathlib.Path] = []

        def create(*args: Any, **kwargs: Any) -> Any:
            directory = original(*args, **kwargs)
            created.append(pathlib.Path(directory.name))
            # Cancellation arrives while the directory is being created
            from_thread.run_sync(scope.cancel)
            return directory

        monkeypatch.setattr(tempfile, "TemporaryDirectory", create)
        manager = TemporaryDirectory(dir=private_tmpdir)
        try:
            with CancelScope() as scope:
                async with manager:
                    await checkpoint()

            assert scope.cancelled_caught
            assert len(created) == 1
            assert not created[0].exists()
        finally:
            monkeypatch.undo()
            await manager.cleanup()
            gc.collect()

        assert list(private_tmpdir.iterdir()) == []

    async def test_uncancelled_lifecycle_unchanged(
        self, private_tmpdir: pathlib.Path
    ) -> None:
        async with TemporaryDirectory(dir=private_tmpdir) as name:
            path = pathlib.Path(name)
            (path / "file.txt").write_text("data")
            assert path.is_dir()

        assert not path.exists()

        manager = TemporaryDirectory(dir=private_tmpdir)
        name = await manager.__aenter__()
        await manager.cleanup()
        assert not pathlib.Path(name).exists()
        await manager.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# SpooledTemporaryFile.rollover()
# ---------------------------------------------------------------------------


class TestSpooledRollover:
    async def test_cancelled_rollover_keeps_contents_and_position(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = tempfile.TemporaryFile

        def create(*args: Any, **kwargs: Any) -> Any:
            from_thread.run_sync(scope.cancel)
            return original(*args, **kwargs)

        async with SpooledTemporaryFile() as stf:
            await stf.write(b"hello world")
            await stf.seek(5)
            monkeypatch.setattr(tempfile, "TemporaryFile", create)
            with CancelScope() as scope:
                await stf.rollover()

            monkeypatch.undo()
            assert await stf.tell() == 5
            await stf.seek(0)
            assert await stf.read() == b"hello world"
            await stf.write(b"!")
            await stf.seek(0)
            assert await stf.read() == b"hello world!"

    async def test_cancelled_rollover_triggered_by_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = tempfile.TemporaryFile

        def create(*args: Any, **kwargs: Any) -> Any:
            from_thread.run_sync(scope.cancel)
            return original(*args, **kwargs)

        async with SpooledTemporaryFile(max_size=8) as stf:
            await stf.write(b"abcdef")
            monkeypatch.setattr(tempfile, "TemporaryFile", create)
            with CancelScope() as scope:
                await stf.write(b"ghijkl")

            monkeypatch.undo()
            await stf.seek(0)
            data = await stf.read()
            # The cancelled write may or may not have happened, but what was
            # already in the file must still be there
            assert data in (b"abcdef", b"abcdefghijkl")


# ---------------------------------------------------------------------------
# Closing files and file streams while cancelled
# ---------------------------------------------------------------------------


class TestCloseWhileCancelled:
    async def test_async_file_aclose(self, tmp_path: pathlib.Path) -> None:
        f = await open_file(tmp_path / "foo", "wb")
        with CancelScope() as scope:
            scope.cancel()
            await f.aclose()

        assert f.wrapped.closed

    async def test_async_file_context_exit(self, tmp_path: pathlib.Path) -> None:
        with CancelScope() as scope:
            async with await open_file(tmp_path / "foo", "wb") as f:
                scope.cancel()

        assert f.wrapped.closed

    async def test_wrapped_file_context_exit(self, tmp_path: pathlib.Path) -> None:
        raw = open(tmp_path / "foo", "wb")
        try:
            with CancelScope() as scope:
                async with wrap_file(raw):
                    scope.cancel()

            assert raw.closed
        finally:
            raw.close()

    async def test_temporary_file_context_exit(self) -> None:
        with CancelScope() as scope:
            async with TemporaryFile() as f:
                scope.cancel()

        assert f.wrapped.closed

    async def test_named_temporary_file_removed(self, private_tmpdir: pathlib.Path) -> None:
        with CancelScope() as scope:
            async with NamedTemporaryFile(dir=private_tmpdir) as f:
                name = f.name
                assert os.path.exists(name)
                scope.cancel()

        assert not os.path.exists(name)

    async def test_spooled_temporary_file_context_exit(self) -> None:
        with CancelScope() as scope:
            async with SpooledTemporaryFile(max_size=4) as f:
                await f.write(b"spill over to disk")
                scope.cancel()

        assert f.closed

    @pytest.mark.parametrize("kind", ["read", "write"])
    async def test_file_stream_aclose(self, tmp_path: pathlib.Path, kind: str) -> None:
        path = tmp_path / "data"
        path.write_bytes(b"data")
        if kind == "read":
            stream = await FileReadStream.from_path(path)
        else:
            stream = await FileWriteStream.from_path(path)

        raw = stream.extra(FileStreamAttribute.file)
        try:
            with CancelScope() as scope:
                async with stream:
                    scope.cancel()

            assert raw.closed
        finally:
            raw.close()

    @pytest.mark.parametrize("kind", ["read", "write"])
    async def test_file_stream_aclose_direct(
        self, tmp_path: pathlib.Path, kind: str
    ) -> None:
        path = tmp_path / "data"
        path.write_bytes(b"data")
        if kind == "read":
            stream = await FileReadStream.from_path(path)
        else:
            stream = await FileWriteStream.from_path(path)

        raw = stream.extra(FileStreamAttribute.file)
        try:
            with CancelScope() as scope:
                scope.cancel()
                await stream.aclose()

            assert raw.closed
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# Nothing above may leave ResourceWarnings behind
# ---------------------------------------------------------------------------


async def test_cancelled_connect_does_not_warn(
    server_sock: socket.socket, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = get_async_backend()
    original = backend.connect_tcp

    async def connect_then_cancel(*args: Any, **kwargs: Any) -> Any:
        stream = await original(*args, **kwargs)
        scope.cancel()
        return stream

    monkeypatch.setattr(backend, "connect_tcp", connect_then_cancel)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        with CancelScope() as scope:
            await connect_tcp(*server_sock.getsockname())

        await checkpoint()
        gc.collect()

    leaks = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert not leaks, [str(w.message) for w in leaks]
