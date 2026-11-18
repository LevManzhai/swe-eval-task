# starlette: rare requests and responses handled against the specs

> **Status: accepted.** Three of three one-shot attempts failed (40, 43 and
> 42 of 44). The deciding case is a raw backslash in a path, and NOTES.md
> explains why it counts. `run.sh` passes all 40 of its checks. Details at
> the end of [`NOTES.md`](NOTES.md).

[starlette](https://github.com/Kludex/starlette) is the ASGI framework that
FastAPI is built on. Upstream recently fixed a run of bugs where starlette
didn't follow RFC 9110, the ASGI spec or its own documentation for rare but
legitimate input. I took starlette at commit `271c277` and reverted seventeen
of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| `HTTPEndpoint` | `POST` to an endpoint with only `get()` | `405` says `Allow: GET`, without `HEAD` |
| `StaticFiles` | `POST` to a static file | `405` without an `Allow` header |
| `FileResponse` | `Range` on a `POST` | a `206` partial answer |
| host matching | `Host: EXAMPLE.com` | not matched |
| `MutableHeaders` | adding a second `Vary` value | the first is overwritten |
| `SessionMiddleware` | `max_age=0` | the cookie is sent without `Max-Age`, so it lives for the browser session |
| `http.response.start` | an app that leaves out `headers` | `KeyError` |
| `Response` | a typed `memoryview` body | `Content-Length` counts items, not bytes |
| `StreamingResponse` | typed `memoryview` chunks | sent as a `memoryview`, wrong size |
| `url_path_for` | a parameter value that looks like `{other}` | substituted again |
| `url_path_for` / `URL` | a path parameter `/x` or `\x`, a request path `//x` | the result reads as an authority |
| WSGI adapter | `root_path="/app"`, path `/application` | `PATH_INFO` becomes `lication` |
| `Config` | a cast without `__name__` (a `functools.partial`) | `AttributeError` while building the error |
| `.env` files | `PASSWORD=abc"` | the quote is stripped |
| `FormParser` | a URL-encoded body whose last field ends with the stream | the field is lost |
| `FormData` | equality with repeated uploads | wrong result |
| `GZipMiddleware` | a response it doesn't compress | `http.response.start` held back until the first body chunk |

The problem statement shows **only the first row** and a five-point contract.

## Why this one

Same recipe as the other tasks in this repository: many bugs, each with an
unusual trigger, in a widely used library whose own suite passes without
noticing them, and no oracle in the sandbox.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | starlette at commit `271c277`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 44 hidden tests through the public API |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | seventeen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. starlette is BSD-licensed; the Dockerfile clones it from GitHub.
