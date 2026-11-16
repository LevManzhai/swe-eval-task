"""
Hidden verifier for the "out-of-order tables" task.

Every check follows from the contract stated in task/PROBLEM.md:

  1. a document that the standard library's ``tomllib`` accepts must parse,
     and ``doc.unwrap()`` must equal ``tomllib.loads(text)``;
  2. a document that ``tomllib`` rejects must still be rejected;
  3. an unmodified document must serialise back byte for byte;
  4. after an edit through the mapping API, the document must hold exactly the
     edited data, and its ``as_string()`` must be valid TOML that ``tomllib``
     parses to that same data.

``tomllib`` is used as the oracle throughout: nothing here depends on how the
reference solution happens to be written.
"""

import copy
import tomllib

import pytest
import tomlkit
from tomlkit.exceptions import TOMLKitError


def check_parse(text):
    expected = tomllib.loads(text)
    doc = tomlkit.parse(text)
    assert doc.unwrap() == expected
    assert doc.as_string() == text
    return doc


def check_document(doc, expected):
    assert doc.unwrap() == expected
    out = doc.as_string()
    assert tomllib.loads(out) == expected, out
    assert tomlkit.parse(out).unwrap() == expected, out


# --------------------------------------------------------------------------- #
# 1. Parsing and byte-for-byte round trip
# --------------------------------------------------------------------------- #

VALID_DOCUMENTS = [
    # A table split around an array of tables (typical pyproject.toml layout).
    '[tool.poetry]\nname = "foo"\n\n[[plugins]]\nname = "bar"\n\n[tool.other]\na = "b"\n',
    "[a]\nx = 1\n[[b]]\ny = 2\n[a.c]\nz = 3\n",
    "[a]\nx = 1\n[[b]]\n[[b]]\ny = 2\n[c]\n[a.d]\nz = 3\n",
    "[t.u]\nk = 1\n\n[[arr]]\nv = 1\n\n[[arr]]\nv = 2\n\n[t.w]\nk = 2\n",
    # An implicit super-table extended later with a dotted key.
    "[a.b.c]\n[a]\nb.z = 1\n",
    "[x.y.z]\nq = 1\n[x]\ny.w = 2\n",
    "[a.b.c]\n[other]\nk = 1\n[a]\nb.z = 1\nb.y = 2\n",
    "[p.q.r.s]\n[p]\nq.t = 1\n",
    # A table defined out of order under an indented header.
    " [a.b.c.d]\n[a.b.c]\n",
    " [[a.b.c.d]]\n[a.b.c]\n",
    " [a.b.c.d]\n[x]\n[a.b.c]\n",
    "  [p.q.r.s]\nk = 1\n[p.q.r]\nm = 2\n",
    " [a.b.c.d.e]\n[a.b.c.d]\nv = 1\n",
    # Shapes that already worked; they must keep working.
    "[a.b]\nx = 1\n[c]\ny = 2\n[a]\nz = 3\n",
    "[a]\nx = 1\n[b]\n[a.c]\ny = 2\n",
]


@pytest.mark.parametrize("text", VALID_DOCUMENTS)
def test_valid_document_parses_and_round_trips(text):
    check_parse(text)


INVALID_DOCUMENTS = [
    # A concrete table cannot be extended with a dotted key from its parent.
    "[a.b]\nx = 1\n[a]\nb.z = 1\n",
    "[a.b]\n[a]\nb.z = 1\n",
    # Plain redefinitions.
    "[a]\nx = 1\n[b]\n[a]\ny = 2\n",
    "[a]\nb = 1\n[a.b]\nc = 2\n",
]


@pytest.mark.parametrize("text", INVALID_DOCUMENTS)
def test_invalid_document_is_rejected(text):
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(text)
    with pytest.raises(TOMLKitError):
        tomlkit.parse(text).unwrap()


def test_indented_out_of_order_table_can_be_edited():
    doc = check_parse(" [a.b.c.d]\n[x]\n[a.b.c]\n")
    doc["a"]["b"]["c"]["k"] = 1
    check_document(doc, {"a": {"b": {"c": {"d": {}, "k": 1}}}, "x": {}})


def test_dotted_super_table_can_be_edited():
    doc = check_parse("[a.b.c]\n[a]\nb.z = 1\n")
    doc["a"]["n"] = 2
    check_document(doc, {"a": {"b": {"c": {}, "z": 1}, "n": 2}})


def test_table_split_around_aot_can_be_edited():
    text = '[tool.poetry]\nname = "foo"\n\n[[plugins]]\nname = "bar"\n\n[tool.other]\na = "b"\n'
    doc = check_parse(text)
    doc["tool"]["other"]["c"] = "d"
    doc["tool"]["poetry"]["version"] = "1.0"
    check_document(
        doc,
        {
            "tool": {
                "poetry": {"name": "foo", "version": "1.0"},
                "other": {"a": "b", "c": "d"},
            },
            "plugins": [{"name": "bar"}],
        },
    )


# --------------------------------------------------------------------------- #
# 2. Adding, replacing and removing keys of a table split in several parts
# --------------------------------------------------------------------------- #

SPLIT = "[a.b]\nx=1\n[other]\ny=2\n[a]\nexisting=3\n"
SPLIT_DATA = {"a": {"b": {"x": 1}, "existing": 3}, "other": {"y": 2}}

