# mistune: rare Markdown parsed or re-rendered wrongly

The repository in `/workspace/repo` is [mistune](https://github.com/lepture/mistune),
a fast Markdown parser with pluggable renderers: HTML, reStructuredText
(`RSTRenderer`) and Markdown itself (`MarkdownRenderer`, used to reformat or
normalize Markdown documents).

## What a user reported

> ```python
> >>> import mistune
> >>> print(mistune.html("-\nfoo\n"))
> <ul>
> <li>foo</li>
> </ul>
> ```
>
> CommonMark says an empty list item can't take a lazy continuation line, so
> `foo` is a paragraph after the list (`<ul><li></li></ul><p>foo</p>`), and
> that's what every other CommonMark implementation we tried gives.

## What we want

Fix that, and treat it as one example of a wider problem: mistune handles
some rare but valid Markdown differently from CommonMark, from the syntax
its plugins document, or from what its renderers promise. We want the
following to hold:

1. **Block structure follows CommonMark**, and plugin blocks follow their
   documented syntax: lists and list items (including empty ones and
   ordered list markers), definition lists, tables, task lists, footnotes,
   abbreviations and fenced directives, also when one is nested in another.
2. **`MarkdownRenderer` round-trips.** For any document, the Markdown it
   writes parses back to the same document: rendering both to HTML gives
   the same result. That includes every inline element and every plugin
   with a Markdown syntax, link and image titles and destinations, code
   spans, headings, block quotes, tables and lists, whatever characters
   they contain.
3. **`RSTRenderer` writes valid reStructuredText for every document**,
   preserving line breaks and content inside list items.
4. **Markdown line endings are LF.** Other Unicode characters that Python
   treats as line breaks (`\x1c`–`\x1e`, `\x85`, ...) are content, and every
   renderer keeps them as such.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is. It doesn't cover these cases.
- Your changes are graded by hidden tests that use the public API:
  `mistune.create_markdown` with plugins and the HTML, RST and Markdown
  renderers.
