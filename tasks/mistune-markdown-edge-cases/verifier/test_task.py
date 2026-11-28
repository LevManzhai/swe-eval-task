"""Hidden tests for the mistune edge-cases task.

Only the public API is used: ``mistune.create_markdown`` with plugins, the
HTML renderer, ``RSTRenderer`` and ``MarkdownRenderer``.

- HTML and RST cases compare with the expected output exactly.
- Markdown renderer cases are round trips: the Markdown that
  ``MarkdownRenderer`` writes for a document must parse back to the same
  HTML as the document itself. Any output with that property is accepted.
"""

from __future__ import annotations

import json

import pytest

import mistune
from mistune.renderers.markdown import MarkdownRenderer
from mistune.renderers.rst import RSTRenderer

CASES = json.loads(r'''
{
"html": [
[
"empty_list_item",
[],
"-\nfoo\n",
"<ul>\n<li></li>\n</ul>\n<p>foo</p>\n"
],
[
"empty_list_item",
[],
"- a\n-\nb\n",
"<ul>\n<li>a</li>\n<li></li>\n</ul>\n<p>b</p>\n"
],
[
"empty_list_item",
[],
"> 1.\n> foo\n",
"<blockquote>\n<ol>\n<li></li>\n</ol>\n<p>foo</p>\n</blockquote>\n"
],
[
"empty_list_item",
[],
"*\nbar\n",
"<ul>\n<li></li>\n</ul>\n<p>bar</p>\n"
],
[
"empty_list_item",
[],
"- a\n\n-\n  b\n",
"<ul>\n<li><p>a</p>\n</li>\n<li><p>b</p>\n</li>\n</ul>\n"
],
[
"ordered_marker",
[],
"1. a\n. b\n",
"<ol>\n<li>a\n. b</li>\n</ol>\n"
],
[
"ordered_marker",
[],
"1) a\n) b\n",
"<ol>\n<li>a\n) b</li>\n</ol>\n"
],
[
"ordered_marker",
[],
"1. a\n123456789. b\n",
"<ol>\n<li>a</li>\n<li>b</li>\n</ol>\n"
],
[
"ordered_marker",
[],
"3. a\n4. b\n. c\n",
"<ol start=\"3\">\n<li>a</li>\n<li>b\n. c</li>\n</ol>\n"
],
[
"def_list",
[
"def_list"
],
"Term\n:\tTab-marked def\n",
"<dl>\n<dt>Term</dt>\n<dd>Tab-marked def</dd>\n</dl>\n"
],
[
"def_list",
[
"def_list"
],
"Term\n    : definition\n",
"<p>Term\n: definition</p>\n"
],
[
"table",
[
"table"
],
"Name | Age\nJohn | 30\nJane | 25\n",
"<p>Name | Age\nJohn | 30\nJane | 25</p>\n"
],
[
"table",
[
"table"
],
"a | b\nfoo | bar\n1 | 2\n",
"<p>a | b\nfoo | bar\n1 | 2</p>\n"
],
[
"table",
[
"table"
],
"| a | b |\n| x | - |\n| 1 | 2 |\n",
"<p>| a | b |\n| x | - |\n| 1 | 2 |</p>\n"
],
[
"table",
[
"table"
],
"| a | b |\n| :- | -: |\n| 1 | 2 |\n",
"<table>\n<thead>\n<tr>\n  <th style=\"text-align:left\">a</th>\n  <th style=\"text-align:right\">b</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n  <td style=\"text-align:left\">1</td>\n  <td style=\"text-align:right\">2</td>\n</tr>\n</tbody>\n</table>\n"
],
[
"task_lists",
[
"task_lists"
],
"- # [ ] unchecked heading\n- ## [x] checked heading\n",
"<ul>\n<li><h1>[ ] unchecked heading</h1>\n</li>\n<li><h2>[x] checked heading</h2>\n</li>\n</ul>\n"
],
[
"task_lists",
[
"task_lists"
],
"- [x] setext heading\n  ==================\n- [ ] setext heading\n  ------------------\n",
"<ul>\n<li><h1>[x] setext heading</h1>\n</li>\n<li><h2>[ ] setext heading</h2>\n</li>\n</ul>\n"
],
[
"task_lists",
[
"task_lists"
],
"- [ ] foo\n- [x] bar\n",
"<ul>\n<li class=\"task-list-item\"><input class=\"task-list-item-checkbox\" type=\"checkbox\" disabled/>foo</li>\n<li class=\"task-list-item\"><input class=\"task-list-item-checkbox\" type=\"checkbox\" disabled checked/>bar</li>\n</ul>\n"
],
[
"task_lists",
[
"task_lists"
],
"-     [x] code\n",
"<ul>\n<li><pre><code>[x] code</code></pre>\n</li>\n</ul>\n"
],
[
"footnotes",
[
"footnotes"
],
"Text[^one].\n\n[^one]: See [link][ref].\n\n    [ref]: /url\n\n    Final paragraph.\n",
"<p>Text<sup class=\"footnote-ref\" id=\"fnref-1\"><a href=\"#fn-1\">1</a></sup>.</p>\n<section class=\"footnotes\">\n<ol>\n<li id=\"fn-1\"><p>See <a href=\"/url\">link</a>.</p>\n<p>Final paragraph.<a href=\"#fnref-1\" class=\"footnote\">&#8617;</a></p></li>\n</ol>\n</section>\n"
],
[
"footnotes",
[
"footnotes"
],
"Text[^one].\n\n[^one]: See [link][ref].\n\n    [ref]: /url\n",
"<p>Text<sup class=\"footnote-ref\" id=\"fnref-1\"><a href=\"#fn-1\">1</a></sup>.</p>\n<section class=\"footnotes\">\n<ol>\n<li id=\"fn-1\"><p>See <a href=\"/url\">link</a>.<a href=\"#fnref-1\" class=\"footnote\">&#8617;</a></p></li>\n</ol>\n</section>\n"
],
[
"footnotes",
[
"footnotes"
],
"Text[^one].\n\n[ref]: /original\n\n[^one]: See [link][ref].\n\n    [ref]: /replacement\n",
"<p>Text<sup class=\"footnote-ref\" id=\"fnref-1\"><a href=\"#fn-1\">1</a></sup>.</p>\n<section class=\"footnotes\">\n<ol>\n<li id=\"fn-1\"><p>See <a href=\"/original\">link</a>.<a href=\"#fnref-1\" class=\"footnote\">&#8617;</a></p></li>\n</ol>\n</section>\n"
],
[
"abbr",
[
"abbr"
],
"HTML5 and HTML\n*[HTML]: Hyper Text Markup Language\n*[HTML5]: Hyper Text Markup Language 5\n",
"<p><abbr title=\"Hyper Text Markup Language 5\">HTML5</abbr> and <abbr title=\"Hyper Text Markup Language\">HTML</abbr></p>\n"
],
[
"abbr",
[
"abbr"
],
"New York City and New York\n*[New York]: State\n*[New York City]: City\n",
"<p><abbr title=\"City\">New York City</abbr> and <abbr title=\"State\">New York</abbr></p>\n"
],
[
"abbr",
[
"abbr"
],
"HTML5 and HTML\n*[HTML5]: Hyper Text Markup Language 5\n*[HTML]: Hyper Text Markup Language\n",
"<p><abbr title=\"Hyper Text Markup Language 5\">HTML5</abbr> and <abbr title=\"Hyper Text Markup Language\">HTML</abbr></p>\n"
]
],
"rst": [
[
"rst_hard_break",
"- first  \n  second\n",
"- | first\n  | second\n"
],
[
"rst_hard_break",
"1. first\\\n   second\n",
"1. | first\n   | second\n"
],
[
"rst_hard_break",
"- a\n- b  \n  c\n",
"- a\n- | b\n  | c\n"
],
[
"rst_separator",
"- before\u0085after\n",
"- before\u0085after\n"
],
[
"rst_separator",
"1. before\u001eafter\n",
"1. before\u001eafter\n"
],
[
"rst_separator",
"- `before\u001cafter`\n",
"- ``before\u001cafter``\n"
]
],
"round": [
[
"empty_destination",
[],
"[a]\n\n[a]: <>\n"
],
[
"empty_destination",
[],
"[a][b]\n\n[b]: <> \"t\"\n"
],
[
"title_quotes",
[],
"[x](/u \"a \\\"q\\\" b\")\n"
],
[
"title_quotes",
[],
"![x](/u 'say \"hi\"')\n"
],
[
"title_quotes",
[],
"[x]\n\n[x]: /u 'a \"b\" c'\n"
],
[
"title_quotes",
[],
"[x](/u \"back\\\\slash\")\n"
],
[
"formatting_plugins",
[
"strikethrough",
"mark",
"insert"
],
"~~gone~~ ==hl== ^^ins^^\n"
],
[
"formatting_plugins",
[
"strikethrough"
],
"a ~~b *c* d~~ e\n"
],
[
"image_alt_url",
[],
"![https://example.com](https://example.com)\n"
],
[
"image_alt_url",
[],
"![user@example.com](mailto:user@example.com)\n"
],
[
"image_alt_url",
[],
"[![https://example.com](https://example.com)](/target)\n"
],
[
"codespan_spaces",
[],
"`  x  `\n"
],
[
"codespan_spaces",
[],
"``  a ` b  ``\n"
],
[
"codespan_spaces",
[],
"`   x   `\n"
],
[
"codespan_spaces",
[],
"a ` b ` c\n"
],
[
"setext_multiline",
[],
"line one\nline two\n===\n"
],
[
"setext_multiline",
[],
"a\nb\nc\n---\n"
],
[
"trailing_hashes",
[],
"# C#\n"
],
[
"trailing_hashes",
[],
"## Issue \\#\n"
],
[
"trailing_hashes",
[],
"Heading ##\n===\n"
],
[
"blockquote_gt",
[],
"> <https://example.com>\n"
],
[
"blockquote_gt",
[],
"> a <b>\n"
],
[
"blockquote_gt",
[],
"> x\n>\n> <y@z.com>\n"
],
[
"table_pipes",
[
"table"
],
"| `a\\|b` |\n| --- |\n| Body |\n"
],
[
"table_pipes",
[
"table"
],
"| Header |\n| --- |\n| `a\\|b\\|c` |\n"
],
[
"table_pipes",
[
"table"
],
"| `a\\\\\\|b` |\n| --- |\n| Body |\n"
],
[
"list_separators",
[],
"- before\u0085after\n"
],
[
"list_separators",
[],
"1. before\u001eafter\n"
],
[
"list_separators",
[],
"- item\n\n  ```\n  a\u001cb\n  ```\n"
],
[
"list_separators",
[],
"- first\n\n- x\u001dy\n"
]
]
}
''')


