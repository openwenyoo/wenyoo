"""Background materialization scheduler for deferred world enrichment."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Deque, Dict, Optional, Tuple

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel
    from src.models.game_state import GameState

logger = logging.getLogger(__name__)


@dataclass
class BackgroundMaterializationJob:
    """A deferred world-simulation request queued after an authoritative commit."""

    session_id: str
    player_id: str
    base_version: int
    reason: str
    source_node_id: Optional[str]
    visible_node_id: Optional[str] = None
    local_only: bool = True
    allow_player_facing_narrative: bool = False
    max_new_entities: int = 2
    max_nodes_to_touch: int = 1
    max_actions_to_add: int = 2
    applied_changes: Optional[list[str]] = None


class BackgroundMaterializationScheduler:
    """Queues and runs deferred materialization jobs with per-session serialization."""

    def __init__(self, game_kernel: "GameKernel"):
        self.game_kernel = game_kernel
        self._pending_queues: Dict[str, Deque[Tuple[str, str, Optional[str]]]] = defaultdict(deque)
        self._pending_jobs: Dict[Tuple[str, str, Optional[str]], BackgroundMaterializationJob] = {}
        self._workers: Dict[str, asyncio.Task] = {}

    def enqueue(self, job: BackgroundMaterializationJob) -> bool:
        """Queue a background materialization job, coalescing duplicates."""
        if not self.game_kernel.llm_provider:
            return False
        if not self.game_kernel.frontend_adapter:
            return False
        if not job.session_id:
            return False

        key = self._make_key(job)
        was_new = key not in self._pending_jobs
        self._pending_jobs[key] = job
        if was_new:
            self._pending_queues[job.session_id].append(key)
            logger.debug(
                "Queued background materialization job %s for session %s",
                key,
                job.session_id,
            )

        worker = self._workers.get(job.session_id)
        if worker is None or worker.done():
            self._workers[job.session_id] = asyncio.create_task(
                self._run_worker(job.session_id),
                name=f"background-materialization-{job.session_id}",
            )
        return True

    def _make_key(self, job: BackgroundMaterializationJob) -> Tuple[str, str, Optional[str]]:
        """Build a coalescing key for a job."""
        if job.local_only:
            scope = job.visible_node_id or job.source_node_id or job.player_id
        else:
            scope = None
        return (job.session_id, job.reason, scope)

    async def _run_worker(self, session_id: str) -> None:
        """Run queued jobs for a session one at a time."""
        try:
            queue = self._pending_queues[session_id]
            while queue:
                key = queue.popleft()
                job = self._pending_jobs.pop(key, None)
                if not job:
                    continue
                try:
                    await self._process_job(job)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Background materialization job failed for session %s: %s",
                        session_id,
                        exc,
                        exc_info=True,
                    )
        finally:
            self._pending_queues.pop(session_id, None)
            self._workers.pop(session_id, None)

    async def _process_job(self, job: BackgroundMaterializationJob) -> None:
        """Run one queued job while respecting the session lock."""
        frontend = self.game_kernel.frontend_adapter
        if not frontend:
            return

        session_entry = frontend.game_sessions.get(job.session_id)
        if not session_entry:
            return

        session_lock = session_entry.get("lock")
        if session_lock:
            async with session_lock:
                await self._process_locked_job(job, session_entry.get("game_state"))
        else:
            await self._process_locked_job(job, session_entry.get("game_state"))

    async def _process_locked_job(
        self,
        job: BackgroundMaterializationJob,
        game_state: Optional["GameState"],
    ) -> None:
        """Process a job after acquiring any relevant session lock."""
        if not game_state:
            return

        current_location = game_state.get_player_location(job.player_id)
        if job.local_only and job.source_node_id and current_location != job.source_node_id:
            logger.debug(
                "Skipping local background materialization for %s: player moved from %s to %s",
                job.player_id,
                job.source_node_id,
                current_location,
            )
            return

        if game_state.version != job.base_version:
            logger.debug(
                "Skipping stale background materialization for session %s: base=%s current=%s",
                job.session_id,
                job.base_version,
                game_state.version,
            )
            return

        from src.core.architect import ArchitectTask

        extra_context = {
            "session_id": job.session_id,
            "background_materialization": True,
            "background_materialization_reason": job.reason,
            "background_source_node_id": job.source_node_id,
            "background_visible_node_id": job.visible_node_id or job.source_node_id,
            "background_local_only": job.local_only,
            "background_allow_player_facing_narrative": job.allow_player_facing_narrative,
            "background_base_version": job.base_version,
            "background_budget": {
                "max_new_entities": job.max_new_entities,
                "max_nodes_to_touch": job.max_nodes_to_touch,
                "max_actions_to_add": job.max_actions_to_add,
            },
            "background_applied_changes": list(job.applied_changes or []),
            # Avoid recursively scheduling another deferred pass from this one.
            "suppress_background_materialization": True,
        }

        task = ArchitectTask(
            task_type="background_materialization",
            node_id=job.source_node_id,
            extra_context=extra_context,
        )

        pre_version = game_state.version
        await self.game_kernel.architect.handle(
            task,
            game_state,
            job.player_id,
            self.game_kernel.story_manifest or game_state.story,
        )
        if game_state.version == pre_version:
            return

        if job.local_only:
            visible_node_id = job.visible_node_id or job.source_node_id
            if visible_node_id:
                await self._push_local_updates(game_state, job.session_id, visible_node_id)

    async def _push_local_updates(
        self,
        game_state: "GameState",
        session_id: str,
        location_id: str,
    ) -> None:
        """Push updated local state to connected players who can currently perceive it."""
        frontend = self.game_kernel.frontend_adapter
        if not frontend:
            return

        player_ids = frontend._get_player_ids_in_location(session_id, location_id)
        if not player_ids:
            return

        await self.game_kernel.architect._push_state_to_players(game_state, player_ids)
        for player_id in player_ids:
            await self.game_kernel._push_characters_update(game_state, player_id, location_id)
