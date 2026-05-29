"""Phase 2 — Pydantic validators that gate authored input (rollout plan §7)."""
from __future__ import annotations

import pytest

from src.models.story_models import (
    FormField,
    StoryAction,
    StoryCondition,
    load_story_from_file,
)


# ── StoryAction validators ──────────────────────────────────────────────────────

def test_action_description_maps_to_text():
    a = StoryAction(id="a1", description="Open the gate")
    assert a.text == "Open the gate"


def test_action_keywords_are_dropped():
    # legacy 'keywords' field is stripped by the before-validator
    a = StoryAction(id="a1", text="x", keywords=["foo", "bar"])
    assert not hasattr(a, "keywords")


def test_action_explicit_text_wins_over_description():
    a = StoryAction(id="a1", text="T", description="D")
    assert a.text == "T"


# ── StoryCondition validators + evaluate ────────────────────────────────────────

def test_state_condition_requires_variable():
    with pytest.raises(ValueError, match="variable is required"):
        StoryCondition(type="state")


def test_state_condition_with_variable_ok():
    c = StoryCondition(type="state", variable="door_open")
    assert c.variable == "door_open"


async def test_variable_condition_evaluates_against_game_state(started_game):
    gs, _ = started_game
    cond = StoryCondition(type="variable", variable="door_open", operator="eq", value=True)
    # tiny.yaml seeds door_open=False
    ok, _resp = cond.evaluate(gs, "player1")
    assert ok is False
    gs.variables["door_open"] = True
    ok, _resp = cond.evaluate(gs, "player1")
    assert ok is True


# ── FormField normalization ─────────────────────────────────────────────────────

def test_form_field_string_options_normalized():
    f = FormField(id="color", type="select", label="Color", options=["red", "green"])
    dumped = f.model_dump()
    assert dumped["options"][0]["value"] == "red"
    assert dumped["options"][0]["text"] == "red"


def test_form_field_defaults():
    f = FormField(id="name", type="text", label="Name")
    assert f.required is False
    assert f.rows == 4


# ── Loader ──────────────────────────────────────────────────────────────────────

def test_load_story_from_file_parses_nested_entities(stories_dir):
    story = load_story_from_file(str(stories_dir / "tiny.yaml"))
    start = story.nodes["start_node"]
    assert start.objects[0].id == "entity_a"
    assert start.actions[0].intent.startswith("Open the door")
    branch = story.nodes["branch_node"]
    assert branch.triggers[0].conditions[0].variable == "door_open"


def test_load_story_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_story_from_file(str(tmp_path / "nope.yaml"))
