# yarl: URLs that don't follow the standard of their mode

The repository in `/workspace/repo` is [yarl](https://github.com/aio-libs/yarl),
the URL library under aiohttp. It is installed as pure Python
(`YARL_NO_EXTENSIONS=1`), so the Cython quoting module isn't used.

A `URL` has a mode. The default, `mode="whatwg"`, is meant to parse,
resolve (`join`) and serialize URLs the way the
[WHATWG URL Standard](https://url.spec.whatwg.org/) does, as browsers do.
`mode="rfc"` is meant to follow RFC 3986 (with RFC 3987 for IRIs and
RFC 6874 for IPv6 zone identifiers) and, for `http` and `https`, RFC 9110.

## What a user reported

> A browser leaves an invalid percent sign alone:
> `new URL("http://example.com/foo%2zbar").href` is
> `"http://example.com/foo%2zbar"`. yarl gives
> `http://example.com/foo%252zbar`, so the path we send is not the path we
> were given.

## What we want

Fix that, and treat it as one example of a wider problem: in both modes,
yarl handles some rare but valid (or validly invalid) input differently from
the standard it claims to follow. We want the following to hold:

1. **WHATWG mode gives the WHATWG URL Standard's result.** For any input and
   base, `URL(input)` and `URL(base).join(URL(input))` produce the URL the
   standard's parser produces, serialized the same way; where the standard's
   parser fails, yarl raises `ValueError`. This covers every part of a URL:
   scheme, userinfo, host (special and non-special schemes), port, path,
   query and fragment, and resolution against every kind of base.
2. **RFC mode gives RFC 3986's result.** Parsing, reference resolution
   (section 5) and serialization follow RFC 3986 and the RFCs named above,
   with only the normalization section 6.2 allows; what the grammar rejects
   (including what RFC 9110 rejects for `http` and `https`) raises
   `ValueError`.
3. **Building a URL follows the same rules as parsing one.** `URL.build`
   accepts and rejects the same things `URL(str)` does for the same
   components.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is (`python -m pytest --no-cov tests`). It
  doesn't cover these cases.
- Your changes are graded by hidden tests that use yarl's public API: `URL`
  in both modes, `URL.join` and `URL.build`. Most cases come from the WHATWG
  URL Standard's own test data, the rest from RFC 3986.
