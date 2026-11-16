"""
Hidden verifier for the "aiohttp HTTP edge cases" task.

Each test checks one clause of the contract in task/PROBLEM.md:

  (1) how bytes are split into chunks never changes what is parsed or read;
  (2) messages are framed as the HTTP/1.1 RFCs say, so one request's bytes
      never end up in another, and the request target means what RFC 9112
      says it means;
  (3) no input makes aiohttp hang, spin or crash;
  (4) every connection, client or server side, is closed when it is no longer
      useful, without waiting for the garbage collector.

The server-side tests talk to a real aiohttp server over raw sockets.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import gc
import socket
import threading
import warnings
from typing import Any
from unittest import mock

import pytest
from multidict import CIMultiDict

import aiohttp
from aiohttp import web
from aiohttp.multipart import BodyPartReader
from aiohttp.streams import StreamReader
from aiohttp.test_utils import make_mocked_request

pytestmark = pytest.mark.timeout(60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Protocol:
    """Just enough of a protocol for a StreamReader."""

    _reading_paused = False

    def pause_reading(self, *args: Any, **kwargs: Any) -> None:
        pass

    def resume_reading(self, *args: Any, **kwargs: Any) -> None:
        pass


def make_stream(chunks: list[bytes], limit: int = 2**16) -> StreamReader:
    loop = asyncio.get_running_loop()
    stream = StreamReader(_Protocol(), limit, loop=loop)  # type: ignore[arg-type]
    for chunk in chunks:
        stream.feed_data(chunk)
    stream.feed_eof()
    return stream


@contextlib.asynccontextmanager
async def run_server(app_or_handler: Any, **site_kwargs: Any):
    if isinstance(app_or_handler, web.Application):
        runner: web.BaseRunner = web.AppRunner(app_or_handler, **site_kwargs)
    else:
        # Handler options (e.g. keepalive_timeout) belong to the Server
        runner = web.ServerRunner(web.Server(app_or_handler, **site_kwargs))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield port
    finally:
        await runner.cleanup()


async def raw_exchange(port: int, data: bytes, timeout: float = 5.0) -> bytes:
    """Send raw bytes, then read until the server closes or goes quiet."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(data)
        await writer.drain()
        out = b""
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(65536), timeout)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            out += chunk
            if timeout > 0.5:
                timeout = 0.5  # once data flows, stop soon after it stops
        return out
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


def run_with_deadline(func: Any, seconds: float) -> Any:
    """Run func in a daemon thread; fail if it does not return in time."""
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["value"] = func()
        except BaseException as exc:  # pragma: no cover - reported below
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        pytest.fail(f"did not finish within {seconds} seconds (hang or busy loop)")
    if "error" in result:
        raise result["error"]
    return result.get("value")


# ---------------------------------------------------------------------------
# (1) StreamReader.readuntil(): a separator split across chunks
# ---------------------------------------------------------------------------


class TestReaduntilChunking:
    PAYLOAD = b"first\r\nsecond\r\nthird"

    @pytest.mark.parametrize("cut", range(1, len(PAYLOAD)))
    async def test_two_chunks_any_cut(self, cut: int) -> None:
        stream = make_stream([self.PAYLOAD[:cut], self.PAYLOAD[cut:]])
        assert await stream.readuntil(b"\r\n") == b"first\r\n"
        assert await stream.readuntil(b"\r\n") == b"second\r\n"
        assert await stream.read() == b"third"

    async def test_one_byte_per_chunk(self) -> None:
        stream = make_stream([bytes([b]) for b in self.PAYLOAD])
        assert await stream.readuntil(b"\r\n") == b"first\r\n"
        assert await stream.readuntil(b"\r\n") == b"second\r\n"
        assert await stream.read() == b"third"

    async def test_long_separator_split_three_ways(self) -> None:
        data = b"head--BOUNDARY--tail"
        stream = make_stream([b"head--BOU", b"NDA", b"RY--tail"])
        assert await stream.readuntil(b"--BOUNDARY--") == b"head--BOUNDARY--"
        assert await stream.read() == b"tail"
        assert data  # keep the readable form of the input next to the test

    async def test_separator_not_present(self) -> None:
        stream = make_stream([b"abc\r", b"x"])
        assert await stream.readuntil(b"\r\n") == b"abc\rx"


