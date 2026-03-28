"""Session management handler."""

import asyncio
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
        persistent_player_to_session: Dict[str, str]
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
        elif msg_type == "load_game":
            return await self._load_game_session(message, player_id, player_name, story_or_template, websocket)
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
        self.player_sessions[player_id]['client_type'] = client_type

        logger.info(f"Creating new game session {session_id}")
        self.game_sessions[session_id] = {
            "game_state": game_state,
            "players": {player_id},
            "lock": asyncio.Lock(),  # Session-level lock for command processing
            "loaded_from_save": False,
            "reserved_player_ids": set(),
        }
        self.game_kernel.start_ticker(session_id)
        self.player_sessions[player_id]["session_id"] = session_id
        self.persistent_player_to_session[player_id] = session_id
        
        await websocket.send_json({"type": "session", "subtype": "created", "session_code": session_id})
        
        await self.websocket_manager.broadcast_to_session(session_id, {
            "type": "multiplayer", "content": f"{player_name} has created and joined the session."
        }, self.player_sessions)

        await self.broadcast_session_players(session_id)

        return session_id

    async def _load_game_session(
        self, 
        message: Dict, 
        player_id: str,
        player_name: str, 
        story_or_template: Any,
        websocket: WebSocket
    ) -> Optional[str]:
        """Load a saved game into a new session.
        
        Args:
            message: The load_game message.
            player_id: The player's ID.
            player_name: The player's name.
            story_or_template: The selected story or template.
            websocket: The player's WebSocket connection.
            
        Returns:
            The new session ID if successful, None otherwise.
        """
        save_code = message.get("save_code")
        logger.info(f"Player {player_id} is loading game with code {save_code}.")
        
        loaded_state_dict = self.game_kernel.state_manager.load_state_by_code(
            save_code, player_name, story_or_template.id
        )

        if not loaded_state_dict:
            await websocket.send_json({
                "type": "error", 
                "content": "Failed to load saved game. Save code may be invalid."
            })
            return None

        game_state = GameState.from_dict(loaded_state_dict, story_or_template)
        if not game_state:
            await websocket.send_json({
                "type": "error", 
                "content": "Failed to initialize game from saved state."
            })
            return None

        client_type = message.get("client_type") or self.player_sessions[player_id].get("client_type", "web")
        self._claim_or_add_player(
            game_state,
            player_id,
            player_name,
            client_type,
            occupied_player_ids=set(),
        )

        session_id = generate_name()
        logger.info(f"Creating new session {session_id} for loaded game.")
        
        self.game_sessions[session_id] = {
            "game_state": game_state,
            "players": {player_id},
            "lock": asyncio.Lock(),  # Session-level lock for command processing
            "loaded_from_save": True,
            "save_slot_id": game_state.save_metadata.get("slot_id"),
            "reserved_player_ids": set(),
        }
        self.game_kernel.start_ticker(session_id)
        self.player_sessions[player_id]["session_id"] = session_id
        self.player_sessions[player_id]["client_type"] = client_type
        self.persistent_player_to_session[player_id] = session_id
        
        await websocket.send_json({"type": "session", "subtype": "joined", "session_code": session_id})
        
        await self.websocket_manager.broadcast_to_session(session_id, {
            "type": "multiplayer", "content": f"{player_name} has loaded a saved game and started the session."
        }, self.player_sessions)

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
        
        await websocket.send_json({"type": "session", "subtype": "joined", "session_code": session_id})
        
        await self.websocket_manager.broadcast_to_session(session_id, {
            "type": "multiplayer", "content": f"{player_name} has joined the session."
        }, self.player_sessions, exclude_player_id=player_id)

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

        await self.websocket_manager.broadcast_to_session(session_id, {
            "type": "multiplayer", "content": f"{player_name} has reconnected."
        }, self.player_sessions, exclude_player_id=player_id)

        await websocket.send_json({"type": "control", "subtype": "rejoin_success"})
        await websocket.send_json({"type": "control", "subtype": "ready_for_state_request"})

        await self.broadcast_session_players(session_id)

        return session_id

    async def cleanup_player_session(self, player_id: str, session_id: str):
        """Clean up after a player disconnects.
        
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

