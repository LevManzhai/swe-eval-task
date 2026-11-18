"""
Hidden verifier for the "starlette spec edge cases" task.

Each test checks one point of the contract in task/PROBLEM.md:

  (1) HTTP semantics per RFC 9110 (405 responses list every allowed method,
      Range only for GET/HEAD, host names are case-insensitive, header values
      are combined rather than overwritten);
  (2) the ASGI specification: optional message keys may be omitted, and
      lengths are byte lengths;
  (3) URLs: building a URL from values gives back exactly those values, and no
      path is ever turned into an authority;
  (4) documented API: settings, parsers and data structures behave as
      documented for every valid input, and raise only documented exceptions;
  (5) streaming: a middleware that doesn't change a response doesn't delay it.
"""

from __future__ import annotations

import array
import functools
from urllib.parse import unquote
import io
import os
from typing import Any

import anyio
import pytest

from starlette.applications import Starlette
from starlette.config import Config
from starlette.datastructures import URL, FormData, Headers, MutableHeaders, UploadFile
from starlette.endpoints import HTTPEndpoint
from starlette.formparsers import FormParser
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Host, Mount, Route, Router
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

with __import__("warnings").catch_warnings():
    __import__("warnings").simplefilter("ignore", DeprecationWarning)
    from starlette.middleware.wsgi import WSGIMiddleware, build_environ


async def homepage(request: Request) -> Response:
    return PlainTextResponse("home")


# ---------------------------------------------------------------------------
# (1) HTTP semantics
# ---------------------------------------------------------------------------


class TestAllowHeader:
    def test_endpoint_with_get_allows_head(self) -> None:
        class Endpoint(HTTPEndpoint):
            async def get(self, request: Request) -> Response:
                return PlainTextResponse("x")

        client = TestClient(Starlette(routes=[Route("/e", Endpoint)]))
        rv = client.post("/e")
        assert rv.status_code == 405
        allowed = {m.strip() for m in rv.headers["allow"].split(",")}
        assert allowed == {"GET", "HEAD"}
        assert client.head("/e").status_code == 200

    def test_endpoint_without_get_does_not_advertise_head(self) -> None:
        class Endpoint(HTTPEndpoint):
            async def post(self, request: Request) -> Response:
                return PlainTextResponse("x")

        rv = TestClient(Starlette(routes=[Route("/e", Endpoint)])).put("/e")
        assert rv.status_code == 405
        assert {m.strip() for m in rv.headers["allow"].split(",")} == {"POST"}

    def test_static_files_405_lists_allowed_methods(self, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("hello")
        app = Starlette(routes=[Mount("/static", StaticFiles(directory=tmp_path))])
        rv = TestClient(app).post("/static/f.txt")
        assert rv.status_code == 405
        assert {m.strip() for m in rv.headers["allow"].split(",")} == {"GET", "HEAD"}


class TestRange:
    @pytest.fixture
    def client(self, tmp_path) -> TestClient:
        path = tmp_path / "f.txt"
        path.write_text("0123456789")

        async def endpoint(request: Request) -> Response:
            return FileResponse(path)

        app = Starlette(routes=[Route("/f", endpoint, methods=["GET", "HEAD", "POST", "PUT"])])
        return TestClient(app)

    @pytest.mark.parametrize("method", ["POST", "PUT"])
    def test_range_is_ignored_for_other_methods(self, client, method: str) -> None:
        rv = client.request(method, "/f", headers={"range": "bytes=0-3"})
        assert rv.status_code == 200
        assert rv.text == "0123456789"

    def test_range_still_works_for_get(self, client) -> None:
        rv = client.get("/f", headers={"range": "bytes=0-3"})
        assert rv.status_code == 206 and rv.text == "0123"

    def test_range_still_applies_to_head(self, client) -> None:
        rv = client.head("/f", headers={"range": "bytes=0-3"})
        assert rv.status_code == 206


class TestHostCase:
    def test_host_route_matches_any_case(self) -> None:
        inner = Starlette(routes=[Route("/", homepage)])
        app = Starlette(routes=[Host("Example.COM", app=inner)])
        assert TestClient(app, base_url="http://example.com").get("/").status_code == 200
        assert TestClient(app, base_url="http://EXAMPLE.com").get("/").status_code == 200

    def test_host_route_with_parameter_any_case(self) -> None:
        inner = Starlette(routes=[Route("/", homepage)])
        app = Starlette(routes=[Host("{sub}.Example.com", app=inner)])
        assert TestClient(app, base_url="http://api.EXAMPLE.com").get("/").status_code == 200

    def test_trusted_hosts_match_any_case(self) -> None:
        app = Starlette(
            routes=[Route("/", homepage)],
            middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["Example.com", "*.Sub.org"])],
        )
        assert TestClient(app, base_url="http://example.COM").get("/").status_code == 200
        assert TestClient(app, base_url="http://a.sub.ORG").get("/").status_code == 200
        assert TestClient(app, base_url="http://other.com").get("/").status_code == 400


