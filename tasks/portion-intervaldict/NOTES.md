# Notes

## Starting point

- Repo: https://github.com/AlexandreDecan/portion
- Commit: `2c34f2830bef51b7bba3dd52e18b95daaf9de248` (October 2026)
- This doesn't come from an issue or PR. The author never optimised this
  class; the docstring says it "does not aim to have the best performance".
  So there's no upstream fix anyone could have memorised. I wrote the
  solution myself.

I went looking for a task like this on purpose. My Flask task failed because
the bug was famous, sat in two neighbouring functions, and the statement
practically spelled out the answer. Here I wanted something that has no
public answer, isn't an obvious edit, and has hard parts the statement doesn't
point to.

## What's slow, and why the fix is harder than it looks

Inside, `IntervalDict` is a `SortedDict` holding one key per distinct value. If
two ranges have the same value, their keys are merged into a union. So `d[x]`
walks through the keys until it finds one that contains `x`, and `d[k] = v`
goes through every key, both to find out whether `v` is already stored and to
cut `k` out of the others.

I measured it on 4096 intervals by counting comparisons:

| Operation | Original | My solution |
|---|---|---|
| `d[x]` | up to 8,197 | 32 |
| `x in d` | about 20,500 | 32 |
| `d[x] = v` | 8,220 – 12,466 | 194 |
| `del d[x]` | up to 8,314 | 178 |
| building, per assignment | about 5,166 | 76 |

The limit is 1000. That's a lot of room for a correct solution, and still far
below what the original code does.

The places I expected people to get it wrong:

1. **Binary search on the existing storage.** The keys are sorted by their
   lower bound, but they're unions that interleave, so the nearest key may
   not contain the point. All of the library's own tests still pass.
2. **Speeding up reads only.** An extra index for lookups is easy to add. But
   writes still have to find "the key that already holds this value" and
   rebuild a union, and that stays linear. You can't avoid changing how the
   data is stored.
3. **Grouping by hash.** Once you store individual pieces, you need to group
   them back by value. A `dict` is the obvious tool, but the README says any
   value that supports `==` is allowed, and lists aren't hashable.
4. **Views.** `keys()` and friends used to be views of the internal
   `SortedDict`. Once that's gone you have to write live views yourself.
5. **Interval subclasses.** `create_api()` builds an `IntervalDict` that uses a
   custom interval class. If you build keys with the base `Interval`, integer
   ranges stop merging.
6. **Touching bounds.** After `[0,1)` and `(1,2)`, the point `1` isn't covered.
   It's easy to be off by one in the binary search.

## My solution

It's in `solution/reference.patch`. It changes one file, `portion/dict.py`,
about 290 lines.

- Storage is a `SortedDict` whose keys are `(lower bound, is open)` and whose
  values are `(atomic interval, value)`. The intervals never overlap.
- A lookup is one bisect plus one containment check.
- A write finds the overlapping pieces with one bisect, cuts the key out of
  them, inserts the new piece, and merges it with a neighbour on either side
  if that neighbour holds an equal value.
- The "one key per value" view is rebuilt when someone asks for it and cached
  until the next write. Grouping tries a hash first and falls back to `==`.
- Three small classes give live `keys()`, `values()` and `items()`.

There are two more correct solutions in `verifier/alt_fixes/`. One uses plain
lists with the `bisect` module and no `sortedcontainers`. The other uses
`SortedKeyList`. Both pass, which tells me the tests check behaviour and not
my implementation.

## The hidden tests

There are 179 of them in `verifier/test_task.py`, and they only use the public
API.

**README examples (13 tests).** Every example comes from the library's README
or follows directly from it. They all pass on the original code, because they
aren't about speed. They're there to catch a fast but broken version.

**Comparison with the original (141 tests).** The Dockerfile copies the
original `dict.py` out of the repo before the agent touches anything. The test
runs 250 random operations on both the old and the new class and compares
everything observable after each step: `repr`, `len`, the order of keys and
values, `domain`, `as_dict`, return values and exceptions. It runs this with
four kinds of values and intervals: plain values, lists, objects that only
define `==`, and integer intervals.

