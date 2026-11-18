# Notes

## Where the bugs come from

- Repo: https://github.com/pallets/click
- Base commit: `08b803cf32ceb2ae6a772c62d5da42757a897d44` (16 November 2026)

| Commit | Date | What it fixed |
|---|---|---|
| `7996a89` | 2026-11-02 | help text is wrapped between words only; hyphenated and long words stay whole, and an indent wider than the width no longer loops |
| `c53d373` | 2026-10-06 | `show_envvar` lists every variable of an `envvar` sequence; an empty `envvar` behaves like none |
| `f316d5c` | 2026-08-15 | a progress bar lands on its final position when `update_min_steps` doesn't divide the length |
| `047adef` | 2026-07-31 | `get_help_option_names` keeps a fixed order (it went through a `set`) |
| `71f2baf` | 2026-07-01 | `unstyle` and `echo` strip every ECMA-48 CSI sequence, not only SGR-like ones |
| `93ba007` | 2026-06-30 | `prompt` and `confirm` strip styles when the stream doesn't support them |
| `6f85d26` | 2026-06-27 | `Path(allow_dash=True)` doesn't compare `str` with `bytes` (fails under `python -bb`) |
| `762c97e` | 2026-06-10 | an optional `Choice`/`DateTime` argument gets one pair of brackets in the usage line |
| `82f377c` | 2026-05-23 | an empty help text gives `(DEPRECATED)`, not ` (DEPRECATED)` |
| `7d05a59` | 2026-05-19 | `get_parameter_source()` works in eager callbacks and type conversion |
| `32ae2ac` | 2026-05-18 | completion of an `Enum` `Choice` offers the names it accepts |
| `1241aba` | 2026-04-21 | the "Try ... for help" hint names a help option a parameter doesn't shadow |
| `3a3e035` | 2026-04-21 | a `default_map` string for a multi-value parameter is split like an env var value |

Eight reverse cleanly. `c53d373`, `6f85d26`, `93ba007`, `82f377c` and
`7d05a59` don't, because later commits moved or reformatted the code; I
reverted them by hand at the current location. Source changes only.
Changelog entries are removed (the Dockerfile also deletes `CHANGES.md` with
the other root Markdown files), and so are two documentation passages that
described the fixed behaviour: the note that help text never breaks inside a
word and the `default_map` "Multi-value parameters" section. 25 upstream test
functions and three `test_term_len` cases that fail on the starting state are
removed; each belongs to one of these fixes. An `import threading` left unused
by the removals is dropped too. One more case, `test_choice_case_sensitive[False]`, is
removed because it pins the lower-cased completion that `32ae2ac` introduced,
which the hidden tests don't require.

Considered and left out: the short-help abbreviation heuristic (`f67c2bb`,
too much of a judgement call), the pager fixes (need a real pager), the
`KeyboardInterrupt` race, `version_option` resolving import names (a
documented behaviour change), and `show_default` strings in prompts (an old
fix whose tests are spread through the suite).

## The hidden tests

`verifier/test_task.py`, 64 tests. Everything goes through `CliRunner`,
commands built with the decorators, `Context`, `click.formatting`,
`progressbar` with a fake tty, `unstyle`, and `ShellComplete`. Two tests run a
small script in a child process: one under `python -bb`, one under twelve
different `PYTHONHASHSEED` values.

Before any attempt ran I loosened one test: the help option names may come in
any fixed order, not only declaration order. The statement asks for the same
output every run, not a particular order.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and
thirteen wrong solutions against the upstream suite (2,394 tests; the
`echo_via_pager` tests are deselected because the image has no `less`, and
they fail the same way on the unmodified upstream commit) and the hidden
tests.

- `verifier/alt_fixes/01_ordering_regex_and_envvar_variants.patch` writes the
  help-option filter, the CSI regex and the env var list differently.
- each wrong solution fixes everything except one bug.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 15 min, 104 tool calls | **failed**, 60 / 64 | a `default_map` string for a multi-value parameter |
| 2 | 19 min, 122 tool calls | **failed**, 60 / 64 | the same |
| 3 | 16 min, 116 tool calls | **failed**, 60 / 64 | the same |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, 9 files, +260 / −63),
**attempt 2** (`difficulty/attempt-2.patch`, 9 files, +331 / −64) and
**attempt 3** (`difficulty/attempt-3.patch`, 9 files, +303 / −69) each fixed
the other twelve bugs. All three also looked at `default_map` under point 2
of the statement: each made `default_map={"flag": True}` resolve to a
non-boolean `flag_value`, as `default=True` does. None of them noticed that
`default_map={"point": "3 4"}` for `nargs=2` (or a tuple type) fails with
"Value must be an iterable", while `POINT="3 4"` in the environment gives
`(3, 4)`.

### What I make of it

- As in the other accepted tasks, the difficulty sits in one bug. The other
  twelve, including the infinite loop in `wrap_text`, the hash-seed-dependent
  help option order and the `-bb` failure, were found by every attempt.
- The statement names `default_map` and the environment explicitly and asks
  for them to be "processed the same way for every kind of parameter". The
  failing case is the most direct reading of that: the same string, from the
  two sources, gives a value in one case and a usage error in the other.
- All three added 260 to 330 lines; upstream's fixes add 93 and remove 115
  (most of the removals are the custom long-word splitting that `7996a89`
  drops).