# ---------------------------------------------------------------------------
# (2) HEAD requests with a body, and pipelining after them (pure-Python parser)
# ---------------------------------------------------------------------------


class TestHeadRequestBody:
    async def test_head_body_is_read_and_next_request_is_intact(self) -> None:
        seen: list[tuple[str, str, bytes]] = []

        async def handler(request: web.BaseRequest) -> web.Response:
            seen.append((request.method, request.path, await request.read()))
            return web.Response(text="ok")

        async with run_server(handler) as port:
            out = await raw_exchange(
                port,
                b"HEAD /first HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello"
                b"GET /second HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n",
            )

        assert ("HEAD", "/first", b"hello") in seen
        assert ("GET", "/second", b"") in seen
        assert len(seen) == 2
        assert out.count(b"HTTP/1.1 200") == 2

    async def test_head_with_chunked_body(self) -> None:
        seen: list[tuple[str, bytes]] = []

        async def handler(request: web.BaseRequest) -> web.Response:
            seen.append((request.method, await request.read()))
            return web.Response(text="ok")

        async with run_server(handler) as port:
            await raw_exchange(
                port,
                b"HEAD / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"3\r\nabc\r\n0\r\n\r\n"
                b"GET /next HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n",
            )

        assert seen == [("HEAD", b"abc"), ("GET", b"")]

    async def test_client_still_ignores_body_of_head_response(self) -> None:
        # Responses to HEAD never have a body, whatever Content-Length says
        async def handler(request: web.BaseRequest) -> web.Response:
            return web.Response(body=b"x" * 10)

        async with run_server(handler) as port:
            async with aiohttp.ClientSession() as session:
                async with session.head(f"http://127.0.0.1:{port}/") as resp:
                    assert resp.status == 200
                    assert await resp.read() == b""
                async with session.get(f"http://127.0.0.1:{port}/") as resp:
                    assert await resp.read() == b"x" * 10


# ---------------------------------------------------------------------------
# (2) Absolute-form request targets (RFC 9112, section 3.2.2)
# ---------------------------------------------------------------------------


class TestAbsoluteForm:
    async def test_host_comes_from_the_target_including_port(self) -> None:
        seen: dict[str, Any] = {}

        async def handler(request: web.BaseRequest) -> web.Response:
            seen["host"] = request.host
            seen["url"] = str(request.url)
            return web.Response(text="ok")

        async with run_server(handler) as port:
            await raw_exchange(
                port,
                b"GET http://example.com:8080/path?q=1 HTTP/1.1\r\n"
                b"Host: other.invalid\r\nConnection: close\r\n\r\n",
            )

        assert seen["host"] == "example.com:8080"
        assert seen["url"] == "http://example.com:8080/path?q=1"

    async def test_default_port_is_not_added(self) -> None:
        seen: dict[str, Any] = {}

        async def handler(request: web.BaseRequest) -> web.Response:
            seen["host"] = request.host
            return web.Response(text="ok")

        async with run_server(handler) as port:
            await raw_exchange(
                port,
                b"GET http://example.com/path HTTP/1.1\r\n"
                b"Host: other.invalid\r\nConnection: close\r\n\r\n",
            )

        assert seen["host"] == "example.com"

    async def test_domain_sub_application_matches_the_target(self) -> None:
        app = web.Application()
        sub = web.Application()

        async def sub_handler(request: web.Request) -> web.Response:
            return web.Response(text="sub")

        async def main_handler(request: web.Request) -> web.Response:
            return web.Response(text="main")

        sub.router.add_get("/", sub_handler)
        app.add_domain("example.com", sub)
        app.router.add_get("/", main_handler)

        async with run_server(app) as port:
            out = await raw_exchange(
                port,
                b"GET http://example.com/ HTTP/1.1\r\n"
                b"Host: other.invalid\r\nConnection: close\r\n\r\n",
            )
            assert out.endswith(b"sub"), out
            out = await raw_exchange(
                port,
                b"GET http://other.invalid/ HTTP/1.1\r\n"
                b"Host: example.com\r\nConnection: close\r\n\r\n",
            )
            assert out.endswith(b"main"), out

    async def test_origin_form_still_uses_the_host_header(self) -> None:
        seen: dict[str, Any] = {}

        async def handler(request: web.BaseRequest) -> web.Response:
            seen["host"] = request.host
            return web.Response(text="ok")

        async with run_server(handler) as port:
            await raw_exchange(
                port,
                b"GET /path HTTP/1.1\r\nHost: example.com:8443\r\n"
                b"Connection: close\r\n\r\n",
            )

        assert seen["host"] == "example.com:8443"


