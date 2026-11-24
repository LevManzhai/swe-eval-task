# markdown-it-py: Markdown that isn't rendered per CommonMark, or not in linear time

The repository in `/workspace/repo` is
[markdown-it-py](https://github.com/executablebooks/markdown-it-py), the
Python port of the markdown-it parser used by Jupyter, MyST, mdformat and
many documentation tools. Its `commonmark` preset targets CommonMark 0.31.2;
everything else follows markdown-it (the JavaScript library) version 15.

## What a user reported

> ```python
> >>> MarkdownIt("commonmark").render("para\n<!doctype html>\n")
> '<p>para\n<!doctype html></p>\n'
> ```
>
> `<!DOCTYPE html>` in the same place ends the paragraph and is passed through
> as an HTML block, as CommonMark says. The lowercase spelling, which HTML5
> tools write, ends up inside the paragraph.

## What we want

Fix that, and treat it as one example of a wider problem: markdown-it-py
handles some rare but valid input differently from CommonMark 0.31.2 or
markdown-it 15, or slowly enough to be a denial-of-service risk. We want the
following to hold:

1. **Block structure follows CommonMark 0.31.2.** Every start and end
   condition of every kind of HTML block applies as the spec writes it,
   including its notion of ASCII case-insensitivity, and inside list items
   and block quotes as well as at the top level. A task-list marker
   (`gfm-like2` preset) is a marker only where it starts a list item's
   paragraph. No input, however it ends and whichever rules are enabled,
   raises an exception.
2. **Inline structure and rendering follow CommonMark 0.31.2.** Code spans,
   link and image labels, and the text an image's `alt` attribute gets, are
   as the spec says, character for character (the spec is precise about
   which characters count as spaces). Link and image destinations are
   normalized as markdown-it 15 does, without breaking any valid URL.
3. **Rendering takes linear time.** No input makes parsing or rendering
   take more than linear time in its length, whatever runs of characters it
   contains and whichever preset and options are used.
4. **The API does what it documents for every argument it accepts.**
   `MarkdownIt.enable()` and `disable()` take a rule name or any iterable of
   rule names, and apply them to every rule chain.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is. It doesn't cover these cases.
- Your changes are graded by hidden tests that use the public API
  (`MarkdownIt` with its presets, `render`, `renderInline`, `enable`,
  `disable`, `get_active_rules`). Timing tests render large inputs in a
  separate process with a time limit generous enough for any linear
  implementation.
