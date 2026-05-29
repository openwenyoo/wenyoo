"""Phase 4 — one e2e WebSocket round-trip through the real FastAPI app (§9).

This is the ONLY phase that exercises the Architect's STREAMING path: the
adapter sets ``game_kernel.frontend_adapter``, so the Architect takes the
``_streaming_llm_call`` branch (architect.py:528) and consumes the streaming
half of the Phase-0 shim. The queued commit's ``arguments`` stream across >=2
chunks, driving the narrative stream extractor end-to-end.

Covered wiring: WS handshake -> register -> pregame (name/story/session) ->
GameKernel.start_new_game -> game_start -> input -> Architect (streaming) ->
commit -> delivery back over the socket. The test is synchronous: TestClient
drives its own event loop, sidestepping pytest-asyncio loop scoping.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.adapters.web_frontend_adapter import WebFrontendAdapter
from src.core.game_kernel import GameKernel
from src.core.state_manager import StateManager
from src.core.story_manager import StoryManager
from tests.helpers.mock_llm_tool_calling import ToolCallingMockLLM, tc

NARRATIVE = "The iron bell tolls twice."


@pytest.fixture
def wired_app(tmp_path):
    stories_dir = __import__("pathlib").Path(__file__).parent.parent / "fixtures" / "stories"
    save_dir = tmp_path / "saves"
    static_dir = tmp_path / "static"
    static_dir.mkdir()

    mock = ToolCallingMockLLM(model="mock")
    sm = StoryManager(stories_dir=str(stories_dir))
    state_mgr = StateManager(save_dir=str(save_dir))
    gk = GameKernel(sm, state_mgr, mock)

    adapter = WebFrontendAdapter(
        host="127.0.0.1",
        port=0,
        static_dir=str(static_dir),
        game_kernel=gk,
        story_manager=sm,
        editor_secret="",
    )
    gk.frontend_adapter = adapter
    gk.register_observer(adapter)

    return TestClient(adapter.app), adapter, mock, save_dir


def _recv_until(ws, predicate, *, limit=60):
    """Receive messages until one satisfies predicate; return (match, all_seen)."""
    seen = []
    for _ in range(limit):
        msg = ws.receive_json()
        seen.append(msg)
        if predicate(msg):
            return msg, seen
    return None, seen


def test_full_turn_streams_narrative_over_websocket(wired_app):
    client, adapter, mock, save_dir = wired_app

    with client.websocket_connect("/ws") as ws:
        # 1. Register a brand-new player.
        ws.send_json({"type": "register_or_rejoin", "player_id": "test_player"})
        registered, _ = _recv_until(ws, lambda m: m.get("type") == "registered")
        assert registered is not None
        assert registered["player_id"] == "test_player"

        # 2. Pregame: name + story selection (no response expected for name).
        ws.send_json({"type": "set_player_name", "name": "Tester"})
        ws.send_json({"type": "select_story", "story_id": "tiny"})
        # select_story -> story_info then session_selection control messages.
        _recv_until(ws, lambda m: m.get("subtype") == "session_selection")

        # 3. Create the session -> start_new_game -> initial perception render
        #    -> game_start. The startup render REQUIRES the Architect to return
        #    text (get_node_perception raises otherwise), so queue a commit for
        #    it BEFORE creating the session.
        mock.queue_tool_calls([
            tc("commit", artifacts=[{"kind": "narrative",
                                     "payload": "You stand in the start room.",
                                     "audience": "self"}]),
        ])
        ws.send_json({"type": "create_session", "client_type": "web"})
        game_start, _ = _recv_until(ws, lambda m: m.get("type") == "game_start")
        assert game_start is not None

        # 4. Queue the input turn's response, THEN send player input.
        mock.queue_tool_calls([
            tc("commit",
               artifacts=[{"kind": "narrative", "payload": NARRATIVE, "audience": "self"}],
               state_changes={"variables": {"door_open": True}}),
        ])
        ws.send_json({"type": "input", "content": "open the door"})

        # 5. The narrative must come back over the socket (streamed tokens and/or
        #    a final game message all carry the text).
        match, seen = _recv_until(ws, lambda m: NARRATIVE in json.dumps(m, ensure_ascii=False))
        assert match is not None, f"narrative never arrived; saw types={[m.get('type') for m in seen]}"

        # 6. Capture state WHILE connected — disconnecting tears the session down.
        assert adapter.game_sessions, "no game session was created"
        gs = next(iter(adapter.game_sessions.values()))["game_state"]
        assert gs.variables.get("door_open") is True   # state advanced through the real kernel
        assert gs.version >= 1

    # Registration wrote the player-token file under save_dir (not a global path):
    # concrete proof the §11 isolation concern is a non-issue here.
    assert (save_dir / "player_tokens.json").exists()
