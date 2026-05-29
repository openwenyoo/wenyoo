"""Phase 1 — Architect contract tests (test-harness-rollout.md §6).

Each test drives the real Architect tool-calling loop with a scripted
``ToolCallingMockLLM`` and asserts ONE load-bearing invariant. The kernel has no
frontend adapter, so the Architect runs its non-streaming path (intended). We
drive via ``architect.handle(...)`` directly so we can pin ``task_profile``.

Determinism note: commit-based tests pass ``suppress_background_materialization``
so the post-commit fire-and-forget background pass can't bump ``version`` out
from under the assertion.
"""
from __future__ import annotations

import json

from src.core.architect import (
    ArchitectTask,
    TASK_PROFILE_BACKGROUND_SIMULATION,
    TASK_PROFILE_PERCEPTION_RENDER,
    TASK_PROFILE_WORLD_ACTION,
)
from tests.helpers.mock_llm_tool_calling import tc


# ── helpers ───────────────────────────────────────────────────────────────────

async def _handle(game_kernel, gs, story, task):
    return await game_kernel.architect.handle(task, gs, "player1", story)


def _world_action(player_input="do something", **extra):
    extra.setdefault("suppress_background_materialization", True)
    return ArchitectTask(
        task_type="player_input",
        player_input=player_input,
        task_profile=TASK_PROFILE_WORLD_ACTION,
        extra_context=extra,
    )


def _narrative_artifacts(ctx):
    return [a for a in ctx["artifacts"] if a["kind"] == "narrative"]


def _has_fallback(gs):
    return any(
        (m.get("metadata") or {}).get("event_type") == "architect_fallback"
        for m in gs.message_history
    )


# ── 1 ──────────────────────────────────────────────────────────────────────────

async def test_world_action_must_produce_narrative_or_form(game_kernel, mock_tool_llm, started_game):
    """A worldAction player_input that ends with no commit/present_form emits a
    synthetic fallback message (architect.py:430-445)."""
    gs, story = started_game
    # Empty queue -> first LLM turn returns no tool_calls and no content.
    await _handle(game_kernel, gs, story, _world_action())
    assert _has_fallback(gs), "expected an architect_fallback message in history"


# ── 2 ──────────────────────────────────────────────────────────────────────────

async def test_bare_text_response_becomes_synthetic_artifact(game_kernel, mock_tool_llm, started_game):
    """Bare text (content, no tool_calls) becomes exactly one narrative artifact
    (architect.py:554-576)."""
    gs, story = started_game
    mock_tool_llm.queue_text("The wind shifts quietly.")
    ctx = await _handle(game_kernel, gs, story, _world_action())
    narratives = _narrative_artifacts(ctx)
    assert len(narratives) == 1
    assert narratives[0]["payload"] == "The wind shifts quietly."


# ── 3 ──────────────────────────────────────────────────────────────────────────

async def test_commit_applies_state_and_artifacts_atomically(game_kernel, mock_tool_llm, started_game):
    """One commit with both state_changes and artifacts bumps version exactly
    once and records the artifact exactly once (architect.py:1703)."""
    gs, story = started_game
    v0 = gs.version
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "You push the door."}],
           state_changes={"variables": {"turns": 1}}),
    ])
    ctx = await _handle(game_kernel, gs, story, _world_action())

    assert gs.version == v0 + 1            # exactly one bump
    assert gs.variables["turns"] == 1
    assert len(_narrative_artifacts(ctx)) == 1


# ── 4 ──────────────────────────────────────────────────────────────────────────

async def test_merge_patch_replaces_arrays_not_append(game_kernel, mock_tool_llm, started_game):
    gs, story = started_game
    gs.variables["mylist"] = [3, 4, 5]
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "x"}],
           state_changes={"variables": {"mylist": [1, 2]}}),
    ])
    await _handle(game_kernel, gs, story, _world_action())
    assert gs.variables["mylist"] == [1, 2]


# ── 5 ──────────────────────────────────────────────────────────────────────────

async def test_merge_patch_null_deletes_key(game_kernel, mock_tool_llm, started_game):
    gs, story = started_game
    gs.variables["doomed"] = True
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "x"}],
           state_changes={"variables": {"doomed": None}}),  # JSON null
    ])
    await _handle(game_kernel, gs, story, _world_action())
    assert "doomed" not in gs.variables


# ── 6 ──────────────────────────────────────────────────────────────────────────

async def test_perception_render_strips_node_state_writes(game_kernel, mock_tool_llm, started_game):
    """perceptionRender runs with capture_only=True (as production sets it,
    game_kernel.py:328); node.state writes are stripped (architect.py:1738-1762)."""
    gs, story = started_game
    before = gs.nodes["start_node"].state
    task = ArchitectTask(
        task_type="render_perception",
        task_profile=TASK_PROFILE_PERCEPTION_RENDER,
        extra_context={"capture_only": True},
    )
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "You look around."}],
           state_changes={"nodes": {"start_node": {"state": "SHOULD BE IGNORED"}}}),
    ])
    await _handle(game_kernel, gs, story, task)
    assert gs.nodes["start_node"].state == before


# ── 7 ──────────────────────────────────────────────────────────────────────────

