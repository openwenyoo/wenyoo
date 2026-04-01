"""Pre-game setup handler."""

from fastapi import WebSocket
from typing import Dict, Any, Optional
import logging

from ..utils.game_state_serializer import build_game_state_dict, format_stories_list

logger = logging.getLogger(__name__)


class PregameHandler:
    """Handles pre-game setup flow (story selection, auto character assignment)."""
    
    def __init__(
        self,
        game_kernel: Any,
        story_manager: Any,
        session_handler: Any,
        game_sessions: Dict[str, Dict[str, Any]],
        player_sessions: Dict[str, Dict[str, Any]],
        frontend_adapter: Any = None
    ):
        """Initialize the pregame handler.
        
        Args:
            game_kernel: The game kernel instance.
            story_manager: The story manager instance.
            session_handler: The session handler instance.
            game_sessions: Dict of active game sessions.
            player_sessions: Dict of player sessions.
            frontend_adapter: The parent frontend adapter (for client formatting).
        """
        self.game_kernel = game_kernel
        self.story_manager = story_manager
        self.session_handler = session_handler
        self.game_sessions = game_sessions
        self.player_sessions = player_sessions
        self.frontend_adapter = frontend_adapter

    def _should_auto_assign_character(self, player_id: str, session_id: str, character: Any) -> bool:
        """Only auto-assign when it will not steal a restored or existing owner."""
        session = self.game_sessions.get(session_id, {})
        game_state = session.get("game_state")
        if not game_state:
            return False

        if game_state.get_controlled_character_id(player_id):
            return False

        for other_player_id, player_data in game_state.variables.get("players", {}).items():
            if other_player_id == player_id:
                continue
            controlled_character_id = player_data.get("controlled_character_id")
            if controlled_character_id == character.id:
                return False

        return True

    def _pick_auto_assign_character(self, player_id: str, session_id: str, story: Any) -> Optional[Any]:
        """Pick the first unclaimed playable character for this player, if any."""
        playable_chars = [c for c in (story.characters or []) if c.is_playable]
        for character in playable_chars:
            if self._should_auto_assign_character(player_id, session_id, character):
                return character
        return None

    async def pre_game_setup_loop(self, websocket: WebSocket, player_id: str) -> Optional[str]:
        """Handle the message flow for a new player before they join a session.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            
        Returns:
            The session ID if successful, None otherwise.
        """
        story_or_template = None
        
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            session_entry = self.player_sessions.setdefault(player_id, {})
            session_entry.setdefault("name", None)
            session_entry["websocket"] = websocket

            if msg_type == "set_player_name":
                player_name = message.get("name", "Player")

                if self.frontend_adapter:
                    existing = self.frontend_adapter.find_player_id_by_name(
                        player_name, exclude_player_id=player_id
                    )
                    if existing:
                        old_pid, old_token = existing
                        logger.info(
                            f"Name '{player_name}' belongs to existing player {old_pid}. "
                            f"Migrating current connection from {player_id}."
                        )
                        self.frontend_adapter.cleanup_ephemeral_player(player_id)
                        await websocket.send_json({
                            "type": "identity_changed",
                            "player_id": old_pid,
                            "player_name": player_name,
                            "session_token": old_token,
                        })
                        return None

                session_entry["name"] = player_name
                if self.frontend_adapter:
                    self.frontend_adapter.update_player_name_in_token(player_id, player_name)
                logger.info(f"Player {player_id} set name to {player_name}")
            
            elif msg_type == "request_stories":
                await self._send_stories_list(websocket)

            elif msg_type == "select_story":
                story_id = message.get("story_id")
                story_or_template = self.story_manager.load_story(story_id)
                if story_or_template:
                    await websocket.send_json({
                        "type": "control", 
                        "subtype": "story_info", 
                        "story": {"title": story_or_template.title}
                    })
                    # Store the selected story for session creation
                    session_entry["selected_story"] = story_or_template
                    # Send session selection prompt
                    await websocket.send_json({"type": "control", "subtype": "session_selection"})
                else:
                    await websocket.send_json({"type": "error", "content": "Failed to load story."})

            elif msg_type in ["create_session", "join_session"]:
                logger.info(f"Handling {msg_type} for player {player_id}")
                
                if not story_or_template:
                    await websocket.send_json({"type": "error", "content": "Please select a story first."})
                    continue
                
                session_id = await self.session_handler.handle_session_selection(
                    websocket, player_id, story_or_template, initial_message=message
                )
                
                if session_id:
                    # Successfully in a session
                    story = self.game_sessions[session_id]["game_state"].story

                    # Auto-assign the first unclaimed playable character when possible.
                    # Without this, multiplayer stories with multiple playable roles
                    # enter the game with no controlled character and therefore no location.
                    auto_character = self._pick_auto_assign_character(player_id, session_id, story)
                    if auto_character:
                        await self._auto_assign_character(player_id, session_id, auto_character)
                    
                    await self._send_initial_game_state(websocket, player_id, session_id)
                    return session_id
        
        return None

    async def _send_stories_list(self, websocket: WebSocket):
        """Send the list of available stories and templates.
        
        Args:
            websocket: The WebSocket to send to.
        """
        stories = self.story_manager.discover_stories()
        formatted_stories = format_stories_list(stories)
        await websocket.send_json({
            "type": "stories", 
            "stories": formatted_stories
        })

    async def _send_initial_game_state(self, websocket: WebSocket, player_id: str, session_id: str):
        """Send the initial game state to a player.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
        """
        game_state = self.game_sessions[session_id]["game_state"]
        if self.frontend_adapter:
            content = await self.frontend_adapter._build_room_start_content(
                session_id,
                player_id,
                game_state,
            )
        else:
            # Fallback used by non-web contexts.
            player_location = game_state.get_player_location(player_id)
            full_description = await self.game_kernel.get_node_perception(
                game_state, player_location, player_id
            )
            game_state_dict = await build_game_state_dict(
                game_state,
                session_id,
                player_id,
                self.game_kernel,
                current_perception=full_description,
            )
            content = {
                "game_state": game_state_dict,
                "response": full_description,
                "transcript": [],
                "pending_form": None,
            }

        await websocket.send_json({
            "type": "game_start",
            "content": content,
        })

        transcript_entries = content.get("transcript") or []
        has_visible_game_transcript = any(
            isinstance(entry, dict) and entry.get("message_type") == "game"
            for entry in transcript_entries
        )
        if content.get("response") and not has_visible_game_transcript:
            game_state.add_transcript_entry(
                "game",
                content["response"],
                is_html=True,
                player_ids=[player_id],
                location=game_state.get_player_location(player_id),
                metadata={"event_type": "initial_room_render"},
            )
            if self.frontend_adapter:
                self.frontend_adapter._schedule_room_autosave(session_id)

    async def _auto_assign_character(self, player_id: str, session_id: str, character: Any):
        """Auto-assign a playable character to a player.
        
        Called when there is exactly one playable character in the story.
        
        Args:
            player_id: The player's ID.
            session_id: The session ID.
            character: The character to assign.
        """
        logger.info(f"Auto-assigning character {character.name} ({character.id}) to player {player_id}.")
        game_state = self.game_sessions[session_id]["game_state"]
        story = game_state.story
        
        # Use set_player_character which uses pointer model
        game_state.set_player_character(player_id, character)
        
        # Get character's starting inventory and add to character_states
        char_inventory = []
        for item_id in character.get_inventory():
            item_obj = story.get_object(item_id)
            if item_obj:
                char_inventory.append(item_obj)
            else:
                logger.warning(f"Could not find item '{item_id}' for character '{character.id}'")
        
        # Store inventory in character_states (pointer model)
        if character.id in game_state.character_states:
            char_props = game_state.character_states[character.id].setdefault('properties', {})
            if not char_props.get('inventory'):
                char_props['inventory'] = char_inventory
        
        logger.info(f"Auto-assigned character {character.name} to player {player_id}.")

