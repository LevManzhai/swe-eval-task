# packaging: inputs the specifications reject, accepted anyway

The repository in `/workspace/repo` is
[packaging](https://github.com/pypa/packaging), the reference implementation
of Python's packaging specifications: version specifiers (PEP 440),
dependency specifiers and environment markers (PEP 508), wheel filenames and
platform compatibility tags, and core metadata. pip, setuptools, uv's Python
bindings, Poetry and most other tools rely on it.

## What a user reported

> Our build tool reads requirements from a file and passes each line to
> `Requirement()`. A line ending in `\n` that our reader forgot to strip,
> `"requests>=2\n"`, is accepted as if the newline weren't there, so a
> malformed requirements file goes through validation without a complaint.
> We'd expect `InvalidRequirement`.

## What we want

Fix that, and treat it as one example of a wider problem: packaging accepts,
misparses or mis-serializes inputs that are rare but possible, instead of
handling them exactly as the specifications say. We want the following to
hold across the library:

1. **Valid if and only if the grammar says so.** A string is valid exactly
   when the whole of it matches the grammar of the specification it's parsed
   against, and a valid string is parsed the way the grammar reads it.
   Anything left over that the grammar doesn't allow, or a character it doesn't
   allow at that position, makes the string invalid.
2. **Invalid input raises the documented exception.** Parsing invalid input
   raises the exception documented for that kind of object
   (`InvalidRequirement`, `InvalidMarker`, `InvalidSpecifier`, `InvalidTag`,
   `InvalidWheelFilename`, ...). It never raises anything else and never
   exhausts the interpreter, however unusual the input.
3. **Serialization round-trips.** `str()` of a parsed object, parsed again,
   gives an equal object that behaves the same way.
4. **Metadata stays well formed.** Writing core metadata never lets the
   content of a field start a new header, whatever characters the value
   contains.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is. It doesn't cover these cases.
- Your changes are graded by hidden tests that use packaging's public API.
