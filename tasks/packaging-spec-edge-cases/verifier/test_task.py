"""
Hidden verifier for the "packaging spec edge cases" task.

Each test checks one point of the contract in task/PROBLEM.md:

  (1) input is accepted if and only if all of it matches the grammar; a
      trailing line break or a character the grammar doesn't allow makes it
      invalid;
  (2) invalid input raises the library's documented exception for that kind
      of object, never another exception (ValueError, AttributeError,
      RecursionError, an email-module error);
  (3) str() of a parsed object parses back to an equal object;
  (4) serialized metadata never lets a field value start a new header.
"""

from __future__ import annotations

import pytest

from packaging.markers import InvalidMarker, Marker
from packaging.metadata import Metadata
from packaging.requirements import InvalidRequirement, Requirement
from packaging.tags import InvalidTag, Tag, parse_tag
from packaging.utils import InvalidWheelFilename, parse_wheel_filename



# ---------------------------------------------------------------------------
# (1) The whole input must match
# ---------------------------------------------------------------------------


class TestWholeInput:
    @pytest.mark.parametrize(
        "value", ["foo>=1\n", "foo\n", "foo[bar]\n", 'foo; python_version >= "3"\n']
    )
    def test_requirement_with_trailing_newline_is_invalid(self, value: str) -> None:
        with pytest.raises(InvalidRequirement):
            Requirement(value)

    @pytest.mark.parametrize(
        "value", ['python_version >= "3"\n', 'extra == "x"\n']
    )
    def test_marker_with_trailing_newline_is_invalid(self, value: str) -> None:
        with pytest.raises(InvalidMarker):
            Marker(value)

    def test_trailing_spaces_are_still_fine(self) -> None:
        assert str(Requirement("foo>=1 ")) == "foo>=1"
        assert str(Marker('python_version >= "3" ')) == 'python_version >= "3"'

    @pytest.mark.parametrize(
        "filename",
        [
            "foo\n-1.0-py3-none-any.whl",
            "foo-1.0-1\n-py3-none-any.whl",
        ],
    )
    def test_wheel_filename_with_newline_is_invalid(self, filename: str) -> None:
        with pytest.raises(InvalidWheelFilename):
            parse_wheel_filename(filename)

    def test_ordinary_wheel_filenames_still_parse(self) -> None:
        name, version, build, tags = parse_wheel_filename(
            "foo_bar-1.0-1abc-py3-none-any.whl"
        )
        assert (name, str(version), build) == ("foo-bar", "1.0", (1, "abc"))
        assert {str(t) for t in tags} == {"py3-none-any"}

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/a\fb.whl",
            "https://example.com/a\vb.whl",
            "https://example.com/a b.whl",
            "https://example.com/a b.whl",
        ],
    )
    def test_requirement_url_with_whitespace_is_invalid(self, url: str) -> None:
        with pytest.raises(InvalidRequirement):
            Requirement(f"foo @ {url}")

    def test_ordinary_url_requirement_still_parses(self) -> None:
        req = Requirement('foo @ https://example.com/foo-1.0.whl ; python_version >= "3"')
        assert req.url == "https://example.com/foo-1.0.whl"
        assert str(req.marker) == 'python_version >= "3"'


# ---------------------------------------------------------------------------
# (2) Only the documented exceptions
# ---------------------------------------------------------------------------


