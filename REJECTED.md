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

**Why it was too easy.**

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

## Earlier candidates

Two earlier candidates, built on `jsonschema` and on `tenacity`, were rejected
by the same gate with 2 of 3 attempts passing. They are not included in this
repository.
