# yarl: URLs that don't follow the standard of their mode

> **Status: accepted.** Three of three one-shot attempts failed (353, 351 and
> 357 of 375). All three missed the same two cases. `run.sh` passes all 24 of
> its checks. Details at the end of [`NOTES.md`](NOTES.md).

[yarl](https://github.com/aio-libs/yarl) is the URL library under aiohttp. In
autumn 2026 it gained a per-URL mode: `whatwg` (the default, as browsers
parse URLs) and `rfc` (RFC 3986). Upstream then closed the gaps between each
mode and its standard one PR at a time. I took yarl as of 18 November 2026
and reverted the last ten:

| Mode | Trigger | What goes wrong |
|---|---|---|
| WHATWG | `http://example.com/foo%2zbar`, `wow:%NBD` | the stray `%` is encoded to `%25` |
| WHATWG | `http://!"$&'()*+,-.;=_`{}~/` | rejected; the standard keeps `"`, `` ` ``, `{`, `}` in a host |
| WHATWG | userinfo with spaces, `[`, `;`, `@` ... | rejected or encoded with the wrong set |
| WHATWG | `sc://ñ.test/`, `sc://faß.ExAmPlE/` | IDNA-encoded, though a non-special host is opaque |
| WHATWG | `i` against base `sc:sd` (an opaque path) | resolved, though the standard fails |
| WHATWG | `///test` against `http://example.org/` | `http://example.org/test` instead of `http://test` |
| WHATWG | `http://`, `http://?`, `http:` against an https base | accepted with an empty host |
| RFC | `http://[0:0:0:0:0:0:13.1.68.3]` | rewritten as `[::d01:4403]` |
| RFC | `http://?`, `///test` against an http base | accepted, though RFC 9110 forbids an empty http host |
| both | `URL.build(scheme="http", port=0)` | accepted without a host |

The problem statement shows **only the first row** and a three-point
contract.

## Why this one

Same recipe as the other tasks in this repository, with the strictest oracle
yet: almost every hidden case comes from the WHATWG URL Standard's own test
data (web-platform-tests `urltestdata.json`). The repository ships that data
and a report of yarl's differences under `tools/conformance/`; the task
image removes it.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | yarl at commit `5350e37`, plus `starting_state.patch`; git history and `tools/conformance/` removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 375 hidden tests: WPT and RFC 3986 cases, and `URL.build` |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | nine "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. yarl is Apache-2.0-licensed; the Dockerfile clones it from
GitHub. The test data embedded in `verifier/test_task.py` comes from
web-platform-tests (3-Clause BSD).
