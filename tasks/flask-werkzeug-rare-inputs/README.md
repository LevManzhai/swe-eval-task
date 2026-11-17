# Flask and Werkzeug: rare inputs accepted when they shouldn't be

> **Status: accepted.** Three of three one-shot attempts failed (66 / 68 each).
> All three fixed twelve of the thirteen bugs and missed the same one. `run.sh`
> passes all 30 of its checks. Details at the end of [`NOTES.md`](NOTES.md).

[Flask](https://github.com/pallets/flask) hands almost all of its HTTP work to
[Werkzeug](https://github.com/pallets/werkzeug). I took Werkzeug as of 9
November 2026 and Flask as of 30 October 2026 and reverted thirteen fixes
from July to October 2026, eleven in Werkzeug and two in Flask. Each one needs
an input that ordinary traffic never sends:

| Where | Trigger | What goes wrong |
|---|---|---|
| routing converters | `GET /invoice/٣` (an Arabic-Indic digit) | matches `<int:invoice_id>` as 3 |
| routing converters | an `int` path segment longer than Python's digit limit | `500` instead of `404` |
| routing converters | a `float` segment too large for a float | the view gets `inf` |
| routing converters | `url_for` with `1e-7`, `1e20` or `inf` | builds `/0.`, `/100000000000000000000.` or `/inf` |
| routing converters | `url_for` with a small negative float | the sign ends up in the wrong place |
| routing matcher | a rule with 10 or more converters in one segment | values are assigned to the wrong names (`10` sorts before `2`) |
| `Authorization` parsing | `Basic` credentials with characters outside base64 | silently decoded into a different user and password |
| `Host` handling | `Host: example.com:99999` or `:0` | accepted as a valid host, passes `TRUSTED_HOSTS` |
| `iri_to_uri` / `uri_to_iri` | `http://:@example.com:0/` | the empty user info and port 0 disappear |
| `LimitedStream.readinto` | a buffer larger than what's left, and a short read underneath | the caller's buffer grows |
| response header properties | `response.access_control_allow_credentials = False` | sends `Access-Control-Allow-Credentials: None` |
| `parse_options_header` | `text/plain; x="y; charset=latin-1` | reads a parameter from inside an unterminated quoted string |
| development server | draining the request fails after the response | the response iterable is never closed |
| Flask `app.run()` / test client | an IPv6 `SERVER_NAME` or host | crash, or a session cookie for the wrong domain |

The problem statement shows **only the first row** and a seven-point contract.

## Why this one

A first Flask/Werkzeug candidate with nine bugs centred on HTTP semantics
(Range requests, conditional headers, IPv6) was solved on its first attempt:
every bug sat where an HTTP-minded audit looks first. This version keeps the
approach that worked for anyio and aiohttp, many bugs each with its own odd
trigger, and moves most of them to places an HTTP audit doesn't reach: number
parsing in URL converters, the order converters are matched in, URL
round-tripping, a stream's buffer handling.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | both repositories at pinned commits plus their starting-state patches; git history removed |
| `solution/reference/` | the upstream fixes, one patch per repository |
| `verifier/test_task.py` | the hidden tests, mostly through a Flask app and its test client |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | twelve "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. Flask and Werkzeug are BSD-3-Clause licensed; the Dockerfile
clones them from GitHub.
