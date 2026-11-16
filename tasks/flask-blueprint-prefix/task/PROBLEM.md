# Blueprint-prefixed routes resolve to the wrong URL

## Observed behaviour

When a `Blueprint` is registered with a `url_prefix`, the final route that
Flask registers does not reliably match "prefix + route" the way a user
would expect from reading the route and the prefix side by side. Depending
on how the prefix and the route happen to be written (trailing slash on the
prefix, leading slash on the route, no slash at all, or an empty route
string), the app ends up serving the view at a URL with a doubled slash, at
a URL that is missing a slash entirely, or it raises an exception while the
blueprint is being registered.

None of this depends on anything exotic — it shows up with perfectly
ordinary prefixes and routes, it just depends on exactly which of the
(arguably) equivalent ways of writing them was used.

## Minimal reproduction

```python
import flask

app = flask.Flask(__name__)
bp = flask.Blueprint("bp", __name__)


@bp.route("/bar")
def bar():
    return "bar"


app.register_blueprint(bp, url_prefix="/foo/")

client = app.test_client()
print(client.get("/foo/bar").status_code)   # expected: 200
```

That example happens to work. But small, seemingly-equivalent variations on
the same idea do not:

```python
import flask

app = flask.Flask(__name__)
bp = flask.Blueprint("bp", __name__)


@bp.route("/bar")
def bar():
    return "bar"


# Note the two trailing slashes here, instead of one.
app.register_blueprint(bp, url_prefix="/foo//")

client = app.test_client()
print(client.get("/foo/bar").status_code)    # expected: 200, actually: 404
print(client.get("/foo//bar").status_code)   # actually matches instead
```

Writing the route without its own leading slash also breaks:

```python
import flask

app = flask.Flask(__name__)
bp = flask.Blueprint("bp", __name__)


@bp.route("bar")  # no leading slash
def bar():
    return "bar"


app.register_blueprint(bp, url_prefix="/foo")

client = app.test_client()
print(client.get("/foo/bar").status_code)  # expected: 200, actually: 404
print(client.get("/foobar").status_code)   # actually matches instead
```

And mounting a blueprint's view directly at its prefix (an empty route
string, a common pattern for a blueprint's "index") can crash registration
outright instead of serving anything:

```python
import flask

app = flask.Flask(__name__)
bp = flask.Blueprint("bp", __name__)


@bp.route("")
def index():
    return "index"


app.register_blueprint(bp, url_prefix="/")

# Raises ValueError while building the app, before a single request is
# ever made.
```

## Expected behaviour

Registering a blueprint with any reasonable combination of a `url_prefix`
and a route string should merge the two into a single `/`-separated URL,
exactly as if the caller had written the prefix and the route out by hand
with normal slash conventions — regardless of incidental extra or missing
slashes at the point where the prefix and the route meet, and without
raising while the blueprint is being registered. A trailing slash that is
part of the *route itself* (not just an artifact of where the prefix ends)
is meaningful to Flask's routing and should still be preserved.

## Task

Find and fix the root cause in the library so that blueprint URL prefixes
and routes are combined correctly and consistently for ordinary registration
patterns like the ones above, without breaking any currently-passing
behaviour.