class TestVary:
    def test_every_existing_vary_header_is_kept(self) -> None:
        headers = MutableHeaders(raw=[(b"vary", b"Accept"), (b"vary", b"Cookie")])
        headers.add_vary_header("Accept-Encoding")
        combined = ", ".join(headers.getlist("vary"))
        parts = [p.strip() for p in combined.split(",")]
        assert set(parts) == {"Accept", "Cookie", "Accept-Encoding"}

    def test_gzip_keeps_vary_from_the_app(self) -> None:
        async def app(scope: Any, receive: Any, send: Any) -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/plain"),
                        (b"vary", b"Accept"),
                        (b"vary", b"Cookie"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"x" * 2000})

        client = TestClient(GZipMiddleware(app, minimum_size=10))
        rv = client.get("/", headers={"accept-encoding": "gzip"})
        parts = {p.strip() for v in rv.headers.get_list("vary") for p in v.split(",")}
        assert {"Accept", "Cookie", "Accept-Encoding"} <= parts


class TestSessionCookie:
    def test_max_age_zero_is_sent(self) -> None:
        async def endpoint(request: Request) -> Response:
            request.session["a"] = 1
            return PlainTextResponse("x")

        app = Starlette(
            routes=[Route("/", endpoint)],
            middleware=[Middleware(SessionMiddleware, secret_key="k", max_age=0)],
        )
        cookie = TestClient(app).get("/").headers["set-cookie"]
        assert "max-age=0" in cookie.lower()

    def test_max_age_none_is_a_browser_session_cookie(self) -> None:
        async def endpoint(request: Request) -> Response:
            request.session["a"] = 1
            return PlainTextResponse("x")

        app = Starlette(
            routes=[Route("/", endpoint)],
            middleware=[Middleware(SessionMiddleware, secret_key="k", max_age=None)],
        )
        assert "max-age" not in TestClient(app).get("/").headers["set-cookie"].lower()


# ---------------------------------------------------------------------------
# (2) ASGI specification
# ---------------------------------------------------------------------------


async def start_without_headers_app(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200})
    await send({"type": "http.response.body", "body": b"hello world, hello world"})


async def _passthrough(request: Request, call_next: Any) -> Response:
    return await call_next(request)


class TestOptionalAsgiKeys:
    @pytest.mark.parametrize(
        "wrap",
        [
            lambda app: SessionMiddleware(app, secret_key="secret"),
            lambda app: GZipMiddleware(app, minimum_size=1),
            lambda app: BaseHTTPMiddleware(app, dispatch=_passthrough),
        ],
        ids=["session", "gzip", "base"],
    )
    def test_response_start_without_headers(self, wrap: Any) -> None:
        client = TestClient(wrap(start_without_headers_app))
        rv = client.get("/", headers={"accept-encoding": "gzip"})
        assert rv.status_code == 200
        assert rv.content == b"hello world, hello world"


