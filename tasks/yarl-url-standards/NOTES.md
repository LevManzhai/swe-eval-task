# Notes

## Where the bugs come from

- Repo: https://github.com/aio-libs/yarl
- Base commit: `5350e374eb1735aa275af45f574661a1ebb80ec7` (18 November 2026)

yarl's `mode="whatwg"` / `mode="rfc"` switch landed on 28 September 2026
(unreleased at the base commit). Over October upstream closed the gaps
between each mode and its standard, one PR at a time. I reverted the ten most
recent, which form a contiguous chain:

| Commit | Date | What it fixed |
|---|---|---|
| `ae2c11b` | 2026-11-17 | `URL.build(port=0)` without a host is rejected like any other port |
| `8ac0a78` | 2026-10-29 | WHATWG mode keeps an invalid percent sign (`%2z`, `%`) as written |
| `83cc6f7` | 2026-10-28 | WHATWG mode keeps `"`, `` ` ``, `{` and `}` in special hosts |
| `36a08fd` | 2026-10-27 | WHATWG mode percent-encodes userinfo with the userinfo encode set |
| `ae7bf60` | 2026-10-27 | RFC mode keeps an IPv6 address as written (lowercased), not compressed |
| `075b4c7` | 2026-10-27 | WHATWG mode rejects a relative reference against an opaque-path base |
| `c253ab6` | 2026-10-27 | non-special URLs get an opaque host (percent-encoded, no IDNA) |
| `d0357f6` | 2026-10-26 | a join reference `///host/...` takes the host after the slashes |
| `d0d6a37` | 2026-10-09 | RFC mode rejects an empty `http(s)` host (RFC 9110 4.2.1) |
| `1b9e377` | 2026-10-05 | WHATWG mode rejects an empty `http(s)` host (`http://`, `http://?`) |

All reverse cleanly, source, tests, `docs/api.rst` and `CHANGES/` fragments
alike. The reference patch is 647 changed lines, most of it `c253ab6` and
`83cc6f7`.

Old versions of upstream tests that pinned the pre-fix behaviour are
removed from the starting state, case by case: they would forbid the fix.
That is about twenty parametrized cases or test functions across `test_rfc3986.py`,
`test_url.py`, `test_url_percent_host.py`, `test_url_rfc_grammar.py`,
`test_url_special_authority.py`, `test_url_update_netloc.py`,
`test_url_userinfo_whatwg.py` and `test_url_empty_components.py`.

The image deletes `tools/conformance/`: it vendors the web-platform-tests URL
corpus, a strict RFC 3986 resolver and a report of every case where yarl
differs from either, which together would be an oracle for this task. It
also deletes the contributor-tool Markdown files at the repository root.
yarl is installed pure Python (`YARL_NO_EXTENSIONS=1`); `_quoting_c.pyx` is part of the reference
but isn't compiled.

## The hidden tests

`verifier/test_task.py`, 375 tests, with all expectations embedded.

- 45 WHATWG-mode cases and 18 RFC-mode cases where the starting state is
  wrong. They are every case of `urltestdata.json` (web-platform-tests
  commit `c48d5874`, the corpus upstream pins) where the reference agrees
  with the standard and the starting state doesn't, for WHATWG; and the same
  for RFC mode against upstream's RFC 3986 resolver. The expected value is
  the standard's result; the reference's output is accepted as an
  equivalent spelling (they differ only by RFC 3986 section 6.2
  normalization). An expected failure means yarl must raise `ValueError` or
  stay relative.
- 150 + 150 cases from the same corpus that the starting state already gets
  right, sampled with a fixed seed, as guards.
- the `URL.build(port=0)` cases from upstream's tests.

## Checking the checker

`run.sh` checks the starting state, the reference, one alternative and nine
wrong solutions against the upstream suite (2,869 tests, run with
`--no-cov`) and the hidden tests.

- `verifier/alt_fixes/01_port_and_ipv6_variants.patch` writes the port check
  and the RFC-mode IPv6 host differently.
- each wrong solution fixes everything except one bug. There is none for
  `c253ab6` (opaque hosts): later commits in the chain rewrote the same code,
  and it can't be reverted on its own.

## Difficulty check

A strong coding agent gets `PROBLEM.md` and the repository, one try. Three
attempts are run. Accepted if at most one of the three passes.

| Attempt | Time | Result | What it missed |
|---|---|---|---|
| 1 | 30 min, 131 tool calls | **failed**, 353 / 375 | userinfo encode set; RFC IPv6 as written; `http://?`; `URL.build(port=0)`; broke 3 guard cases (`xn--` labels) |
| 2 | 28 min, 93 tool calls | **failed**, 351 / 375 | userinfo encode set; RFC IPv6 as written; RFC `///host` joins and empty http host; `URL.build(port=0)` |
| 3 | 19 min, 80 tool calls | **failed**, 357 / 375 | userinfo encode set; RFC IPv6 as written; opaque host followed by `?`/`#`; `http:` against an https base |

**Result: accepted, 0 of 3.**

**Attempt 1** (`difficulty/attempt-1.patch`, +375 / −64, plus test changes
not counted here) wrote a reference WHATWG parser from the spec and about
980 inputs from memory, and fixed the reported `%` case, opaque hosts,
special-host characters, opaque-path bases and `///host` joins. It also
started rejecting `xn--` labels that the pinned WHATWG test data accepts.

**Attempt 2** (`difficulty/attempt-2.patch`, +1,107 / −16) wrote a new
`yarl/_whatwg.py`, a full implementation of the WHATWG parser state machine,
and routed WHATWG-mode parsing and joins through it. WHATWG mode is the
closest of the three; RFC mode got the least attention.

**Attempt 3** (`difficulty/attempt-3.patch`, +234 / −36) made the smallest
change and was the only one to fix `URL.build(port=0)`.

What all three missed:

- **The userinfo percent-encode set.** WHATWG encodes `;`, `=` and `:` (in
  the password) in userinfo, among others. All three leave `;` and `=` as
  they are. Attempt 1 says an existing `human_repr` round-trip test pins
  them; it doesn't (the reference encodes them and passes the whole suite).
- **IPv6 addresses in RFC mode.** RFC 3986 section 6.2 allows lowercasing a
  host but not rewriting it; all three still compress
  `[0:0:0:0:0:0:13.1.68.3]` to `[::d01:4403]` in RFC mode, as WHATWG does.

### What I make of it

- This is the first task here whose hidden cases come almost entirely from a
  standard's own test data rather than from tests I wrote. The 18 failures
  of the best attempt are all cases where the standard (or RFC 3986) is
  unambiguous.
- Two attempts wrote a WHATWG parser of their own from memory; neither
  matched the standard on the userinfo encode set, which is easy to get
  wrong without the spec's tables at hand.
