# tomlkit: eight bugs in document structure, one symptom in the report

> **Status: difficulty check in progress.** See the end of
> [`NOTES.md`](NOTES.md).

This is the second version of
[`tomlkit-out-of-order-tables`](../tomlkit-out-of-order-tables). The first
version came close: one of three attempts failed on a real bug. The two that
passed did it by rewriting about a thousand lines and fuzzing against
`tomllib`. Whether an attempt passed came down to whether its random generator
happened to produce one unusual document shape.

So this version keeps the same design and adds more bugs of that kind. Each of
them needs its own specific shape or operation to show up:

| # | Upstream fix | What breaks |
|---|---|---|
| 1 | `29c31d2` #702 | a table split around an `[[array]]` is written back reordered (the only bug shown in the statement) |
| 2 | `229ee86` #565 | `[a.b.c]` then `[a]` with `b.z = 1` is rejected, although it's valid |
| 3 | `398c53e` #663 | `AttributeError` while parsing a table defined out of order under an indented header four levels deep |
| 4 | `bb7cdd5` #699 | a key added through a split table's proxy can't be deleted or replaced afterwards |
| 5 | `55d0768` #677 | `update()` on a split table drops unrelated keys |
| 6 | `d41d237` #631 | slice assignment on an array of tables writes invalid TOML |
| 7 | `85d391e` #664 | deleting the last key under a dotted prefix in an inline table leaves `, ,` |
| 8 | `67d3e86` #549 | replacing a dotted key with an array of tables swallows the following sibling |

All eight were fixed upstream between July and November 2026. The repo is
given without git history.

## Layout

The same as the first version:

- `task/PROBLEM.md`
- `environment/` (pinned Dockerfile plus `starting_state.patch`)
- `solution/reference.patch` (the eight upstream fixes, code only)
- `verifier/test_task.py` (100 hidden tests, with `tomllib` as the oracle)
- `verifier/alt_fixes/` (2 patches that must pass)
- `verifier/wrong_fixes/` (7 patches that must fail)
- `run.sh`

## Running it

You need Docker.

```bash
./run.sh
```