class TestMemoryviewLengths:
    @pytest.mark.parametrize("typecode", ["i", "d", "H"])
    def test_typed_memoryview_body_length(self, typecode: str) -> None:
        data = array.array(typecode, [1, 2, 3, 4])
        expected = data.tobytes()

        async def endpoint(request: Request) -> Response:
            return Response(memoryview(data))

        rv = TestClient(Starlette(routes=[Route("/", endpoint)])).get("/")
        assert rv.content == expected
        assert int(rv.headers["content-length"]) == len(expected)

    def test_multidimensional_memoryview_body(self) -> None:
        raw = bytes(range(12))
        view = memoryview(raw).cast("B", shape=[3, 4])

        async def endpoint(request: Request) -> Response:
            return Response(view)

        rv = TestClient(Starlette(routes=[Route("/", endpoint)])).get("/")
        assert rv.content == raw
        assert int(rv.headers["content-length"]) == 12

    def test_typed_memoryview_streaming_chunks(self) -> None:
        data = array.array("i", [10, 20, 30])

        async def chunks():
            yield memoryview(data)
            yield memoryview(data)

        async def endpoint(request: Request) -> Response:
            return StreamingResponse(chunks())

        rv = TestClient(Starlette(routes=[Route("/", endpoint)])).get("/")
        assert rv.content == data.tobytes() * 2


    def test_streamed_chunks_are_byte_sized(self) -> None:
        # The ASGI spec makes ``body`` a byte string; a server takes len(body)
        # as the number of bytes it writes (for example as a chunk size).
        data = array.array("i", [10, 20, 30])
        sent: list[Any] = []

        async def chunks():
            yield memoryview(data)

        async def main() -> None:
            response = StreamingResponse(chunks())

            async def receive() -> Any:
                await anyio.sleep_forever()

            async def send(message: Any) -> None:
                sent.append(message)

            scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "asgi": {"spec_version": "2.4"}}
            await response(scope, receive, send)

        anyio.run(main)
        bodies = [m["body"] for m in sent if m["type"] == "http.response.body" and m.get("body")]
        assert b"".join(bytes(b) for b in bodies) == data.tobytes()
        for body in bodies:
            assert len(body) == memoryview(body).nbytes


# ---------------------------------------------------------------------------
# (3) URLs
# ---------------------------------------------------------------------------


class TestUrlBuilding:
    def test_parameter_value_that_looks_like_a_placeholder(self) -> None:
        router = Router([Route("/u/{a}/{b}", homepage, name="u")])
        # Braces may be left as they are or percent-encoded.
        assert unquote(router.url_path_for("u", a="{b}", b="zz")) == "/u/{b}/zz"

    def test_parameter_value_with_braces_round_trips(self) -> None:
        seen: dict[str, str] = {}

        async def endpoint(request: Request) -> Response:
            seen.update(request.path_params)
            return PlainTextResponse("x")

        app = Starlette(routes=[Route("/u/{a}/{b}", endpoint, name="u")])
        url = app.url_path_for("u", a="{b}", b="value")
        TestClient(app).get(url)
        assert seen == {"a": "{b}", "b": "value"}

    @pytest.mark.parametrize(
        "path, expected",
        [("/example.org/a", "/%2Fexample.org/a"), ("\\example.org/a", "/%5Cexample.org/a")],
    )
    def test_path_parameter_never_becomes_an_authority(self, path: str, expected: str) -> None:
        router = Router([Route("/{path:path}", homepage, name="catchall")])
        url = router.url_path_for("catchall", path=path)
        assert url == expected or (
            unquote(url) == "/" + path and not url.startswith("//") and "\\" not in url
        )

    def test_url_from_scope_escapes_delimiters_in_path(self) -> None:
        u = URL(scope={"path": "/a?b#c", "query_string": b"d=e", "headers": [(b"host", b"example.org")]})
        assert u.path == "/a%3Fb%23c"
        assert u.query == "d=e"

    def test_url_from_scope_with_double_slash_path(self) -> None:
        u = URL(scope={"path": "//example.org/a", "query_string": b"", "headers": []})
        assert u.netloc == ""
        # Read back from its string form, it must still have no authority.
        assert URL(str(u)).netloc == ""

    def test_url_from_scope_with_backslash(self) -> None:
        u = URL(scope={"path": "/\\example.org/a", "query_string": b"", "headers": []})
        assert "\\" not in str(u)


class TestWsgiRootPath:
    @pytest.mark.parametrize(
        "root_path, path, path_info",
        [
            ("/app", "/application", "/application"),
            ("/app", "/app/users", "/users"),
            ("/app", "/app", ""),
        ],
    )
    def test_root_path_only_at_a_segment_boundary(self, root_path: str, path: str, path_info: str) -> None:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "root_path": root_path,
            "query_string": b"",
            "headers": [],
        }
        environ = build_environ(scope, b"")
        assert environ["PATH_INFO"] == path_info


# ---------------------------------------------------------------------------
# (4) Documented API
# ---------------------------------------------------------------------------


