# tomlkit produces, accepts and rejects the wrong TOML

We use tomlkit to read and update `pyproject.toml` files and other config
files without losing their formatting. That is the whole point of tomlkit, and
for simple files it works. On real-world files it doesn't hold up.

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

That is the one we hit in production. Since then our users have reported a
steady trickle of other problems:

- files that our tool wrote and that other TOML parsers then refuse to read;
- files that tomlkit rejects although other parsers accept them;
- files that tomlkit accepts although they are not valid TOML;
- exceptions during editing;
- edits that end up with different data than what was written.

We don't have reliable reproductions for those, and they don't seem to come
from one place. Please treat this as a request to make tomlkit hold up its
contract, not just to fix the example above.

## The contract

"Valid TOML" and "the data a document holds" mean what the
[TOML v1.0.0 specification](https://toml.io/en/v1.0.0) says. Python's
`tomllib` is a conforming parser.

1. **Parsing.** If a document is valid TOML, `tomlkit.parse()` accepts it, and
   `doc.unwrap()` is the data the document holds. If it is not valid TOML,
   tomlkit rejects it with a `tomlkit.exceptions.TOMLKitError`, either while
   parsing or at the latest when the data is accessed.
2. **Round trip.** If a parsed document is not modified, `doc.as_string()`
   returns the input unchanged, byte for byte.
3. **Editing.** After any change made through tomlkit's public API,
   `doc.as_string()` is valid TOML. If the change succeeded, the document
   holds exactly the data that was written. A timezone-aware datetime counts
   as the same data if it denotes the same instant. If the change is not
   possible, it raises an exception instead, and the document is still valid
   TOML afterwards.

   That covers:
   - the dict-like interface of documents and tables (setting, replacing or
     deleting keys, `pop()`, `update()`, at any level, including through the
     object you get back from `doc["some_table"]` when that table is split);
   - the list-like interface of arrays and arrays of tables (item and slice
     assignment, `del`, `append()`, `insert()`);
   - assigning any Python value tomlkit supports (`str`, numbers, `bool`,
     `datetime`/`date`/`time`, lists, dicts), as well as items built with
     `tomlkit.table()`, `tomlkit.aot()`, `tomlkit.comment()` and the like;
   - the methods and operators of tomlkit's items (for example
     `item.comment(...)`, or `+` on a string item).

Where the existing test suite already pins down a specific behaviour that
conflicts with the list above, keep the tested behaviour.

We don't mind how the code is organised internally.

## Constraints

- No new dependencies.
- The existing test suite must keep passing: `python -m pytest tests` from the
  root of the repository.
