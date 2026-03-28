"""
Ticker service for managing timed events in the game engine.
Handles background processing of delayed effects and scheduled events.
"""

import asyncio
import time
import logging
from typing import Dict, TYPE_CHECKING, Any, Optional

from src.models.story_models import TimedEvent

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel

logger = logging.getLogger(__name__)


class TickerService:
    """Manages timed events and background processing for game sessions."""

    def __init__(self, game_kernel: 'GameKernel'):
        """
        Initialize the ticker service.
        
        Args:
            game_kernel: Reference to the main game kernel
        """
        self.game_kernel = game_kernel
        self.session_tickers: Dict[str, asyncio.Task] = {}

    def _resolve_actor_player_id(
        self,
        event: TimedEvent,
        session_entry: Dict[str, Any],
        game_state: Any,
    ) -> Optional[str]:
        """Pick a live player ID to anchor Architect event processing."""
        active_players = list(session_entry.get("players") or [])

        if event.player_id in active_players:
            return event.player_id

        if event.scope == "player" and event.player_id and event.player_id not in game_state.variables.get("players", {}):
            logger.warning(
                "Dropping player-scoped timed event %s because player %s is no longer active",
                event.id,
                event.player_id,
            )
            return None

        if active_players:
            return active_players[0]

        saved_players = list((game_state.variables.get("players") or {}).keys())
        return saved_players[0] if saved_players else None

    def _build_timed_event_context(self, event: TimedEvent) -> str:
        """Build a compact human-readable event instruction for the Architect."""
        if event.event_context:
            return event.event_context

        if event.object_id and event.rule_id:
            return (
                f"Timed rule '{event.rule_id}' has triggered for object '{event.object_id}'. "
                "Apply the intended delayed state change and narrate it only to players "
                "who can currently perceive it."
            )

        return "A timed event has triggered. Resolve it as an authoritative world event."

    @staticmethod
    def _format_timed_event_for_prompt(event: TimedEvent, event_location: str | None) -> str:
        """Render a single structured block the Architect can parse easily."""
        import json as _json

        lines = [
            f"id: {event.id}",
            f"event_type: {event.event_type}",
            f"scope: {event.scope}",
        ]
        if event.object_id:
            lines.append(f"object_id: {event.object_id}")
        if event.rule_id:
            lines.append(f"rule_id: {event.rule_id}")
        if event.player_id:
            lines.append(f"source_player_id: {event.player_id}")
        if event_location:
            lines.append(f"location_id: {event_location}")
        if event.audience:
            lines.append(f"audience: {event.audience}")
        if event.intended_state_changes:
            lines.append(f"intended_state_changes: {_json.dumps(event.intended_state_changes, default=str)}")
        return "\n".join(lines)

    async def _process_locked_tick(self, session_id: str, session_entry: Dict[str, Any]) -> None:
        """Process one timer tick after acquiring any relevant session lock."""
        game_state = session_entry.get("game_state")
        if not game_state or not game_state.timed_events:
            return

        now = time.time()
        triggered_events = []
        for event_data in list(game_state.timed_events):
            event = TimedEvent(**event_data)
            if now >= event.trigger_timestamp:
                logger.info(
                    "Event %s triggered for player %s in session %s",
                    event.id,
                    event.player_id,
                    session_id,
                )
                triggered_events.append((event, event_data))

        if not triggered_events:
            return

        story = self.game_kernel._get_story(game_state.story_id)
        if not story:
            logger.error(
                "Could not load story %s for timed event processing.",
                game_state.story_id,
            )
            return

        from src.core.architect import ArchitectTask

        for event, event_data in triggered_events:
            actor_player_id = self._resolve_actor_player_id(event, session_entry, game_state)
            if not actor_player_id:
                if event_data in game_state.timed_events:
                    game_state.timed_events.remove(event_data)
                continue

            event_location = event.location_id or event.node_id
            timed_event_summary = self._format_timed_event_for_prompt(event, event_location)

            extra_context = {
                "session_id": session_id,
                "timed_event": timed_event_summary,
                "suppress_background_materialization": True,
            }
            task = ArchitectTask(
                task_type="process_event",
                event_context=self._build_timed_event_context(event),
                extra_context=extra_context,
            )

            pre_version = game_state.version
            try:
                await self.game_kernel.architect.handle(
                    task,
                    game_state,
                    actor_player_id,
                    story,
                )
            except Exception:
                logger.exception(
                    "Architect failed to process timed event %s in session %s; "
                    "event will retry on next tick",
                    event.id,
                    session_id,
                )
                continue

            if event_data in game_state.timed_events:
                game_state.timed_events.remove(event_data)
            if game_state.version != pre_version:
                self.game_kernel._notify_observers(game_state, session_id)

    async def _run_game_ticker_async(self, session_id: str):
        """
        The game ticker for processing timed events.
        
        Runs continuously, checking for and executing timed events every second.
        
        Args:
            session_id: The session ID to run the ticker for
        """
        logger.info(f"Starting game ticker for session {session_id}")
        while True:
            await asyncio.sleep(1)
            
            frontend_adapter = self.game_kernel.frontend_adapter
            if not frontend_adapter or session_id not in frontend_adapter.game_sessions:
                logger.warning(f"Ticker for session {session_id} stopping: session not found.")
                break

            session_entry = frontend_adapter.game_sessions[session_id]
            session_lock = session_entry.get("lock")
            if session_lock:
                async with session_lock:
                    await self._process_locked_tick(session_id, session_entry)
            else:
                await self._process_locked_tick(session_id, session_entry)

    def start_ticker(self, session_id: str):
        """
        Start the game ticker for a specific session.
        
        Args:
            session_id: The session ID to start the ticker for
        """
        if session_id not in self.session_tickers:
            task = asyncio.create_task(self._run_game_ticker_async(session_id))
            self.session_tickers[session_id] = task
            logger.info(f"Ticker task created for session {session_id}: {task}")

    def stop_ticker(self, session_id: str):
        """
        Stop the game ticker for a specific session.
        
        Args:
            session_id: The session ID to stop the ticker for
        """
        logger.info(f"Attempting to stop ticker for session {session_id}")
        if session_id in self.session_tickers:
            task = self.session_tickers[session_id]
            task.cancel()
            del self.session_tickers[session_id]
            logger.info(f"Stopped and removed ticker task for session {session_id}: {task}")
        else:
            logger.warning(f"No ticker task found for session {session_id} to stop.")

