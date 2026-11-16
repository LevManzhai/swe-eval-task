"""
Hidden verifier for the "redis-py connection lifecycle" task.

Every test checks one clause of the contract in task/PROBLEM.md:

  (1) a connection taken from a pool goes back exactly once, whatever happens
      to the code using it (an exception, a failed handshake, cancellation);
  (2) a connection that is handed out again is either connected and fully
      set up (AUTH, SELECT, ...) or disconnected, never half set up;
  (3) a connection carries nothing over from its previous user;
  (4) a dropped connection is not reopened just to undo state that dropping
      it already undid on the server.

A Redis server must be listening on localhost:6379. Leaks are detected the way
a user would notice them wherever possible: through a pool of size one, whose
next command fails or blocks if the connection never came back, and through
the server's own count of connections received.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio

import redis
import redis.asyncio as aredis
from redis.credentials import CredentialProvider
from redis.exceptions import (
    AuthenticationError,
    ConnectionError,
    MaxConnectionsError,
    NoPermissionError,
    RedisError,
)

HOST, PORT = "localhost", 6379

pytestmark = pytest.mark.timeout(60)


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------


def connections_received() -> int:
    admin = redis.Redis(host=HOST, port=PORT)
    try:
        return int(admin.info("stats")["total_connections_received"])
    finally:
        admin.close()


@pytest.fixture
def admin():
    client = redis.Redis(host=HOST, port=PORT)
    client.flushdb()
    yield client
    with contextlib.suppress(Exception):
        client.client_unpause()
    client.close()


@pytest.fixture
def acl_user(admin):
    """A user that may authenticate with username/password."""
    name = f"task-{uuid.uuid4().hex[:8]}"
    admin.acl_setuser(
        name, enabled=True, reset=True, passwords=["+secret"], commands=["+@all"],
        keys=["*"], channels=["*"],
    )
    yield name
    admin.acl_deluser(name)


@pytest_asyncio.fixture
async def ar():
    client = aredis.Redis(host=HOST, port=PORT)
    yield client
    await client.aclose()


async def released(pool: Any, connection: Any, timeout: float = 3.0) -> bool:
    """Wait until ``connection`` is no longer counted as in use by ``pool``."""
    async with asyncio.timeout(timeout):
        while connection in pool._in_use_connections:
            await asyncio.sleep(0.01)
    return True


async def cancel_when(task: asyncio.Task, event: asyncio.Event, times: int = 1) -> None:
    await asyncio.wait_for(event.wait(), 5)
    for _ in range(times):
        task.cancel()
        await asyncio.sleep(0.01)
    with pytest.raises(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# (4) Pipeline.reset() on a dropped connection
# ---------------------------------------------------------------------------


class TestPipelineResetOnDroppedConnection:
    def test_sync_reset_does_not_reconnect(self, admin):
        client = redis.Redis(host=HOST, port=PORT)
        try:
            client.set("a", 0)
            pipe = client.pipeline()
            pipe.watch("a")
            leased = pipe.connection
            leased.disconnect()
            before = connections_received()
            pipe.reset()
            assert connections_received() - before == 1  # only our own probe
            assert not leased.is_connected
            assert pipe.watching is False
            assert pipe.connection is None
            # and the connection went back to the pool
            assert leased not in client.connection_pool._in_use_connections
        finally:
            client.close()

    async def test_async_reset_does_not_reconnect(self, admin):
        client = aredis.Redis(host=HOST, port=PORT)
        try:
            await client.set("a", 0)
            pipe = client.pipeline()
            await pipe.watch("a")
            leased = pipe.connection
            await leased.disconnect()
            before = connections_received()
            await pipe.reset()
            assert connections_received() - before == 1
            assert not leased.is_connected
            assert pipe.watching is False
            assert pipe.connection is None
            assert await released(client.connection_pool, leased)
        finally:
            await client.aclose()

    async def test_async_cancelled_watch_transaction(self, admin):
        client = aredis.Redis(host=HOST, port=PORT)
        try:
            await client.set("a", 0)
            pipe = client.pipeline()
            await pipe.watch("a")
            leased = pipe.connection
            pipe.multi()
            pipe.set("a", 1)
            # Writes are paused on the server, so EXEC hangs until cancelled
            admin.client_pause(5000, all=False)
            try:
                task = asyncio.create_task(pipe.execute())
                await asyncio.sleep(0.3)
                assert not task.done()
                before = connections_received()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                new_connections = connections_received() - before - 1
            finally:
                admin.client_unpause()

            assert new_connections == 0, (
                "cleanup after the cancelled transaction opened a new connection"
            )
            assert pipe.watching is False
            assert pipe.connection is None
            assert await released(client.connection_pool, leased)
            assert await client.get("a") == b"0"
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# (3) A PubSub's push handler must not stay on a pooled connection
# ---------------------------------------------------------------------------


async def _next_message(p: Any, timeout: float = 2.0) -> Any:
    async with asyncio.timeout(timeout):
        while True:
            message = await p.get_message(timeout=0.1)
            if message is not None:
                return message


def _next_message_sync(p: Any, timeout: float = 2.0) -> Any:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = p.get_message(timeout=0.1)
        if message is not None:
            return message
    return None


class TestPushHandlerNotInherited:
    async def test_async_next_pubsub_gets_its_own_messages(self, admin):
        seen: list[Any] = []
        pool = aredis.ConnectionPool(host=HOST, port=PORT, protocol=3, max_connections=1)
        client = aredis.Redis(connection_pool=pool)
        try:
            async def handler(message: Any) -> None:  # async client: a coroutine
                seen.append(message)

            p1 = client.pubsub(push_handler_func=handler)
            await p1.subscribe("foo")
            async with asyncio.timeout(2):
                while not seen:
                    await p1.get_message(timeout=0.1)
            await p1.aclose()
            seen.clear()

            p2 = client.pubsub()
            await p2.subscribe("foo")
            first = await _next_message(p2)
            assert first["type"] == "subscribe"
            assert admin.publish("foo", "hello") == 1
            second = await _next_message(p2)
            assert second["type"] == "message" and second["data"] == b"hello"
            assert seen == [], "a closed PubSub's handler received messages"
            await p2.aclose()
        finally:
            await client.aclose()
            await pool.disconnect()

    def test_sync_next_pubsub_gets_its_own_messages(self, admin):
        seen: list[Any] = []
        pool = redis.ConnectionPool(host=HOST, port=PORT, protocol=3, max_connections=1)
        client = redis.Redis(connection_pool=pool)
        try:
            p1 = client.pubsub(push_handler_func=seen.append)
            p1.subscribe("foo")
            assert _next_message_sync(p1) is None or seen  # handled by the handler
            for _ in range(20):
                if seen:
                    break
                p1.get_message(timeout=0.1)
            assert seen
            p1.close()
            seen.clear()

            p2 = client.pubsub()
            p2.subscribe("foo")
            first = _next_message_sync(p2)
            assert first is not None and first["type"] == "subscribe"
            assert admin.publish("foo", "hello") == 1
            second = _next_message_sync(p2)
            assert second is not None and second["data"] == b"hello"
            assert seen == [], "a closed PubSub's handler received messages"
            p2.close()
        finally:
            client.close()
            pool.disconnect()


# ---------------------------------------------------------------------------
# (2) A failed handshake must not leave a "connected" but unauthenticated socket
# ---------------------------------------------------------------------------


class _FailingOnceProvider(CredentialProvider):
    def __init__(self, username: str, stall: bool = False):
        self.username = username
        self.stall = stall
        self.calls = 0
        self.fetching = asyncio.Event()

    def get_credentials(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("token endpoint unavailable")
        return self.username, "secret"

    async def get_credentials_async(self):
        self.calls += 1
        if self.calls == 1:
            self.fetching.set()
            if self.stall:
                await asyncio.Event().wait()
            raise RuntimeError("token endpoint unavailable")
        return self.username, "secret"


class TestFailedHandshake:
    async def test_async_provider_error_then_next_command_is_authenticated(
        self, acl_user
    ):
        provider = _FailingOnceProvider(acl_user)
        pool = aredis.ConnectionPool(
            host=HOST, port=PORT, credential_provider=provider, max_connections=1
        )
        client = aredis.Redis(connection_pool=pool)
        try:
            with pytest.raises(RuntimeError):
                await client.ping()
            assert await client.acl_whoami() == acl_user
        finally:
            await client.aclose()
            await pool.disconnect()

    async def test_async_cancelled_credential_fetch(self, acl_user):
        provider = _FailingOnceProvider(acl_user, stall=True)
        pool = aredis.ConnectionPool(
            host=HOST, port=PORT, credential_provider=provider, max_connections=1
        )
        client = aredis.Redis(connection_pool=pool)
        try:
            task = asyncio.create_task(client.ping())
            await cancel_when(task, provider.fetching)
            assert await client.acl_whoami() == acl_user
        finally:
            await client.aclose()
            await pool.disconnect()

    def test_sync_provider_error_then_next_command_is_authenticated(self, acl_user):
        provider = _FailingOnceProvider(acl_user)
        pool = redis.ConnectionPool(
            host=HOST, port=PORT, credential_provider=provider, max_connections=1
        )
        client = redis.Redis(connection_pool=pool)
        try:
            with pytest.raises(RuntimeError):
                client.ping()
            assert client.acl_whoami() == acl_user
        finally:
            client.close()
            pool.disconnect()

    async def test_async_select_happens_after_failed_handshake(self, admin):
        # Same thing without credentials: the database must be selected
        admin.select(0)
        aredis_pool = aredis.ConnectionPool(host=HOST, port=PORT, db=5, max_connections=1)
        client = aredis.Redis(connection_pool=aredis_pool)
        try:
            original = aredis.Connection.on_connect_check_health
            calls = 0

            async def flaky(self, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("callback failed")
                return await original(self, *args, **kwargs)

            with mock.patch.object(aredis.Connection, "on_connect_check_health", flaky):
                with pytest.raises(RuntimeError):
                    await client.set("db-check", "x")
                await client.set("db-check", "x")
            info = (await client.client_info())
            assert int(info["db"]) == 5
        finally:
            await client.aclose()
            await aredis_pool.disconnect()


# ---------------------------------------------------------------------------
# (1) ConnectionPool.release() and its callers under cancellation
# ---------------------------------------------------------------------------


class TestReleaseWhenCancelled:
    @pytest.mark.parametrize(
        "pool_class", [aredis.ConnectionPool, aredis.BlockingConnectionPool]
    )
    async def test_release_cancelled_while_waiting(self, pool_class):
        pool = pool_class(host=HOST, port=PORT)
        try:
            connection = await pool.get_connection()
            await pool._lock.acquire()
            try:
                task = asyncio.ensure_future(pool.release(connection))
                await asyncio.sleep(0.05)
                task.cancel()
                await asyncio.sleep(0.01)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                pool._lock.release()
            assert await released(pool, connection)
            assert connection in pool._available_connections
        finally:
            await pool.disconnect()

    async def test_command_cancelled_during_release(self):
        pool = aredis.ConnectionPool(host=HOST, port=PORT, max_connections=1)
        client = aredis.Redis(connection_pool=pool)
        try:
            await client.ping()
            entered = asyncio.Event()
            release = pool.release

            async def signalling_release(connection):
                entered.set()
                return await release(connection)

            await pool._lock.acquire()
            try:
                with mock.patch.object(pool, "release", side_effect=signalling_release):
                    task = asyncio.ensure_future(client.ping())
                    await asyncio.sleep(0.05)
                    # get_connection() itself needs the lock; let it through
                    pool._lock.release()
                    await asyncio.wait_for(entered.wait(), 5)
                    await pool._lock.acquire()
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            finally:
                if pool._lock.locked():
                    pool._lock.release()

            # The pool has one connection; it must be usable again
            async with asyncio.timeout(3):
                while True:
                    try:
                        assert await client.ping()
                        break
                    except MaxConnectionsError:
                        await asyncio.sleep(0.05)
        finally:
            await client.aclose()
            await pool.disconnect()

    async def test_pipeline_reset_cancelled_during_release(self):
        pool = aredis.ConnectionPool(host=HOST, port=PORT)
        client = aredis.Redis(connection_pool=pool)
        try:
            pipe = client.pipeline()
            await pipe.watch("a")
            leased = pipe.connection
            await pool._lock.acquire()
            try:
                task = asyncio.ensure_future(pipe.reset())
                await asyncio.sleep(0.05)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            finally:
                pool._lock.release()
            assert await released(pool, leased)
            assert pipe.connection is None
        finally:
            await client.aclose()
            await pool.disconnect()


# ---------------------------------------------------------------------------
# (1) PubSub.aclose() under cancellation
# ---------------------------------------------------------------------------


class TestPubSubAcloseCancelled:
    async def _check(self, stage: str) -> None:
        pool = aredis.ConnectionPool(host=HOST, port=PORT, max_connections=1)
        client = aredis.Redis(connection_pool=pool)
        try:
            p = client.pubsub()
            await p.subscribe("foo")
            leased = p.connection
            started = asyncio.Event()
            resume = asyncio.Event()

            if stage == "disconnect":
                original = leased.disconnect

                async def slow(*args, **kwargs):
                    started.set()
                    await resume.wait()
                    return await original(*args, **kwargs)

                patcher = mock.patch.object(leased, "disconnect", side_effect=slow)
            else:
                patcher = contextlib.nullcontext()

            if stage == "release":
                # Keep the release waiting for the pool's lock
                await pool._lock.acquire()
            try:
                with patcher:
                    task = asyncio.ensure_future(p.aclose())
                    if stage == "release":
                        await asyncio.sleep(0.1)
                    else:
                        await asyncio.wait_for(started.wait(), 5)
                    task.cancel()
                    await asyncio.sleep(0.01)
                    task.cancel()
                    await asyncio.sleep(0.01)
                    resume.set()
                    if pool._lock.locked() and stage == "release":
                        pool._lock.release()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            finally:
                if stage == "release" and pool._lock.locked():
                    pool._lock.release()

            assert await released(pool, leased)
            assert await client.ping()
        finally:
            await client.aclose()
            await pool.disconnect()

    async def test_cancelled_while_disconnecting(self):
        await self._check("disconnect")

    async def test_cancelled_while_releasing(self):
        await self._check("release")

    async def test_async_with_pubsub_inside_timeout(self):
        pool = aredis.ConnectionPool(host=HOST, port=PORT, max_connections=1)
        client = aredis.Redis(connection_pool=pool)
        try:
            for _ in range(5):
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(0.05):
                        async with client.pubsub() as p:
                            await p.subscribe("foo")
                            await asyncio.sleep(1)
            assert await client.ping()
        finally:
            await client.aclose()
            await pool.disconnect()


# ---------------------------------------------------------------------------
# (1) Monitor whose entry fails or is cancelled
# ---------------------------------------------------------------------------


@pytest.fixture
def no_monitor_user(admin):
    name = f"task-nomon-{uuid.uuid4().hex[:8]}"
    admin.acl_setuser(name, enabled=True, reset=True, nopass=True, commands=["+ping"])
    yield name
    admin.acl_deluser(name)


class TestMonitorEntry:
    async def test_async_failed_entry_releases_connection(self, no_monitor_user):
        pool = aredis.ConnectionPool(
            host=HOST, port=PORT, username=no_monitor_user, max_connections=1
        )
        client = aredis.Redis(connection_pool=pool)
        try:
            with pytest.raises(NoPermissionError):
                async with client.monitor():
                    pytest.fail("MONITOR must not be entered")
            assert await client.ping()
        finally:
            await client.aclose()
            await pool.disconnect()

    def test_sync_failed_entry_releases_connection(self, no_monitor_user):
        pool = redis.ConnectionPool(
            host=HOST, port=PORT, username=no_monitor_user, max_connections=1
        )
        client = redis.Redis(connection_pool=pool)
        try:
            with pytest.raises(NoPermissionError):
                with client.monitor():
                    pytest.fail("MONITOR must not be entered")
            assert client.ping()
        finally:
            client.close()
            pool.disconnect()

    async def test_async_cancelled_entry_releases_connection(self, admin):
        pool = aredis.ConnectionPool(host=HOST, port=PORT, max_connections=1)
        client = aredis.Redis(connection_pool=pool)
        try:
            # Writes paused does not block MONITOR; pause everything instead
            admin.client_pause(5000, all=True)
            try:
                task = asyncio.create_task(client.monitor().__aenter__())
                await asyncio.sleep(0.3)
                assert not task.done()
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            finally:
                admin.client_unpause()
            async with asyncio.timeout(5):
                assert await client.ping()
        finally:
            await client.aclose()
            await pool.disconnect()


# ---------------------------------------------------------------------------
# (1) Redis / RedisCluster used as async context managers
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx_client(monkeypatch):
    # The statement asks for the standalone client only
    client = aredis.Redis(host=HOST, port=PORT)

    async def initialize():
        return client

    monkeypatch.setattr(client, "initialize", initialize)
    return client


class TestClientContextManager:
    async def test_cancelled_entry_does_not_keep_the_client_open(
        self, ctx_client, monkeypatch
    ):
        initializing = asyncio.Event()

        async def hang():
            initializing.set()
            await asyncio.Event().wait()

        closes = 0

        async def aclose():
            nonlocal closes
            closes += 1

        monkeypatch.setattr(ctx_client, "aclose", aclose)
        monkeypatch.setattr(ctx_client, "initialize", hang)

        async def use():
            async with ctx_client:
                pytest.fail("must not enter")

        task = asyncio.create_task(use())
        await cancel_when(task, initializing)
        assert closes == 0

        async def ok():
            return ctx_client

        monkeypatch.setattr(ctx_client, "initialize", ok)
        async with ctx_client as entered:
            assert entered is ctx_client
        assert closes == 1, "the last context exit did not close the client"

    async def test_cancelled_exit_still_closes(self, ctx_client, monkeypatch):
        closing = asyncio.Event()
        finish = asyncio.Event()
        closed = asyncio.Event()

        async def aclose():
            closing.set()
            await finish.wait()
            closed.set()

        monkeypatch.setattr(ctx_client, "aclose", aclose)

        async def use():
            async with ctx_client:
                pass

        task = asyncio.create_task(use())
        await asyncio.wait_for(closing.wait(), 5)
        task.cancel()
        await asyncio.sleep(0.01)
        finish.set()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await asyncio.wait_for(closed.wait(), 5)

    async def test_failed_entry_does_not_close_an_active_context(
        self, ctx_client, monkeypatch
    ):
        closes = 0

        async def aclose():
            nonlocal closes
            closes += 1

        monkeypatch.setattr(ctx_client, "aclose", aclose)
        async with ctx_client:
            async def boom():
                raise RedisError("init failed")

            monkeypatch.setattr(ctx_client, "initialize", boom)
            with pytest.raises(RedisError):
                async with ctx_client:
                    pass
            assert closes == 0, "a failed nested entry closed the client in use"
        assert closes == 1
