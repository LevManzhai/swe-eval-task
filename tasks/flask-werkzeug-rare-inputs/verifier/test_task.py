"""
Hidden verifier for the "Flask and Werkzeug rare inputs" task.

Each test checks one point of the contract in task/PROBLEM.md:

  (1) values parsed from a request follow their grammar exactly (ASCII digits,
      real base64, ports 1-65535); anything else counts as invalid;
  (2) malformed or out-of-range input is a client error or no match, never a
      server error and never a wrong value;
  (3) URL building and URL matching are inverses;
  (4) conversions keep information: URL components survive IRI/URI
      conversion, and reading into a caller's buffer never resizes it;
  (5) response header attributes: "not set" removes the header, and quoted
      strings follow their grammar;
  (6) IPv6 literals work for Flask's host handling;
  (7) the development server always closes response iterables.
"""

from __future__ import annotations

import io
import socket
import sys
import threading
from typing import Any

import pytest
from flask import Flask, Response, request, session, url_for
from werkzeug.routing import BuildError

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test")
    return app


def run_with_deadline(func: Any, seconds: float) -> Any:
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
# (1)/(2) Number converters: ASCII digits only, no 500s, no wrong values
# ---------------------------------------------------------------------------


def number_app() -> Flask:
    app = Flask(__name__)

    @app.get("/i/<int:x>")
    def int_view(x: int) -> str:
        return repr(x)

    @app.get("/f/<float:x>")
    def float_view(x: float) -> str:
        return repr(x)

    @app.get("/sf/<float(signed=True):x>")
    def signed_float_view(x: float) -> str:
        return repr(x)

    @app.get("/fd/<int(fixed_digits=3, signed=True):x>")
    def fixed_view(x: int) -> str:
        return repr(x)

    return app


class TestNumberConverters:
    @pytest.mark.parametrize(
        "path",
        ["/i/\u0663", "/i/1\u0663", "/i/\uff11\uff12", "/f/\u0663.5", "/f/1.\u0665"],
    )
    def test_non_ascii_digits_do_not_match(self, path: str) -> None:
        assert number_app().test_client().get(path).status_code == 404

    def test_ascii_digits_still_match(self) -> None:
        client = number_app().test_client()
        assert client.get("/i/42").text == "42"
        assert client.get("/f/1.5").text == "1.5"

    def test_int_longer_than_the_digit_limit_is_a_404(self) -> None:
        digits = sys.get_int_max_str_digits() + 10
        rv = number_app().test_client().get("/i/" + "9" * digits)
        assert rv.status_code == 404

    def test_float_too_large_for_a_float_is_a_404(self) -> None:
        rv = number_app().test_client().get("/f/" + "9" * 400 + ".0")
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# (3) URL building is the inverse of matching
# ---------------------------------------------------------------------------


class TestBuildingInvertsMatching:
    @pytest.mark.parametrize(
        "value",
        [1e-7, 0.000123, 1e20, 1.5e16, -1e-7, -0.00001, -2.5e-9, -3e18, 0.0, 12.25],
    )
    def test_float_round_trips(self, value: float) -> None:
        app = number_app()
        with app.test_request_context():
            url = url_for("signed_float_view", x=value)
        assert "e" not in url.lower(), url
        rv = app.test_client().get(url)
        assert rv.status_code == 200, url
        assert float(rv.text) == value

    @pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
    def test_float_rejects_values_it_would_never_match(self, value: float) -> None:
        app = number_app()
        with app.test_request_context():
            with pytest.raises(BuildError):
                url_for("signed_float_view", x=value)

    def test_many_converters_in_one_segment(self) -> None:
        app = Flask(__name__)
        names = [f"a{i}" for i in range(12)]
        rule = "/m/" + "-".join(f"<int:{n}>" for n in names)

        def view(**kwargs: int) -> str:
            return ",".join(str(kwargs[n]) for n in names)

        app.add_url_rule(rule, "many", view)
        values = {n: 100 + i for i, n in enumerate(names)}
        with app.test_request_context():
            url = url_for("many", **values)
        rv = app.test_client().get(url)
        assert rv.text == ",".join(str(100 + i) for i in range(12))

    def test_many_converters_values_assigned_by_position(self) -> None:
        app = Flask(__name__)
        names = [f"p{i}" for i in range(11)]
        rule = "/x/" + ".".join(f"<{n}>" for n in names)
        seen: dict[str, Any] = {}

        def view(**kwargs: str) -> str:
            seen.update(kwargs)
            return "ok"

        app.add_url_rule(rule, "dots", view)
        app.test_client().get("/x/" + ".".join(f"v{i}" for i in range(11)))
        assert seen == {f"p{i}": f"v{i}" for i in range(11)}


