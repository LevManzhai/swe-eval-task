# Flask blueprint URL-prefix merging bug — a SWE-bench-style eval task

> **Status: rejected.** This task did not pass the difficulty gate described in
> the [top-level README](../../README.md): three out of three independent
> attempts solved it in a single shot. It is kept as a worked example of a
> well-built but too-easy task; see [`REJECTED.md`](../../REJECTED.md) for the
> post-mortem.

This repository packages one real, upstream-fixed bug in
[Flask](https://github.com/pallets/flask) as a self-contained coding task
for evaluating AI coding models, in the style of
[SWE-bench](https://www.swebench.com/): given a buggy checkout of a real
library and a plain-language bug report, produce a patch that makes a
hidden test suite pass without breaking anything else.

## What this is

- **The bug**: `flask.Blueprint` incorrectly merges a blueprint's
  `url_prefix` with each route's rule string. Depending on incidental
  trailing/leading slashes (or an empty route string), the resulting URL
  either has a doubled slash, is missing a slash, or registration raises
  `ValueError`. See `task/PROBLEM.md` for the exact behaviour a solver is
  given to work from.
- **The upstream history**: this is a real bug, fixed for real in Flask
  1.0.1 (2018, issue
  [pallets/flask#2731](https://github.com/pallets/flask/issues/2731)).
  Upstream's own commit history shows the first "obvious" fix was itself
  incomplete and needed two more follow-up commits — see `NOTES.md` for the
  full story and why that matters for difficulty.
- **The task**: starting from the exact parent commit of the real fix, with
  the bug present, produce a patch to the library source that makes
  `verifier/test_task.py` (written from scratch, not copied from upstream)
  pass.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | The problem statement a solver sees. No hints about which file or function. |
| `environment/Dockerfile` | Builds the exact starting environment: pinned Python, Flask checked out at the buggy parent commit, pinned dependencies. |
| `environment/requirements.txt` | Exact `==` pinned dependency versions. |
| `solution/reference.patch` | The reference fix, as a unified diff against the starting state. |
| `verifier/test_task.py` | The hidden test suite (21 pytest cases, 3 groups). |
| `verifier/wrong_fixes/` | 3 plausible-but-wrong/incomplete patches that must still fail the verifier. |
| `verifier/alt_fixes/` | 2 differently-implemented patches that correctly fix the bug and must pass the verifier. |
| `run.sh` | End-to-end self-check: builds the image, then proves (b)-(e) from the brief (starting state fails, reference + alt fixes pass, wrong fixes fail). |
| `NOTES.md` | Upstream references, why this is hard, what each wrong fix gets wrong, a plain-language file-by-file guide, verifier limitations, and the blind difficulty-check result. |
| `LICENSE-UPSTREAM` | Flask's own license, reproduced for attribution. |

## How to run it

Requires Docker.

```bash
./run.sh
```

This builds the environment image once and then, inside throwaway
containers with networking disabled, runs the hidden verifier against: the
unmodified starting state (must fail), `solution/reference.patch` (must
pass), every patch in `verifier/alt_fixes/` (must pass), and every patch in
`verifier/wrong_fixes/` (must fail). It prints a `PASS`/`FAIL` line for each
of these checks and exits non-zero if any expectation is violated.

To try solving it yourself: read only `task/PROBLEM.md`, then build the
image and work against the checkout at `/workspace/repo` inside it. Don't
look at `solution/`, `verifier/`, or `NOTES.md` first — that's the point.