async def test_background_simulation_suppresses_narrative_delivery(game_kernel, mock_tool_llm, started_game):
    """backgroundSimulation with allow_player_facing_narrative=False (the
    background job default, background_materialization.py:29) records the
    narrative artifact but does NOT deliver it to displayed_messages
    (architect.py:1881)."""
    gs, story = started_game
    task = ArchitectTask(
        task_type="background_materialization",
        task_profile=TASK_PROFILE_BACKGROUND_SIMULATION,
        extra_context={
            "background_allow_player_facing_narrative": False,
            "background_materialization": True,  # avoid re-scheduling
        },
    )
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "Off-screen, rain falls."}]),
    ])
    ctx = await _handle(game_kernel, gs, story, task)
    assert len(_narrative_artifacts(ctx)) == 1          # recorded
    assert ctx["displayed_messages"] == []              # but not delivered


# ── 8 ──────────────────────────────────────────────────────────────────────────

async def test_loop_terminates_at_max_iterations(game_kernel, mock_tool_llm, started_game):
    """20 non-terminal read_game_state calls -> the loop breaks at
    max_iterations=12 (architect.py:527), no exception."""
    gs, story = started_game
    for _ in range(20):
        mock_tool_llm.queue_tool_calls([tc("read_game_state", view="local")])
    await _handle(game_kernel, gs, story, _world_action())
    # One LLM round-trip per iteration; capped at 12.
    assert len(mock_tool_llm.captured_calls()) == 12
    assert _has_fallback(gs)


# ── 9 ──────────────────────────────────────────────────────────────────────────

async def test_commit_world_event_legacy_shim_delegates_to_commit(game_kernel, mock_tool_llm):
    """commit_world_event(narrative=...) yields the same version bump and
    narrative artifact as the equivalent commit (architect.py:1992)."""
    # Game A: new-style commit.
    gs_a = await game_kernel.start_new_game_async("tiny", "player1")
    story = game_kernel.story_manifest
    va0 = gs_a.version
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "A bell rings."}]),
    ])
    ctx_a = await _handle(game_kernel, gs_a, story, _world_action())

    # Game B: legacy commit_world_event.
    gs_b = await game_kernel.start_new_game_async("tiny", "player1")
    vb0 = gs_b.version
    mock_tool_llm.queue_tool_calls([
        tc("commit_world_event", narrative="A bell rings."),
    ])
    ctx_b = await _handle(game_kernel, gs_b, story, _world_action())

    assert (gs_a.version - va0) == (gs_b.version - vb0)
    a, b = _narrative_artifacts(ctx_a), _narrative_artifacts(ctx_b)
    assert len(a) == len(b) == 1
    assert a[0]["payload"] == b[0]["payload"] == "A bell rings."


# ── 10 ─────────────────────────────────────────────────────────────────────────

async def test_form_pending_blocks_subsequent_input(game_kernel, mock_tool_llm, started_game):
    """With the player in _pending_forms, process_input returns early
    (script_paused) without entering the Architect loop (game_kernel.py:719)."""
    gs, story = started_game
    game_kernel._pending_forms["player1"] = {"form_id": "sign_in"}
    result = await game_kernel.process_input("anything", gs, story, "player1")
    assert result.get("script_paused") is True
    assert mock_tool_llm.captured_calls() == []         # Architect never invoked


# ── Suggested extras (rollout plan §6) ──────────────────────────────────────────

async def test_json_repair_recovers_truncated_args(game_kernel, mock_tool_llm, started_game):
    """Truncated tool args (missing closing braces) are repaired by _repair_json
    and the tool still executes (architect.py:717, dispatch :783-793)."""
    gs, story = started_game
    truncated = '{"artifacts":[{"kind":"narrative","payload":"hi"}]'  # missing final }
    mock_tool_llm.queue_tool_calls([
        {"id": "call_trunc", "type": "function",
         "function": {"name": "commit", "arguments": truncated}},
    ])
    ctx = await _handle(game_kernel, gs, story, _world_action())
    narratives = _narrative_artifacts(ctx)
    assert len(narratives) == 1 and narratives[0]["payload"] == "hi"


async def test_unknown_tool_returns_error_and_loop_recovers(game_kernel, mock_tool_llm, started_game):
    """An unknown tool yields an {'error': ...} result (not a crash); the loop
    continues and a later commit still delivers."""
    gs, story = started_game
    mock_tool_llm.queue_tool_calls([tc("no_such_tool", foo="bar")])
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "recovered"}]),
    ])
    ctx = await _handle(game_kernel, gs, story, _world_action())
    assert any(a["payload"] == "recovered" for a in _narrative_artifacts(ctx))


async def test_early_exit_after_commit_and_terminal_tools(game_kernel, mock_tool_llm, started_game):
    """commit + roll_dice in one turn -> early exit; a second queued commit is
    never consumed (architect.py:638-648)."""
    gs, story = started_game
    v0 = gs.version
    # First commit carries a state change so version bumps exactly once; if the
    # second (never-consumed) commit ran it would bump again.
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "done"}],
           state_changes={"variables": {"turns": 1}}),
        tc("roll_dice", dice="1d20", reason="check"),
    ])
    mock_tool_llm.queue_tool_calls([
        tc("commit",
           artifacts=[{"kind": "narrative", "payload": "SHOULD NOT RUN"}],
           state_changes={"variables": {"turns": 99}}),
    ])
    await _handle(game_kernel, gs, story, _world_action())
    assert len(mock_tool_llm.captured_calls()) == 1     # single round-trip
    assert gs.version == v0 + 1                          # only the first commit applied
    assert gs.variables["turns"] == 1                    # not 99