# ---------------------------------------------------------------------------
# (3) A malformed Forwarded header must not hang the worker
# ---------------------------------------------------------------------------


class TestForwardedHeader:
    @pytest.mark.parametrize(
        "value",
        ["a", "for=1.2.3.4;a", "for=1.2.3.4; ", "for=1.2.3.4;;x", "for=1.2.3.4, a"],
    )
    def test_malformed_value_returns(self, value: str) -> None:
        request = make_mocked_request(
            "GET", "/", headers=CIMultiDict({"Forwarded": value})
        )
        forwarded = run_with_deadline(lambda: request.forwarded, 5)
        assert isinstance(forwarded, tuple)

    def test_valid_value_still_parsed(self) -> None:
        request = make_mocked_request(
            "GET",
            "/",
            headers=CIMultiDict({"Forwarded": 'for=1.2.3.4;proto=https, for="[::1]"'}),
        )
        forwarded = run_with_deadline(lambda: request.forwarded, 5)
        assert forwarded[0]["for"] == "1.2.3.4"
        assert forwarded[0]["proto"] == "https"
        assert forwarded[1]["for"] == "[::1]"


# ---------------------------------------------------------------------------
# (1)/(3) Multipart body parts
# ---------------------------------------------------------------------------


def _part(body: bytes, headers: dict[str, str], boundary: bytes = b"--:") -> BodyPartReader:
    loop = asyncio.get_running_loop()
    stream = StreamReader(_Protocol(), 2**16, loop=loop)  # type: ignore[arg-type]
    stream.feed_data(body + b"\r\n" + boundary + b"--\r\n")
    stream.feed_eof()
    return BodyPartReader(boundary, CIMultiDict(headers), stream)


async def _read_all_chunks(part: BodyPartReader, size: int) -> list[bytes]:
    chunks = []
    for _ in range(10000):
        chunk = await part.read_chunk(size)
        if not chunk:
            break
        chunks.append(chunk)
    assert part.at_eof()
    return chunks


class TestMultipartParts:
    @pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 16])
    async def test_zero_content_length_any_chunk_size(self, size: int) -> None:
        part = _part(b"", {"Content-Length": "0"})
        assert await part.read_chunk(size) == b""
        assert part.at_eof()

    async def test_zero_content_length_read(self) -> None:
        part = _part(b"", {"Content-Length": "0"})
        assert await part.read() == b""

    # A chunk needs room for at least one quartet plus a line break to be
    # decodable on its own, so tiny sizes are not part of the contract.
    @pytest.mark.parametrize("size", [7, 9, 13, 64, 100])
    @pytest.mark.parametrize("wrap", [0, 4, 6, 76])
    @pytest.mark.parametrize("with_length", [False, True])
    async def test_base64_chunks_decode_independently(
        self, size: int, wrap: int, with_length: bool
    ) -> None:
        raw = bytes(range(256)) * 2 + b"tail!"
        encoded = base64.b64encode(raw)
        if wrap:
            encoded = b"\r\n".join(
                encoded[i : i + wrap] for i in range(0, len(encoded), wrap)
            )
        headers = {"Content-Transfer-Encoding": "base64"}
        if with_length:
            headers["Content-Length"] = str(len(encoded))
        part = _part(encoded, headers)
        chunks = await _read_all_chunks(part, size)
        # Each chunk must decode on its own, and together give the payload
        decoded = b"".join(part.decode(c) for c in chunks)
        assert decoded == raw

    async def test_base64_read_whole_part(self) -> None:
        raw = b"hello world, this is base64"
        encoded = base64.b64encode(raw)
        part = _part(encoded, {"Content-Transfer-Encoding": "base64"})
        assert await part.read(decode=True) == raw


# ---------------------------------------------------------------------------
# (4) Server: idle connections are closed even before a first request
# ---------------------------------------------------------------------------


