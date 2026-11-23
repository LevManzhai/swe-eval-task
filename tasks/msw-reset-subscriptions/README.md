# msw: GraphQL subscriptions after `resetHandlers()`

> **Status: difficulty check in progress, 1 of 1 attempts passed** (12 / 12,
> in about 5 minutes). `run.sh` passes all of its checks. See
> [`NOTES.md`](NOTES.md).

[msw](https://github.com/mswjs/msw) (Mock Service Worker) is the API mocking
library used in many JavaScript test suites. This task is a different kind
from the others in this repository: not a hunt for many small bugs, but **one
bug whose symptom shows up far from its cause**, in TypeScript.

The user's report: a long-lived `graphql-ws` client stops getting any
subscription data after the first test, because `server.resetHandlers()`
broke it. msw says the subscription "has no matching subscription handler".

The cause sits two layers down from where the warning is printed: in how the
generic handler controller resets handlers, and in a hidden sibling handler
that every `graphql.link()` creates. The obvious fix at the symptom site
makes the report pass and introduces the opposite bug: handlers from the
previous test keep answering. A correct fix needs a "this handler was
removed" event that the controller doesn't have.

The upstream fix is msw commit `3818a81` (October 2026).

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees: a user bug report and the acceptance criteria |
| `environment/Dockerfile` | msw at commit `3818a81`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fix, source only |
| `verifier/task.node.test.ts` | 12 hidden tests through the public API |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | four plausible wrong solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. msw is MIT-licensed; the Dockerfile clones it from GitHub.
