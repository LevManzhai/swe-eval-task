# click: rare command lines, help pages and terminals handled wrongly

> **Status: accepted.** Three of three one-shot attempts failed (60 of 64
> each). All three missed the same bug. `run.sh` passes all 32 of its checks.
> Details at the end of [`NOTES.md`](NOTES.md).

[click](https://github.com/pallets/click) is the command-line toolkit under
Flask, black, pip-tools and many other tools. Between April and November 2026
upstream fixed a run of bugs where click mishandled rare but legitimate
command definitions, input and terminals. I took click as of 16 November 2026
and reverted thirteen of them:

| Where | Trigger | What goes wrong |
|---|---|---|
| usage line | an optional argument of type `Choice` | `[[fast|slow]]` |
| help text | `--avoid-motorways` near the end of a line | split into `--avoid-` and `motorways` |
| help text | a word longer than the width | cut in two |
| `wrap_text` | an indent wider than the width | loops forever |
| `show_envvar` | `envvar=["A", "B"]` on a required option | the error shows `['A', 'B']` |
| `show_envvar` | `envvar=[]` or `""` | help shows `[env var: ]` |
| deprecated option or command | `help=""` | ` (DEPRECATED)` with a leading space |
| error hint | an option that takes `-h` while `-h` is a help name | `Try 'cli -h' for help.` |
| `default_map` | `{"point": "3 4"}` for `nargs=2` | the string isn't split, so conversion fails |
| callbacks and types | `ctx.get_parameter_source()` in an eager callback or `convert()` | `None` |
| `unstyle` / `echo` | colon true-colour, mouse or cursor-shape sequences | left in the output |
| `prompt` / `confirm` | a styled prompt with colour off | escape codes in the prompt |
| `progressbar` | `update_min_steps` that doesn't divide the length | ends at 18/20 |
| help option names | `help_option_names=["-h", "--help", "-?"]` | order changes from run to run |
| completion | `Choice(MyEnum)` | offers `MyEnum.RED`, which isn't accepted |
| `Path(allow_dash=True)` | `python -bb` | `BytesWarning` raised |

The problem statement shows **only the first row** and a five-point contract.

## Why this one

Same recipe as the other tasks in this repository: many bugs, each with an
unusual trigger, in a widely used library whose own suite passes without
noticing them, and no oracle in the sandbox.

## Layout

| Path | What it is |
|---|---|
| `task/PROBLEM.md` | what the solver sees |
| `environment/Dockerfile` | click at commit `08b803c`, plus `starting_state.patch`; git history removed |
| `solution/reference.patch` | the upstream fixes, source only |
| `verifier/test_task.py` | 64 hidden tests through the public API |
| `verifier/alt_fixes/` | a correct solution written differently; must pass |
| `verifier/wrong_fixes/` | thirteen "all but one" solutions; must fail |
| `difficulty/` | the patches the one-shot attempts produced |
| `run.sh` | builds the image and checks all of the above |

## Running it

```bash
./run.sh
```

You need Docker. click is BSD-licensed; the Dockerfile clones it from GitHub.