class TestIdleServerConnections:
    async def test_connection_without_any_request_is_closed(self) -> None:
        async def handler(request: web.BaseRequest) -> web.Response:
            return web.Response(text="ok")

        async with run_server(handler, keepalive_timeout=0.3) as port:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                assert await asyncio.wait_for(reader.read(), timeout=5) == b""
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def test_connection_after_a_request_is_still_closed_when_idle(self) -> None:
        async def handler(request: web.BaseRequest) -> web.Response:
            return web.Response(text="ok")

        async with run_server(handler, keepalive_timeout=0.3) as port:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                await writer.drain()
                data = await asyncio.wait_for(reader.read(), timeout=5)
                assert data.startswith(b"HTTP/1.1 200")
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def test_active_connection_is_not_cut_off(self) -> None:
        async def handler(request: web.BaseRequest) -> web.Response:
            await asyncio.sleep(0.6)  # longer than keepalive_timeout
            return web.Response(text="done")

        async with run_server(handler, keepalive_timeout=0.3) as port:
            out = await raw_exchange(
                port, b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"
            )
        assert out.startswith(b"HTTP/1.1 200") and out.endswith(b"done")


# ---------------------------------------------------------------------------
# (3) Client: keepalive_timeout=None
# ---------------------------------------------------------------------------


class TestKeepaliveTimeoutNone:
    async def test_connection_reuse_does_not_crash(self) -> None:
        peers: set[Any] = set()

        async def handler(request: web.BaseRequest) -> web.Response:
            peers.add(request.transport.get_extra_info("peername"))  # type: ignore[union-attr]
            return web.Response(text="ok")

        async with run_server(handler) as port:
            connector = aiohttp.TCPConnector(keepalive_timeout=None)
            async with aiohttp.ClientSession(connector=connector) as session:
                for _ in range(3):
                    async with session.get(f"http://127.0.0.1:{port}/") as resp:
                        assert await resp.text() == "ok"
        assert len(peers) == 1, "the idle connection was not reused"

    async def test_default_keepalive_still_works(self) -> None:
        async def handler(request: web.BaseRequest) -> web.Response:
            return web.Response(text="ok")

        async with run_server(handler) as port:
            async with aiohttp.ClientSession() as session:
                for _ in range(2):
                    async with session.get(f"http://127.0.0.1:{port}/") as resp:
                        assert await resp.text() == "ok"

    def test_force_close_with_keepalive_timeout_still_rejected(self) -> None:
        async def make() -> None:
            aiohttp.TCPConnector(force_close=True, keepalive_timeout=5)

        with pytest.raises(ValueError):
            asyncio.run(make())


# ---------------------------------------------------------------------------
# (4) Client: a proxy connection whose CONNECT cannot be sent
# ---------------------------------------------------------------------------


class TestProxyConnectFailure:
    async def test_proxy_connection_closed_when_connect_send_fails(self) -> None:
        accepted: list[socket.socket] = []
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        listener.settimeout(5)
        proxy_port = listener.getsockname()[1]

        from aiohttp import client_reqrep

        original_send = client_reqrep.ClientRequestBase._send

        async def failing_send(self: Any, conn: Any) -> Any:
            if self.method == "CONNECT":
                raise aiohttp.ClientConnectionResetError(
                    "Cannot write to closing transport"
                )
            return await original_send(self, conn)

        caught: list[BaseException] = []
        gc.disable()
        try:
            with mock.patch.object(client_reqrep.ClientRequestBase, "_send", failing_send):
                async with aiohttp.ClientSession() as session:
                    task = asyncio.ensure_future(
                        session.get(
                            "https://example.invalid/",
                            proxy=f"http://127.0.0.1:{proxy_port}",
                        )
                    )
                    conn, _ = await asyncio.get_running_loop().run_in_executor(
                        None, listener.accept
                    )
                    accepted.append(conn)
                    try:
                        await task
                    except aiohttp.ClientError as exc:
                        caught.append(exc)  # keep the traceback alive

                    assert caught, "the request was expected to fail"
                    # Without relying on garbage collection, the client must
                    # already have closed its side of the proxy connection
                    conn.settimeout(5)
                    data = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: conn.recv(65536)
                    )
                    assert data == b"", "the proxy connection was left open"
        finally:
            gc.enable()
            for c in accepted:
                c.close()
            listener.close()
            caught.clear()