class TestConfig:
    def _env(self, tmp_path, text: str) -> Config:
        path = tmp_path / ".env"
        path.write_text(text)
        return Config(path)

    def test_a_matching_pair_of_quotes_is_removed(self, tmp_path) -> None:
        cfg = self._env(tmp_path, 'B=\'"inner"\'\nC="plain"\nD=\'single\'\nE=unquoted\n')
        assert cfg("B") == '"inner"'
        assert cfg("C") == "plain"
        assert cfg("D") == "single"
        assert cfg("E") == "unquoted"

    def test_quote_characters_that_are_data_are_kept(self, tmp_path) -> None:
        cfg = self._env(tmp_path, 'PASSWORD=abc"\nTOKEN=\'xyz\nNAME=it\'s\n')
        assert cfg("PASSWORD") == 'abc"'
        assert cfg("TOKEN") == "'xyz"
        assert cfg("NAME") == "it's"

    def test_mismatched_quotes_are_kept(self, tmp_path) -> None:
        cfg = self._env(tmp_path, "A=\"x'\nB='y\n")
        assert cfg("A") == "\"x'"
        assert cfg("B") == "'y"

    def test_invalid_value_with_a_partial_cast_raises_value_error(self) -> None:
        cfg = Config(environ={"X": "abc"})
        with pytest.raises(ValueError):
            cfg("X", cast=functools.partial(int, base=10))

    def test_invalid_value_with_a_callable_object_cast(self) -> None:
        class Caster:
            def __call__(self, value: str) -> int:
                return int(value)

        with pytest.raises(ValueError):
            Config(environ={"X": "abc"})("X", cast=Caster())


class TestFormParsing:
    def test_urlencoded_stream_without_empty_final_chunk(self) -> None:
        async def stream():
            yield b"first=one&second=two"

        async def main() -> FormData:
            parser = FormParser(Headers({"content-type": "application/x-www-form-urlencoded"}), stream())
            return await parser.parse()

        form = anyio.run(main)
        assert form == FormData([("first", "one"), ("second", "two")])

    def test_urlencoded_stream_split_without_empty_final_chunk(self) -> None:
        async def stream():
            yield b"first=o"
            yield b"ne&second=t"
            yield b"wo"

        async def main() -> FormData:
            parser = FormParser(Headers({"content-type": "application/x-www-form-urlencoded"}), stream())
            return await parser.parse()

        assert dict(anyio.run(main)) == {"first": "one", "second": "two"}

    def test_form_data_with_repeated_uploads_compares(self) -> None:
        with io.BytesIO(b"a") as a, io.BytesIO(b"b") as b:
            file_a = UploadFile(a, filename="a.txt")
            file_b = UploadFile(b, filename="b.txt")
            form = FormData([("files", file_a), ("files", file_b), ("name", "x")])
            assert form == FormData(form)
            assert form == FormData([("name", "x"), ("files", file_a), ("files", file_b)])
            assert form != FormData([("name", "y"), ("files", file_a), ("files", file_b)])


# ---------------------------------------------------------------------------
# (5) Streaming through GZipMiddleware
# ---------------------------------------------------------------------------


class TestGzipDoesNotDelay:
    @pytest.mark.parametrize(
        "headers",
        [
            [(b"content-type", b"text/event-stream")],
            [(b"content-type", b"text/plain"), (b"content-encoding", b"br")],
        ],
        ids=["excluded-type", "already-encoded"],
    )
    def test_response_start_is_sent_before_the_first_body(self, headers: list) -> None:
        events: list[str] = []

        async def main() -> None:
            start_sent = anyio.Event()

            async def app(scope: Any, receive: Any, send: Any) -> None:
                await send({"type": "http.response.start", "status": 200, "headers": headers})
                await start_sent.wait()
                await send({"type": "http.response.body", "body": b"data"})

            async def send(message: Any) -> None:
                events.append(message["type"])
                start_sent.set()

            async def receive() -> Any:
                raise NotImplementedError

            scope = {"type": "http", "method": "GET", "path": "/", "headers": [(b"accept-encoding", b"gzip")]}
            with anyio.fail_after(2):
                await GZipMiddleware(app)(scope, receive, send)

        main_result = anyio.run(main) if True else None
        assert events == ["http.response.start", "http.response.body"]
        assert main_result is None

    def test_compressible_responses_are_still_compressed(self) -> None:
        async def endpoint(request: Request) -> Response:
            return PlainTextResponse("x" * 2000)

        app = Starlette(routes=[Route("/", endpoint)], middleware=[Middleware(GZipMiddleware, minimum_size=10)])
        rv = TestClient(app).get("/", headers={"accept-encoding": "gzip"})
        assert rv.headers["content-encoding"] == "gzip"
        assert rv.text == "x" * 2000
