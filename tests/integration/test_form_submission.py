"""Phase 3 — form lifecycle: present_form -> submit -> on_submit effects (§8)."""
from __future__ import annotations

import pytest


@pytest.fixture
async def form_game(game_kernel):
    gs = await game_kernel.start_new_game_async("with_form", "player1")
    assert gs is not None
    return gs, game_kernel.story_manifest


async def test_present_form_registers_pending(game_kernel, form_game):
    gs, story = form_game
    result = await game_kernel.present_form("sign_in", gs, "player1", story)
    assert result["success"] is True
    assert game_kernel._pending_forms["player1"]["form_id"] == "sign_in"


async def test_submit_stores_variables_and_clears_pending(game_kernel, form_game):
    gs, story = form_game
    await game_kernel.present_form("sign_in", gs, "player1", story)

    result = await game_kernel.process_form_submission(
        "sign_in",
        {"name": "Ada", "color": "blue"},
        {},                     # no files
        gs, "player1", story,
    )
    assert result["success"] is True
    # store_variables: name -> registered_name, color -> chosen_color
    assert gs.variables["registered_name"] == "Ada"
    assert gs.variables["chosen_color"] == "blue"
    # pending form cleared so the player is unblocked
    assert "player1" not in game_kernel._pending_forms


async def test_submit_unknown_form_is_rejected(game_kernel, form_game):
    gs, story = form_game
    result = await game_kernel.process_form_submission(
        "ghost_form", {}, {}, gs, "player1", story
    )
    assert result["success"] is False
