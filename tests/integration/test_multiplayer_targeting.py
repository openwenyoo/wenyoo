"""Phase 3 — commit audience resolution (rollout plan §8).

Drives a commit with each audience scope and asserts the resolved delivery
targets recorded on the displayed message (architect._resolve_message_targets).
"""
from __future__ import annotations

import pytest

from tests.helpers.mock_llm_tool_calling import tc


@pytest.fixture
async def three_player_game(game_kernel):
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    gs.add_player("player2")
    gs.add_player("player3")
    return gs, game_kernel.story_manifest


async def _commit_with_audience(game_kernel, mock_tool_llm, gs, story, **artifact):
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "broadcast", **artifact}]),
    ])
    from src.core.architect import ArchitectTask, TASK_PROFILE_WORLD_ACTION
    task = ArchitectTask(
        task_type="player_input", player_input="x",
        task_profile=TASK_PROFILE_WORLD_ACTION,
        extra_context={"suppress_background_materialization": True},
    )
    ctx = await game_kernel.architect.handle(task, gs, "player1", story)
    return ctx["displayed_messages"][0]["target_player_ids"]


async def test_audience_self(game_kernel, mock_tool_llm, three_player_game):
    gs, story = three_player_game
    targets = await _commit_with_audience(game_kernel, mock_tool_llm, gs, story, audience="self")
    assert targets == ["player1"]


async def test_audience_specific_players(game_kernel, mock_tool_llm, three_player_game):
    gs, story = three_player_game
    targets = await _commit_with_audience(
        game_kernel, mock_tool_llm, gs, story,
        audience="specific_players", target_player_ids=["player2"],
    )
    assert targets == ["player2"]


async def test_audience_players_here(game_kernel, mock_tool_llm, three_player_game):
    gs, story = three_player_game
    # all three start at start_node
    targets = await _commit_with_audience(
        game_kernel, mock_tool_llm, gs, story, audience="players_here"
    )
    assert set(targets) == {"player1", "player2", "player3"}


async def test_audience_location_players_filters_by_node(game_kernel, mock_tool_llm, three_player_game):
    gs, story = three_player_game
    gs.move_to_node("branch_node", "player2")   # only player2 leaves
    targets = await _commit_with_audience(
        game_kernel, mock_tool_llm, gs, story,
        audience="location_players", location_id="branch_node",
    )
    assert targets == ["player2"]
