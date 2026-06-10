"""Deterministic `set_controlled_character` form effect (engine-executed).

These tests exercise the engine path that switches which character a player
embodies when a form's on_submit contains a `set_controlled_character` effect,
including despawning the previous "shell" character. All LLM-free.
"""
from __future__ import annotations

import pytest

from src.models.story_models import Effect
from src.core.game_kernel import GameKernel


@pytest.fixture
async def role_game(game_kernel):
    # Start controlling the faceless shell, as the pregame handler would.
    gs = await game_kernel.start_new_game_async(
        "role_select", "player1", character_id="shell"
    )
    assert gs is not None
    assert gs.get_controlled_character_id("player1") == "shell"
    return gs, game_kernel.story_manifest


async def _submit_role(game_kernel, gs, story, role):
    await game_kernel.present_form("pick_role", gs, "player1", story)
    return await game_kernel.process_form_submission(
        "pick_role", {"chosen_role": role}, {}, gs, "player1", story
    )


async def test_takeover_switches_pointer_and_location(game_kernel, role_game):
    gs, story = role_game
    result = await _submit_role(game_kernel, gs, story, "knight")

    assert result["success"] is True
    # pointer switched to the chosen named character
    assert gs.get_controlled_character_id("player1") == "knight"
    # player location synced to the character's location (no goto_node needed)
    assert gs.variables["players"]["player1"]["location"] == "hall"
    # store_variables still ran
    assert gs.variables["chosen_role"] == "knight"
    # pending form cleared
    assert "player1" not in game_kernel._pending_forms


async def test_shell_is_despawned_and_absent_from_node(game_kernel, role_game):
    gs, story = role_game
    await _submit_role(game_kernel, gs, story, "knight")

    # shell removed from the runtime world entirely
    assert "shell" not in gs.character_states
    assert "shell" not in gs.get_characters_in_node("intro")
    assert "shell" not in gs.get_npcs_in_node("intro")
    # the taken-over character is hidden from NPC listings (it's player-controlled)
    assert "knight" not in gs.get_npcs_in_node("hall")
    assert "knight" in gs.get_characters_in_node("hall")


async def test_inventory_hydrated_on_takeover(game_kernel, role_game):
    gs, story = role_game
    await _submit_role(game_kernel, gs, story, "knight")

    inv = gs.character_states["knight"]["properties"].get("inventory", [])
    # the iron_sword object id should have been hydrated into the inventory
    ids = [getattr(i, "id", i.get("id") if isinstance(i, dict) else i) for i in inv]
    assert "iron_sword" in ids


async def test_visited_nodes_updated(game_kernel, role_game):
    gs, story = role_game
    await _submit_role(game_kernel, gs, story, "mage")
    assert "hall" in gs.visited_nodes


async def test_unknown_target_is_graceful_noop(game_kernel, role_game):
    gs, story = role_game
    # Patch the pending form's on_submit to point at a non-existent character.
    await game_kernel.present_form("pick_role", gs, "player1", story)
    form_ctx = game_kernel._pending_forms["player1"]
    form_ctx["on_submit_override"] = form_ctx["form_def"].on_submit.model_copy(
        update={
            "effects": [
                Effect(type="set_controlled_character", target="ghost", despawn_previous=True)
            ]
        }
    )
    result = await game_kernel.process_form_submission(
        "pick_role", {"chosen_role": "ghost"}, {}, gs, "player1", story
    )
    # Submission still succeeds; pointer unchanged; shell not despawned.
    assert result["success"] is True
    assert gs.get_controlled_character_id("player1") == "shell"
    assert "shell" in gs.character_states


async def test_no_steal_from_other_player(game_kernel, role_game):
    gs, story = role_game
    # player2 already controls knight
    p2_char = story.get_character("knight")
    gs.set_player_character("player2", p2_char)
    assert gs.get_controlled_character_id("player2") == "knight"

    await _submit_role(game_kernel, gs, story, "knight")

    # player1 was refused; player2 keeps knight; player1 still on shell
    assert gs.get_controlled_character_id("player2") == "knight"
    assert gs.get_controlled_character_id("player1") == "shell"


async def test_literal_target_without_substitution(game_kernel, role_game):
    gs, story = role_game
    await game_kernel.present_form("pick_role", gs, "player1", story)
    form_ctx = game_kernel._pending_forms["player1"]
    form_ctx["on_submit_override"] = form_ctx["form_def"].on_submit.model_copy(
        update={
            "effects": [
                Effect(type="set_controlled_character", target="mage", despawn_previous=True)
            ]
        }
    )
    await game_kernel.process_form_submission(
        "pick_role", {"chosen_role": "mage"}, {}, gs, "player1", story
    )
    assert gs.get_controlled_character_id("player1") == "mage"


def test_summary_marks_applied_effect():
    from src.models.story_models import FormOnSubmit

    eff = Effect(type="set_controlled_character", target="knight", despawn_previous=True)
    on_submit = FormOnSubmit(effects=[eff])
    summary = GameKernel._summarize_on_submit(on_submit, [eff])
    assert "ALREADY APPLIED BY ENGINE" in summary

    # Not applied -> no marker
    summary_none = GameKernel._summarize_on_submit(on_submit, [])
    assert "ALREADY APPLIED" not in summary_none


def test_effect_model_parses_despawn_previous():
    eff = Effect(type="set_controlled_character", target="x", despawn_previous=True)
    assert eff.despawn_previous is True
    # default is False
    assert Effect(type="goto_node", target="y").despawn_previous is False
