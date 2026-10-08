from __future__ import annotations

import pytest

from spec2kb.profiles import ProfileError, ProfileStore, deep_merge, diff_overrides
from spec2kb.profiles.store import _NO_DIFF


def test_builtins_resolve_and_inherit(tmp_path):
    st = ProfileStore(tmp_path)
    ids = [p["id"] for p in st.list()]
    assert {"general", "jedec", "customer"} <= set(ids)
    jedec = st.resolve("jedec")
    general = st.resolve("general")
    assert st.chain("jedec") == ["jedec", "general"]
    assert general.parsing.paragraphs.columns == "auto"       # general override
    assert jedec.parsing.paragraphs.columns == "1"            # jedec override wins
    assert jedec.parsing.tables.strategy == "lines"
    assert jedec.parsing.figures.caption_position == "below"
    # id-merged image type: jedec changes the timing prompt but keeps the other rules
    assert "JEDEC timing diagram" in jedec.image_type("timing_diagram").prompt
    assert jedec.image_type("state_diagram").prompt == general.image_type("state_diagram").prompt


def test_child_profile_stores_minimal_diff(tmp_path):
    st = ProfileStore(tmp_path)
    st.create("team", "Team", "jedec", "inherit")
    full = st.resolved_dict("team")
    full["markdown"]["split_level"] = 2
    full["vision"]["image_types"][1]["prompt"] = "custom state prompt"
    st.update("team", resolved=full)
    raw = st.get_raw("team")
    assert raw["overrides"] == {"markdown": {"split_level": 2},
                                "vision": {"image_types": [{"prompt": "custom state prompt", "id": "state_diagram"}]}}
    # parent changes still flow into the child for untouched fields
    assert st.resolve("team").parsing.paragraphs.columns == "1"


def test_clone_flatten_delete_and_guards(tmp_path):
    st = ProfileStore(tmp_path)
    st.create("pa", "A", "jedec", "inherit")
    st.update("pa", overrides={"markdown": {"table_format": "html"}})
    st.create("pb", "B", "pa", "clone")
    assert st.get_raw("pb")["extends"] == "jedec"
    assert st.resolve("pb").markdown.table_format == "html"
    st.create("pc", "C", "pa", "flatten")
    assert st.get_raw("pc")["extends"] is None
    assert st.resolve("pc").parsing.metadata.publisher == "JEDEC"
    with pytest.raises(ProfileError):
        st.update("jedec", name="x")             # builtin read-only
    with pytest.raises(ProfileError):
        st.delete("general")
    st.create("child", "Child", "pa", "inherit")
    with pytest.raises(ProfileError):
        st.delete("pa")                           # has children
    with pytest.raises(ProfileError):
        st.update("pa", extends="child")          # cycle a -> child -> a
    assert st.get_raw("pa")["extends"] == "jedec"  # rolled back
    with pytest.raises(ProfileError):
        st.create("BAD ID", "x")


def test_invalid_regex_rejected_and_rolled_back(tmp_path):
    st = ProfileStore(tmp_path)
    st.create("rx", "R", "general")
    with pytest.raises(ProfileError, match="numbered_pattern"):
        st.update("rx", overrides={"parsing": {"headings": {"numbered_pattern": "(unclosed"}}})
    with pytest.raises(ProfileError, match="title"):
        st.update("rx", overrides={"parsing": {"tables": {"caption_pattern": r"^Table (?P<num>\d+)"}}})
    assert st.get_raw("rx")["overrides"] == {}


def test_deep_merge_id_lists_and_delete():
    base = {"x": [{"id": "a", "v": 1}, {"id": "b", "v": 2}], "y": {"z": 1}}
    over = {"x": [{"id": "b", "v": 3}, {"id": "c", "v": 4}, {"id": "a", "_delete": True}], "y": {"w": 2}}
    out = deep_merge(base, over)
    assert out == {"x": [{"id": "b", "v": 3}, {"id": "c", "v": 4}], "y": {"z": 1, "w": 2}}
    assert deep_merge(base, diff_overrides(out, base)) == out
    assert diff_overrides(base, base) is _NO_DIFF


def test_import_profile(tmp_path):
    st = ProfileStore(tmp_path)
    st.import_raw({"id": "imp", "name": "Imported", "extends": "customer",
                   "overrides": {"validation": {"coverage_warn_ratio": 0.8}}})
    assert st.resolve("imp").validation.coverage_warn_ratio == 0.8
    with pytest.raises(ProfileError):
        st.import_raw({"id": "imp"})
    with pytest.raises(ProfileError):
        st.import_raw({"id": "x2", "extends": "missing"})