# ---------------------------------------------------------------------------
# (1) Basic auth and Host ports
# ---------------------------------------------------------------------------


class TestStrictValues:
    @pytest.mark.parametrize(
        "header",
        ["Basic dXNlcjpwYXNz!!", "Basic dXNl cjpwYXNz", "Basic ????", "Basic dXNlcjpwYXNz*"],
    )
    def test_invalid_base64_basic_auth_is_no_auth(self, app, header: str) -> None:
        with app.test_request_context(headers={"Authorization": header}):
            assert request.authorization is None

    def test_valid_basic_auth_still_parses(self, app) -> None:
        with app.test_request_context(
            headers={"Authorization": "Basic dXNlcjpwYXNz"}
        ):
            auth = request.authorization
            assert auth is not None
            assert (auth.username, auth.password) == ("user", "pass")

    @pytest.mark.parametrize("host", ["example.com:0", "example.com:65536", "example.com:99999", "example.com:00080"])
    def test_host_with_invalid_port_is_invalid(self, app, host: str) -> None:
        with app.test_request_context(headers={"Host": host}):
            assert request.host == ""

    @pytest.mark.parametrize("host", ["example.com:1", "example.com:65535", "example.com:8080", "example.com"])
    def test_host_with_valid_port_is_kept(self, app, host: str) -> None:
        with app.test_request_context(headers={"Host": host}):
            assert request.host == host

    def test_trusted_hosts_reject_invalid_port(self) -> None:
        app = Flask(__name__)
        app.config["TRUSTED_HOSTS"] = ["example.com"]

        @app.get("/")
        def index() -> str:
            return request.host

        client = app.test_client()
        assert client.get("/", headers={"Host": "example.com:8080"}).status_code == 200
        assert client.get("/", headers={"Host": "example.com:70000"}).status_code == 400


# ---------------------------------------------------------------------------
# (4) Conversions keep information
# ---------------------------------------------------------------------------


