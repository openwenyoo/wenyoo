"""Phase 3 — kernel ↔ Architect ↔ observer wiring (rollout plan §8).

Correction to the plan: ``_notify_observers`` fires at game start/load
(game_kernel.py:214, 271), NOT once per ``process_input``. During a turn the
frontend adapter delivers narration directly via the Architect; observer
``.update()`` carries state snapshots at lifecycle boundaries. These tests
assert the wiring that actually exists.
"""
from __future__ import annotations

from tests.helpers.mock_llm_tool_calling import tc


class _RecordingObserver:
    def __init__(self):
        self.updates = []

    def update(self, state, session_id=None):
        self.updates.append((state, session_id))


async def test_observer_notified_on_game_start(game_kernel):
    obs = _RecordingObserver()
    game_kernel.register_observer(obs)
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    assert len(obs.updates) == 1
    state, _session = obs.updates[0]
    assert state is gs


async def test_process_input_full_path_mutates_state(game_kernel, mock_tool_llm):
    """input -> Architect -> commit -> state mutation, surfaced in the return."""
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    story = game_kernel.story_manifest
    v0 = gs.version
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "The door creaks open.", "audience": "self"}],
           state_changes={"variables": {"door_open": True}}),
    ])
    result = await game_kernel.process_input("open the door", gs, story, "player1")

    assert gs.variables["door_open"] is True
    assert gs.version == v0 + 1
    assert result["script_paused"] is False
    assert "door" in result["narrative_response"].lower()


async def test_process_input_records_player_message_in_history(game_kernel, mock_tool_llm):
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    story = game_kernel.story_manifest
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "ok", "audience": "self"}]),
    ])
    await game_kernel.process_input("look around", gs, story, "player1")
    assert any(
        (m.get("metadata") or {}).get("event_type") == "player_input"
        for m in gs.message_history
    )