def _id(case: list) -> str:
    src = case[2] if len(case) > 3 or case[0] in {c[0] for c in CASES["round"]} else case[1]
    return f"{case[0]}:{src[:40]!r}"


@pytest.mark.parametrize("case", CASES["html"], ids=lambda c: f"{c[0]}:{c[2][:40]!r}")
def test_html(case: list) -> None:
    group, plugins, src, expected = case
    assert mistune.create_markdown(plugins=plugins)(src) == expected


@pytest.mark.parametrize("case", CASES["rst"], ids=lambda c: f"{c[0]}:{c[1][:40]!r}")
def test_rst(case: list) -> None:
    group, src, expected = case
    assert mistune.create_markdown(renderer=RSTRenderer())(src) == expected


@pytest.mark.parametrize("case", CASES["round"], ids=lambda c: f"{c[0]}:{c[2][:40]!r}")
def test_markdown_round_trip(case: list) -> None:
    group, plugins, src = case
    to_html = mistune.create_markdown(plugins=plugins)
    to_markdown = mistune.create_markdown(renderer=MarkdownRenderer(), plugins=plugins)
    rendered = to_markdown(src)
    assert to_html(rendered) == to_html(src), rendered


@pytest.mark.parametrize("case", CASES["round"], ids=lambda c: f"{c[0]}:{c[2][:40]!r}")
def test_markdown_round_trip_is_stable(case: list) -> None:
    group, plugins, src = case
    to_markdown = mistune.create_markdown(renderer=MarkdownRenderer(), plugins=plugins)
    once = to_markdown(src)
    to_html = mistune.create_markdown(plugins=plugins)
    assert to_html(to_markdown(once)) == to_html(src)


# ---------------------------------------------------------------------------
# Fenced directives inside list items
# ---------------------------------------------------------------------------


def _directive_md():
    from mistune.directives import Admonition, FencedDirective

    return mistune.create_markdown(escape=False, plugins=[FencedDirective([Admonition()], markers=":")])


@pytest.mark.parametrize("src", ["- item\n:{note}\nlazy\n", "- item\n::{note}\nlazy\n", "1. item\n:{note}\nlazy\n"])
def test_short_marker_run_in_a_list_is_not_a_directive(src: str) -> None:
    html = _directive_md()(src)
    assert "admonition" not in html
    assert "{note}" in html


@pytest.mark.parametrize("src", [":{note}\nlazy\n", "100. item\n:{note}\nlazy\n"])
def test_short_marker_run_outside_a_list_unchanged(src: str) -> None:
    assert "admonition" not in _directive_md()(src)


def test_directive_still_breaks_a_list() -> None:
    html = _directive_md()("- item\n:::{note}\nbody\n:::\n")
    assert '<section class="admonition note">' in html
    assert "<p>body</p>" in html
