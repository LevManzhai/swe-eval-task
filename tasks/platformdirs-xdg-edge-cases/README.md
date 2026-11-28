# platformdirs: XDG directories wrong in unusual environments

> **Status: accepted, with one caveat.** Three of three one-shot attempts
> failed (367, 368 and 368 of 370). All three miss the same safety rule: they
> create directories through another user's symlink before refusing the
> runtime directory. Attempts 2 and 3 miss nothing else. `run.sh` passes all
> 34 of its checks. Details and the caveat are at the end of
> [`NOTES.md`](NOTES.md).

[platformdirs](https://github.com/tox-dev/platformdirs) decides where pip,
virtualenv, black and many other tools put their data, config, cache and
runtime files. In autumn 2026 upstream fixed a run of Unix edge cases,
several of them security-relevant. I took platformdirs as of 6 November 2026
and reverted 14 of them:

| Area | Trigger | What goes wrong |
|---|---|---|
| root | `use_site_for_root=True` under `sudo` | the invoking user's `XDG_DOCUMENTS_DIR` / `user-dirs.dirs` is used, and created |
| root | `user_documents_path(use_site_for_root=True)` | `TypeError` |
| environment | `XDG_DATA_HOME="/data "` | the trailing space is stripped, a different directory |
| environment | `HOME=relative` | paths land under the working directory |
| directory lists | `XDG_DATA_DIRS=/a:/a/:/a/.` | the same directory listed three times |
| directory lists | `multipath=True`, `appname="org:app"` | the joined string splits into the wrong directories |
| `user-dirs.dirs` | unreadable file | `PermissionError` from every media call |
| `user-dirs.dirs` | a long run of blanks | quadratic time |
| runtime dir | `XDG_RUNTIME_DIR` below a world-writable or foreign-owned parent | accepted, and created through the other user's symlink |
| runtime dir | `XDG_RUNTIME_DIR=/path/to/symlink/` | the symlink check is bypassed |
| runtime dir | temporary directory `/` | `//runtime-0`, a different path to pathlib |
| `ensure_exists` | a regular file where a media directory is configured | the path is returned as if it were a directory |
| CLI | `python -m platformdirs` with no home | crashes partway through the report |
| `platformdirs.testing` | `isolated_dirs("rel")` then `chdir` | the isolation root moves |

The problem statement shows **only the first row** and a seven-point
contract.

## Why this one

Same recipe as the other tasks in this repository. The rules come from the
XDG Base Directory Specification and from the sort of local-attacker threat
model that runtime directories need. The hidden tests are upstream's own
tests for these fixes.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | platformdirs at commit `e7139ef`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/hidden/`, `verifier/hidden_tests.txt`, `verifier/run_hidden.sh` | 370 hidden test cases: upstream's test files at the base commit, run by id inside the repository's `tests/` |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | fourteen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. platformdirs is MIT-licensed; the Dockerfile clones it from
GitHub.
