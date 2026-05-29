"""Phase 2 — apply_merge_patch (RFC 7386) semantics (test-harness-rollout.md §7).

The atomic-commit layer beneath the Architect. No LLM involvement.
"""
from __future__ import annotations


async def test_replaces_arrays(started_game):
    gs, _ = started_game
    gs.variables["lst"] = [3, 4, 5]
    gs.apply_merge_patch({"variables": {"lst": [1, 2]}}, "player1")
    assert gs.variables["lst"] == [1, 2]   # replaced, not appended


async def test_deep_merges_nested_dicts(started_game):
    gs, _ = started_game
    gs.variables["nested"] = {"a": 1, "keep": True}
    gs.apply_merge_patch({"variables": {"nested": {"b": 2}}}, "player1")
    assert gs.variables["nested"] == {"a": 1, "keep": True, "b": 2}


async def test_null_deletes_key(started_game):
    gs, _ = started_game
    gs.variables["gone"] = "x"
    gs.apply_merge_patch({"variables": {"gone": None}}, "player1")
    assert "gone" not in gs.variables


async def test_version_bumps_exactly_once_per_applied_call(started_game):
    gs, _ = started_game
    v0 = gs.version
    gs.apply_merge_patch({"variables": {"a": 1, "b": 2}}, "player1")
    assert gs.version == v0 + 1   # one bump regardless of how many keys changed


async def test_no_op_patch_does_not_bump_version(started_game):
    """A patch that matches nothing applies nothing and must not bump version
    (version only advances `if applied`, game_state.py:1637)."""
    gs, _ = started_game
    v0 = gs.version
    applied = gs.apply_merge_patch({"unknown_top_level_key": {"x": 1}}, "player1")
    assert applied == []
    assert gs.version == v0


async def test_unknown_top_level_key_does_not_corrupt_state(started_game):
    """Current behavior is silent-ignore (NOT a raised typed error — the plan's
    'raises typed error' is aspirational). State must remain intact."""
    gs, _ = started_game
    before = dict(gs.variables)
    gs.apply_merge_patch({"bogus": 123}, "player1")
    assert gs.variables == before


async def test_read_only_fields_are_ignored(started_game):
    gs, _ = started_game
    v0 = gs.version
    # 'version' is read-only; writing it must be ignored (and contributes no apply).
    gs.apply_merge_patch({"version": 9999, "variables": {"a": 1}}, "player1")
    assert gs.version == v0 + 1   # bumped by the variables change, not set to 9999
