"""
Hidden verifier for the "urllib3 response edge cases" task.

Each test checks one point of the contract in task/PROBLEM.md:

  (1) a response body reads the same however it is read: in one call or in
      reads of any size, whatever the content encoding;
  (2) values from the wire follow the HTTP grammar (RFC 9110/9112); anything
      else is an error or is normalised the way the RFC prescribes;
  (3) nothing raises an exception other than urllib3's documented ones, and
      nothing overflows, however large or odd the numbers involved;
  (4) a redirect never carries credentials or request-body state to a place
      it shouldn't, and honours what the server asked for;
  (5) misuse is reported before any data is lost.
"""

from __future__ import annotations

import gzip
import io
import socket
import threading
import time
import zlib
from typing import Any, Callable
from unittest import mock

import pytest

import urllib3
from urllib3 import HTTPConnectionPool, HTTPResponse, PoolManager, ProxyManager
from urllib3.exceptions import (
    HTTPError,
    InvalidChunkLength,
    InvalidHeader,
    ProtocolError,
    SSLError,
    UnrewindableBodyError,
)
from urllib3.util.retry import Retry

pytestmark = pytest.mark.timeout(60)


# ---------------------------------------------------------------------------
# A tiny scripted HTTP server
# ---------------------------------------------------------------------------


