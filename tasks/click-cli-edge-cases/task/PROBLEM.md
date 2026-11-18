# click: rare command lines, help pages and terminals handled wrongly

The repository in `/workspace/repo` is [click](https://github.com/pallets/click),
the command-line toolkit that Flask, black, pip-tools and many other tools are
built on.

## What a user reported

> One of our commands takes an optional argument with a fixed set of values:
>
> ```python
> @click.command()
> @click.argument("speed", type=click.Choice(["fast", "slow"]), required=False)
> def cli(speed): ...
> ```
>
> Its help page starts with `Usage: cli [OPTIONS] [[fast|slow]]`. Nothing
> else in the help uses double brackets, and our docs generator chokes on it.

## What we want

Fix that, and treat it as one example of a wider problem: click handles some
rare but legitimate command definitions, inputs and environments in ways that
don't match its documentation or what its users can reasonably expect. We
want the following to hold across the library:

1. **Help, usage and error messages are well-formed, true and complete.**
   Text is wrapped between words only, never inside one, whatever the width.
   Usage synopses and labels are formatted consistently, with no doubled
   brackets and no stray spaces. Whatever a help page or an error message
   tells the user (an environment variable to set, an option to try) is
   accurate and complete for how the command is actually defined.
2. **A value is treated the same wherever it comes from.** The command line,
   an environment variable, `default_map` and a default are processed the same
   way for every kind of parameter, and code that processes a value
   (callbacks, parameter types) can find out where it came from.
3. **Terminal output respects the terminal.** Where styling is not
   supported, every kind of terminal control sequence is removed, from all
   output, prompts included. A progress bar ends showing where it really
   ended.
4. **The same input gives the same output, and completion offers what is
   accepted.** Nothing a user sees depends on per-process randomness, and
   shell completion suggests exactly the values the parameter accepts.
5. **click works under Python's strict flags.** Nothing in click warns or
   fails when Python runs with `-bb` or with warnings turned into errors.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is, apart from the tests that run the `less`
  pager, which isn't installed in this sandbox. It doesn't cover these cases.
- Your changes are graded by hidden tests that use click's public API:
  commands, groups, options and arguments, `CliRunner`, `Context`,
  `click.formatting`, `progressbar`, `style`/`unstyle`/`echo`/`prompt`/`confirm`,
  and `click.shell_completion.ShellComplete`. Some run small scripts in a
  separate Python process.