class TestDocumentedExceptions:
    @pytest.mark.parametrize(
        "tag", ["py3-none", "py3", "py3-none-any-x", "py-3-none-any", ""]
    )
    def test_wrong_number_of_tag_fields_is_invalid_tag(self, tag: str) -> None:
        with pytest.raises(InvalidTag):
            parse_tag(tag)

    def test_valid_tags_still_parse(self) -> None:
        assert parse_tag("cp312-cp312-manylinux_2_17_x86_64") == {
            Tag("cp312", "cp312", "manylinux_2_17_x86_64")
        }
        assert {str(t) for t in parse_tag("py2.py3-none-any")} == {
            "py2-none-any",
            "py3-none-any",
        }

    @pytest.mark.parametrize("depth", [5000, 20000])
    def test_deeply_nested_marker_does_not_blow_the_stack(self, depth: int) -> None:
        text = "(" * depth + 'python_version >= "3"' + ")" * depth
        try:
            Marker(text)
        except InvalidMarker:
            pass

    @pytest.mark.parametrize("depth", [5000, 20000])
    def test_deeply_nested_requirement_marker(self, depth: int) -> None:
        text = "foo; " + "(" * depth + 'python_version >= "3"' + ")" * depth
        try:
            Requirement(text)
        except InvalidRequirement:
            pass

    def test_moderately_nested_marker_still_works(self) -> None:
        text = "(" * 20 + 'python_version >= "3"' + ")" * 20
        assert Marker(text).evaluate({"python_version": "3.12"})

    def test_metadata_with_carriage_return_serializes(self) -> None:
        meta = _metadata()
        meta.summary = "first\rsecond"
        out = _rfc822(meta)
        assert "first" in out and "second" in out


# ---------------------------------------------------------------------------
# (3) Round trips
# ---------------------------------------------------------------------------


class TestRoundTrips:
    @pytest.mark.parametrize(
        "text",
        [
            "platform_release == 'a\"b'",
            "platform_version == 'say \"hi\"'",
            'implementation_name == "it\'s"',
        ],
    )
    def test_marker_values_with_quotes_round_trip(self, text: str) -> None:
        marker = Marker(text)
        again = Marker(str(marker))
        assert again == marker
        env = {"platform_release": 'a"b', "platform_version": 'say "hi"', "implementation_name": "it's"}
        assert again.evaluate(env) == marker.evaluate(env)

    def test_requirement_with_quoted_marker_round_trips(self) -> None:
        req = Requirement("foo; platform_release == 'a\"b'")
        assert Requirement(str(req)) == req

    @pytest.mark.parametrize(
        "text",
        ["foo===1.0, >= 2", "foo === 1.0 , >=2", "foo===1.0,>=2,<3", "foo>=2, ===1.0"],
    )
    def test_arbitrary_equality_next_to_other_specifiers(self, text: str) -> None:
        req = Requirement(text)
        operators = sorted(s.operator for s in req.specifier)
        assert "===" in operators and ">=" in operators
        arbitrary = next(s for s in req.specifier if s.operator == "===")
        assert arbitrary.version == "1.0"
        assert Requirement(str(req)) == req

    def test_lone_arbitrary_equality_still_works(self) -> None:
        req = Requirement("foo===1.0+local.thing")
        assert [s.version for s in req.specifier] == ["1.0+local.thing"]


# ---------------------------------------------------------------------------
# (4) Metadata headers
# ---------------------------------------------------------------------------


def _metadata() -> Metadata:
    return Metadata.from_raw(
        {"metadata_version": "2.1", "name": "foo", "version": "1.0"}, validate=False
    )


def _rfc822(meta: Metadata) -> str:
    return bytes(meta.as_rfc822()).decode("utf-8")


def _headers_read_back(text: str) -> set[str]:
    """
    The header names a reader sees in the written metadata: packaging's own
    parser and the standard library's email parser, as installed here.
    """
    import email

    from packaging.metadata import parse_email

    raw, unparsed = parse_email(text)
    assert not unparsed, unparsed
    names = {k.lower() for k in email.message_from_string(text).keys()}
    return names | set(raw)


EXPECTED = {"metadata-version", "metadata_version", "name", "version", "summary"}


class TestMetadataHeaders:
    @pytest.mark.parametrize(
        "sep", ["\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]
    )
    def test_value_cannot_inject_a_header(self, sep: str) -> None:
        meta = _metadata()
        meta.summary = f"innocent{sep}Injected: yes"
        out = _rfc822(meta)
        assert _headers_read_back(out) <= EXPECTED, out

    def test_plain_newline_is_still_folded(self) -> None:
        meta = _metadata()
        meta.summary = "a\nb"
        out = _rfc822(meta)
        assert _headers_read_back(out) <= EXPECTED
        assert "b" in out

    def test_ordinary_summary_unchanged(self) -> None:
        meta = _metadata()
        meta.summary = "A small library"
        assert "summary: A small library\n" in _rfc822(meta).lower().replace(
            "a small library", "A small library"
        )
