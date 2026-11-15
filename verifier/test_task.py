"""Hidden regression tests for the Blueprint url_prefix/route merging bug.

All assertions go through Flask's public API only: ``flask.Flask``,
``flask.Blueprint``, ``Flask.register_blueprint``, ``Flask.test_client``,
``Flask.url_map`` (a documented public attribute) and ``flask.url_for``.
No private attributes or internal call sequences are inspected.

Tests are grouped into three sections:

  * ``TestCoreRegression``   - the double-slash / missing-slash bug itself.
  * ``TestEdgeCases``        - related edge cases around the same merge
                                logic (empty routes, root prefixes, trailing
                                slashes that are part of the route itself).
  * ``TestExistingBehavior`` - behaviour that must keep working exactly as
                                before: unprefixed blueprints, multiple
                                routes, the static route, url_for, and
                                multiple independently-prefixed blueprints.
"""
import flask
import pytest


def make_app(prefix, rule, endpoint="view", view_return="ok"):
    """Build a tiny app with a single blueprint route and return the app."""
    app = flask.Flask(__name__)
    bp = flask.Blueprint("bp", __name__)

    @bp.route(rule, endpoint=endpoint)
    def _view():
        return view_return

    app.register_blueprint(bp, url_prefix=prefix)
    return app


class TestCoreRegression:
    """The reported bug: prefix/route slash combinations must merge to a
    single, predictable URL instead of doubling or dropping a slash."""

    @pytest.mark.parametrize(
        "prefix,rule",
        [
            ("/foo/", "/bar"),
            ("/foo//", "/bar"),
            ("/foo///", "/bar"),
            ("/foo", "//bar"),
            ("/foo", "///bar"),
            ("/foo/", "//bar"),
        ],
    )
    def test_extra_slashes_merge_to_single_slash(self, prefix, rule):
        app = make_app(prefix, rule)
        client = app.test_client()

        assert client.get("/foo/bar").status_code == 200
        # The doubled-slash variant must NOT also match - there should be
        # exactly one registered URL for this view.
        assert client.get("/foo//bar").status_code == 404

    @pytest.mark.parametrize("prefix,rule", [("/foo", "bar"), ("/foo/", "bar")])
    def test_missing_leading_slash_on_rule_still_gets_merged(self, prefix, rule):
        app = make_app(prefix, rule)
        client = app.test_client()

        assert client.get("/foo/bar").status_code == 200
        # Without the fix this falls back to naive concatenation and would
        # serve the view at the wrong, slash-less URL instead.
        assert client.get("/foobar").status_code == 404

    def test_prefix_without_trailing_slash_and_rule_with_leading_slash(self):
        # The one combination that happens to already work even with the
        # naive implementation - must keep working.
        app = make_app("/foo", "/bar")
        client = app.test_client()

        assert client.get("/foo/bar").status_code == 200


class TestEdgeCases:
    """Edge cases around the same merge logic that a partial fix tends to
    miss: empty route strings, a bare "/" prefix, and trailing slashes that
    are meaningful because they belong to the route itself."""

    def test_empty_rule_mounts_view_exactly_at_prefix(self):
        # A blueprint "index" view registered with an empty rule string
        # should live exactly at the prefix, with no extra trailing slash.
        app = make_app("/foo", "")
        client = app.test_client()

        assert client.get("/foo").status_code == 200
        assert client.get("/foo/").status_code == 404

    def test_empty_rule_keeps_prefix_trailing_slash_if_present(self):
        # If the prefix itself ends in a slash, an empty rule should keep
        # that slash rather than silently dropping it.
        app = make_app("/foo/", "")
        client = app.test_client()

        assert client.get("/foo/").status_code == 200

    def test_root_prefix_with_empty_rule_does_not_raise(self):
        # Mounting a blueprint's index view at url_prefix="/" must not raise
        # while the app is being constructed.
        app = make_app("/", "")
        client = app.test_client()

        assert client.get("/").status_code == 200

    @pytest.mark.parametrize("prefix", ["/foo", "/foo/", "/foo//"])
    def test_trailing_slash_on_the_route_itself_is_preserved(self, prefix):
        # A trailing slash that is part of the route string (not just an
        # artifact of the prefix) changes Flask's routing behaviour and
        # must survive the merge.
        app = make_app(prefix, "/bar/")
        client = app.test_client()

        assert client.get("/foo/bar/").status_code == 200

    def test_blank_prefix_is_equivalent_to_no_prefix(self):
        app = make_app("", "/bar")
        client = app.test_client()

        assert client.get("/bar").status_code == 200


class TestExistingBehavior:
    """Behaviour that already worked and must not regress."""

    def test_blueprint_without_url_prefix_is_unaffected(self):
        app = flask.Flask(__name__)
        bp = flask.Blueprint("bp", __name__)

        @bp.route("/plain")
        def plain():
            return "plain"

        app.register_blueprint(bp)
        client = app.test_client()

        assert client.get("/plain").status_code == 200

    def test_multiple_routes_on_one_prefixed_blueprint(self):
        app = flask.Flask(__name__)
        bp = flask.Blueprint("bp", __name__)

        @bp.route("/users")
        def users():
            return "users"

        @bp.route("/users/<int:user_id>")
        def user_detail(user_id):
            return "user %d" % user_id

        app.register_blueprint(bp, url_prefix="/api")
        client = app.test_client()

        assert client.get("/api/users").status_code == 200
        assert client.get("/api/users/42").status_code == 200
        assert client.get("/api/users/not-an-int").status_code == 404

    def test_static_route_survives_blueprint_registration(self):
        app = flask.Flask(__name__)
        bp = flask.Blueprint("bp", __name__)

        @bp.route("/bar")
        def bar():
            return "bar"

        app.register_blueprint(bp, url_prefix="/foo")

        endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
        assert "static" in endpoints

    def test_url_for_matches_the_merged_route(self):
        app = flask.Flask(__name__)
        bp = flask.Blueprint("bp", __name__)

        @bp.route("/bar")
        def bar():
            return "bar"

        app.register_blueprint(bp, url_prefix="/foo/")

        with app.test_request_context():
            assert flask.url_for("bp.bar") == "/foo/bar"

    def test_two_independently_prefixed_blueprints_do_not_collide(self):
        app = flask.Flask(__name__)

        bp_a = flask.Blueprint("a", __name__)
        bp_b = flask.Blueprint("b", __name__)

        @bp_a.route("/thing")
        def a_thing():
            return "a"

        @bp_b.route("/thing")
        def b_thing():
            return "b"

        app.register_blueprint(bp_a, url_prefix="/svc-a/")
        app.register_blueprint(bp_b, url_prefix="/svc-b")

        client = app.test_client()
        assert client.get("/svc-a/thing").data == b"a"
        assert client.get("/svc-b/thing").data == b"b"
