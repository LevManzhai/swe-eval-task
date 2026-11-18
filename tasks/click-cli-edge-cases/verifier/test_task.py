"""Hidden tests for the click CLI edge-cases task.

Only click's public API is used: commands, options and arguments built with
the decorators or the classes, ``CliRunner``, ``Context``, the formatting
helpers, ``progressbar``, ``unstyle``/``style`` and the shell completion
classes.
"""

from __future__ import annotations

import enum
import io
import os
import subprocess
import sys
import textwrap
import threading

import pytest

import click
import click._termui_impl
from click.core import ParameterSource
from click.shell_completion import ShellComplete
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def completions(cli: click.Command, args: list[str], incomplete: str) -> list[str]:
    comp = ShellComplete(cli, {}, cli.name or "cli", "_CLI_COMPLETE")
    return [c.value for c in comp.get_completions(args, incomplete)]


def words(text: str) -> set[str]:
    return set(text.split())


# ---------------------------------------------------------------------------
# (1) Help, usage and error messages
# ---------------------------------------------------------------------------


class TestHelpWrapping:
    TEXT = (
        "Plan a route. Add --avoid-motorways to stay on country roads, or "
        "--prefer-scenic-routes-over-fast-ones to see more, through "
        "Llanfairpwllgwyngyllgogerychwyrndrobwll."
    )

    @pytest.mark.parametrize("width", [20, 28, 36])
    def test_command_help_keeps_words_whole(self, runner: CliRunner, width: int) -> None:
        @click.command(
            help=self.TEXT,
            context_settings={"terminal_width": width, "max_content_width": width},
        )
        def cli() -> None:
            pass

        out = runner.invoke(cli, ["--help"]).output
        assert words(self.TEXT) <= words(out)

    @pytest.mark.parametrize("width", [24, 32])
    def test_option_help_keeps_words_whole(self, runner: CliRunner, width: int) -> None:
        @click.command(context_settings={"terminal_width": width, "max_content_width": width})
        @click.option("--route", help=self.TEXT)
        def cli(route: str | None) -> None:
            pass

        out = runner.invoke(cli, ["--help"]).output
        assert words(self.TEXT) <= words(out)

    def test_wrap_text_keeps_words_whole(self) -> None:
        text = "Add --avoid-motorways to stay on country roads."
        lines = click.formatting.wrap_text(text, 20).splitlines()
        assert [w for line in lines for w in line.split()] == text.split()

    def test_long_word_is_not_cut(self) -> None:
        lines = click.formatting.wrap_text("Visit Llanfairpwllgwyngyll in Wales.", 10).splitlines()
        assert "Llanfairpwllgwyngyll" in [line.strip() for line in lines]

    def test_styled_long_word_is_not_cut(self) -> None:
        word = click.style("Llanfairpwllgwyngyll", fg="red")
        lines = click.formatting.wrap_text(f"Visit {word} in Wales.", 10).splitlines()
        assert word in [line.strip() for line in lines]

    def test_indent_wider_than_width_returns(self) -> None:
        result: list[str] = []

        def run() -> None:
            result.append(
                click.formatting.wrap_text(
                    " rain", 5, initial_indent=" " * 8, subsequent_indent=" " * 8
                )
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive(), "wrap_text did not return"
        assert result and result[0].split() == ["rain"]


class TestUsageSynopsis:
    def test_optional_choice_argument_has_one_pair_of_brackets(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("speed", type=click.Choice(["fast", "slow"]), required=False)
        def cli(speed: str | None) -> None:
            pass

        out = runner.invoke(cli, ["--help"]).output
        assert "[fast|slow]" in out
        assert "[[" not in out and "]]" not in out

    def test_optional_variadic_choice_argument(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("speed", type=click.Choice(["a", "b"]), nargs=-1)
        def cli(speed: tuple[str, ...]) -> None:
            pass

        out = runner.invoke(cli, ["--help"]).output
        assert "[a|b]..." in out
        assert "[[" not in out

    def test_required_choice_argument_unchanged(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("speed", type=click.Choice(["fast", "slow"]))
        def cli(speed: str) -> None:
            pass

        assert "Usage: cli [OPTIONS] {fast|slow}" in runner.invoke(cli, ["--help"]).output

    def test_optional_plain_argument_unchanged(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("name", required=False)
        def cli(name: str | None) -> None:
            pass

        assert "Usage: cli [OPTIONS] [NAME]" in runner.invoke(cli, ["--help"]).output


class TestDeprecatedLabel:
    @pytest.mark.parametrize(
        ("deprecated", "label"),
        [(True, "(DEPRECATED)"), ("use --b", "(DEPRECATED: use --b)")],
    )
    def test_option_with_empty_help(self, deprecated: bool | str, label: str) -> None:
        opt = click.Option(["--foo"], help="", deprecated=deprecated)
        record = opt.get_help_record(click.Context(click.Command("cli")))
        assert record is not None
        assert record[1] == label

    def test_command_with_empty_help(self, runner: CliRunner) -> None:
        cli = click.Command("cli", help="", deprecated=True)
        out = runner.invoke(cli, ["--help"]).output
        assert "\n  (DEPRECATED)\n" in out

    def test_option_with_help_keeps_its_text(self) -> None:
        opt = click.Option(["--foo"], help="Old.", deprecated=True)
        record = opt.get_help_record(click.Context(click.Command("cli")))
        assert record is not None and record[1] == "Old. (DEPRECATED)"


class TestShowEnvvar:
    def test_error_lists_every_variable(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--units", required=True, envvar=["WEATHER_UNITS", "UNITS"], show_envvar=True)
        def cli(units: str) -> None:
            pass

        result = runner.invoke(cli, [], env={"WEATHER_UNITS": None, "UNITS": None})
        assert result.exit_code == 2
        assert "'WEATHER_UNITS'" in result.output
        assert "'UNITS'" in result.output
        assert "[" not in result.output.split("Error:")[1]

    def test_error_with_a_single_variable(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--units", required=True, envvar="UNITS", show_envvar=True)
        def cli(units: str) -> None:
            pass

        result = runner.invoke(cli, [], env={"UNITS": None})
        assert "(env var: 'UNITS')" in result.output

    @pytest.mark.parametrize("envvar", [[], ""])
    def test_empty_envvar_shows_nothing(self, runner: CliRunner, envvar: object) -> None:
        @click.command()
        @click.option("--units", envvar=envvar, show_envvar=True)
        def cli(units: str | None) -> None:
            pass

        out = runner.invoke(cli, ["--help"]).output
        assert "env var" not in out

    @pytest.mark.parametrize("envvar", [[], ""])
    def test_empty_envvar_falls_back_to_auto_envvar(self, runner: CliRunner, envvar: object) -> None:
        @click.command()
        @click.option("--units", envvar=envvar, show_envvar=True)
        def cli(units: str | None) -> None:
            pass

        out = runner.invoke(cli, ["--help"], auto_envvar_prefix="WEATHER").output
        assert "[env var: WEATHER_UNITS]" in out

    @pytest.mark.parametrize("envvar", [[], ""])
    def test_empty_envvar_error_has_no_env_hint(self, runner: CliRunner, envvar: object) -> None:
        @click.command()
        @click.option("--units", required=True, envvar=envvar, show_envvar=True)
        def cli(units: str) -> None:
            pass

        out = runner.invoke(cli, []).output
        assert "env var" not in out


class TestHelpHint:
    def test_hint_does_not_name_a_shadowed_help_option(self, runner: CliRunner) -> None:
        @click.command(context_settings={"help_option_names": ["-h", "--help"]})
        @click.option("-h", "--height", type=int)
        @click.argument("name")
        def cli(height: int | None, name: str) -> None:
            pass

        result = runner.invoke(cli, [])
        assert result.exit_code == 2
        assert "Try 'cli --help' for help." in result.output
        assert runner.invoke(cli, ["--help"]).exit_code == 0

    def test_hint_in_a_group_names_the_subcommands_help(self, runner: CliRunner) -> None:
        @click.group(context_settings={"help_option_names": ["-h", "--help"]})
        def cli() -> None:
            pass

        @cli.command()
        @click.option("-h", "--host")
        @click.argument("port", type=int)
        def serve(host: str | None, port: int) -> None:
            pass

        result = runner.invoke(cli, ["serve"])
        assert "Try 'cli serve --help' for help." in result.output

    def test_hint_unchanged_without_shadowing(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("name")
        def cli(name: str) -> None:
            pass

        assert "Try 'cli --help' for help." in runner.invoke(cli, []).output


# ---------------------------------------------------------------------------
# (2) Where a value comes from
# ---------------------------------------------------------------------------


class TestDefaultMapLikeEnvvar:
    def test_nargs_option_from_default_map_string(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--point", nargs=2, type=int)
        def cli(point: tuple[int, int] | None) -> None:
            click.echo(repr(point))

        result = runner.invoke(cli, [], default_map={"point": "3 4"})
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "(3, 4)"

    def test_same_as_from_envvar(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--point", nargs=2, type=int, envvar="POINT")
        def cli(point: tuple[int, int] | None) -> None:
            click.echo(repr(point))

        from_env = runner.invoke(cli, [], env={"POINT": "5 6"}).output
        from_map = runner.invoke(cli, [], default_map={"point": "5 6"}, env={"POINT": None}).output
        assert from_env == from_map == "(5, 6)\n"

    def test_tuple_type_from_default_map_string(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--size", type=(int, str))
        def cli(size: tuple[int, str] | None) -> None:
            click.echo(repr(size))

        result = runner.invoke(cli, [], default_map={"size": "2 m"})
        assert result.output.strip() == "(2, 'm')"

    def test_nargs_argument_from_default_map_string(self, runner: CliRunner) -> None:
        @click.command()
        @click.argument("xy", nargs=2, type=float, required=False)
        def cli(xy: tuple[float, float] | None) -> None:
            click.echo(repr(xy))

        result = runner.invoke(cli, [], default_map={"xy": "1.5 2"})
        assert result.output.strip() == "(1.5, 2.0)"

    def test_structured_default_map_value_is_used_as_is(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--point", nargs=2, type=int)
        def cli(point: tuple[int, int] | None) -> None:
            click.echo(repr(point))

        assert runner.invoke(cli, [], default_map={"point": (7, 8)}).output == "(7, 8)\n"

    def test_single_value_string_not_split(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--name")
        def cli(name: str | None) -> None:
            click.echo(repr(name))

        assert runner.invoke(cli, [], default_map={"name": "a b"}).output == "'a b'\n"


class TestParameterSourceWhileProcessing:
    def test_eager_callback_sees_the_source(self, runner: CliRunner) -> None:
        def cb(ctx: click.Context, param: click.Parameter, value: object) -> object:
            click.echo(f"cb={ctx.get_parameter_source(param.name)!r}")
            return value

        @click.command()
        @click.option("--flag/--no-flag", default=False, is_eager=True, callback=cb, expose_value=False)
        def cli() -> None:
            pass

        assert "cb=<ParameterSource.DEFAULT" in runner.invoke(cli, []).output
        assert "cb=<ParameterSource.COMMANDLINE" in runner.invoke(cli, ["--flag"]).output

    def test_callback_sees_the_source(self, runner: CliRunner) -> None:
        def cb(ctx: click.Context, param: click.Parameter, value: object) -> object:
            click.echo(f"cb={ctx.get_parameter_source(param.name)!r}")
            return value

        @click.command()
        @click.option("--name", envvar="NAME", default="x", callback=cb)
        def cli(name: str) -> None:
            pass

        assert "ParameterSource.ENVIRONMENT" in runner.invoke(cli, [], env={"NAME": "y"}).output
        assert "ParameterSource.DEFAULT_MAP" in runner.invoke(cli, [], default_map={"name": "z"}, env={"NAME": None}).output

    def test_type_conversion_sees_the_source(self, runner: CliRunner) -> None:
        seen: list[object] = []

        class Recording(click.ParamType):
            name = "rec"

            def convert(self, value, param, ctx):  # type: ignore[no-untyped-def]
                seen.append(ctx.get_parameter_source(param.name))
                return value

        @click.command()
        @click.option("--value", type=Recording(), default="d")
        def cli(value: str) -> None:
            pass

        runner.invoke(cli, ["--value", "v"])
        runner.invoke(cli, [])
        assert seen == [ParameterSource.COMMANDLINE, ParameterSource.DEFAULT]

    def test_feature_switch_source_is_the_winner(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--upper", "case", flag_value="upper")
        @click.option("--lower", "case", flag_value="lower", default=True)
        def cli(case: str) -> None:
            ctx = click.get_current_context()
            click.echo(f"{case} {ctx.get_parameter_source('case')!r}")

        out = runner.invoke(cli, ["--upper"]).output
        assert out.startswith("upper <ParameterSource.COMMANDLINE")


# ---------------------------------------------------------------------------
# (3) Terminal output
# ---------------------------------------------------------------------------


class TestUnstyle:
    @pytest.mark.parametrize(
        ("text", "plain"),
        [
            ("\x1b[38:2:255:0:0mx y\x1b[0m", "x y"),
            ("\x1b[38:5:200mx y\x1b[0m", "x y"),
            ("\x1b[<0;1;1Mx y\x1b[<0;1;1m", "x y"),
            ("\x1b[0 qx y", "x y"),
            ("x\x1b[3~y", "xy"),
            ("\x1b[?25lx\x1b[?25h", "x"),
        ],
    )
    def test_every_csi_sequence_is_removed(self, text: str, plain: str) -> None:
        assert click.unstyle(text) == plain

    def test_echo_without_color_removes_them(self, runner: CliRunner) -> None:
        @click.command()
        def cli() -> None:
            click.echo("\x1b[38:2:1:2:3mred\x1b[0m and \x1b[0 qblock")

        assert runner.invoke(cli, [], color=False).output == "red and block\n"

    def test_existing_sgr_still_removed(self) -> None:
        assert click.unstyle(click.style("hi", fg="red", bold=True)) == "hi"


class TestPromptStyling:
    def test_prompt_strips_styles_when_color_is_off(self, runner: CliRunner) -> None:
        @click.command()
        def cli() -> None:
            name = click.prompt(click.style("Name", fg="green"))
            click.echo(f"hi {name}")

        out = runner.invoke(cli, [], input="Ann\n", color=False).output
        assert "\x1b" not in out
        assert "Name: Ann" in out

    def test_confirm_strips_styles_when_color_is_off(self, runner: CliRunner) -> None:
        @click.command()
        def cli() -> None:
            click.confirm(click.style("Sure?", bold=True))

        out = runner.invoke(cli, [], input="y\n", color=False).output
        assert "\x1b" not in out
        assert "Sure? [y/N]" in out

    def test_option_prompt_strips_styles(self, runner: CliRunner) -> None:
        @click.command()
        @click.option("--name", prompt=click.style("Your name", fg="blue"))
        def cli(name: str) -> None:
            pass

        out = runner.invoke(cli, [], input="Bo\n", color=False).output
        assert "\x1b" not in out

    def test_prompt_keeps_styles_when_color_is_on(self, runner: CliRunner) -> None:
        @click.command()
        def cli() -> None:
            click.prompt(click.style("Name", fg="green"))

        out = runner.invoke(cli, [], input="Ann\n", color=True).output
        assert "\x1b[32m" in out


class TestProgressBarFinalPosition:
    @pytest.fixture(autouse=True)
    def _tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(click._termui_impl, "isatty", lambda _: True)

    @pytest.mark.parametrize("length", [7, 20, 25])
    def test_iterating_ends_at_length(self, length: int) -> None:
        stream = io.StringIO()
        with click.progressbar(range(length), update_min_steps=3, file=stream) as bar:
            for _ in bar:
                pass
        assert bar.pos == length

    @pytest.mark.parametrize("length", [7, 20])
    def test_updating_ends_at_length(self, length: int) -> None:
        stream = io.StringIO()
        with click.progressbar(length=length, update_min_steps=3, file=stream) as bar:
            for _ in range(length):
                bar.update(1)
        assert bar.pos == length

    def test_finished_bar_shows_final_position(self) -> None:
        stream = io.StringIO()
        with click.progressbar(range(20), update_min_steps=7, show_pos=True, file=stream) as bar:
            for _ in bar:
                pass
        assert "20/20" in stream.getvalue()

    def test_dividing_threshold_unchanged(self) -> None:
        stream = io.StringIO()
        with click.progressbar(range(20), update_min_steps=5, show_pos=True, file=stream) as bar:
            for _ in bar:
                pass
        assert bar.pos == 20 and "20/20" in stream.getvalue()


# ---------------------------------------------------------------------------
# (4) Same output every run; completion offers what is accepted
# ---------------------------------------------------------------------------


HELP_ORDER_SCRIPT = textwrap.dedent(
    """
    import click

    @click.command(context_settings={"help_option_names": ["-h", "--help", "-?"]})
    def cli():
        pass

    ctx = click.Context(cli, help_option_names=["-h", "--help", "-?"])
    print(cli.get_help_option_names(ctx))
    """
)


class TestHelpOptionOrder:
    def test_names_are_all_kept(self) -> None:
        cli = click.Command("cli")
        ctx = click.Context(cli, help_option_names=["-h", "--help", "-?"])
        assert sorted(cli.get_help_option_names(ctx)) == ["--help", "-?", "-h"]

    def test_order_does_not_depend_on_the_hash_seed(self) -> None:
        # Any fixed order is accepted; it must not change from run to run.
        outputs = set()
        for seed in range(12):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            out = subprocess.run(
                [sys.executable, "-c", HELP_ORDER_SCRIPT],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            outputs.add(out)
        assert len(outputs) == 1

    def test_shadowed_name_is_dropped(self) -> None:
        cli = click.Command("cli", params=[click.Option(["-h", "--height"])])
        ctx = click.Context(cli, help_option_names=["-h", "--help"])
        assert cli.get_help_option_names(ctx) == ["--help"]


class Color(enum.Enum):
    RED = "r"
    GREEN = "g"


class TestEnumChoiceCompletion:
    def test_enum_choice_completes_to_accepted_names(self, runner: CliRunner) -> None:
        cli = click.Command("cli", params=[click.Option(["--color"], type=click.Choice(Color))])
        offered = completions(cli, ["--color"], "")
        assert offered == ["RED", "GREEN"]

        @click.command()
        @click.option("--color", type=click.Choice(Color))
        def run(color: Color) -> None:
            click.echo(color.name)

        for value in offered:
            assert runner.invoke(run, ["--color", value]).output == f"{value}\n"

    def test_enum_choice_completion_filters_by_prefix(self) -> None:
        cli = click.Command("cli", params=[click.Option(["--color"], type=click.Choice(Color))])
        assert completions(cli, ["--color"], "G") == ["GREEN"]

    def test_string_choices_unchanged(self) -> None:
        cli = click.Command("cli", params=[click.Option(["-a"], type=click.Choice(["Au", "al", "Bc"]))])
        assert completions(cli, ["-a"], "a") == ["al"]


# ---------------------------------------------------------------------------
# (5) Strict interpreter flags
# ---------------------------------------------------------------------------


BYTES_SCRIPT = textwrap.dedent(
    """
    import click
    from click.testing import CliRunner

    @click.command()
    @click.argument("src", type=click.Path(allow_dash=True))
    @click.option("--out", type=click.Path(allow_dash=True, path_type=bytes), default="-")
    def cli(src, out):
        click.echo(f"{src!r} {out!r}")

    result = CliRunner().invoke(cli, ["-"], catch_exceptions=False)
    print(result.output, end="")
    result = CliRunner().invoke(cli, ["data.txt", "--out", "x.bin"], catch_exceptions=False)
    print(result.output, end="")
    """
)


class TestStrictFlags:
    def test_path_with_dash_under_bb(self, tmp_path) -> None:
        proc = subprocess.run(
            [sys.executable, "-bb", "-c", BYTES_SCRIPT],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == "'-' b'-'\n'data.txt' b'x.bin'\n"
