# Flask and Werkzeug: rare inputs that are accepted when they shouldn't be

Two repositories are installed in editable mode:

- `/workspace/flask`, the [Flask](https://github.com/pallets/flask) web
  framework;
- `/workspace/werkzeug`, [Werkzeug](https://github.com/pallets/werkzeug), the
  WSGI toolkit Flask is built on, which does Flask's request parsing,
  routing, URL handling, responses and development server.

Changes may be needed in either or both.

## What a user reported

> We have `@app.get("/invoice/<int:invoice_id>")`. Our security scanner found
> that `GET /invoice/٣` (an Arabic-Indic digit three) returns invoice 3, so a
> request that no client of ours would ever send reaches the view as if it
> were normal. We'd expect a 404.

## What we want

Fix that, and treat it as one example of a wider problem: rare inputs that
Flask and Werkzeug accept, convert or emit incorrectly instead of handling
them exactly as specified. We want the following to hold across both
projects:

1. **Values follow their grammar exactly.** Where a specification defines a
   value's syntax (a digit is an ASCII digit, base64 uses the base64
   alphabet, a TCP port is 1 to 65535 written without leading zeros), a value
   that doesn't match is treated as invalid. It is never accepted because it
   happens to convert.
2. **Bad input is the client's error.** A request whose path or headers are
   malformed or out of range ends in a client error or a failed match. It
   never causes a server error, and never produces a wrong value (such as an
   overflow).
3. **URL building is the inverse of URL matching.** For every rule, the URL
   built for given values matches that rule and converts back to the same
   values. Values a rule could never match are rejected when building.
4. **Conversions keep information.** Converting a URL between IRI and URI
   form keeps every component, including ones that are present but empty.
   Reading into a buffer the caller provides fills it, and never changes its
   size.
5. **Headers follow their grammar too.** Setting a response header attribute
   to a value that means "not set" removes the header instead of sending a
   placeholder. Text inside a quoted string, even one that is never closed, is
   never read as further header parameters.
6. **IPv6 literals work.** Wherever Flask handles a host or `host:port`
   (configuration, `app.run()`, the test client), a bracketed IPv6 literal
   such as `[::1]:8080` works like a host name.
7. **Response iterables are always closed.** The development server calls a
   response iterable's `close()` after every request, including when
   something fails while it finishes the request.

Behaviour that has nothing to do with these points must not change. If an
existing test in either repository pins down a behaviour, keep it.

## Notes

- Both test suites pass as they are. They don't cover these cases.
- Your changes are graded by hidden tests that mostly use a Flask application
  and its test client, plus Werkzeug's public API. To make something fail at
  a precise moment in the development server, a test may replace the
  standard library's `selectors.DefaultSelector` as seen from
  `werkzeug.serving`; to check `app.run()`, a test may replace
  `werkzeug.serving.run_simple`.