Since the reference here is the library's own original code, these tests only
ask for what the library already does, nothing I made up. There are three
things I left out on purpose, because I don't think a correct solution should
have to copy them:

- which of two equal objects gets kept (`1` vs `1.0`);
- values that aren't equal to themselves (`nan`);
- the insertion order of the plain `dict` that `as_dict()` returns.

**Cost (25 tests).** Interval bounds are a class that counts every comparison,
and values are a class that counts every `==`. The mapping holds 4096
intervals, in two variants: every value different, and just two alternating
values. Every operation is measured at about thirty positions, and the worst
one has to stay at or under 1000.

These tests also rule out shortcuts. Every key is queried for the first time,
so caching earlier results doesn't help. Reads and writes are interleaved, so
an index that gets rebuilt after every write is caught.

**The wrong solutions in `verifier/wrong_fixes/`**, all of which fail:

| Patch | What it does | Passes the library's tests? |
|---|---|---|
| 01 | binary search on the existing keys | yes |
| 02 | groups values by hash only | no |
| 03 | exposes the internal pieces instead of one key per value | no |
| 04 | index for reads only, rebuilt after every write | yes |
| 05 | caches lookup results | yes |
| 06 | ignores the custom interval class | no |
| 07 | off by one on open bounds | yes |

Four of the seven pass the whole existing test suite. That matters, because
the existing suite is what the agent can run on its own machine.

## Difficulty check, and why it failed

Each attempt got a folder containing `PROBLEM.md`, the repo with no git
history, and a virtualenv. No network, and no access to this repo, the tests
or my solution. One try each. Afterwards I graded their patches with the
hidden tests in Docker, the same way `run.sh` does.

| Attempt | Library tests | Hidden tests |
|---|---|---|
| 1 | passed | **179 / 179** |
| 2 | passed | **179 / 179** |
| 3 | — | stopped; the result was already decided |

My bar is at most one in three, so once two passed the task was rejected.
Attempt 1 hit a usage limit partway through and was resumed from where it
stopped, with no extra information.

**How they solved it.** Both landed on the same design, and it wasn't mine. The
main storage was a sorted list of atomic pieces, plus a hash index for finding
a value that's already stored. They kept the old `SortedDict` as a cache that
gets rebuilt for operations that need the whole mapping. That's a smart move,
because it makes most of the "reconstruct the old view" problem go away:
`repr()`, `keys()` and `as_dict()` keep running on the original code.

Both were also more careful than my tests require. They preserved `1` vs `1.0`,
`nan`, and pickling.

**Why it was easy.** I think the main reason is this. When the requirement is
"don't change the behaviour", the original code is a complete, executable
specification, and it ships with the task. Both attempts copied the original
class, wrote their own random tester against it, and only finished once it
came back clean. One ran 3,000 seeds and the other 60,000 sequences. All of my
traps are things a random tester finds in seconds.

The speed requirement could also be checked by the agent itself. To be fair, I
gave the counting method and the limit in the statement, so both attempts just
wrote their own counter. And everything is in one file, so there was nothing
to hunt for.

So the task took a lot of work (both wrote 400–500 lines), but it wasn't hard.
Those turn out to be different things.

**Was the statement unclear?** I asked each attempt to list anything that
confused it. Both raised the same point. For values that can't be hashed,
checking whether a value is already stored takes one `==` per stored value, so
the limit can't be met. My tests only measure cost with hashable values, but
the statement doesn't say that. If I were keeping the task, I'd add one
sentence to `PROBLEM.md`.

**What I'd do differently next time.** Before building anything, I'd ask: can
the agent check its own answer mechanically? If the repo contains something
that already does the right thing, the task will get solved. A hard task needs
behaviour that doesn't exist in the code yet and has to be worked out from
the docs, or a bug that's expensive to reproduce (ordering, concurrency), or a
cause that's far away from the symptom in a big codebase.
