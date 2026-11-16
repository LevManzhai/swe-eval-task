# Coding tasks that stay hard for LLM agents

A small collection of software-engineering tasks built on real open-source
repositories, each packaged the way SWE-bench-style benchmarks package them:
a problem statement, a reproducible environment, a reference solution, and a
deterministic hidden verifier.

What I am actually interested in here is the part that usually goes
unreported: **most candidate tasks turn out to be too easy**, and the only way
to know is to measure. Every candidate in this repository goes through the
same gate before it is accepted, and the ones that fail it are kept, with a
post-mortem, in [`REJECTED.md`](REJECTED.md).

## Tasks

| Task | Repository | Kind | Status |
|---|---|---|---|
| [`tasks/portion-intervaldict`](tasks/portion-intervaldict) | [AlexandreDecan/portion](https://github.com/AlexandreDecan/portion) | Performance work under a strict behaviour-preservation constraint | see its `NOTES.md` |
| [`tasks/flask-blueprint-prefix`](tasks/flask-blueprint-prefix) | [pallets/flask](https://github.com/pallets/flask) | Bug fix | **rejected** by the difficulty gate, kept for reference |

## What every task contains

- `task/PROBLEM.md` — what the solver sees. It describes the symptom and the
  acceptance criteria, not where to look.
- `environment/` — a Dockerfile with everything pinned (base image, upstream
  commit, dependencies). Test runs happen with networking disabled.
- `solution/reference.patch` — one way to solve it.
- `verifier/` — the hidden test suite, plus two sets of patches that keep the
  verifier honest: `alt_fixes/` (different but correct implementations, which
  must pass) and `wrong_fixes/` (plausible but wrong, incomplete or hard-coded
  ones, which must fail).
- `run.sh` — builds the image and checks the whole matrix: starting state
  fails, reference and alternative solutions pass, wrong solutions fail.
- `NOTES.md` — why the task is hard, why each hidden check is justified by the
  documented behaviour rather than by an arbitrary choice, and the result of
  the difficulty check.

## The acceptance gate

A candidate is accepted only if all of the following hold:

1. **Reproducible** — `run.sh` is green from a clean checkout.
2. **Fair** — every hidden check is traceable to the problem statement, the
   library's documentation, or the behaviour of the unmodified code. Anything
   that is merely an accident of the reference solution is left untested.
3. **Implementation-agnostic** — structurally different correct solutions
   pass; the verifier never looks at private attributes.
4. **Hard** — three independent attempts by a frontier coding agent, each given
   only the problem statement and the repository (no history, no notes, no
   verifier), in a single shot. The candidate is accepted if at most one of the
   three passes the hidden verifier.
5. **Hard for the right reason** — when attempts fail, the failures must come
   from the engineering difficulty, not from an ambiguous statement or a broken
   environment. Each attempt is asked to report what it found ambiguous, and
   every failure is traced back to a specific documented behaviour.

Gate 4 is deliberately not tuned after the fact: a statement is never blurred
or cut down to make a task "pass". If a task is too easy it is rejected and
written up.
