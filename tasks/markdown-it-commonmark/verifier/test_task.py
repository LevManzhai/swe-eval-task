"""Hidden tests for the markdown-it-py CommonMark edge-cases task.

Only the public API is used: ``MarkdownIt`` with its presets, ``render``,
``enable``/``disable`` and ``get_active_rules``. Rendering cases give the
input and the expected HTML (CommonMark 0.31.2, and markdown-it 15's
behaviour where CommonMark leaves a choice, as for task lists and URL
normalization). Timing cases run in a child process with a hard timeout.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from markdown_it import MarkdownIt

CASES = json.loads(r'''
[
[
"html_block_start",
"commonmark",
{},
"foo\n<!bar baz>\n",
"<p>foo</p>\n<!bar baz>\n"
],
[
"html_block_start",
"commonmark",
{},
"para\n<!doctype html>\n\npara\n<!DOCTYPE html>\n",
"<p>para</p>\n<!doctype html>\n<p>para</p>\n<!DOCTYPE html>\n"
],
[
"html_block_start",
"commonmark",
{},
"<!doctype html>\n<p>x</p>\n",
"<!doctype html>\n<p>x</p>\n"
],
[
"html_block_start",
"commonmark",
{},
"para\n<\u017fcript>\ntext\n",
"<p>para\n&lt;\u017fcript&gt;\ntext</p>\n"
],
[
"html_block_start",
"commonmark",
{},
"para\n<d\u0130v>\ntext\n",
"<p>para\n&lt;d\u0130v&gt;\ntext</p>\n"
],
[
"html_block_start",
"commonmark",
{},
"para\n<d\u0131v>\ntext\n",
"<p>para\n&lt;d\u0131v&gt;\ntext</p>\n"
],
[
"html_block_start",
"commonmark",
{},
"<script>\nx\n</\u017fcript>\ny\n</script>\nz\n",
"<script>\nx\n</\u017fcript>\ny\n</script>\n<p>z</p>\n"
],
[
"html_block_start",
"commonmark",
{},
"<DIV>\nx\n</DIV>\n",
"<DIV>\nx\n</DIV>\n"
],
[
"html_block_container",
"commonmark",
{},
"1. item\n\n    <!--\n    a\n\n    b\n    -->\n    c\n",
"<ol>\n<li>\n<p>item</p>\n <!--\n a\n\n b\n -->\n<p>c</p>\n</li>\n</ol>\n"
],
[
"html_block_container",
"commonmark",
{},
"> <!--\n> a\n>\n> b\n> -->\n> c\n",
"<blockquote>\n<!--\na\n\nb\n-->\n<p>c</p>\n</blockquote>\n"
],
[
"html_block_container",
"commonmark",
{},
"> <script>\n> a\n>\n> b\n> </script>\n> c\n",
"<blockquote>\n<script>\na\n\nb\n</script>\n<p>c</p>\n</blockquote>\n"
],
[
"html_block_container",
"commonmark",
{},
"- <?php\n\n  echo 1;\n  ?>\n  after\n",
"<ul>\n<li>\n<?php\n\necho 1;\n?>\nafter</li>\n</ul>\n"
],
[
"html_block_container",
"commonmark",
{},
"> <![CDATA[\n> x\n>\n> ]]>\n> y\n",
"<blockquote>\n<![CDATA[\nx\n\n]]>\n<p>y</p>\n</blockquote>\n"
],
[
"html_block_container",
"commonmark",
{},
"> <div>\n> a\n>\n> b\n",
"<blockquote>\n<div>\na\n<p>b</p>\n</blockquote>\n"
],
[
"code_span",
"commonmark",
{},
"[foo `bar` baz`\n",
"<p>[foo <code>bar</code> baz`</p>\n"
],
[
"code_span",
"commonmark",
{},
"![alt `code` x`\n",
"<p>![alt <code>code</code> x`</p>\n"
],
[
"code_span",
"commonmark",
{},
"[`](``)\n",
"<p><a href=\"%60%60\">`</a></p>\n"
],
[
"code_span",
"commonmark",
{},
"[`a](/x)``b\n",
"<p><a href=\"/x\">`a</a>``b</p>\n"
],
[
"code_span",
"commonmark",
{},
"[foo `bar](/url)` baz\n",
"<p>[foo <code>bar](/url)</code> baz</p>\n"
],
[
"code_span",
"commonmark",
{},
"`   `\n",
"<p><code>   </code></p>\n"
],
[
"code_span",
"commonmark",
{},
"` \t `\n",
"<p><code>\t</code></p>\n"
],
[
"code_span",
"commonmark",
{},
"` \u00a0 `\n",
"<p><code>\u00a0</code></p>\n"
],
[
"code_span",
"commonmark",
{},
"` a `\n",
"<p><code>a</code></p>\n"
],
[
"tasklist",
"gfm-like2",
{},
"-     [x] literal\n",
"<ul>\n<li>\n<pre><code>[x] literal\n</code></pre>\n</li>\n</ul>\n"
],
[
"tasklist",
"gfm-like2",
{},
"-      [ ] literal\n",
"<ul>\n<li>\n<pre><code> [ ] literal\n</code></pre>\n</li>\n</ul>\n"
],
[
"tasklist",
"gfm-like2",
{},
"1.     [X] literal\n",
"<ol>\n<li>\n<pre><code>[X] literal\n</code></pre>\n</li>\n</ol>\n"
],
[
"tasklist",
"gfm-like2",
{},
"-\t\t[x] literal\n",
"<ul>\n<li>\n<pre><code>  [x] literal\n</code></pre>\n</li>\n</ul>\n"
],
[
"tasklist",
"gfm-like2",
{},
"- [x] done\n- [ ] todo\n",
"<ul class=\"contains-task-list\">\n<li class=\"task-list-item\"><input class=\"task-list-item-checkbox\" disabled=\"\" type=\"checkbox\" checked=\"\"> done</li>\n<li class=\"task-list-item\"><input class=\"task-list-item-checkbox\" disabled=\"\" type=\"checkbox\"> todo</li>\n</ul>\n"
],
[
"normalize",
"commonmark",
{},
"[foo](https://user:pass@[2001:db8::1]:8443/a[b]?q=[c]#[d])\n",
"<p><a href=\"https://user:pass@[2001:db8::1]:8443/a%5Bb%5D?q=%5Bc%5D#%5Bd%5D\">foo</a></p>\n"
],
[
"normalize",
"commonmark",
{},
"[foo](//[::ffff:192.0.2.1]/)\n",
"<p><a href=\"//[::ffff:192.0.2.1]/\">foo</a></p>\n"
],
[
"normalize",
"commonmark",
{},
"<http://[::1]:8000/>\n",
"<p><a href=\"http://[::1]:8000/\">http://[::1]:8000/</a></p>\n"
],
[
"normalize",
"commonmark",
{},
"![foo](https://[::1]/a.png)\n",
"<p><img src=\"https://[::1]/a.png\" alt=\"foo\" /></p>\n"
],
[
"normalize",
"commonmark",
{},
"[foo](http://user:password@[2001:db8:0:0:0:0:0:1]:1926/)\n",
"<p><a href=\"http://user:password@[2001:db8:0:0:0:0:0:1]:1926/\">foo</a></p>\n"
],
[
"normalize",
"commonmark",
{},
"[foo](http://example.com/a[b])\n",
"<p><a href=\"http://example.com/a%5Bb%5D\">foo</a></p>\n"
],
[
"alt_text",
"commonmark",
{},
"![foo\\\nbar](/url)\n",
"<p><img src=\"/url\" alt=\"foo\nbar\" /></p>\n"
],
[
"alt_text",
"commonmark",
{},
"![a<b>c](/url)\n",
"<p><img src=\"/url\" alt=\"a&lt;b&gt;c\" /></p>\n"
],
[
"alt_text",
"commonmark",
{},
"![foo  \nbar](/url)\n",
"<p><img src=\"/url\" alt=\"foo\nbar\" /></p>\n"
],
[
"alt_text",
"commonmark",
{},
"![foo\nbar](/url)\n",
"<p><img src=\"/url\" alt=\"foo\nbar\" /></p>\n"
]
]
''')


def _id(case: list) -> str:
    return f"{case[0]}:{case[3][:40]!r}"


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_render(case: list) -> None:
    group, preset, options, src, expected = case
    md = MarkdownIt(preset, options) if options else MarkdownIt(preset)
    assert md.render(src) == expected


# ---------------------------------------------------------------------------
# enable() / disable() with any iterable of rule names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["enable", "disable"])
@pytest.mark.parametrize("wrap", [list, tuple, iter, lambda xs: (x for x in xs)], ids=["list", "tuple", "iter", "generator"])
def test_rule_names_apply_to_every_chain(method: str, wrap) -> None:
    md = MarkdownIt("zero" if method == "enable" else "commonmark")
    core_rule = "smartquotes" if method == "enable" else "normalize"
    assert getattr(md, method)(wrap([core_rule, "heading", "emphasis"])) is md
    active = md.get_active_rules()
    for chain, name in [("core", core_rule), ("block", "heading"), ("inline", "emphasis"), ("inline2", "emphasis")]:
        assert (name in active[chain]) is (method == "enable"), (chain, name)


@pytest.mark.parametrize("method", ["enable", "disable"])
@pytest.mark.parametrize("wrap", [list, lambda xs: (x for x in xs)], ids=["list", "generator"])
def test_unknown_rule_names_raise(method: str, wrap) -> None:
    with pytest.raises(ValueError):
        getattr(MarkdownIt(), method)(wrap(["missing-rule"]))


@pytest.mark.parametrize("method", ["enable", "disable"])
def test_unknown_rule_names_ignored_on_request(method: str) -> None:
    md = MarkdownIt("zero" if method == "enable" else "commonmark")
    getattr(md, method)((n for n in ["missing-rule", "heading"]), True)
    assert ("heading" in md.get_active_rules()["block"]) is (method == "enable")


# ---------------------------------------------------------------------------
# Input that ends early
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    ["> | a | b |\n> |---|---|\n>", "> | a | b |\n> |---|---|\n> ", "> | a |\n> |---|\n>\n>"],
)
@pytest.mark.parametrize("html", [True, False])
def test_table_in_blockquote_at_end_of_input(src: str, html: bool) -> None:
    md = MarkdownIt("commonmark", {"html": html}).enable("table")
    out = md.render(src)
    assert "<table>" in out and "<blockquote>" in out


# ---------------------------------------------------------------------------
# Linear time on hostile input
# ---------------------------------------------------------------------------


TIMING = textwrap.dedent(
    """
    import sys
    from markdown_it import MarkdownIt
    preset, html, src = sys.argv[1], sys.argv[2] == "1", sys.argv[3]
    md = MarkdownIt(preset, {"html": html}) if preset == "commonmark" else MarkdownIt(preset)
    md.render(eval(src))
    """
)


def _render_within(preset: str, html: bool, src_expr: str, seconds: float) -> None:
    try:
        subprocess.run(
            [sys.executable, "-c", TIMING, preset, "1" if html else "0", src_expr],
            check=True,
            timeout=seconds,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"rendering {src_expr} took more than {seconds}s")


@pytest.mark.parametrize(
    "src_expr",
    ['"x" + "<!--" * 30000', '"x" + "<?" * 40000', '"x" + "<![CDATA[" * 15000', '"x" + "<!a" * 60000'],
)
def test_unterminated_inline_html(src_expr: str) -> None:
    _render_within("commonmark", True, src_expr, 8)


@pytest.mark.parametrize(
    "preset,html,src_expr",
    [
        ("commonmark", False, '"&" * 1_200_000'),
        ("commonmark", False, '"&#" * 800_000'),
        ("commonmark", True, '"<a" * 800_000'),
        ("default", False, '"&" * 1_200_000'),
    ],
)
def test_runs_of_rule_start_characters(preset: str, html: bool, src_expr: str) -> None:
    _render_within(preset, html, src_expr, 15)


def test_hostile_input_still_renders_correctly() -> None:
    md = MarkdownIt("commonmark")
    assert md.renderInline("&" * 2000) == "&amp;" * 2000
    assert md.render("x" + "<!--" * 100) == "<p>x" + "&lt;!--" * 100 + "</p>\n"
    assert md.renderInline("&amp;" * 8) == "&amp;" * 8
    assert md.renderInline("&#35;" * 8) == "#" * 8