VALUES = [4, "text", [1, 2], {"nested": 3}, [{"k": 1}]]


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("operation", ["del", "pop", "doc_del"])
def test_new_key_can_be_removed(value, operation):
    doc = tomlkit.parse(SPLIT)
    proxy = doc["a"]
    proxy["new"] = value
    assert proxy["new"] == value
    assert "new" in proxy

    if operation == "del":
        del proxy["new"]
    elif operation == "pop":
        assert proxy.pop("new") == value
    else:
        # Deleting through a fresh lookup; the earlier proxy object is a view
        # that is not required to observe changes made through another one.
        del doc["a"]["new"]
        proxy = doc["a"]

    assert "new" not in proxy
    assert "new" not in doc["a"]
    check_document(doc, SPLIT_DATA)


@pytest.mark.parametrize(
    ("initial", "replacement"),
    [
        (4, 5),
        ({"old": 4}, {"new": 5}),
        ({"old": 4}, 5),
        (4, {"new": 5}),
        ([{"old": 4}], 5),
        (4, [{"new": 5}]),
        ("s", [1, 2]),
        ([{"old": 4}], {"new": 5}),
    ],
)
def test_new_key_can_be_replaced(initial, replacement):
    doc = tomlkit.parse(SPLIT)
    proxy = doc["a"]
    proxy["new"] = initial
    proxy["new"] = replacement
    assert proxy["new"] == replacement
    expected = copy.deepcopy(SPLIT_DATA)
    expected["a"]["new"] = replacement
    check_document(doc, expected)


def test_new_key_replaced_then_removed():
    doc = tomlkit.parse(SPLIT)
    proxy = doc["a"]
    proxy["new"] = 1
    proxy["new"] = {"t": 2}
    proxy["other_new"] = "v"
    del proxy["new"]
    expected = copy.deepcopy(SPLIT_DATA)
    expected["a"]["other_new"] = "v"
    check_document(doc, expected)
    assert set(doc["a"]) == {"b", "existing", "other_new"}


def test_several_new_keys():
    doc = tomlkit.parse(SPLIT)
    proxy = doc["a"]
    for i in range(5):
        proxy[f"k{i}"] = i
    for i in (1, 3):
        del proxy[f"k{i}"]
    proxy["k0"] = "zero"
    expected = copy.deepcopy(SPLIT_DATA)
    expected["a"].update({"k0": "zero", "k2": 2, "k4": 4})
    check_document(doc, expected)


# --------------------------------------------------------------------------- #
# 3. Updating a key that appears in several parts
# --------------------------------------------------------------------------- #

SIBLINGS = "[y.y.b]\nc = 1\n[y]\nd = 1\n[y.b]\ne = 2\n[y.y]\n"


@pytest.mark.parametrize("replacement", [{"z": 1}, [{"z": 1}], 1, "s"])
@pytest.mark.parametrize("remove_subtable", [False, True])
@pytest.mark.parametrize("sibling_first", [False, True])
def test_update_preserves_siblings(replacement, remove_subtable, sibling_first):
    doc = tomlkit.parse(SIBLINGS)
    if remove_subtable:
        doc["y"]["y"].pop("b")

    table = doc["y"]
    updates = {"y": replacement, "b": {"e": -0.5}}
    if sibling_first:
        updates = dict(reversed(updates.items()))
    table.update(updates)

    expected = {"y": {"y": replacement, "d": 1, "b": {"e": -0.5}}}
    assert table.unwrap() == expected["y"]
    check_document(doc, expected)


@pytest.mark.parametrize("replacement", [{"z": 1}, 7])
def test_setting_repeated_key_keeps_unrelated_entries(replacement):
    text = "[s.t.u]\nv = 1\n[s]\nw = 2\n[s.k]\nm = 3\n[s.t]\nq = 4\n[s.n]\no = 5\n"
    doc = check_parse(text)
    doc["s"]["t"] = replacement
    expected = {"s": {"t": replacement, "w": 2, "k": {"m": 3}, "n": {"o": 5}}}
    check_document(doc, expected)


# --------------------------------------------------------------------------- #
# 4. Mixed sequences on documents with split tables
# --------------------------------------------------------------------------- #

DOCUMENTS = [
    SPLIT,
    SIBLINGS,
    '[tool.poetry]\nname = "foo"\n\n[[plugins]]\nname = "bar"\n\n[tool.other]\na = "b"\n',
    "[a.b.c]\n[other]\nk = 1\n[a]\nb.z = 1\n",
]

OPERATIONS = [
    ("set_scalar", lambda t: t.__setitem__("added", 1)),
    ("set_table", lambda t: t.__setitem__("added", {"in": 2})),
    ("set_aot", lambda t: t.__setitem__("added", [{"in": 3}])),
]


def _first_split_key(text):
    return next(iter(tomllib.loads(text)))


@pytest.mark.parametrize("text", DOCUMENTS)
@pytest.mark.parametrize("name,operation", OPERATIONS, ids=[o[0] for o in OPERATIONS])
def test_add_then_remove_restores_data(text, name, operation):
    doc = tomlkit.parse(text)
    key = _first_split_key(text)
    original = tomllib.loads(text)

    table = doc[key]
    operation(table)
    expected = copy.deepcopy(original)
    expected[key]["added"] = tomlkit.parse(doc.as_string())[key]["added"].unwrap()
    check_document(doc, expected)

    del doc[key]["added"]
    check_document(doc, original)
