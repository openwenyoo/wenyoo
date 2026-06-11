"""Integration tests for offscreen world progression.

Drive the real Architect + the OffscreenProgressionRunner with a scripted
ToolCallingMockLLM (no frontend adapter, no wall-clock). A foreground turn
commits an ``offscreen_progression`` structured artifact; the runner fans the
declared beats into small background commits (v1 serial / v2 parallel).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.core.architect import ArchitectTask, TASK_PROFILE_WORLD_ACTION
from src.core.offscreen_progression import OffscreenBatch, OffscreenBeat
from tests.helpers.mock_llm_tool_calling import tc


# ── helpers ───────────────────────────────────────────────────────────────────

async def _start(game_kernel):
    gs = await game_kernel.start_new_game_async("offscreen", "player1", character_id="hero")
    assert gs is not None
    return gs, game_kernel.story_manifest


def _foreground_task(session_id="s1", player_input="I lie down to rest until dawn"):
    return ArchitectTask(
        task_type="player_input",
        player_input=player_input,
        task_profile=TASK_PROFILE_WORLD_ACTION,
        extra_context={"session_id": session_id, "suppress_background_materialization": True},
    )


def _offscreen_payload(beats, elapsed="until the small hours"):
    return {
        "kind": "structured",
        "summary": "offscreen_progression",
        "payload": {"offscreen_progression": {"elapsed": elapsed, "beats": beats}},
    }


_TWO_BEATS = [
    {"npc_ids": ["npc_a", "npc_b"], "focus": "slip away together"},
    {"npc_ids": ["npc_c"], "focus": "prowl the halls"},
]


async def _drain(game_kernel, session_id="s1", timeout=10):
    worker = game_kernel.offscreen_progression._workers.get(session_id)
    if worker is not None:
        await asyncio.wait_for(asyncio.shield(worker), timeout)


def _beat_calls(mock):
    """Captured calls that are offscreen-beat generations (forced tool_choice)."""
    return [c for c in mock.captured_calls() if isinstance(c.tool_choice, dict)]


def _last_user(call):
    for m in reversed(call.messages):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


# ── 1 + 4: fan-out, v1 serial end-to-end, no recursion ──────────────────────────

async def test_v1_fanout_applies_beats_and_no_recursion(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "You lie down; sleep takes you."},
                   _offscreen_payload(_TWO_BEATS)],
        state_changes={"variables": {"rested": True}},
    )])
    # Two beat commits, in declared order (serial v1 = FIFO).
    mock_tool_llm.queue_tool_calls([tc("commit", state_changes={"variables": {"beat_ab": "done"}})])
    mock_tool_llm.queue_tool_calls([tc("commit", state_changes={"variables": {"beat_c": "done"}})])

    ctx = await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)

    # Foreground delivered narrative + recorded the structured artifact.
    assert len(ctx["displayed_messages"]) >= 1
    assert any("offscreen_progression" in (r.get("summary") or "") for r in ctx["structured_results"])
    assert gs.variables.get("rested") is True

    await _drain(game_kernel)

    # Both beats applied.
    assert gs.variables.get("beat_ab") == "done"
    assert gs.variables.get("beat_c") == "done"
    # Exactly 3 LLM calls: foreground + 2 beats (no recursion, no extra passes).
    assert len(mock_tool_llm.captured_calls()) == 3
    # No background-materialization recursion was queued.
    assert not game_kernel.background_materialization._pending_jobs


# ── 2: trivial turn — no payload, no beats ──────────────────────────────────────

async def test_trivial_turn_enqueues_no_beats(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "You glance around."}],
        state_changes={"variables": {"looked": True}},
    )])
    await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)

    assert not game_kernel.offscreen_progression._queues.get("s1")
    assert "s1" not in game_kernel.offscreen_progression._workers
    # Foreground sequence bumped exactly once.
    assert game_kernel.offscreen_progression.current_seq("s1") == 1
    assert len(mock_tool_llm.captured_calls()) == 1


# ── 3: witnessed beat is not deferred ───────────────────────────────────────────

async def test_witnessed_beat_not_enqueued(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    # npc_here is colocated with the player -> beat dropped at parse -> no batch.
    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "You wait."},
                   _offscreen_payload([{"npc_ids": ["npc_here"], "focus": "loiter"}])],
    )])
    await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)
    assert not game_kernel.offscreen_progression._queues.get("s1")
    assert "s1" not in game_kernel.offscreen_progression._workers


# ── 5: a beat that commits nothing leaves state untouched, no fallback ──────────

async def test_beat_commits_nothing(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "You doze off."},
                   _offscreen_payload([{"npc_ids": ["npc_c"], "focus": "nothing to do"}])],
    )])
    # Beat turn returns NO tool calls (empty queue -> bare no-op response).
    await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)
    version_before_drain = gs.version
    await _drain(game_kernel)

    # No state change from the empty beat; no architect fallback for a beat task.
    assert gs.version == version_before_drain
    assert not any(
        (m.get("metadata") or {}).get("event_type") == "architect_fallback"
        for m in gs.message_history
    )


# ── 8: beat prompt carries lore + dossier + sibling + elapsed ───────────────────

async def test_beat_prompt_contract(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "Sleep."}, _offscreen_payload(_TWO_BEATS)],
    )])
    mock_tool_llm.queue_tool_calls([tc("commit", state_changes={"variables": {"x": 1}})])
    mock_tool_llm.queue_tool_calls([tc("commit", state_changes={"variables": {"y": 1}})])
    await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)
    await _drain(game_kernel)

    beat_msgs = [_last_user(c) for c in mock_tool_llm.captured_calls()
                 if "## OFFSCREEN NPC BEAT" in _last_user(c)]
    assert beat_msgs, "no offscreen beat prompt captured"
    # The beat dossier for npc_a/npc_b
    ab = next((m for m in beat_msgs if "Agent A" in m), None)
    assert ab is not None
    assert "## LOREBOOK" in ab                      # lore injected (lore_world_progression)
    assert "When the player rests or waits" in ab   # lore body
    assert "## CHARACTER(S) IN THIS BEAT" in ab
    assert "## OTHER OFFSCREEN EVENTS THIS SPAN" in ab
    assert "until the small hours" in ab            # elapsed span


# ── 6: v2 parallel generation (proven via concurrency barrier) ──────────────────

async def test_v2_parallel_generation(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    game_kernel.offscreen_progression.parallel = True

    mock_tool_llm.queue_tool_calls([tc(
        "commit",
        artifacts=[{"kind": "narrative", "payload": "You rest."}, _offscreen_payload(_TWO_BEATS)],
    )])
    ctx = await game_kernel.architect.handle(_foreground_task(), gs, "player1", story)
    assert len(ctx["displayed_messages"]) >= 1

    # Arm the barrier AFTER the foreground call; route each beat by its UNIQUE
    # header line (character names recur in every prompt's world index, so a
    # name substring would be ambiguous).
    mock_tool_llm.hold_until(2)
    mock_tool_llm.queue_routed_tool_calls(
        "This beat's character(s): npc_a",
        [tc("commit", state_changes={"variables": {"last_beat": "a", "beat_ab": "done"}})])
    mock_tool_llm.queue_routed_tool_calls(
        "This beat's character(s): npc_c",
        [tc("commit", state_changes={"variables": {"last_beat": "c", "beat_c": "done"}})])

    await _drain(game_kernel)  # serial runner would never reach the 2-call barrier -> timeout

    assert gs.variables.get("beat_ab") == "done"
    assert gs.variables.get("beat_c") == "done"
    # Applied serially in declared order: beat_c (second) wins last_beat.
    assert gs.variables.get("last_beat") == "c"
    # Both beat generations used forced commit tool_choice.
    beat_calls = _beat_calls(mock_tool_llm)
    assert len(beat_calls) == 2
    for c in beat_calls:
        assert c.tool_choice == {"type": "function", "function": {"name": "commit"}}
        assert c.tools  # commit tool definitions passed


# ── 7: v2 regenerate-once when a foreground turn interleaves ─────────────────────

async def test_v2_regenerate_on_interleave(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    runner = game_kernel.offscreen_progression
    runner.parallel = True
    runner.note_foreground_commit("s1")  # seq -> 1 (the foreground turn)

    batch = OffscreenBatch(session_id="s1", player_id="player1", elapsed="x",
                           beats=[OffscreenBeat(npc_ids=["npc_c"], focus="prowl")],
                           foreground_seq=1)
    beat, messages = runner._snapshot_beat_prompts(batch, gs)[0]
    seq0 = runner.current_seq("s1")          # 1, captured at snapshot

    runner.note_foreground_commit("s1")      # seq -> 2 : a foreground turn interleaved
    mock_tool_llm.queue_routed_tool_calls(
        "Loner C", [tc("commit", state_changes={"variables": {"npc_c_progress": "done"}})])

    stale = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])
    await runner._apply_parallel_beat(batch, beat, messages, stale, gs, seq0)

    # The stale response was discarded; the regenerated commit applied.
    assert gs.variables.get("npc_c_progress") == "done"


async def test_v2_skip_on_second_interleave(game_kernel, mock_tool_llm):
    gs, story = await _start(game_kernel)
    runner = game_kernel.offscreen_progression
    runner.parallel = True
    runner.note_foreground_commit("s1")  # seq -> 1
    batch = OffscreenBatch(session_id="s1", player_id="player1", elapsed="x",
                           beats=[OffscreenBeat(npc_ids=["npc_c"], focus="prowl")],
                           foreground_seq=1)
    beat = batch.beats[0]

    # A second foreground turn lands DURING regeneration -> skip (return None).
    orig = runner._generate_one_shot

    async def gen_then_bump(messages):
        runner.note_foreground_commit("s1")  # interleave again mid-generation
        return await orig(messages)

    runner._generate_one_shot = gen_then_bump
    mock_tool_llm.queue_routed_tool_calls(
        "Loner C", [tc("commit", state_changes={"variables": {"npc_c_progress": "done"}})])

    result = await runner._regenerate_beat(batch, beat, gs)
    assert result is None
    assert "npc_c_progress" not in gs.variables  # nothing applied
