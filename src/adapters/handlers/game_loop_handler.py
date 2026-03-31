"""Main game loop handler."""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional, Set
import asyncio
import json
import logging

# Import websockets exception for graceful handling of abrupt disconnections
try:
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    ConnectionClosedError = Exception
    ConnectionClosedOK = Exception

from ..utils.game_state_serializer import (
    build_game_state_dict, 
    build_object_definitions,
    format_stories_list
)

logger = logging.getLogger(__name__)

# How often to send keepalive pings during long-running processing (seconds).
# The game loop blocks on process_input (Architect LLM calls) which can take
# 60+ seconds. Without pings the WebSocket may be considered idle and dropped.
_KEEPALIVE_INTERVAL = 15

# Commands that can be processed instantly without the session lock
INSTANT_COMMANDS: Set[str] = set()

# Command prefixes that are instant transport/meta queries
INSTANT_PREFIXES = (
    "load ",                   # Load game (handled separately)
    "get_object_actions:",     # Read-only query
)


class GameLoopHandler:
    """Handles the main game loop for connected players."""
    
    def __init__(
        self,
        game_kernel: Any,
        story_manager: Any,
        websocket_manager: Any,
        session_handler: Any,
        game_sessions: Dict[str, Dict[str, Any]],
        player_sessions: Dict[str, Dict[str, Any]],
        persistent_player_to_session: Dict[str, str],
        frontend_adapter: Any = None
    ):
        """Initialize the game loop handler.
        
        Args:
            game_kernel: The game kernel instance.
            story_manager: The story manager instance.
            websocket_manager: The WebSocket manager instance.
            session_handler: The session handler instance.
            game_sessions: Dict of active game sessions.
            player_sessions: Dict of player sessions.
            persistent_player_to_session: Dict mapping player IDs to session IDs.
            frontend_adapter: The parent frontend adapter (for client formatting).
        """
        self.game_kernel = game_kernel
        self.story_manager = story_manager
        self.websocket_manager = websocket_manager
        self.session_handler = session_handler
        self.game_sessions = game_sessions
        self.player_sessions = player_sessions
        self.persistent_player_to_session = persistent_player_to_session
        self.frontend_adapter = frontend_adapter

    async def game_loop(self, websocket: WebSocket, player_id: str, session_id: str) -> bool:
        """Main game loop for a connected player.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
            
        Returns:
            True if the player left intentionally, False otherwise.
        """
        while True:
            try:
                # Wait for message with timeout for keepalive
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=20.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
                    continue

                message = json.loads(data)
                msg_type = message.get("type")
                
                # Handle detach / leave session
                if msg_type in {"leave_session", "detach_session"}:
                    return await self._handle_leave_session(websocket, player_id, session_id)

                # Handle various message types
                if msg_type == "set_client_type":
                    await self._handle_set_client_type(player_id, session_id, message)
                    continue

                if msg_type == "request_initial_state":
                    await self._send_initial_state(websocket, player_id, session_id)
                    continue

                if msg_type == "request_stories":
                    await self._send_stories_list(websocket)
                    continue

                # Handle form submission
                if msg_type == "form_submit":
                    await self._handle_form_submit(websocket, player_id, session_id, message)
                    continue

                # Handle game commands
                content = message.get("content", "").strip()
                if not content:
                    continue

                input_type = message.get("input_type", "typed")
                action_hint = message.get("action_hint", "")
                display_text = message.get("display_text") or content
                logger.info(
                    "Received command from player %s in session %s: %s",
                    player_id,
                    session_id,
                    content,
                )
                await self._process_game_command(websocket, player_id, session_id, content, input_type, action_hint, display_text)

            except WebSocketDisconnect:
                raise  # Re-raise to be caught by the outer handler
            except (ConnectionClosedError, ConnectionClosedOK) as e:
                # Client disconnected abruptly (common during tests or browser close)
                logger.debug(f"WebSocket closed for player {player_id}: {e}")
                raise WebSocketDisconnect()  # Treat as normal disconnect
            except Exception as e:
                logger.error(f"Error in game loop for player {player_id}: {e}", exc_info=True)
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"An unexpected error occurred: {e}"
                    })
                except (ConnectionClosedError, ConnectionClosedOK):
                    pass  # Client already gone
                except Exception as send_err:
                    logger.debug(f"Failed to send error to player {player_id}: {send_err}")
                return False

    async def _handle_leave_session(self, websocket: WebSocket, player_id: str, session_id: str) -> bool:
        """Handle a player intentionally detaching from a room.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
            
        Returns:
            True to signal intentional leave.
        """
        logger.info(f"Player {player_id} is intentionally detaching from session {session_id}.")

        await self.session_handler.detach_player_from_room(
            player_id,
            session_id,
            clear_persistent_mapping=True,
            announce=True,
        )

        if player_id in self.player_sessions:
            self.player_sessions[player_id].pop('selected_story', None)

        # Send story list back to client
        await self._send_stories_list(websocket)
        
        return True

    async def _handle_set_client_type(self, player_id: str, session_id: str, message: Dict):
        """Handle setting the client type.
        
        Args:
            player_id: The player's ID.
            session_id: The session ID.
            message: The message containing client_type.
        """
        game_state = self.game_sessions[session_id]["game_state"]
        player_data = game_state.variables.setdefault('players', {}).setdefault(player_id, {})
        new_client_type = message.get('client_type')
        player_data['client_type'] = new_client_type
        self.player_sessions.setdefault(player_id, {})['client_type'] = new_client_type
        logger.info(f"Set client_type to {new_client_type} for player {player_id}")

    async def _send_initial_state(self, websocket: WebSocket, player_id: str, session_id: str):
        """Send the initial game state to a player.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
        """
        game_state = self.game_sessions[session_id]["game_state"]
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

        if self.frontend_adapter:
            self.frontend_adapter._format_game_state_for_player(game_state_dict, player_id)
            client_type = self.player_sessions.get(player_id, {}).get('client_type', 'web')
            full_description = self.frontend_adapter.format_for_client(full_description, client_type)

        await websocket.send_json({
            "type": "game_start",
            "content": {
                "game_state": game_state_dict,
                "response": full_description
            }
        })

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

    async def _process_game_command(
        self, 
        websocket: WebSocket, 
        player_id: str, 
        session_id: str, 
        content: str,
        input_type: str = "typed",
        action_hint: str = "",
        display_text: Optional[str] = None,
    ):
        """Process a game command from a player.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
            content: The command content.
            input_type: How the input was triggered ('typed' or 'action_click').
            action_hint: Optional hint text from story author for the Architect.
        """
        # Handle special commands
        if content.lower() == "save":
            await self._handle_save_command(websocket, player_id, session_id)
            return
        
        if content.startswith("get_object_actions:"):
            object_id = content.split(":", 1)[1].strip()
            await self._handle_get_object_actions(player_id, session_id, object_id)
            return
            
        # Handle regular game command
        await self._handle_game_command(websocket, player_id, session_id, content, input_type, action_hint, display_text)

    async def _handle_save_command(self, websocket: WebSocket, player_id: str, session_id: str):
        """Handle the save command.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
        """
        try:
            game_session = self.game_sessions.get(session_id)
            if not game_session:
                await websocket.send_json({"type": "error", "content": "No active game session found."})
                return

            game_state = game_session.get("game_state")
            if not game_state:
                await websocket.send_json({"type": "error", "content": "No active game state found."})
                return

            if self.frontend_adapter:
                self.frontend_adapter._cancel_room_autosave(session_id)
                self.frontend_adapter._persist_room_snapshot(session_id, status="active")
                await self.frontend_adapter.send_game_message(
                    "Game saved successfully.",
                    player_id,
                    message_type="game",
                    session_id=session_id,
                )
            else:
                await websocket.send_json({
                    "type": "error",
                    "content": "Manual save requires the web frontend persistence layer."
                })
                
        except Exception as e:
            logger.error(f"Error handling save command: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "content": f"Error saving game: {str(e)}"})

    async def _handle_get_object_actions(self, player_id: str, session_id: str, object_id: str):
        """Send available actions for an object to the requesting player."""
        game_state = self.game_sessions[session_id]["game_state"]
        actions = await self.game_kernel.get_actions_for_object(game_state, player_id, object_id)
        actions_data = [{"id": action.id, "text": action.text} for action in actions]

        await self.websocket_manager.send_to_player(player_id, {
            "type": "object_actions",
            "object_id": object_id,
            "actions": actions_data,
        })

    def _is_instant_command(self, command: str) -> bool:
        """Check if a command can be processed instantly without LLM.
        
        Instant commands don't modify shared game state in ways that could
        conflict with other players, so they don't need the session lock.
        
        Args:
            command: The command string (already stripped).
            
        Returns:
            True if the command is instant and doesn't need locking.
        """
        command_lower = command.lower()
        
        # Check exact matches
        if command_lower in INSTANT_COMMANDS:
            return True
        
        # Check prefixes
        if command_lower.startswith(INSTANT_PREFIXES):
            return True
        
        return False

    # TODO: The keepalive-during-processing approach below is a pragmatic fix.
    #       A more elegant solution would decouple the WebSocket receive loop
    #       from long-running game processing entirely (e.g. run process_input
    #       in a separate task while the game loop continues to handle ping/pong
    #       and queues incoming messages). This would also allow the client to
    #       cancel in-flight requests or send out-of-band messages during processing.

    @staticmethod
    async def _keepalive_ping_loop(websocket: WebSocket):
        """Send periodic pings to prevent WebSocket idle-timeout disconnects.

        Meant to run as a background task while a long-running operation
        (e.g. Architect LLM calls) blocks the main game loop iteration.
        """
        try:
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
                await websocket.send_json({"type": "ping"})
        except (asyncio.CancelledError, WebSocketDisconnect,
                ConnectionClosedError, ConnectionClosedOK):
            pass
        except Exception as e:
            logger.debug(f"Keepalive ping failed for player: {e}")

    async def _handle_game_command(
        self, 
        websocket: WebSocket, 
        player_id: str, 
        session_id: str, 
        command: str,
        input_type: str = "typed",
        action_hint: str = "",
        display_text: Optional[str] = None,
    ):
        """Handle a regular game command.
        
        Uses a session-level lock for commands that may modify shared state.
        Only read-only transport/meta queries bypass the lock.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
            command: The command to process.
            input_type: How the input was triggered ('typed' or 'action_click').
            action_hint: Optional hint text from story author for the Architect.
        """
        if session_id not in self.game_sessions:
            logger.error(f"Session {session_id} not found for player {player_id}")
            await websocket.send_json({
                "type": "error", 
                "content": "Session not found. Please rejoin or start a new game."
            })
            return

        game_session = self.game_sessions[session_id]
        game_state = game_session["game_state"]
        story = game_state.story
        original_location = game_state.get_player_location(player_id)
        original_version = game_state.version

        # Start background keepalive pings so the WebSocket stays alive
        # during long Architect / LLM processing.
        ping_task = asyncio.create_task(self._keepalive_ping_loop(websocket))
        try:
            if self._is_instant_command(command):
                response = await self.game_kernel.process_input(command, game_state, story, player_id, session_id, input_type=input_type, action_hint=action_hint, display_text=display_text)
                await self._post_command_update(
                    websocket, player_id, session_id, response, command,
                    original_location, original_version, game_state,
                )
            else:
                session_lock = game_session.get("lock")
                if session_lock:
                    async with session_lock:
                        response = await self.game_kernel.process_input(command, game_state, story, player_id, session_id, input_type=input_type, action_hint=action_hint, display_text=display_text)
                        await self._post_command_update(
                            websocket, player_id, session_id, response, command,
                            original_location, original_version, game_state,
                        )
                else:
                    response = await self.game_kernel.process_input(command, game_state, story, player_id, session_id, input_type=input_type, action_hint=action_hint, display_text=display_text)
                    await self._post_command_update(
                        websocket, player_id, session_id, response, command,
                        original_location, original_version, game_state,
                    )
        finally:
            ping_task.cancel()

    async def _post_command_update(
        self,
        websocket: WebSocket,
        player_id: str,
        session_id: str,
        response: Any,
        command: str,
        original_location: str,
        original_version: int,
        game_state: Any,
    ):
        """Send game_state snapshot and broadcast to other players (background)."""
        try:
            current_perception = None
            if isinstance(response, dict):
                narrative = response.get("narrative_response", "")
                if narrative:
                    current_perception = narrative

            game_state_dict = await build_game_state_dict(
                game_state, session_id, player_id, self.game_kernel,
                current_perception=current_perception,
            )

            if self.frontend_adapter:
                self.frontend_adapter._format_game_state_for_player(game_state_dict, player_id)

            await websocket.send_json({
                "type": "command_result",
                "content": {
                    "game_state": game_state_dict,
                    "response": response
                }
            })

            new_location = game_state.get_player_location(player_id)
            if game_state.version != original_version or new_location != original_location:
                await self._push_session_state(session_id, exclude_player_id=player_id)
        except Exception as e:
            logger.error("Error in _post_command_update for player %s: %s", player_id, e, exc_info=True)

    async def _handle_form_submit(
        self,
        websocket: WebSocket,
        player_id: str,
        session_id: str,
        message: Dict
    ):
        """Handle a form submission from a player.
        
        Args:
            websocket: The player's WebSocket connection.
            player_id: The player's ID.
            session_id: The session ID.
            message: The form submission message containing:
                - form_id: ID of the submitted form
                - data: Dict of field values
                - files: Dict of file data (optional)
        """
        try:
            form_id = message.get("form_id")
            form_data = message.get("data", {})
            files_data = message.get("files", {})
            
            if not form_id:
                await websocket.send_json({
                    "type": "form_error",
                    "form_id": form_id,
                    "errors": {"_form": "Missing form ID"}
                })
                return
            
            if session_id not in self.game_sessions:
                await websocket.send_json({
                    "type": "form_error",
                    "form_id": form_id,
                    "errors": {"_form": "Session not found"}
                })
                return
            
            game_session = self.game_sessions[session_id]
            game_state = game_session["game_state"]
            story = game_state.story
            
            # Keep WebSocket alive during long form processing (character
            # selection triggers Architect + explicit_state generation).
            ping_task = asyncio.create_task(self._keepalive_ping_loop(websocket))
            try:
                result = await self.game_kernel.process_form_submission(
                    form_id, form_data, files_data, game_state, player_id, story
                )
            finally:
                ping_task.cancel()
            
            if result.get("success"):
                # Send success response
                await websocket.send_json({
                    "type": "form_success",
                    "form_id": form_id
                })
                
                game_state_dict = await build_game_state_dict(
                    game_state, session_id, player_id, self.game_kernel
                )
                if self.frontend_adapter:
                    self.frontend_adapter._format_game_state_for_player(game_state_dict, player_id)

                await websocket.send_json({
                    "type": "command_result",
                    "content": {
                        "game_state": game_state_dict,
                        "response": {"narrative_response": "", "script_paused": result.get("script_paused", False)}
                    }
                })
                await self._push_session_state(session_id, exclude_player_id=player_id)
            else:
                # Send validation errors
                await websocket.send_json({
                    "type": "form_error",
                    "form_id": form_id,
                    "errors": result.get("errors", {"_form": result.get("error", "Unknown error")})
                })
                
        except Exception as e:
            logger.error(f"Error handling form submission: {e}", exc_info=True)
            await websocket.send_json({
                "type": "form_error",
                "form_id": message.get("form_id"),
                "errors": {"_form": f"Error processing form: {str(e)}"}
            })

    async def _push_session_state(self, session_id: str, exclude_player_id: Optional[str] = None):
        """Push the latest game_state snapshot to connected players in the session."""
        if not self.frontend_adapter or session_id not in self.game_sessions:
            return

        game_state = self.game_sessions[session_id]["game_state"]
        for target_player_id, session_data in self.player_sessions.items():
            if session_data.get("session_id") != session_id:
                continue
            if exclude_player_id and target_player_id == exclude_player_id:
                continue

            game_state_dict = await build_game_state_dict(
                game_state, session_id, target_player_id, self.game_kernel
            )
            self.frontend_adapter._format_game_state_for_player(game_state_dict, target_player_id)
            await self.websocket_manager.send_to_player(target_player_id, {
                "type": "game_state",
                "content": game_state_dict
            })

