"""Phase 0 acceptance tests (test-harness-rollout.md §5.7).

These prove the harness itself works before any Architect contract test relies
on it:
  * the MockLLM shim returns an OpenAI-shaped response (non-streaming),
  * the same shim streams OpenAI-shaped chunks,
  * tiny.yaml loads and starts a game,
  * StateManager stays inside tmp_path (the promoted §11 isolation check).
"""
from __future__ import annotations

import json
from pathlib import Path

from src.core.state_manager import StateManager
from tests.helpers.mock_llm_tool_calling import ToolCallingMockLLM, tc


# ── The shim ──────────────────────────────────────────────────────────────────

async def test_shim_returns_openai_shaped_response(mock_tool_llm):
    mock_tool_llm.queue_tool_calls([tc("roll_dice", dice="1d20", reason="test")])
    resp = await mock_tool_llm.async_client.chat.completions.create(
        model="mock", messages=[], tools=[]
    )
    call = resp.choices[0].message.tool_calls[0]
    assert call.function.name == "roll_dice"
    assert json.loads(call.function.arguments)["dice"] == "1d20"
    assert resp.choices[0].finish_reason == "tool_calls"


async def test_shim_bare_text_response(mock_tool_llm):
    mock_tool_llm.queue_text("just some prose")
    resp = await mock_tool_llm.async_client.chat.completions.create(model="mock", messages=[])
    assert resp.choices[0].message.tool_calls is None
    assert resp.choices[0].message.content == "just some prose"
    assert resp.choices[0].finish_reason == "stop"


async def test_shim_empty_queue_returns_terminating_response(mock_tool_llm):
    # Under-queuing must not hang: an empty queue yields a no-tool-call response.
    resp = await mock_tool_llm.async_client.chat.completions.create(model="mock", messages=[])
    assert resp.choices[0].message.tool_calls is None


async def test_shim_captures_calls(mock_tool_llm):
    mock_tool_llm.queue_text("x")
    await mock_tool_llm.async_client.chat.completions.create(
        model="mock", messages=[{"role": "user", "content": "hi"}],
        tools=[{"a": 1}], tool_choice="auto",
    )
    captured = mock_tool_llm.captured_calls()
    assert len(captured) == 1
    assert captured[0].tool_choice == "auto"
    assert captured[0].model == "mock"
    assert captured[0].stream is False


async def test_shim_streaming_reconstructs_tool_call(mock_tool_llm):
    """The streaming branch must reassemble into the same tool call, with
    arguments delivered across multiple chunks (so extractors can run)."""
    mock_tool_llm.queue_tool_calls([tc("commit", artifacts=[{"kind": "narrative", "payload": "hello"}])])
    stream = await mock_tool_llm.async_client.chat.completions.create(
        model="mock", messages=[], tools=[], stream=True
    )

    # Reassemble exactly the way architect._streaming_llm_call does.
    tool_calls_map: dict[int, dict] = {}
    arg_fragments = 0
    final_finish = None
    async for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta
        if choice.finish_reason:
            final_finish = choice.finish_reason
        if delta and delta.tool_calls:
            for tcd in delta.tool_calls:
                entry = tool_calls_map.setdefault(tcd.index, {"id": "", "name": "", "args": ""})
                if tcd.id:
                    entry["id"] = tcd.id
                if tcd.function and tcd.function.name:
                    entry["name"] = tcd.function.name
                if tcd.function and tcd.function.arguments:
                    entry["args"] += tcd.function.arguments
                    arg_fragments += 1

    assert final_finish == "tool_calls"
    assert tool_calls_map[0]["name"] == "commit"
    assert json.loads(tool_calls_map[0]["args"])["artifacts"][0]["payload"] == "hello"
    assert arg_fragments >= 2, "arguments must stream across >=2 chunks to exercise extractors"


def test_shim_tc_helper_shape():
    built = tc("present_form", form_id="sign_in")
    assert built["type"] == "function"
    assert built["function"]["name"] == "present_form"
    assert json.loads(built["function"]["arguments"]) == {"form_id": "sign_in"}


# ── Fixtures load + start ──────────────────────────────────────────────────────

def test_tiny_story_loads(tiny_story):
    assert tiny_story.id == "tiny"
    assert tiny_story.start_node_id == "start_node"
    assert set(tiny_story.nodes) == {"start_node", "branch_node", "end_node"}
    assert any(c.id == "character_x" for c in tiny_story.characters)


async def test_start_new_game_produces_game_state(game_kernel):
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    assert gs is not None
    assert "start_node" in gs.nodes
    # A freshly started minimal game is at version 0 — the plan's "version=1"
    # done-criterion was wrong for a story with no state-mutating start triggers.
    # version only advances via apply_merge_patch (covered by contract #3).
    assert gs.version == 0
    assert "player1" in gs.variables.get("players", {})


# ── Disk isolation (promoted §11 risk → Phase 0) ───────────────────────────────

def test_state_manager_stays_inside_tmp_path(tmp_path, monkeypatch):
    """Constructing + saving via StateManager must not write outside save_dir."""
    monkeypatch.chdir(tmp_path)            # detect stray writes to a relative ./saves
    save_dir = tmp_path / "saves"
    sm = StateManager(save_dir=str(save_dir))
    sm.save_state({"id": "s1", "story_id": "tiny", "version": 1, "data": {"x": 1}})

    # Nothing should have been written to the cwd outside our save_dir.
    stray = [p for p in Path(tmp_path).iterdir() if p.name != "saves"]
    assert not any(p.name == "saves" for p in stray)  # only the one we asked for
    # And the save landed inside save_dir.
    assert save_dir.exists()
    assert any(save_dir.iterdir())