class TestConversionsKeepInformation:
    @pytest.mark.parametrize(
        "url",
        [
            "http://:@example.com:0/",
            "http://@example.com/",
            "http://user:@example.com/",
            "http://:pass@example.com/",
            "http://example.com:0/path",
        ],
    )
    def test_iri_uri_round_trip_keeps_empty_components(self, url: str) -> None:
        from werkzeug.urls import iri_to_uri, uri_to_iri

        assert iri_to_uri(url) == url
        assert uri_to_iri(url) == url

    def test_ordinary_iri_conversion_unchanged(self) -> None:
        from werkzeug.urls import iri_to_uri, uri_to_iri

        assert iri_to_uri("http://\u2603.net/p\xe5th") == "http://xn--n3h.net/p%C3%A5th"
        assert uri_to_iri("http://xn--n3h.net/p%C3%A5th") == "http://\u2603.net/p\xe5th"

    def test_limited_stream_readinto_never_resizes_the_buffer(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from werkzeug.wsgi import LimitedStream

        class Trickle(io.RawIOBase):
            """A stream that hands out at most 3 bytes per read."""

            def __init__(self, data: bytes) -> None:
                self._data = io.BytesIO(data)

            def readable(self) -> bool:
                return True

            def readinto(self, b: Any) -> int:
                chunk = self._data.read(min(3, len(b)))
                b[: len(chunk)] = chunk
                return len(chunk)

        stream = LimitedStream(Trickle(b"abcdefghij"), 5)
        buf = bytearray(10)
        n = stream.readinto(buf)
        assert len(buf) == 10, "readinto changed the size of the caller's buffer"
        assert n == 3 and bytes(buf[:3]) == b"abc"

        stream = LimitedStream(Trickle(b"abcdefghij"), 5)
        view = memoryview(bytearray(10))
        n = stream.readinto(view)
        assert n == 3 and bytes(view[:3]) == b"abc"

    def test_request_stream_reads_whole_body_through_short_reads(self, app) -> None:
        @app.post("/")
        def index() -> str:
            return str(len(request.get_data()))

        rv = app.test_client().post("/", data=b"x" * 1000)
        assert rv.text == "1000"


# ---------------------------------------------------------------------------
# (5) Response header attributes
# ---------------------------------------------------------------------------


class TestHeaderAttributes:
    def test_false_credentials_flag_removes_the_header(self) -> None:
        resp = Response("x")
        resp.access_control_allow_credentials = True
        assert resp.headers["Access-Control-Allow-Credentials"] == "true"
        resp.access_control_allow_credentials = False
        assert "Access-Control-Allow-Credentials" not in resp.headers
        assert resp.access_control_allow_credentials is False

    def test_false_credentials_flag_never_sends_a_placeholder(self, app) -> None:
        @app.get("/cors")
        def cors() -> Response:
            resp = Response("x")
            resp.access_control_allow_credentials = False
            return resp

        rv = app.test_client().get("/cors")
        assert "Access-Control-Allow-Credentials" not in rv.headers

    def test_empty_set_and_none_still_remove_headers(self) -> None:
        resp = Response("x")
        resp.allow = {"GET"}
        assert resp.headers["Allow"] == "GET"
        resp.allow = set()
        assert "Allow" not in resp.headers
        resp.retry_after = 5
        assert resp.headers["Retry-After"] == "5"
        resp.retry_after = None
        assert "Retry-After" not in resp.headers


# ---------------------------------------------------------------------------
# (5) Quoted strings
# ---------------------------------------------------------------------------


class TestUnclosedQuote:
    @pytest.mark.parametrize(
        "value",
        [
            'text/plain; charset="utf-8',
            'multipart/form-data; boundary="abc',
            'text/plain; a="x\\"; b=1',
            'text/html; charset="',
        ],
    )
    def test_parse_options_header_returns(self, value: str) -> None:
        from werkzeug.http import parse_options_header

        mimetype, _ = run_with_deadline(lambda: parse_options_header(value), 5)
        assert mimetype == value.split(";")[0]

    @pytest.mark.parametrize(
        "value",
        [
            'a; b="c; d=e',
            'text/plain; a="x\\"; b=1',
            'multipart/form-data; boundary="abc; charset=evil',
        ],
    )
    def test_nothing_inside_an_unterminated_quote_becomes_a_parameter(
        self, value: str
    ) -> None:
        from werkzeug.http import parse_options_header

        _, options = run_with_deadline(lambda: parse_options_header(value), 5)
        assert "d" not in options
        assert "b" not in options or options.get("b") != "1"
        assert "charset" not in options

    def test_request_charset_not_taken_from_inside_a_quote(self, app) -> None:
        with app.test_request_context(
            headers={"Content-Type": 'text/plain; x="y; charset=latin-1'}
        ):
            assert "charset" not in request.mimetype_params

    def test_request_mimetype_returns(self, app) -> None:
        def get() -> str:
            with app.test_request_context(
                headers={"Content-Type": 'text/plain; charset="utf-8'}
            ):
                return request.mimetype

        assert run_with_deadline(get, 5) == "text/plain"

    def test_well_formed_quotes_still_parse(self) -> None:
        from werkzeug.http import parse_options_header

        assert parse_options_header('text/plain; charset="utf-8"; a=b') == (
            "text/plain",
            {"charset": "utf-8", "a": "b"},
        )


# ---------------------------------------------------------------------------
# (6) IPv6
# ---------------------------------------------------------------------------


class TestIPv6:
    @pytest.mark.parametrize(
        "server_name, expected",
        [
            ("[::1]:8080", ("::1", 8080)),
            ("[::1]", ("::1", 5000)),
            ("[2001:db8::1]:9000", ("2001:db8::1", 9000)),
            ("localhost:8081", ("localhost", 8081)),
            ("example.com", ("example.com", 5000)),
        ],
    )
    def test_run_uses_server_name(self, monkeypatch, server_name, expected) -> None:
        calls: list[tuple[Any, Any]] = []

        def fake_run_simple(host, port, *args, **kwargs):
            calls.append((host, port))

        monkeypatch.setattr("werkzeug.serving.run_simple", fake_run_simple)
        monkeypatch.delenv("FLASK_RUN_FROM_CLI", raising=False)
        app = Flask(__name__)
        app.config["SERVER_NAME"] = server_name
        app.run()
        assert calls == [expected]

    def test_session_transaction_on_ipv6_host(self) -> None:
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.get("/")
        def index() -> str:
            return str(session.get("value"))

        client = app.test_client()
        with client.session_transaction(base_url="http://[::1]/") as sess:
            sess["value"] = 42
        assert client.get("/", base_url="http://[::1]/").text == "42"

    def test_session_transaction_on_ipv6_host_with_port(self) -> None:
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.get("/")
        def index() -> str:
            return str(session.get("value"))

        client = app.test_client()
        with client.session_transaction(base_url="http://[::1]:5000/") as sess:
            sess["value"] = "x"
        assert client.get("/", base_url="http://[::1]:5000/").text == "x"

    def test_session_transaction_on_named_host_still_works(self) -> None:
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.get("/")
        def index() -> str:
            return str(session.get("value"))

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["value"] = 1
        assert client.get("/").text == "1"


# ---------------------------------------------------------------------------
# (7) The development server always closes the response iterable
# ---------------------------------------------------------------------------


class _Closing:
    def __init__(self) -> None:
        self.closed = threading.Event()

    def __iter__(self):
        yield b"hello"

    def close(self) -> None:
        self.closed.set()


class TestDevServerCleanup:
    def _serve(self, app: Any):
        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _request(self, port: int, body: bytes = b"") -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(
                b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            out = b""
            try:
                while chunk := sock.recv(65536):
                    out += chunk
            except OSError:
                pass
            return out

    def test_iterable_closed_when_draining_the_request_fails(self, monkeypatch) -> None:
        import werkzeug.serving

        iterable = _Closing()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return iterable

        class FailingSelector:
            def __init__(self) -> None:
                pass

            def register(self, *args: Any, **kwargs: Any) -> None:
                raise ConnectionResetError("client went away")

            def select(self, *args: Any, **kwargs: Any) -> list[Any]:
                raise ConnectionResetError("client went away")

            def close(self) -> None:
                pass

            def __enter__(self) -> "FailingSelector":
                return self

            def __exit__(self, *exc: Any) -> None:
                self.close()

        monkeypatch.setattr(werkzeug.serving.selectors, "DefaultSelector", FailingSelector)
        server, thread = self._serve(app)
        try:
            self._request(server.server_port, b"abc")
            assert iterable.closed.wait(5), "the response iterable was never closed"
        finally:
            server.shutdown()
            thread.join(5)

    def test_iterable_closed_normally(self) -> None:
        iterable = _Closing()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return iterable

        server, thread = self._serve(app)
        try:
            out = self._request(server.server_port)
            assert out.split(b" ", 2)[1] == b"200" and out.endswith(b"hello")
            assert iterable.closed.wait(5)
        finally:
            server.shutdown()
            thread.join(5)
