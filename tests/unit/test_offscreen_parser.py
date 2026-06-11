"""Unit tests for parse_offscreen_progression — pure, no LLM, no kernel."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.models.game_state import GameState
from src.models.story_models import load_story_from_file
from src.core.offscreen_progression import parse_offscreen_progression

STORY = Path(__file__).parent.parent / "fixtures" / "stories" / "offscreen.yaml"


@pytest.fixture
def gs():
    story = load_story_from_file(str(STORY))
    state = GameState(story)
    state.add_player("p1")
    state.set_player_character("p1", story.get_character("hero"))  # player at start_node
    return state


def _payload(beats, elapsed="until dawn"):
    return {"offscreen_progression": {"elapsed": elapsed, "beats": beats}}


def test_valid_two_beats_ordered(gs):
    parsed = parse_offscreen_progression(_payload([
        {"npc_ids": ["npc_a", "npc_b"], "focus": "act together"},
        {"npc_ids": ["npc_c"], "focus": "skulk"},
    ]), gs)
    assert parsed is not None
    elapsed, beats = parsed
    assert elapsed == "until dawn"
    assert [b.npc_ids for b in beats] == [["npc_a", "npc_b"], ["npc_c"]]
    assert beats[0].focus == "act together"


def test_unknown_npc_dropped(gs):
    _, beats = parse_offscreen_progression(_payload([
        {"npc_ids": ["npc_a", "ghost"], "focus": "x"},
    ]), gs)
    assert [b.npc_ids for b in beats] == [["npc_a"]]


def test_witnessed_beat_dropped(gs):
    # npc_here is colocated with the player -> the whole beat is witnessed.
    parsed = parse_offscreen_progression(_payload([
        {"npc_ids": ["npc_here"], "focus": "loiter"},
    ]), gs)
    assert parsed is None


def test_npc_deduped_across_beats(gs):
    _, beats = parse_offscreen_progression(_payload([
        {"npc_ids": ["npc_a"], "focus": "first"},
        {"npc_ids": ["npc_a", "npc_c"], "focus": "second"},
    ]), gs)
    # npc_a kept only in the first beat; second beat keeps just npc_c.
    assert [b.npc_ids for b in beats] == [["npc_a"], ["npc_c"]]


def test_clamp_max_beats(gs):
    beats_in = [{"npc_ids": [f"npc_{i}"], "focus": "x"} for i in range(10)]
    # only npc_a/npc_b/npc_c exist; pad with valid distinct ids by reusing known ones
    beats_in = [
        {"npc_ids": ["npc_a"], "focus": "1"},
        {"npc_ids": ["npc_b"], "focus": "2"},
        {"npc_ids": ["npc_c"], "focus": "3"},
        {"npc_ids": ["npc_a"], "focus": "4"},  # dup -> empty -> skipped
    ]
    parsed = parse_offscreen_progression(_payload(beats_in), gs)
    _, beats = parsed
    assert len(beats) <= 4


def test_malformed_payloads_return_none(gs):
    assert parse_offscreen_progression(None, gs) is None
    assert parse_offscreen_progression({}, gs) is None
    assert parse_offscreen_progression({"offscreen_progression": {"beats": "nope"}}, gs) is None
    assert parse_offscreen_progression(_payload([]), gs) is None
    # beat missing focus, and beat not a dict -> dropped, leaving nothing
    assert parse_offscreen_progression(_payload([
        {"npc_ids": ["npc_a"]}, "garbage",
    ]), gs) is None


def test_string_npc_ids_coerced(gs):
    _, beats = parse_offscreen_progression(_payload([
        {"npc_ids": "npc_c", "focus": "single id as string"},
    ]), gs)
    assert [b.npc_ids for b in beats] == [["npc_c"]]


def test_inner_payload_without_wrapper(gs):
    # parser also accepts the inner dict directly
    parsed = parse_offscreen_progression(
        {"elapsed": "a while", "beats": [{"npc_ids": ["npc_c"], "focus": "x"}]}, gs
    )
    assert parsed is not None
    assert parsed[0] == "a while"
