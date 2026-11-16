# Rejected candidates

Candidates that were built, verified, and then rejected by the acceptance gate
described in the [README](README.md). Each entry records why the candidate
looked promising, how it was measured, and what the failure taught.

## Flask — blueprint `url_prefix` slash merging

- Task: [`tasks/flask-blueprint-prefix`](tasks/flask-blueprint-prefix)
- Repository: pallets/flask, parent of the fix for issue #2731 (2018)
- Kind: bug fix, one file, about ten lines
- Gate result: **3 of 3 attempts passed** (21/21 hidden tests each) — rejected

**Why it looked promising.** Upstream itself needed four commits over four days
to get this right: the first, plausibly titled fix introduced a regression for
empty rules and left a crash in place. The verifier includes that real,
incomplete upstream commit as a wrong fix, and it does fail.

**Why it was easy.**

1. *The bug is local.* Symptom and cause are in two adjacent methods of one
   small class. There is nothing to trace: reading the file is enough.
2. *The statement was close to a specification.* To be unambiguous, the problem
   statement walked through the slash combinations one by one. With the cases
   enumerated, the fix is an exercise in string handling.
3. *The trap targets inattention, not difficulty.* "The obvious fix misses the
   empty-rule case" catches someone who stops after the headline symptom. An
   agent that enumerates edge cases as a matter of routine does not stop there.
4. *The material is old and famous.* The issue, the discussion and the final
   code have been public since 2018 in one of the most-read Python projects.

**What changed in the selection criteria afterwards.**

- Prefer tasks where the difficulty is a *conflict between requirements* (make
  it fast, but keep every observable behaviour) over tasks where the difficulty
  is a missed case.
- The statement must be able to state the acceptance criteria completely
  *without* enumerating the cases that make the task hard. If it cannot, the
  task is either ambiguous or easy.
- Prefer code that has no well-known upstream fix: recent commits in
  moderately known repositories, or work upstream has never done.
- Visible tests must not catch the tempting wrong solutions.

## tomlkit — five bugs in split tables, one symptom in the report

- Task: [`tasks/tomlkit-out-of-order-tables`](tasks/tomlkit-out-of-order-tables)
- Repository: python-poetry/tomlkit at `7bf7284` (November 2026), with five fixes
  from October–November 2026 reverted
- Kind: bug hunt in one subsystem, a 1,300-line file
- Gate result: **2 of 3 attempts passed** — rejected, narrowly

This is the closest so far. One attempt failed on a real bug it never found
(73/77). The two that passed each needed about 30 minutes and a rewrite of
about 1,000 lines, where upstream fixed the same bugs in 31.

**Why it still wasn't enough.** The contract could be checked mechanically
against `tomllib`, which ships with Python. All three attempts wrote random
testers. Whether they passed came down to whether their generator happened to
produce one unusual document shape: an indented header nested four levels
deep.

**Takeaway.** Hiding the cases helps, but it isn't enough when there's a
mechanical oracle. Hitting the 1-in-3 bar probably needs a task where the
expected behaviour can't be checked by a program the solver writes in a few
minutes.

## portion — logarithmic `IntervalDict`

- Task: [`tasks/portion-intervaldict`](tasks/portion-intervaldict)
- Repository: AlexandreDecan/portion, commit `2c34f28` (October 2026)
- Kind: performance work under a behaviour-preservation constraint, one file,
  about 290 changed lines in the reference solution
- Gate result: **2 of 2 graded attempts passed** (179/179 hidden tests each) —
  rejected before the third attempt finished

**Why it looked promising.** It was chosen to avoid everything that sank the
Flask task: no upstream fix exists, the statement gives complete acceptance
criteria without enumerating the hard cases, four of the seven wrong solutions
pass the whole visible test suite, and the tempting optimisation (binary search
on the existing storage) is incorrect for a non-obvious reason.

**Why it was easy.**

1. *The solver could rebuild the hidden verifier.* A "do not change behaviour"
   constraint makes the unmodified code a complete executable specification.
   Both attempts wrote their own differential fuzzer against the original class
   and their own comparison counter, and only stopped when both were clean.
   Every trap in the task is something a fuzzer finds in seconds.
2. *Nothing had to be discovered.* One file, and the statement names the class.
3. *Long is not hard.* The attempts produced 400–500 line rewrites without
   difficulty. Volume of careful work is not a source of failure for an agent
   that can test itself.

**What changed in the selection criteria afterwards.**

- Ask of every candidate: *can the solver check its own answer mechanically?*
  If the starting repository contains an executable oracle for the expected
  behaviour, the task is self-verifying and will be solved.
- Difficulty therefore has to sit where self-checking does not reach: behaviour
  that the existing code does **not** already exhibit and that has to be derived
  from documentation spread across subsystems; failures that are expensive to
  reproduce (ordering, concurrency, resource lifetime); or a cause that has to
  be located in a large codebase from a symptom observed far away.
- Line count and number of invariants are not predictors of difficulty.

## Earlier candidates

Two earlier candidates, built on `jsonschema` and on `tenacity`, were rejected
by the same gate with 2 of 3 attempts passing. They are not included in this
repository.
