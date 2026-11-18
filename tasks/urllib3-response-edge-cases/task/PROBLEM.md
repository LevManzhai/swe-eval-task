# urllib3: rare responses and redirects handled wrongly

The repository in `/workspace/repo` is [urllib3](https://github.com/urllib3/urllib3),
the HTTP client underneath requests, botocore and pip. Optional dependencies
for brotli, zstd (`backports.zstd`), SOCKS and HTTP/2 are installed.

## What a user reported

> We talk to an old embedded device through urllib3. Its responses sometimes
> continue a header on the next line (obsolete line folding, with the
> continuation starting with a space). urllib3 hands us `Set-Cookie` values
> that contain a raw `\r\n` in the middle, which our cookie code then stores
> as two cookies.

## What we want

Fix that, and treat it as one example of a wider problem: urllib3 mishandles
responses, retries and redirects that are rare but legal, or at least
possible. We want the following to hold across the library:

1. **A body reads the same however it is read.** Reading a response in one
   call, in reads of any size, with `read1()`, or through `stream()` gives the
   same bytes, for every supported content encoding and combination of
   encodings. A body that turns out to be truncated is an error, not a
   shorter body.
2. **Values from the wire follow the HTTP grammar.** Header values, framing
   numbers (`Content-Length`, chunk sizes) and dates are taken as RFC 9110 and
   RFC 9112 define them. Where the RFCs say a malformed value is to be
   replaced, normalised or not used, urllib3 does that; it never passes on
   characters a field value can't contain, and never accepts a number the
   grammar doesn't allow just because Python's `int()` would.
3. **Only documented exceptions, no overflows.** However large or odd the
   numbers involved (retry counts, backoff, dates), urllib3 raises only its
   own documented exceptions and never overflows.
4. **Redirects carry exactly what they should.** A redirect strips
   credentials and other sensitive headers if and only if it goes to a
   different origin, also when the request goes through a proxy. Request-body
   state that doesn't apply to the redirected request is not carried over, and
   what the server asked for in the redirect response (such as `Retry-After`)
   is honoured.
5. **Misuse is reported before data is lost.** When a call is refused because
   of how the response was used earlier, it is refused before it consumes any
   data.

Behaviour that has nothing to do with these points must not change. If an
existing test in `test/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is (one test needs IPv6 and fails in this
  sandbox for that reason alone). It doesn't cover these cases.
- Your changes are graded by hidden tests that use urllib3's public API
  against small local HTTP servers, plus `HTTPResponse` built over an
  in-memory body, `Retry`, `urllib3.util.request.rewind_body` and
  `urllib3.util.ssl_.assert_fingerprint`.
