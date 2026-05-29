"""Phase 3 — save/load fidelity (rollout plan §8).

start -> mutate -> save -> load -> state matches (modulo timestamps). All disk
writes land in tmp_path via the ``game_kernel`` fixture's StateManager.
"""
from __future__ import annotations

from tests.helpers.mock_llm_tool_calling import tc


async def test_save_then_load_round_trips_state(game_kernel, mock_tool_llm):
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    story = game_kernel.story_manifest

    # Mutate via a commit so there's non-trivial state to round-trip.
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "ok", "audience": "self"}],
           state_changes={"variables": {"door_open": True, "turns": 3}}),
    ])
    await game_kernel.process_input("open door", gs, story, "player1")

    # save_game_state returns a save *code*; load keys off the state *id*.
    state_id = gs.to_dict()["id"]
    save_code = game_kernel.state_manager.save_game_state(gs)
    assert save_code

    loaded = game_kernel.state_manager.load_game_state(state_id, story)
    assert loaded is not None
    assert loaded.version == gs.version
    assert loaded.variables["door_open"] is True
    assert loaded.variables["turns"] == 3
    assert "player1" in loaded.variables.get("players", {})


async def test_loaded_state_preserves_player_location(game_kernel, mock_tool_llm):
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    story = game_kernel.story_manifest
    gs.move_to_node("branch_node", "player1")

    state_id = gs.to_dict()["id"]
    game_kernel.state_manager.save_game_state(gs)
    loaded = game_kernel.state_manager.load_game_state(state_id, story)
    assert loaded.get_player_location("player1") == "branch_node"
