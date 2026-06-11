"""Offscreen world progression — advance NPCs during time-passing player actions.

When a foreground turn's commit carries a structured ``offscreen_progression``
artifact, the engine queues a batch of small per-NPC "beats". Each beat is a
``backgroundSimulation`` task that commits one minimal state change describing
what that NPC (or coordinated NPC group) did during the elapsed in-fiction span,
while the player was occupied. The player already has their foreground response;
beats run behind the session lock and surface as discoverable world state.

Engine-agnostic: Python only understands "structured artifact -> batch of NPC
beats". WHO does WHAT over an interval lives entirely in the story's ``lore_*``
variables, which the Architect reads when resolving each beat.

Two execution modes:
- v1 (default / fallback): beats run serially through the normal agentic
  ``architect.handle`` loop, one at a time under the session lock.
- v2 (``offscreen_parallel`` config, needs forced tool_choice support): all
  beat prompts are snapshotted under the lock, generated concurrently outside
  it via one-shot forced-``commit`` calls, then applied serially under the lock.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel
    from src.models.game_state import GameState

logger = logging.getLogger(__name__)

MAX_BEATS_PER_BATCH = 4
MAX_NPCS_PER_BEAT = 3


@dataclass
class OffscreenBeat:
    """One offscreen action by a single NPC or a coordinated NPC group."""

    npc_ids: List[str]
    focus: str
    perceptible: bool = False  # TODO(perceptible-cues): emit one oblique ambient line for nearby players


@dataclass
class OffscreenBatch:
    """All offscreen beats declared by a single foreground turn."""

    session_id: str
    player_id: str
    elapsed: str
    beats: List[OffscreenBeat]
    foreground_seq: int = 0
    base_version: int = 0


def parse_offscreen_progression(
    payload: Any, game_state: "GameState"
) -> Optional[Tuple[str, List[OffscreenBeat]]]:
    """Validate a foreground ``offscreen_progression`` payload into beats.

    Returns ``(elapsed, beats)`` or ``None`` if nothing valid remains. Never
    raises — malformed input yields ``None``. Drops unknown NPC ids and beats
    whose NPCs are currently co-located with a player (witnessed events resolve
    in the foreground), dedupes NPCs across beats, and clamps sizes.
    """
    if not isinstance(payload, dict):
        return None
    prog = payload.get("offscreen_progression", payload)
    if not isinstance(prog, dict):
        return None
    raw_beats = prog.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats:
        return None
    elapsed = str(prog.get("elapsed") or "").strip()

    known_ids = set(game_state.character_states.keys())
    # Nodes currently occupied by a player — beats touching these are witnessed.
    player_nodes = {
        game_state.get_player_location(pid)
        for pid in game_state.variables.get("players", {})
    }
    player_nodes.discard(None)

    seen_npcs: set = set()
    beats: List[OffscreenBeat] = []
    for raw in raw_beats:
        if len(beats) >= MAX_BEATS_PER_BATCH:
            logger.debug("offscreen: clamped beats to %d", MAX_BEATS_PER_BATCH)
            break
        if not isinstance(raw, dict):
            continue
        ids = raw.get("npc_ids")
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list):
            continue
        focus = str(raw.get("focus") or "").strip()
        if not focus:
            continue

        clean_ids: List[str] = []
        witnessed = False
        for npc_id in ids:
            if not isinstance(npc_id, str):
                continue
            if npc_id not in known_ids:
                logger.debug("offscreen: dropping unknown npc '%s'", npc_id)
                continue
            if npc_id in seen_npcs:
                continue  # an NPC may appear in at most one beat
            loc = game_state.get_character_location(npc_id)
            if loc and loc in player_nodes:
                witnessed = True
                break
            clean_ids.append(npc_id)
            if len(clean_ids) >= MAX_NPCS_PER_BEAT:
                break
        if witnessed:
            logger.debug("offscreen: dropping witnessed beat %s", ids)
            continue
        if not clean_ids:
            continue
        seen_npcs.update(clean_ids)
        beats.append(OffscreenBeat(npc_ids=clean_ids, focus=focus,
                                   perceptible=bool(raw.get("perceptible"))))

    if not beats:
        return None
    return elapsed, beats


class OffscreenProgressionRunner:
    """Queues and runs offscreen NPC beats with per-session serialization."""

    def __init__(self, game_kernel: "GameKernel"):
        self.game_kernel = game_kernel
        self.parallel: bool = False  # set from config; v2 path
        self._queues: Dict[str, Deque[OffscreenBatch]] = defaultdict(deque)
        self._workers: Dict[str, asyncio.Task] = {}
        self._foreground_seq: Dict[str, int] = defaultdict(int)

    def note_foreground_commit(self, session_id: str) -> None:
        """Mark that a foreground turn committed; used to detect interleaving."""
        if session_id:
            self._foreground_seq[session_id] += 1

    def current_seq(self, session_id: str) -> int:
        return self._foreground_seq.get(session_id, 0)

    def enqueue_batch(self, batch: OffscreenBatch) -> bool:
        """Queue a batch of beats; spawn the per-session worker if needed."""
        if not self.game_kernel.llm_provider:
            return False
        if not batch.session_id or not batch.beats:
            return False

        batch.foreground_seq = self._foreground_seq.get(batch.session_id, 0)
        self._queues[batch.session_id].append(batch)
        logger.debug(
            "offscreen: queued batch (%d beats) for session %s",
            len(batch.beats),
            batch.session_id,
        )

        worker = self._workers.get(batch.session_id)
        if worker is None or worker.done():
            self._workers[batch.session_id] = asyncio.create_task(
                self._run_worker(batch.session_id),
                name=f"offscreen-progression-{batch.session_id}",
            )
        return True

    # ── session resolution (works with or without a frontend adapter) ──

    def _resolve_session(self, session_id: str) -> Tuple[Optional["GameState"], Optional[asyncio.Lock]]:
        frontend = self.game_kernel.frontend_adapter
        if frontend:
            session_entry = frontend.game_sessions.get(session_id)
            if session_entry:
                return session_entry.get("game_state"), session_entry.get("lock")
        # Headless (tests): fall back to the kernel's current game state, no lock.
        return self.game_kernel.current_game_state, None

    async def _run_worker(self, session_id: str) -> None:
        """Drain queued batches for a session, one batch at a time."""
        try:
            queue = self._queues[session_id]
            while queue:
                batch = queue.popleft()
                try:
                    await self._run_batch(batch)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "offscreen: batch failed for session %s: %s",
                        session_id,
                        exc,
                        exc_info=True,
                    )
        finally:
            self._queues.pop(session_id, None)
            self._workers.pop(session_id, None)

    async def _run_batch(self, batch: OffscreenBatch) -> None:
        game_state, lock = self._resolve_session(batch.session_id)
        if not game_state:
            return
        provider = self.game_kernel.llm_provider
        can_parallel = self.parallel and self._provider_supports_forced_choice(provider)
        if can_parallel:
            await self._run_batch_parallel(batch, game_state, lock)
        else:
            await self._run_batch_serial(batch, game_state, lock)

    @staticmethod
    def _provider_supports_forced_choice(provider) -> bool:
        # base (OpenAI-compatible) and claude map forced tool_choice; ollama has
        # no async_client. The mock test provider accepts any tool_choice.
        return provider is not None and getattr(provider, "async_client", None) is not None

    # ── v1: serial beats via the normal agentic loop ──

    async def _run_batch_serial(
        self, batch: OffscreenBatch, game_state: "GameState", lock: Optional[asyncio.Lock]
    ) -> None:
        affected_nodes: set = set()
        for beat in batch.beats:
            if lock:
                async with lock:
                    changed = await self._run_beat_serial(batch, beat, game_state)
            else:
                changed = await self._run_beat_serial(batch, beat, game_state)
            affected_nodes |= changed
        await self._push_batch_updates(game_state, batch.session_id, affected_nodes)

    async def _run_beat_serial(
        self, batch: OffscreenBatch, beat: OffscreenBeat, game_state: "GameState"
    ) -> set:
        """Run one beat through architect.handle; return nodes whose state changed."""
        if self._beat_witnessed(game_state, beat):
            logger.debug("offscreen: beat now witnessed, skipping %s", beat.npc_ids)
            return set()

        before = self._npc_nodes(game_state, beat.npc_ids)
        pre_version = game_state.version

        from src.core.architect import ArchitectTask, infer_task_profile

        task = ArchitectTask(
            task_type="offscreen_npc_beat",
            task_profile=infer_task_profile("offscreen_npc_beat"),
            extra_context=self._beat_extra_context(batch, beat),
        )
        await self.game_kernel.architect.handle(
            task,
            game_state,
            batch.player_id,
            self.game_kernel.story_manifest or game_state.story,
        )
        if game_state.version == pre_version:
            return set()
        after = self._npc_nodes(game_state, beat.npc_ids)
        return before | after

    # ── v2: parallel generation, serial application ──

    async def _run_batch_parallel(
        self, batch: OffscreenBatch, game_state: "GameState", lock: Optional[asyncio.Lock]
    ) -> None:
        # 1) Snapshot each beat's prompt under the lock (cheap, no LLM).
        if lock:
            async with lock:
                snapshots = self._snapshot_beat_prompts(batch, game_state)
                seq0 = self._foreground_seq.get(batch.session_id, 0)
        else:
            snapshots = self._snapshot_beat_prompts(batch, game_state)
            seq0 = self._foreground_seq.get(batch.session_id, 0)

        # 2) Generate all beats concurrently OUTSIDE the lock.
        responses = await asyncio.gather(
            *[self._generate_one_shot(messages) for (_, messages) in snapshots],
            return_exceptions=True,
        )

        # 3) Apply serially under the lock, in declared order.
        affected_nodes: set = set()
        for (beat, messages), response in zip(snapshots, responses):
            if lock:
                async with lock:
                    changed = await self._apply_parallel_beat(
                        batch, beat, messages, response, game_state, seq0
                    )
            else:
                changed = await self._apply_parallel_beat(
                    batch, beat, messages, response, game_state, seq0
                )
            affected_nodes |= changed
        await self._push_batch_updates(game_state, batch.session_id, affected_nodes)

    def _snapshot_beat_prompts(
        self, batch: OffscreenBatch, game_state: "GameState"
    ) -> List[Tuple[OffscreenBeat, List[dict]]]:
        architect = self.game_kernel.architect
        story = self.game_kernel.story_manifest or game_state.story
        system_prompt = architect._get_system_prompt()
        snapshots: List[Tuple[OffscreenBeat, List[dict]]] = []
        from src.core.architect import ArchitectTask, infer_task_profile

        for beat in batch.beats:
            task = ArchitectTask(
                task_type="offscreen_npc_beat",
                task_profile=infer_task_profile("offscreen_npc_beat"),
                extra_context=self._beat_extra_context(batch, beat),
            )
            world_index = architect._build_world_index(game_state, batch.player_id, story)
            user_prompt = architect._build_task_prompt(task, world_index, game_state, batch.player_id)
            snapshots.append((beat, [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]))
        return snapshots

    async def _generate_one_shot(self, messages: List[dict]):
        provider = self.game_kernel.llm_provider
        return await provider.async_client.chat.completions.create(
            model=provider.model,
            messages=messages,
            tools=self.game_kernel.architect._tool_definitions,
            tool_choice={"type": "function", "function": {"name": "commit"}},
        )

    async def _apply_parallel_beat(
        self,
        batch: OffscreenBatch,
        beat: OffscreenBeat,
        messages: List[dict],
        response,
        game_state: "GameState",
        seq0: int,
    ) -> set:
        if isinstance(response, Exception):
            logger.warning("offscreen: beat generation failed %s: %s", beat.npc_ids, response)
            return set()
        if self._beat_witnessed(game_state, beat):
            logger.debug("offscreen: beat now witnessed, skipping %s", beat.npc_ids)
            return set()

        # If a foreground turn interleaved during generation, regenerate once
        # against fresh state (sibling-beat version bumps do NOT count).
        if self._foreground_seq.get(batch.session_id, 0) != seq0:
            logger.debug("offscreen: foreground interleaved, regenerating beat %s", beat.npc_ids)
            regen = await self._regenerate_beat(batch, beat, game_state)
            if regen is None:
                return set()
            response = regen

        tool_calls = getattr(response.choices[0].message, "tool_calls", None) or []
        before = self._npc_nodes(game_state, beat.npc_ids)
        pre_version = game_state.version
        ctx = self._beat_ctx(batch, beat, game_state)
        for tool_call in tool_calls:
            if tool_call.function.name != "commit":
                continue
            await self.game_kernel.architect._dispatch_tool(tool_call, ctx)
        if game_state.version == pre_version:
            return set()
        after = self._npc_nodes(game_state, beat.npc_ids)
        return before | after

    async def _regenerate_beat(self, batch: OffscreenBatch, beat: OffscreenBeat, game_state: "GameState"):
        """One serial regeneration against current state; None if still stale."""
        seq_now = self._foreground_seq.get(batch.session_id, 0)
        snapshots = self._snapshot_beat_prompts(batch, game_state)
        messages = next((m for (b, m) in snapshots if b is beat), None)
        if messages is None:
            return None
        response = await self._generate_one_shot(messages)
        if self._foreground_seq.get(batch.session_id, 0) != seq_now:
            logger.debug("offscreen: foreground interleaved again, skipping beat %s", beat.npc_ids)
            return None
        return response

    # ── shared helpers ──

    def _beat_extra_context(self, batch: OffscreenBatch, beat: OffscreenBeat) -> Dict[str, Any]:
        siblings = [
            {"npc_ids": b.npc_ids, "focus": b.focus}
            for b in batch.beats if b is not beat
        ]
        return {
            "session_id": batch.session_id,
            "offscreen_beat": True,
            # Recursion guards: a beat must never schedule more beats or
            # background materialization.
            "suppress_background_materialization": True,
            # delivery.py defaults this True; beats are state-only.
            "background_allow_player_facing_narrative": False,
            "offscreen_elapsed": batch.elapsed,
            "offscreen_npc_ids": list(beat.npc_ids),
            "offscreen_focus": beat.focus,
            "offscreen_sibling_beats": siblings,
        }

    def _beat_ctx(self, batch: OffscreenBatch, beat: OffscreenBeat, game_state: "GameState") -> Dict[str, Any]:
        from src.core.architect.task import TASK_PROFILE_BACKGROUND_SIMULATION

        ctx: Dict[str, Any] = {
            "game_state": game_state,
            "player_id": batch.player_id,
            "story": self.game_kernel.story_manifest or game_state.story,
            "displayed_messages": [],
            "world_events": [],
            "structured_results": [],
            "artifacts": [],
            "task_type": "offscreen_npc_beat",
            "task_profile": TASK_PROFILE_BACKGROUND_SIMULATION,
        }
        ctx.update(self._beat_extra_context(batch, beat))
        return ctx

    @staticmethod
    def _beat_witnessed(game_state: "GameState", beat: OffscreenBeat) -> bool:
        for npc_id in beat.npc_ids:
            loc = game_state.get_character_location(npc_id)
            if loc and game_state.get_players_in_location(loc):
                return True
        return False

    @staticmethod
    def _npc_nodes(game_state: "GameState", npc_ids: List[str]) -> set:
        nodes = set()
        for npc_id in npc_ids:
            loc = game_state.get_character_location(npc_id)
            if loc:
                nodes.add(loc)
        return nodes

    async def _push_batch_updates(
        self, game_state: "GameState", session_id: str, affected_nodes: set
    ) -> None:
        """Notify observers and push local state to players in changed nodes."""
        if not affected_nodes:
            return
        self.game_kernel._notify_observers(game_state, session_id)
        frontend = self.game_kernel.frontend_adapter
        if not frontend:
            return
        # TODO(perceptible-cues): for beats flagged perceptible, also deliver one
        # short oblique sensory line to players in adjacent/same nodes here.
        for node_id in affected_nodes:
            player_ids = frontend._get_player_ids_in_location(session_id, node_id)
            if not player_ids:
                continue
            await self.game_kernel.architect._push_state_to_players(game_state, player_ids)
            for player_id in player_ids:
                await self.game_kernel._push_characters_update(game_state, player_id, node_id)
