# Editing TOML files with tomlkit scrambles or breaks them

We use tomlkit to read and update `pyproject.toml` files and other config
files without losing their formatting. That works fine for simple files. It
goes wrong for files with a bit more structure: a table written in several
separate places (which TOML allows), arrays of tables, dotted keys, inline
tables.

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

That's the one we hit in production. Since then we keep running into other odd
behaviour on files like this: exceptions raised during parsing or editing,
valid files rejected, and files that aren't valid TOML any more, or hold
different data, after an edit. We haven't narrowed those down, so we'd rather
not guess. We are fairly sure there is more than one defect, all in how
tomlkit handles the structure of a document: tables and sub-tables (in
particular tables split into several parts), arrays of tables, dotted keys and
inline tables.

## What we expect

"Valid TOML" and "the data a document holds" below mean what the
[TOML v1.0.0 specification](https://toml.io/en/v1.0.0) says.

1. If a document is valid TOML, `tomlkit.parse()` accepts it, and
   `doc.unwrap()` is the data the document holds.
2. If a document is not valid TOML because it defines a table or key twice, or
   extends one in a way the specification forbids, tomlkit rejects it (a
   `tomlkit.exceptions.TOMLKitError`, either while parsing or at the latest
   when the data is accessed).
3. If the document is not modified, `doc.as_string()` returns the input
   unchanged, byte for byte.
4. After the document has been modified, no exception is raised, the document
   holds exactly the data that was written, and `doc.as_string()` is valid
   TOML that holds that same data. "Modified" means through the dict-like
   interface of tables (setting, replacing or deleting keys, `pop()`,
   `update()`, at any level, including through the object you get back from
   `doc["some_table"]` when that table is split) and through the list-like
   interface of arrays of tables (item and slice assignment, `del`, `append()`,
   `insert()`), with plain Python values or with items built by `tomlkit.table()`,
   `tomlkit.aot()` and the like.

Where the existing test suite already pins down a specific behaviour that
conflicts with the list above, keep the tested behaviour.

Please fix the library so that these hold. We don't mind how the code is
organised internally.

## Constraints

- No new dependencies.
- The existing test suite must keep passing: `python -m pytest tests` from the
  root of the repository.
