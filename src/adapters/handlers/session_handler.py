"""Session management handler."""

import asyncio
import copy
from fastapi import WebSocket
from typing import Dict, Any, Optional
import logging

from src.models.game_state import GameState
from src.models.story_models import Story
from src.utils.name_generator import generate_name

logger = logging.getLogger(__name__)


class SessionHandler:
    """Handles session creation, joining, and cleanup."""
    
    def __init__(
        self,
        game_kernel: Any,
        websocket_manager: Any,
        game_sessions: Dict[str, Dict[str, Any]],
        player_sessions: Dict[str, Dict[str, Any]],
        persistent_player_to_session: Dict[str, str],
        frontend_adapter: Any = None,
    ):
        """Initialize the session handler.
        
        Args:
            game_kernel: The game kernel instance.
            websocket_manager: The WebSocket manager instance.
            game_sessions: Dict of active game sessions.
            player_sessions: Dict of player sessions.
            persistent_player_to_session: Dict mapping player IDs to session IDs.
        """
        self.game_kernel = game_kernel
        self.websocket_manager = websocket_manager
        self.game_sessions = game_sessions
        self.player_sessions = player_sessions
        self.persistent_player_to_session = persistent_player_to_session
        self.frontend_adapter = frontend_adapter

    def _claim_or_add_player(
        self,
        game_state: GameState,
        player_id: str,
        player_name: str,
        client_type: str,
        defaults: Optional[Dict[str, Any]] = None,
        occupied_player_ids: Optional[set] = None,
    ) -> None:
        """Claim a saved participant slot when possible, else add a fresh player entry."""
        claimed_player_id = game_state.claim_next_saved_participant(
            player_id,
            player_name=player_name,
            client_type=client_type,
            occupied_player_ids=occupied_player_ids,
        )
        if claimed_player_id:
            player_state = game_state.variables.setdefault("players", {}).setdefault(claimed_player_id, {})
            player_state["name"] = player_name
            player_state["client_type"] = client_type
            game_state.ensure_save_metadata()
            return

        if player_id not in game_state.variables.get("players", {}):
            game_state.add_player(player_id, defaults=defaults)

        player_state = game_state.variables.setdefault("players", {}).setdefault(player_id, {})
        player_state["name"] = player_name
        player_state["client_type"] = client_type
        game_state.ensure_save_metadata()

    async def broadcast_session_players(self, session_id: str) -> None:
        """Broadcast the current session's player list to all connected clients."""
        if not session_id or session_id not in self.game_sessions:
            return

        players = []
        for pid in self.game_sessions[session_id]["players"]:
            if not self.websocket_manager.is_connected(pid):
                continue
            session_data = self.player_sessions.get(pid, {})
            player_name = session_data.get("name")
            if player_name:
                players.append({"id": pid, "name": player_name})

        await self.websocket_manager.broadcast_to_session(session_id, {
            "type": "session_players",
            "players": players
        }, self.player_sessions)

    async def handle_session_selection(
        self, 
        websocket: WebSocket, 
        player_id: str, 
        story_or_template: Any, 
        initial_message: Optional[Dict] = None
    ) -> Optional[str]:
        """Handle session selection (create, join, or load).
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            story_or_template: The selected story or template.
            initial_message: Optional initial message to process.
            
        Returns:
            The session ID if successful, None otherwise.
        """
        player_name = self.player_sessions[player_id].get('name')

        if initial_message:
            return await self._process_session_message(initial_message, player_id, player_name, story_or_template, websocket)
        else:
            import json
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                session_id = await self._process_session_message(message, player_id, player_name, story_or_template, websocket)
                if session_id:
                    return session_id

    async def _process_session_message(
        self, 
        message: Dict, 
        player_id: str,
        player_name: str, 
        story_or_template: Any,
        websocket: WebSocket
    ) -> Optional[str]:
        """Process a session-related message.
        
        Args:
            message: The message to process.
            player_id: The player's ID.
            player_name: The player's name.
            story_or_template: The selected story or template.
            websocket: The player's WebSocket connection.
            
        Returns:
            The session ID if a session was created/joined, None otherwise.
        """
        msg_type = message.get("type")
        
        if msg_type == "create_session":
            return await self._create_session(message, player_id, player_name, story_or_template, websocket)
        elif msg_type == "join_session":
            return await self._join_session(message, player_id, player_name, websocket)
        
        return None

    async def _create_session(
        self, 
        message: Dict, 
        player_id: str,
        player_name: str, 
        story_or_template: Any,
        websocket: WebSocket
    ) -> Optional[str]:
        """Create a new game session.
        
        Args:
            message: The create_session message.
            player_id: The player's ID.
            player_name: The player's name.
            story_or_template: The selected story or template.
            websocket: The player's WebSocket connection.
            
        Returns:
            The new session ID if successful, None otherwise.
        """
        client_type = message.get("client_type", "web")
        session_id = generate_name()
        logger.info(f"Player {player_id} is creating session {session_id} with client_type: {client_type}.")
        
        game_state = None
        if isinstance(story_or_template, Story):
            character_id = message.get("character_id")
            game_state = await self.game_kernel.start_new_game_async(
                story_or_template.id,
                player_id,
                session_id=session_id,
                character_id=character_id,
                notify_observers=False,
            )

        if not game_state:
            await websocket.send_json({"type": "error", "content": "Failed to start new game."})
            return None

        game_state.variables['players'][player_id]['name'] = player_name
        game_state.variables['players'][player_id]['client_type'] = client_type
        game_state.save_metadata["room_id"] = session_id
        self.player_sessions[player_id]['client_type'] = client_type

        logger.info(f"Creating new game session {session_id}")
        self.game_sessions[session_id] = {
            "game_state": game_state,
            "players": {player_id},
            "lock": asyncio.Lock(),  # Session-level lock for command processing
            "loaded_from_save": False,
            "reserved_player_ids": set(),
            "pending_forms": {},
        }
        self.game_kernel.start_ticker(session_id)
        self.player_sessions[player_id]["session_id"] = session_id
        self.persistent_player_to_session[player_id] = session_id
        if self.frontend_adapter:
            self.frontend_adapter._persist_room_snapshot(session_id, status="active")
        
        await websocket.send_json({"type": "session", "subtype": "created", "session_code": session_id})
        
        if self.frontend_adapter:
            await self.frontend_adapter.send_game_message(
                f"{player_name} has created and joined the session.",
                player_id,
                message_type="multiplayer",
                audience_scope="session",
                session_id=session_id,
            )

        await self.broadcast_session_players(session_id)

        return session_id

    async def _join_session(
        self, 
        message: Dict, 
        player_id: str,
        player_name: str, 
        websocket: WebSocket
    ) -> Optional[str]:
        """Join an existing session.
        
        Args:
            message: The join_session message.
            player_id: The player's ID.
            player_name: The player's name.
            websocket: The player's WebSocket connection.
            
        Returns:
            The session ID if successful, None otherwise.
        """
        session_id = message.get("session_code")
        logger.info(f"Player {player_id} is joining session {session_id}.")

        if session_id not in self.game_sessions and self.frontend_adapter:
            self.frontend_adapter._activate_persisted_room(session_id)

        if session_id not in self.game_sessions:
            logger.warning(f"Player {player_id} failed to join session {session_id} (not found).")
            await websocket.send_json({"type": "session", "subtype": "error", "message": "Session not found."})
            return None

        selected_story = self.player_sessions.get(player_id, {}).get("selected_story")
        session_story = self.game_sessions[session_id]["game_state"].story
        selected_story_id = getattr(selected_story, "id", None)
        if selected_story_id and selected_story_id != session_story.id:
            await websocket.send_json({
                "type": "session",
                "subtype": "error",
                "message": "This session is running a different story."
            })
            return None

        self.game_sessions[session_id]["players"].add(player_id)
        self.game_sessions[session_id].setdefault("reserved_player_ids", set()).discard(player_id)
        self.player_sessions[player_id]["session_id"] = session_id
        client_type = message.get("client_type") or self.player_sessions[player_id].get("client_type", "web")
        self.player_sessions[player_id]["client_type"] = client_type
        self.persistent_player_to_session[player_id] = session_id

        game_state = self.game_sessions[session_id]["game_state"]
        defaults = game_state.story.player_character_defaults
        defaults_dict = None
        if isinstance(defaults, str):
            defaults_dict = self.game_kernel.lua_runtime.execute_script_with_return(defaults, player_id, game_state)
        elif isinstance(defaults, dict):
            defaults_dict = defaults

        self._claim_or_add_player(
            game_state,
            player_id,
            player_name,
            client_type,
            defaults=defaults_dict,
            occupied_player_ids=(
                self.game_sessions[session_id]["players"] - {player_id}
            ) | self.game_sessions[session_id].setdefault("reserved_player_ids", set()),
        )
        if self.frontend_adapter:
            self.frontend_adapter._restore_pending_form_for_player(session_id, player_id)
        self.game_kernel.start_ticker(session_id)
        if self.frontend_adapter:
            self.frontend_adapter._persist_room_snapshot(session_id, status="active")
        
        await websocket.send_json({"type": "session", "subtype": "joined", "session_code": session_id})
        
        if self.frontend_adapter:
            await self.frontend_adapter.send_game_message(
                f"{player_name} has joined the session.",
                player_id,
                message_type="multiplayer",
                audience_scope="session",
                session_id=session_id,
                exclude_player_ids=[player_id],
            )

        await self.broadcast_session_players(session_id)

        return session_id

    async def handle_rejoin_session(
        self, 
        websocket: WebSocket, 
        player_id: str, 
        session_id: str
    ) -> Optional[str]:
        """Handle a player rejoining a session.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID to rejoin.
            
        Returns:
            The session ID if successful, None otherwise.
        """
        logger.info(f"Player {player_id} attempting to rejoin session {session_id}.")
        
        if session_id not in self.game_sessions:
            logger.warning(f"Rejoin failed: Session {session_id} not found.")
            await websocket.send_json({"type": "error", "content": "Session not found. Starting fresh."})
            return None

        game_state = self.game_sessions[session_id]["game_state"]
        
        if player_id not in game_state.variables.get('players', {}):
            logger.warning(f"Rejoin failed: Player {player_id} not found in session {session_id}.")
            await websocket.send_json({"type": "error", "content": "Player not found in session. Starting fresh."})
            return None
            
        player_state = game_state.variables['players'][player_id]
        player_name = player_state.get('name', 'A Player')
        client_type = player_state.get('client_type', 'web')
        await self.websocket_manager.connect(websocket, player_id)
        self.player_sessions[player_id] = {
            "name": player_name,
            "session_id": session_id,
            "websocket": websocket,
            "client_type": client_type,
        }
        self.game_sessions[session_id]["players"].add(player_id)
        self.game_sessions[session_id].setdefault("reserved_player_ids", set()).discard(player_id)

        logger.info(f"Player {player_name} ({player_id}) reconnected to session {session_id}.")

        if self.frontend_adapter:
            await self.frontend_adapter.send_game_message(
                f"{player_name} has reconnected.",
                player_id,
                message_type="multiplayer",
                audience_scope="session",
                session_id=session_id,
                exclude_player_ids=[player_id],
            )

        await websocket.send_json({"type": "control", "subtype": "rejoin_success"})
        await websocket.send_json({"type": "control", "subtype": "ready_for_state_request"})

        await self.broadcast_session_players(session_id)

        return session_id

    async def cleanup_player_session(self, player_id: str, session_id: str):
        """Legacy destructive cleanup path.
        
        Args:
            player_id: The player's ID.
            session_id: The session ID.
        """
        logger.info(f"Starting cleanup for player {player_id}, session {session_id}")
        
        player_name = self.player_sessions.get(player_id, {}).get('name', 'A player')
        
        # Remove player from the persistent mapping
        if player_id in self.persistent_player_to_session:
            del self.persistent_player_to_session[player_id]

        # Remove player from player_sessions
        if player_id in self.player_sessions:
            del self.player_sessions[player_id]
            logger.info(f"Cleaned up session data for player {player_id}")

        if session_id and session_id in self.game_sessions:
            game_state = self.game_sessions[session_id]["game_state"]
            self.game_sessions[session_id]["players"].discard(player_id)
            self.game_sessions[session_id].setdefault("reserved_player_ids", set()).discard(player_id)
            game_state.remove_player(player_id, drop_timed_events=True)
            logger.info(f"Removed player {player_id} from session {session_id}")

            await self.websocket_manager.broadcast_to_session(session_id, {
                "type": "multiplayer", "content": f"{player_name} has left the session."
            }, self.player_sessions)

            # Clean up empty sessions
            if not self.game_sessions[session_id]["players"]:
                logger.info(f"Session {session_id} is now empty, cleaning up.")
                self.game_kernel.stop_ticker(session_id)
                del self.game_sessions[session_id]
                logger.info(f"Session {session_id} has been removed.")
            else:
                logger.info(f"Session {session_id} still has {len(self.game_sessions[session_id]['players'])} players.")
                await self.broadcast_session_players(session_id)

    async def detach_player_from_room(
        self,
        player_id: str,
        session_id: str,
        *,
        clear_persistent_mapping: bool = False,
        announce: bool = True,
    ) -> None:
        """Detach a live player connection from a room without deleting membership."""
        logger.info("Detaching player %s from room %s", player_id, session_id)

        if clear_persistent_mapping:
            self.persistent_player_to_session.pop(player_id, None)

        session_data = self.player_sessions.get(player_id)
        player_name = (session_data or {}).get("name", "A player")
        if session_data:
            session_data.pop("session_id", None)
            session_data.pop("websocket", None)

        if not session_id or session_id not in self.game_sessions:
            return

        session_entry = self.game_sessions[session_id]
        pending_form = self.game_kernel._pending_forms.pop(player_id, None)
        if pending_form:
            on_submit_override = pending_form.get("on_submit_override")
            session_entry.setdefault("pending_forms", {})[player_id] = {
                "form_id": pending_form.get("form_id"),
                "prefill": dict(pending_form.get("prefill") or {}),
                "on_submit_override": (
                    on_submit_override.dict()
                    if hasattr(on_submit_override, "dict")
                    else copy.deepcopy(on_submit_override)
                ),
            }
        else:
            session_entry.setdefault("pending_forms", {}).pop(player_id, None)
        session_entry["players"].discard(player_id)
        session_entry.setdefault("reserved_player_ids", set()).discard(player_id)

        if announce and self.frontend_adapter:
            await self.frontend_adapter.send_game_message(
                f"{player_name} has left the room.",
                player_id,
                message_type="multiplayer",
                audience_scope="session",
                session_id=session_id,
                exclude_player_ids=[player_id],
            )

        if not session_entry["players"]:
            logger.info("No connected players remain in room %s; archiving.", session_id)
            if self.frontend_adapter:
                self.frontend_adapter._archive_room(session_id)
            return

        if self.frontend_adapter:
            self.frontend_adapter._schedule_room_autosave(session_id)
        await self.broadcast_session_players(session_id)

    async def delete_room(self, room_id: str) -> bool:
        """Delete a persistent room and any active in-memory copy."""
        logger.info("Deleting room %s", room_id)

        if self.frontend_adapter:
            self.frontend_adapter._cancel_room_autosave(room_id)
        if room_id in self.game_sessions:
            self.game_kernel.stop_ticker(room_id)
            del self.game_sessions[room_id]

        for player_id, mapped_room_id in list(self.persistent_player_to_session.items()):
            if mapped_room_id == room_id:
                del self.persistent_player_to_session[player_id]

        affected_player_ids = []
        for player_id, session_data in self.player_sessions.items():
            if session_data.get("session_id") == room_id:
                session_data.pop("session_id", None)
                affected_player_ids.append(player_id)

        for player_id in affected_player_ids:
            self.game_kernel._pending_forms.pop(player_id, None)

        return self.game_kernel.state_manager.delete_persistent_room(room_id)

