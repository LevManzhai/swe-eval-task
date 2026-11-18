# starlette: rare requests and responses handled against the specs

The repository in `/workspace/repo` is [starlette](https://github.com/Kludex/starlette),
the ASGI framework that FastAPI is built on. Its optional dependencies
(`python-multipart`, `itsdangerous`, `jinja2`, `httpx`, ...) are installed.

## What a user reported

> Our endpoint class only defines `get()`. A client that sends `POST` gets a
> `405 Method Not Allowed` with `Allow: GET`. But the endpoint answers `HEAD`
> as well, so the header is wrong, and our API-conformance checker flags it.

## What we want

Fix that, and treat it as one example of a wider problem: starlette handles
requests, responses and configuration that are rare but legitimate in ways
that don't match the specifications it implements, or its own documentation.
We want the following to hold across the framework:

1. **HTTP semantics follow RFC 9110.** A `405` response lists every method the
   resource supports. `Range` is honoured only where the RFC says it applies.
   Host names are compared the way the RFC defines them. A header that may
   appear more than once is combined, never silently overwritten.
2. **The ASGI specification is followed in both directions.** Keys the spec
   marks optional may be left out by an application, and what starlette sends
   satisfies the spec's types and meanings, including what a byte length is.
3. **URLs round-trip and stay paths.** A URL built from route parameters
   matches the route and gives back exactly those values. Whether starlette
   builds a URL from a route or from a request, a path never ends up read as
   an authority, a query or a fragment.
4. **Documented APIs behave as documented, for every valid input.** This
   covers settings (`Config` and `.env` files), the session middleware's
   options, form parsing and the data structures it returns, and the WSGI
   adapter. Invalid input raises only the documented exceptions.
5. **Middleware doesn't delay what it doesn't change.** A middleware that
   passes a response through unchanged doesn't hold back any part of it.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is (one test relies on file permissions and
  fails when run as root, as in this sandbox). It doesn't cover these cases.
- Your changes are graded by hidden tests that use starlette's public API:
  applications and the `TestClient`, routers, middleware called directly as
  ASGI apps, `URL`, `Config`, `FormParser`, `FormData`, `MutableHeaders`, and
  `starlette.middleware.wsgi.build_environ`.
