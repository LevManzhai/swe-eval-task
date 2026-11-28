# Notes

## Where the bugs come from

- Repo: https://github.com/tox-dev/platformdirs
- Base commit: `e7139eff13db0ebfe4e1dc2ade044d7b73b0d47c` (6 November 2026)

| Commit | Date | What it fixed |
|---|---|---|
| `da92c16` | 2026-11-04 | accept use_site_for_root in the media and fonts functions (#686) |
| `c9ad21d` | 2026-11-04 | avoid // in the runtime fallback when the temp dir is / (#687) |
| `7fbe87d` | 2026-11-02 | preserve whitespace in paths (#679) |
| `3b870de` | 2026-10-31 | deduplicate directory spellings (#677) |
| `18620ed` | 2026-10-28 | check XDG_RUNTIME_DIR parents (#668) |
| `3a5e7d0` | 2026-10-28 | raise when a media dir is a file (#672) |
| `3ee973f` | 2026-10-28 | ignore inherited media vars for root (#661) |
| `a94826e` | 2026-10-28 | parse user-dirs blank runs in linear time (#663) |
| `3b4cf5f` | 2026-10-28 | reject runtime dir symlink with trailing / (#665) |
| `f5b537b` | 2026-10-28 | treat a relative HOME as unset (#664) |
| `a249615` | 2026-10-28 | reject os.pathsep in multipath site dirs (#662) |
| `a3c9e1e` | 2026-10-28 | pin relative isolation roots (#643) |
| `4e0605e` | 2026-10-28 | keep reporting when home is unknown (#638) |
| `dbe1497` | 2026-10-28 | default when user-dirs.dirs unreadable (#632) |

All 14 reverse cleanly at the base commit, newest first. The reference patch
is the source part, +165 / −82 lines in six files. The fixes for
Windows, macOS and Android from the same weeks are left fixed; they can't be
tested in a Linux container.

The starting state also undoes what the fixes wrote outside `src/`:

- the changelog bullets, and `docs/changelog/686.bugfix.rst`;
- their paragraphs in `docs/parameters.rst`, `docs/api.rst`,
  `docs/explanation.rst` and `docs/howto.rst` (one paragraph by hand);
- the runtime-directory row that `18620ed` added to `.github/THREAT_MODEL.md`.
  I missed this one at first, see "Difficulty check".

Tests added by the fixes are removed. So are 34 test functions in `tests/`
that fail on the starting state. The upstream suite then passes on both the
starting state and the reference: 2,282 passed, 126 skipped.

## The hidden tests

`verifier/hidden/` holds upstream's own test files at the base commit
(`test_api`, `test_ios`, `test_macos`, `test_main`, `test_testing`,
`test_unix`). `verifier/run_hidden.sh` copies them into the repository's
`tests/` directory, so `tests/conftest.py` provides their fixtures, and runs
the 34 test functions listed in `verifier/hidden_tests.txt`: 370 test cases.
The starting state fails 250 of them.

Loosened before grading: assertions on the exact text of warnings and of new
error messages. The statement says wording isn't graded.

Fairness review after the first round of attempts. Every attempt was
re-graded after each change.

- `use_site_for_root` media and fonts directories. Upstream expects
  `$HOME/Documents` for root, and `$HOME/.local/share/fonts`. Most attempts
  read "nothing inherited from the invoking user" as covering an inherited
  `HOME` too. They used root's home from the password database, and put fonts
  in the site data directory, the way applications already are. The
  statement allows both readings, so the checks now accept either: root's
  `HOME`, root's password-database home, or a site data directory for fonts.
  Being under the inherited directory is still rejected.
- `python -m platformdirs` without a home, and `user-dirs.dirs` with
  `$HOME/...` and no home. Both still asserted message text; both now check
  only the behaviour.
- `test_relative_passwd_home_raises` was dropped. The statement says `HOME`
  must be absolute, but says nothing about the home in the password database.

## Checking the checker

`run.sh` runs 34 checks on the starting state, the reference, one
alternative and fourteen wrong solutions. Each is checked against the
upstream suite and the hidden tests.

- `verifier/alt_fixes/01-string-paths.patch` writes the CLI catch, the
  temporary-fallback join and the absolute isolation root differently.
- Each `verifier/wrong_fixes/NN-without-<commit>.patch` is the reference with
  that one commit reversed. All fourteen pass the upstream suite and fail
  between 1 and 106 hidden tests.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. The task is accepted if at most one of the three passes.

**First round (discarded).** One attempt passed and two failed. The attempt
that passed cited `.github/THREAT_MODEL.md` for the runtime-directory rules.
That was the row `18620ed` had added, and I hadn't reverted it. I reverted
it, rebuilt the image and ran all three attempts again from scratch. The
first round's patches are not kept.

**Second round (counted):**

| Attempt | Result | What it missed |
|---|---|---|
| 1 | **failed**, 367 / 370 | runtime dir: creates directories through another user's symlink before refusing it; accepts a missing `XDG_RUNTIME_DIR` below a world-writable, non-sticky directory |
| 2 | **failed**, 368 / 370 | runtime dir: creates directories through another user's symlink before refusing it |
| 3 | **failed**, 368 / 370 | the same as attempt 2 |

**Result: accepted, 0 of 3.**

All three attempts (`difficulty/attempt-N.patch`, +337/−104, +432/−123 and
+359/−110 lines) fixed the reported bug and did every other point of the
statement. Each kept the upstream suite green and wrote a linear-time
`user-dirs.dirs` parser and a walk over the runtime directory's parents. All
three also guarded against FIFOs and NUL bytes, which upstream doesn't do.

Each walk refuses an unsafe `XDG_RUNTIME_DIR` and falls back. But with
`ensure_exists=True` (or through `place_runtime_file`), each attempt first
creates the missing levels and checks afterwards. When `XDG_RUNTIME_DIR` is
`/tmp/shared/run/user` and `run` is a symlink planted by another user in the
sticky shared directory, the attempts create `user` inside the attacker's
target directory before rejecting the path. Upstream's fix checks the
parents before creating anything, for exactly this reason ("creating the
missing levels follows whatever symlink sits at a parent"). I reproduced it
outside the test suite, with a symlink really owned by uid 1234 instead of
the test's mocked `lstat`: the reference creates nothing, and all three
attempts create the directory.

Attempt 1 also skips the parent check when `XDG_RUNTIME_DIR` doesn't exist
yet, so it returns `/tmp/open/session/app` below a mode-0777 directory.

### What I make of it

- **The verdict rests on one requirement.** Attempts 2 and 3 fail only the
  "creates nothing through a foreign symlink" check (two cases of one test).
  The statement says the runtime directory must be one "that no other user
  can replace, through the directory itself or any directory above it". I
  read that as covering what platformdirs does while checking. A reviewer
  who reads it as covering only the returned path would score attempts 2
  and 3 as passes, and the task would be rejected at 2 of 3.
- The THREAT_MODEL leak was a real mistake on my side: grep `.github/` and
  other non-doc files for each fix commit, not only `docs/`.
