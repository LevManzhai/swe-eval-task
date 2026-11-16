# Editing a `pyproject.toml` with tomlkit scrambles or breaks it

We use tomlkit to read and update `pyproject.toml` files and other config
files without losing their formatting. That works fine for most files. It
breaks for files where one table is written in several separate places, which
TOML allows: a sub-table such as `[tool.poetry]` here and `[tool.other]` further
down, with something else in between.

This file is a typical example:

```toml
[tool.poetry]
name = "foo"

[[plugins]]
name = "bar"

[tool.other]
a = "b"
```

We don't change anything, we only parse it and write it back:

```python
import tomlkit

text = open("pyproject.toml").read()
doc = tomlkit.parse(text)
assert doc.as_string() == text   # fails
```

The output has the same data, but the sections come out in a different order
than in the input, so our tool produces a diff on files it was not supposed to
touch.

That's the one we hit in production. Since then we've been running into other
odd behaviour on files like this, such as exceptions raised during parsing or
editing, and files that aren't valid TOML any more after an edit. We haven't
narrowed those down, so we'd rather not guess. We are fairly sure there is more
than one defect, all in the handling of tables that are split into several
parts in the document.

## What we expect

For any TOML document, and in particular for documents in which a table is
defined in several non-contiguous parts:

1. If Python's standard library parser (`tomllib`) accepts the document,
   `tomlkit.parse()` accepts it too, and `doc.unwrap()` equals
   `tomllib.loads(text)`.
2. If `tomllib` rejects the document, tomlkit rejects it as well (a
   `tomlkit.exceptions.TOMLKitError`, either while parsing or at the latest
   when the data is accessed).
3. If the document is not modified, `doc.as_string()` returns the input
   unchanged, byte for byte.
4. After the document has been modified through its dict-like interface
   (setting, replacing or deleting keys, `pop()`, `update()`, at any level,
   including through the object you get back from `doc["some_table"]` when
   that table is split), no exception is raised, the document holds exactly
   the data that was written, and `doc.as_string()` is valid TOML that
   `tomllib` parses to that same data.

Where the existing test suite already pins down a specific behaviour that
conflicts with the list above, keep the tested behaviour.

Please fix the library so that these hold. We don't mind how the code is
organised internally.

## Constraints

- No new dependencies.
- The existing test suite must keep passing: `python -m pytest tests` from the
  root of the repository.