class Server:
    """Accepts connections and answers each request with ``respond(request)``."""

    def __init__(self, respond: Callable[[dict[str, Any]], bytes]) -> None:
        self.respond = respond
        self.requests: list[dict[str, Any]] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _read_request(self, conn: socket.socket) -> dict[str, Any] | None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return None
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers: dict[str, str] = {}
        raw_headers = []
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
            raw_headers.append((name.strip(), value.strip()))
        body = rest
        if "content-length" in headers:
            n = int(headers["content-length"])
            while len(body) < n:
                body += conn.recv(65536)
        elif headers.get("transfer-encoding", "").lower() == "chunked":
            while not body.endswith(b"0\r\n\r\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                body += chunk
        return {
            "method": method,
            "target": target,
            "headers": headers,
            "raw_headers": raw_headers,
            "body": body,
        }

    def _run(self) -> None:
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(5)
                try:
                    req = self._read_request(conn)
                except OSError:
                    continue
                if req is None:
                    continue
                self.requests.append(req)
                try:
                    conn.sendall(self.respond(req))
                except OSError:
                    pass

    def close(self) -> None:
        self._stop = True
        self.thread.join(2)
        self.sock.close()


@pytest.fixture
def make_server():
    servers: list[Server] = []

    def factory(respond: Callable[[dict[str, Any]], bytes]) -> Server:
        server = Server(respond)
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.close()


def raw_response(head: str, body: bytes = b"") -> bytes:
    return head.encode("latin-1") + b"\r\n\r\n" + body


def response_for(body: bytes, encoding: str | None) -> HTTPResponse:
    headers = {"content-encoding": encoding} if encoding else {}
    return HTTPResponse(
        body=io.BytesIO(body), headers=headers, preload_content=False, status=200
    )


# ---------------------------------------------------------------------------
# (1) Bodies read the same however they are read
# ---------------------------------------------------------------------------


PAYLOAD = b"".join(b"line %d of the payload\n" % i for i in range(400))


def _deflate_raw(data: bytes) -> bytes:
    obj = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return obj.compress(data) + obj.flush()


def _encoded(encoding: str) -> bytes:
    if encoding == "gzip":
        return gzip.compress(PAYLOAD)
    if encoding == "deflate":
        return zlib.compress(PAYLOAD)
    if encoding == "deflate-raw":
        return _deflate_raw(PAYLOAD)
    if encoding == "gzip-members":
        half = len(PAYLOAD) // 2
        return gzip.compress(PAYLOAD[:half]) + gzip.compress(PAYLOAD[half:])
    if encoding == "zstd":
        from backports import zstd

        return zstd.compress(PAYLOAD)
    raise AssertionError(encoding)


HEADER_FOR = {
    "gzip": "gzip",
    "deflate": "deflate",
    "deflate-raw": "deflate",
    "gzip-members": "gzip",
    "zstd": "zstd",
}


class TestReadSizes:
    @pytest.mark.parametrize("encoding", sorted(HEADER_FOR))
    @pytest.mark.parametrize("amt", [1, 3, 7, 64, 1000])
    def test_small_reads_give_the_whole_body(self, encoding: str, amt: int) -> None:
        resp = response_for(_encoded(encoding), HEADER_FOR[encoding])
        out = b""
        for _ in range(100000):
            chunk = resp.read(amt)
            if not chunk:
                break
            out += chunk
        assert out == PAYLOAD

    @pytest.mark.parametrize("encoding", sorted(HEADER_FOR))
    def test_stream_gives_the_whole_body(self, encoding: str) -> None:
        resp = response_for(_encoded(encoding), HEADER_FOR[encoding])
        assert b"".join(resp.stream(5)) == PAYLOAD

    @pytest.mark.parametrize("encoding", sorted(HEADER_FOR))
    def test_one_read_still_works(self, encoding: str) -> None:
        resp = response_for(_encoded(encoding), HEADER_FOR[encoding])
        assert resp.read() == PAYLOAD

    @pytest.mark.parametrize("method", ["read", "read1"])
    def test_multi_member_gzip_read_at_member_boundaries(self, method: str) -> None:
        data = gzip.compress(b"x" * 1024) + gzip.compress(b"y" * 1024)
        resp = response_for(data, "gzip")
        read = getattr(resp, method)
        assert read(1024) == b"x" * 1024
        assert read(1024) == b"y" * 1024
        assert read() == b""

    def test_stacked_encodings_in_one_byte_reads(self) -> None:
        msg = b"abc" * 10
        outer = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        data = outer.compress(_deflate_raw(msg)) + outer.flush()
        resp = response_for(data, "deflate, gzip")
        assert b"".join(iter(lambda: resp.read(1), b"")) == msg

    def test_truncated_zstd_body_is_an_error(self) -> None:
        from backports import zstd

        from urllib3.exceptions import DecodeError

        data = zstd.compress(PAYLOAD)[:-1]
        resp = response_for(data, "zstd")
        with pytest.raises(DecodeError):
            while resp.read(64):
                pass

    def test_empty_zstd_body_is_empty(self) -> None:
        resp = response_for(b"", "zstd")
        assert resp.read(64) == b""
        assert resp.read(64) == b""

    @pytest.mark.parametrize("how", ["read64", "stream", "big_then_rest"])
    def test_raw_deflate_over_the_wire_in_small_reads(self, make_server, how: str) -> None:
        msg = b"abc" * 2000
        data = _deflate_raw(msg)
        server = make_server(
            lambda req: raw_response(
                f"HTTP/1.1 200 OK\r\nContent-Encoding: deflate\r\nContent-Length: {len(data)}\r\nConnection: close",
                data,
            )
        )
        with HTTPConnectionPool("127.0.0.1", server.port, retries=False) as pool:
            resp = pool.request("GET", "/", preload_content=False)
            if how == "read64":
                out = b"".join(iter(lambda: resp.read(64), b""))
            elif how == "stream":
                out = b"".join(resp.stream(64))
            else:
                out = resp.read(5952) + resp.read()
        assert out == msg

    def test_multi_member_gzip_after_a_bounded_read(self) -> None:
        resp = response_for(_encoded("gzip-members"), "gzip")
        first = resp.read(10)
        rest = resp.read()
        assert first + rest == PAYLOAD


# ---------------------------------------------------------------------------
# (5) Switching decode mode is refused before data is lost
# ---------------------------------------------------------------------------


class TestDecodeModeSwitch:
    def test_switch_is_refused_without_consuming_data(self) -> None:
        resp = response_for(gzip.compress(PAYLOAD), "gzip")
        first = resp.read(10, decode_content=True)
        with pytest.raises(RuntimeError):
            resp.read(5, decode_content=False)
        rest = resp.read(decode_content=True)
        assert first + rest == PAYLOAD

    def test_switch_without_amount_is_refused_without_consuming_data(self) -> None:
        resp = response_for(gzip.compress(PAYLOAD), "gzip")
        first = resp.read(10, decode_content=True)
        with pytest.raises(RuntimeError):
            resp.read(decode_content=False)
        assert first + resp.read(decode_content=True) == PAYLOAD

    def test_raw_reads_alone_still_work(self) -> None:
        data = gzip.compress(PAYLOAD)
        resp = response_for(data, "gzip")
        assert resp.read(5, decode_content=False) + resp.read(decode_content=False) == data


# ---------------------------------------------------------------------------
# (2) Framing numbers and header values follow the grammar
# ---------------------------------------------------------------------------


class TestFraming:
    @pytest.mark.parametrize("value", ["+5", "5_0", "1_000", "0x10", "0o10", "\u0967\u0968", " -5"])
    def test_non_rfc_content_length_is_not_a_length(self, value: str) -> None:
        # RFC 9112 section 6.3: Content-Length = 1*DIGIT. A value int() would
        # accept but the grammar doesn't is not a usable length.
        resp = HTTPResponse(
            io.BytesIO(b"12345"), headers={"content-length": value}, preload_content=False
        )
        assert resp.length_remaining is None

    @pytest.mark.parametrize("value", ["5", " 5 ", "5, 5", " 5 , 5 "])
    def test_valid_content_length_is_a_length(self, value: str) -> None:
        resp = HTTPResponse(
            io.BytesIO(b"12345"), headers={"content-length": value}, preload_content=False
        )
        assert resp.length_remaining == 5

    def _chunked(self, make_server, body: bytes) -> HTTPResponse:
        server = make_server(
            lambda req: raw_response(
                "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close",
                body,
            )
        )
        pool = HTTPConnectionPool("127.0.0.1", server.port, retries=False)
        return pool.request("GET", "/", preload_content=False)

    @pytest.mark.parametrize("size", [b"+5", b"-5", b"5_", b"0x5", b"1_f", b" 5"])
    def test_invalid_chunk_size_is_rejected(self, make_server, size: bytes) -> None:
        resp = self._chunked(make_server, size + b"\r\nhello\r\n0\r\n\r\n")
        with pytest.raises((InvalidChunkLength, ProtocolError)):
            b"".join(resp.read_chunked())

    @pytest.mark.parametrize("size", [b"5", b"5 ", b"5;name=value", b"5\t"])
    def test_valid_chunk_sizes_still_read(self, make_server, size: bytes) -> None:
        resp = self._chunked(make_server, size + b"\r\nhello\r\n0\r\n\r\n")
        assert b"".join(resp.read_chunked()) == b"hello"


class TestHeaderValues:
    def _get_header(self, make_server, raw: bytes) -> str:
        server = make_server(
            lambda req: b"HTTP/1.1 200 OK\r\n"
            + raw
            + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )
        with HTTPConnectionPool("127.0.0.1", server.port, retries=False) as pool:
            return pool.request("GET", "/").headers["X-Test"]

    def test_obsolete_line_folding_is_unfolded(self, make_server) -> None:
        assert self._get_header(make_server, b"X-Test: first\r\n   second") == "first second"

    def test_folding_with_tabs(self, make_server) -> None:
        assert self._get_header(make_server, b"X-Test: a\r\n\tb\r\n c") == "a b c"

    def test_bare_lf_continuation_is_replaced(self, make_server) -> None:
        # http.client accepts bare-LF line endings and joins the continuation
        # line, leaving a raw LF in the value unless urllib3 replaces it.
        server = make_server(
            lambda req: b"HTTP/1.1 200 OK\n"
            b"Set-Cookie: sessionid=abc\n evil=INJECTED\n"
            b"Content-Length: 0\n"
            b"\n"
        )
        with HTTPConnectionPool("127.0.0.1", server.port, retries=False) as pool:
            r = pool.request("GET", "/")
        assert all("\r" not in v and "\n" not in v for v in r.headers.values())
        assert r.headers["set-cookie"].replace("  ", " ") == "sessionid=abc evil=INJECTED"

    def test_nul_is_replaced(self, make_server) -> None:
        assert self._get_header(make_server, b"X-Test: a\x00b") == "a b"

    def test_surrounding_whitespace_is_trimmed(self, make_server) -> None:
        assert self._get_header(make_server, b"X-Test: \t value \t") == "value"

    def test_ordinary_value_unchanged(self, make_server) -> None:
        assert self._get_header(make_server, b"X-Test: plain value") == "plain value"


# ---------------------------------------------------------------------------
# (3) Retry numbers never overflow or escape as other exceptions
# ---------------------------------------------------------------------------


class TestRetryNumbers:
    def _with_history(self, retry: Retry, n: int) -> Retry:
        for _ in range(n):
            retry = retry.increment(method="GET", url="/", error=ConnectionError())
        return retry

    @pytest.mark.parametrize("n", [1100, 5000])
    def test_backoff_does_not_overflow(self, n: int) -> None:
        retry = self._with_history(Retry(total=None, connect=None, backoff_factor=0.5, backoff_max=120), n)
        assert retry.get_backoff_time() == 120

    def test_zero_backoff_with_huge_history_and_jitter(self) -> None:
        retry = self._with_history(
            Retry(total=None, connect=None, backoff_factor=0, backoff_jitter=1.0), 1100
        )
        assert 0 <= retry.get_backoff_time() <= 1.0

    def test_small_backoff_unchanged(self) -> None:
        retry = self._with_history(Retry(total=10, backoff_factor=0.5), 3)
        assert retry.get_backoff_time() == 2.0

    @pytest.mark.parametrize(
        "value",
        ["Fri, 31 Dec 99999 23:59:59 GMT", "Tue, 01 Jan 10000 00:00:00 GMT"],
    )
    def test_out_of_range_retry_after_date(self, value: str) -> None:
        # Either reject the header with urllib3's own exception or turn it into
        # a usable, finite wait. Anything else (OverflowError, ValueError) is
        # an undocumented exception.
        import math

        try:
            seconds = Retry().parse_retry_after(value)
        except InvalidHeader:
            return
        assert isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds >= 0

    def test_valid_retry_after_still_parses(self) -> None:
        assert Retry().parse_retry_after("3") == 3


# ---------------------------------------------------------------------------
# (4) Redirects
# ---------------------------------------------------------------------------


class TestRedirects:
    def test_303_drops_chunked_framing(self, make_server) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"] == "/start":
                return raw_response(
                    "HTTP/1.1 303 See Other\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        server = make_server(respond)
        with HTTPConnectionPool("127.0.0.1", server.port) as pool:
            resp = pool.request(
                "POST", "/start", body=iter([b"abc", b"def"]), chunked=True
            )
            assert resp.data == b"ok"
        second = server.requests[-1]
        assert second["method"] == "GET"
        assert "transfer-encoding" not in second["headers"]
        assert second["body"] == b""

    def test_303_through_pool_manager_drops_chunked_framing(self, make_server) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"] == "/start":
                return raw_response(
                    "HTTP/1.1 303 See Other\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        server = make_server(respond)
        with PoolManager() as pm:
            resp = pm.request(
                "POST",
                f"http://127.0.0.1:{server.port}/start",
                body=iter([b"abc"]),
                headers={"Transfer-Encoding": "chunked"},
            )
            assert resp.data == b"ok"
        second = server.requests[-1]
        assert second["method"] == "GET"
        assert "transfer-encoding" not in second["headers"]

    def test_pool_manager_redirect_honours_retry_after(self, make_server) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"] == "/start":
                return raw_response(
                    "HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close"
                ) if False else raw_response(
                    "HTTP/1.1 307 Temporary Redirect\r\nRetry-After: 2\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        server = make_server(respond)
        slept: list[float] = []
        with mock.patch("urllib3.util.retry.time.sleep", side_effect=slept.append):
            with PoolManager() as pm:
                resp = pm.request(
                    "GET",
                    f"http://127.0.0.1:{server.port}/start",
                    retries=Retry(redirect=3, respect_retry_after_header=True),
                )
                assert resp.data == b"ok"
        assert slept and max(slept) == pytest.approx(2, abs=0.01)

    def test_cross_host_redirect_through_http_proxy_strips_credentials(
        self, make_server
    ) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"].startswith("http://first.test"):
                return raw_response(
                    "HTTP/1.1 302 Found\r\nLocation: http://second.test/landing\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        proxy = make_server(respond)
        with ProxyManager(f"http://127.0.0.1:{proxy.port}") as pm:
            resp = pm.request(
                "GET",
                "http://first.test/start",
                headers={"Authorization": "Bearer secret", "Cookie": "id=1"},
            )
            assert resp.data == b"ok"
        second = proxy.requests[-1]
        assert second["target"].startswith("http://second.test/")
        assert "authorization" not in second["headers"]
        assert "cookie" not in second["headers"]
        assert second["headers"].get("host") == "second.test"

    def test_same_host_redirect_through_http_proxy_keeps_credentials(
        self, make_server
    ) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"].endswith("/start"):
                return raw_response(
                    "HTTP/1.1 302 Found\r\nLocation: http://first.test/landing\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        proxy = make_server(respond)
        with ProxyManager(f"http://127.0.0.1:{proxy.port}") as pm:
            pm.request("GET", "http://first.test/start", headers={"Authorization": "Bearer secret"})
        second = proxy.requests[-1]
        assert second["headers"].get("authorization") == "Bearer secret"


# ---------------------------------------------------------------------------
# (3) Bodies without seek, and fingerprints
# ---------------------------------------------------------------------------


class _TellOnly(io.RawIOBase):
    def __init__(self, data: bytes) -> None:
        self._data = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def readinto(self, b: Any) -> int:
        chunk = self._data.read(len(b))
        b[: len(chunk)] = chunk
        return len(chunk)

    def tell(self) -> int:
        return self._data.tell()

    seek = None  # type: ignore[assignment]


class TestMiscErrors:
    def test_rewinding_a_body_without_seek_is_unrewindable(self) -> None:
        from urllib3.util.request import rewind_body

        body = _TellOnly(b"data")
        with pytest.raises(UnrewindableBodyError):
            rewind_body(body, 0)  # type: ignore[arg-type]

    def test_retrying_a_body_without_seek_is_unrewindable(self, make_server) -> None:
        def respond(req: dict[str, Any]) -> bytes:
            if req["target"] == "/start":
                return raw_response(
                    "HTTP/1.1 307 Temporary Redirect\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close"
                )
            return raw_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close", b"ok")

        server = make_server(respond)
        with HTTPConnectionPool("127.0.0.1", server.port) as pool:
            with pytest.raises(UnrewindableBodyError):
                pool.urlopen("POST", "/start", body=_TellOnly(b"data"), redirect=True)

    @pytest.mark.parametrize("fingerprint", ["zz" * 20, "g" * 64, "0x" + "a" * 30])
    def test_non_hex_fingerprint_is_an_ssl_error(self, fingerprint: str) -> None:
        from urllib3.util.ssl_ import assert_fingerprint

        with pytest.raises(SSLError):
            assert_fingerprint(b"certificate bytes", fingerprint)

    def test_wrong_hex_fingerprint_is_still_an_ssl_error(self) -> None:
        from urllib3.util.ssl_ import assert_fingerprint

        with pytest.raises(SSLError):
            assert_fingerprint(b"certificate bytes", "aa" * 20)
