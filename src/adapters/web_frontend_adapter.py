"""Web frontend adapter for the AI Native game engine.

This module provides the main web interface using FastAPI and WebSockets.
The adapter has been refactored into modular components:

- websocket_manager.py: WebSocket connection management
- routes/: REST API routes (story, llm, game)
- handlers/: WebSocket message handlers (session, pregame, game_loop, multiplayer)
- utils/: Utility functions (game_state_serializer, llm_prompts)
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Dict, Any
import hmac
import logging
import secrets
import asyncio
import os
import re
import time
from pathlib import Path

from html import escape as html_escape

from src.adapters.base import FrontendAdapter
from src.models.game_state import GameState

# Import modular components
from .websocket_manager import WebSocketManager
from .routes import register_story_routes, register_llm_routes, register_game_routes, register_plan_routes
from .handlers import SessionHandler, PregameHandler, GameLoopHandler
from .utils.game_state_serializer import build_game_state_dict

logger = logging.getLogger(__name__)

# Path prefixes that require editor authentication when editor_secret is set.
_EDITOR_AUTH_PREFIXES = (
    "/api/story",
    "/api/llm/",
    "/api/editor/",
)
# Read-only GET routes that should remain public even with a secret set.
_EDITOR_PUBLIC_READS = frozenset({"/api/stories"})


class EditorAuthMiddleware(BaseHTTPMiddleware):
    """Reject mutating editor requests when the configured secret doesn't match."""

    def __init__(self, app, editor_secret: str):
        super().__init__(app)
        self.editor_secret = editor_secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        needs_auth = any(path.startswith(p) for p in _EDITOR_AUTH_PREFIXES)
        if needs_auth and path in _EDITOR_PUBLIC_READS and request.method == "GET":
            needs_auth = False
        if needs_auth and request.method == "GET" and path.startswith("/api/story/") and "version" not in path:
            needs_auth = False

        if needs_auth:
            token = (
                request.headers.get("x-editor-token")
                or request.query_params.get("editor_token")
            )
            if not token or not hmac.compare_digest(token, self.editor_secret):
                return JSONResponse(
                    {"error": "Editor authentication required. Set X-Editor-Token header."},
                    status_code=403,
                )

        return await call_next(request)


class WebFrontendAdapter(FrontendAdapter):
    """A web-based frontend adapter implementing the observer pattern.
    
    This adapter provides:
    - REST API endpoints for story management and LLM features
    - WebSocket connections for real-time game communication
    - Session management for multiplayer games
    """
    
    def __init__(
        self, 
        host: str = "127.0.0.1", 
        port: int = 8000, 
        static_dir: str = "static",
        game_kernel: Optional[Any] = None, 
        story_manager: Optional[Any] = None,
        editor_secret: Optional[str] = None,
    ):
        """Initialize the web frontend adapter.
        
        Args:
            host: The host to bind to.
            port: The port to bind to.
            static_dir: The directory containing static files.
            game_kernel: The game kernel instance.
            story_manager: The story manager instance.
            editor_secret: Optional shared secret for editor API auth.
        """
        super().__init__(game_kernel)
        
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.story_manager = story_manager
        
        # FastAPI app
        self.app = FastAPI(title="Wenyoo API", version="1.0.0")

        if editor_secret:
            self.app.add_middleware(EditorAuthMiddleware, editor_secret=editor_secret)
            logger.info("Editor API authentication enabled")
        
        # Connection manager
        self.websocket_manager = WebSocketManager()
        
        # Session tracking
        self.player_sessions: Dict[str, Dict[str, Any]] = {}
        self.game_sessions: Dict[str, Dict[str, Any]] = {}
        self.persistent_player_to_session: Dict[str, str] = {}
        self.disconnected_players: Dict[str, float] = {}
        self._player_tokens: Dict[str, str] = {}

        # Initialize handlers
        self._init_handlers()
        
        # Set up routes
        self._setup_routes()
        
        # Start background tasks
        asyncio.create_task(self._reaper_task())
        
        logger.info(f"Web Frontend Adapter initialized on {host}:{port}")

    def _init_handlers(self):
        """Initialize the handler instances."""
        self.session_handler = SessionHandler(
            game_kernel=self.game_kernel,
            websocket_manager=self.websocket_manager,
            game_sessions=self.game_sessions,
            player_sessions=self.player_sessions,
            persistent_player_to_session=self.persistent_player_to_session
        )
        
        self.pregame_handler = PregameHandler(
            game_kernel=self.game_kernel,
            story_manager=self.story_manager,
            session_handler=self.session_handler,
            game_sessions=self.game_sessions,
            player_sessions=self.player_sessions,
            frontend_adapter=self
        )
        
        self.game_loop_handler = GameLoopHandler(
            game_kernel=self.game_kernel,
            story_manager=self.story_manager,
            websocket_manager=self.websocket_manager,
            session_handler=self.session_handler,
            game_sessions=self.game_sessions,
            player_sessions=self.player_sessions,
            persistent_player_to_session=self.persistent_player_to_session,
            frontend_adapter=self
        )

    def _setup_routes(self):
        """Set up the routes for the web frontend."""
        # Mount static files
        self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")
        
        # Register HTML routes
        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            with open(f"{self.static_dir}/index.html", "r", encoding="utf-8") as f:
                return f.read()

        @self.app.get("/editor", response_class=HTMLResponse)
        async def get_editor():
            editor_path = Path(self.static_dir) / "editor.html"
            if not editor_path.exists():
                return HTMLResponse("<html><body><h1>Editor coming soon!</h1></body></html>", status_code=200)
            with open(editor_path, "r", encoding="utf-8") as f:
                return f.read()

        # Register API routes from modules
        register_story_routes(self.app, self.story_manager)
        register_llm_routes(self.app, self.game_kernel, self.story_manager)
        register_game_routes(
            self.app, 
            self.game_kernel, 
            self.story_manager,
            self.game_sessions,
            self.player_sessions
        )
        register_plan_routes(self.app, self.game_kernel, self.story_manager)
        
        # Register WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket(websocket)

    async def _reaper_task(self):
        """Periodically cleans up players who have been disconnected for too long."""
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            now = time.time()
            reaped_players = []
            
            for player_id, disconnected_time in list(self.disconnected_players.items()):
                if now - disconnected_time > 300:  # 5-minute grace period
                    logger.info(f"Reaping player {player_id} after grace period expired.")
                    session_id = self.player_sessions.get(player_id, {}).get("session_id")
                    if session_id:
                        await self.session_handler.cleanup_player_session(player_id, session_id)
                    reaped_players.append(player_id)
            
            for player_id in reaped_players:
                if player_id in self.disconnected_players:
                    del self.disconnected_players[player_id]

    async def _handle_websocket(self, websocket: WebSocket):
        """Handle a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection.
        """
        player_id = None
        try:
            await websocket.accept()
            logger.info("WebSocket connection accepted.")

            # First message must be to register the persistent player ID
            message = await websocket.receive_json()
            msg_type = message.get("type")
            player_id = message.get("player_id")
            client_token = message.get("session_token")

            if msg_type != "register_or_rejoin" or not player_id:
                logger.warning(f"First message was not register_or_rejoin. Got: {message}")
                await websocket.close(code=1008)
                return

            # Validate session token on rejoin attempts
            existing_token = self._player_tokens.get(player_id)
            if existing_token:
                if not client_token or not hmac.compare_digest(client_token, existing_token):
                    logger.warning(f"Session token mismatch for player {player_id}. Rejecting rejoin, treating as new player.")
                    self._player_tokens.pop(player_id, None)
                    self.persistent_player_to_session.pop(player_id, None)

            await self.websocket_manager.connect(websocket, player_id)

            # Main connection loop
            current_session_id = None

            # Check if player is rejoining an active session
            session_id = self.persistent_player_to_session.get(player_id)
            if session_id and session_id in self.game_sessions:
                logger.info(f"Player {player_id} is rejoining session {session_id}.")
                if player_id in self.disconnected_players:
                    del self.disconnected_players[player_id]

                game_state = self.game_sessions[session_id]["game_state"]
                self.game_sessions[session_id].setdefault("reserved_player_ids", set()).discard(player_id)
                if player_id not in game_state.variables.get('players', {}):
                    logger.warning(f"Rejoin failed: player {player_id} no longer exists in session state {session_id}.")
                    session_id = None
                    self.persistent_player_to_session.pop(player_id, None)
                else:
                    player_data = game_state.variables['players'][player_id]
                    player_name = player_data.get('name', 'A Player')
                    client_type = (
                        self.player_sessions.get(player_id, {}).get("client_type")
                        or player_data.get("client_type")
                        or "web"
                    )
                    
                    self.player_sessions[player_id] = {
                        "name": player_name, 
                        "session_id": session_id, 
                        "websocket": websocket,
                        "client_type": client_type,
                    }
                    self.game_sessions[session_id]["players"].add(player_id)

                    await self.websocket_manager.broadcast_to_session(session_id, {
                        "type": "multiplayer", "content": f"{player_name} has reconnected."
                    }, self.player_sessions, exclude_player_id=player_id)
                    
                    player_location = game_state.get_player_location(player_id)
                    full_description = await self.game_kernel.get_node_perception(
                        game_state,
                        player_location,
                        player_id
                    )
                    game_state_dict = await build_game_state_dict(
                        game_state,
                        session_id,
                        player_id,
                        self.game_kernel,
                        current_perception=full_description,
                    )
                    self._format_game_state_for_player(game_state_dict, player_id)

                    await websocket.send_json({
                        "type": "rejoined",
                        "content": {
                            "game_state": game_state_dict,
                            "response": self.format_for_client(full_description, client_type)
                        }
                    })
                    
                    current_session_id = session_id
            else:
                # New player registration — issue a session token
                logger.info(f"Registering new player {player_id}.")
                new_token = secrets.token_urlsafe(32)
                self._player_tokens[player_id] = new_token
                self.player_sessions[player_id] = {"name": None, "websocket": websocket}
                player_name = self.player_sessions[player_id].get('name')
                await websocket.send_json({
                    "type": "registered", 
                    "player_id": player_id, 
                    "player_name": player_name,
                    "session_token": new_token,
                })

            while True:
                # If we are not already in a session (from rejoin), run pre-game setup
                if not current_session_id:
                    current_session_id = await self.pregame_handler.pre_game_setup_loop(websocket, player_id)
                
                if not current_session_id:
                    logger.warning(f"Player {player_id} disconnected during pre-game setup.")
                    break

                intentionally_left = await self.game_loop_handler.game_loop(websocket, player_id, current_session_id)

                if not intentionally_left:
                    logger.warning(f"Game loop for player {player_id} ended unexpectedly.")
                    break
                
                logger.info(f"Player {player_id} has returned to the menu.")
                # Reset session ID so we go back to pregame setup on next loop
                current_session_id = None

        except WebSocketDisconnect:
            logger.info(f"Player {player_id} disconnected unexpectedly.")
            session_id = self.persistent_player_to_session.get(player_id)
            if session_id and session_id in self.game_sessions:
                logger.info(f"Player {player_id} was in session {session_id}. Starting grace period.")
                self.disconnected_players[player_id] = time.time()
                self.game_sessions[session_id].setdefault("reserved_player_ids", set()).add(player_id)
                await self.websocket_manager.broadcast_to_session(session_id, {
                    "type": "multiplayer", 
                    "content": f"{self.player_sessions.get(player_id, {}).get('name', 'A player')} has disconnected."
                }, self.player_sessions)

        except Exception as e:
            logger.error(f"Error in WebSocket endpoint for player {player_id}: {e}", exc_info=True)

        finally:
            logger.info(f"Closing WebSocket connection for player {player_id}.")
            if player_id:
                # Check if we should perform cleanup (not in grace period)
                should_cleanup = True
                if player_id in self.disconnected_players:
                    logger.info(f"Player {player_id} is in grace period. Skipping immediate cleanup.")
                    should_cleanup = False
                
                if should_cleanup:
                    session_id = self.persistent_player_to_session.get(player_id)
                    if session_id:
                        logger.info(f"Performing final cleanup for player {player_id} in session {session_id}.")
                        await self.session_handler.cleanup_player_session(player_id, session_id)
                
                self.websocket_manager.disconnect(player_id)

    # ---- Client-specific formatting ----

    _LINK_TOKEN_RE = re.compile(r'\[\[(character|object|input):([^|]+)\|([^\]]*)\]\]')
    _BRACE_COLON_LINK_RE = re.compile(r'\{([^{}:]+):([^{}]+)\}')
    _BRACE_BARE_LINK_RE = re.compile(r'\{([^{}]+)\}')

    def format_for_client(self, text: str, client_type: str = 'web') -> str:
        if not text:
            return text

        def _render_input_link(display_text: str, action_hint: str = "") -> str:
            safe_display = html_escape(display_text)
            escaped_display = display_text.replace("'", "\\'").replace('"', '\\"')
            escaped_hint = action_hint.replace("'", "\\'").replace('"', '\\"')
            return (
                f'<a href="#" class="game-action-link" '
                f"onclick=\"onActionClick('{escaped_display}', '{escaped_hint}'); return false;\">"
                f'{safe_display}</a>'
            )

        def _render_entity_link(link_type: str, element_id: str, display_text: str) -> str:
            safe_display = html_escape(display_text)
            escaped_id = element_id.replace("'", "\\'").replace('"', '\\"')
            if link_type == 'character':
                return (
                    f'<a href="#" class="game-character-link" '
                    f"onclick=\"onCharacterClick('{escaped_id}'); return false;\">"
                    f'{safe_display}</a>'
                )
            return (
                f'<a href="#" class="game-object-link" '
                f"onclick=\"onObjectClick('{escaped_id}'); return false;\">"
                f'{safe_display}</a>'
            )

        def _replace_token(match):
            link_type = match.group(1)
            g2 = match.group(2)
            g3 = match.group(3)
            if link_type == 'input':
                return _render_input_link(g2, g3)
            return _render_entity_link(link_type, g2, g3)

        def _replace_brace_colon(match):
            left = match.group(1).strip()
            right = match.group(2).strip()

            if left.startswith('@') and len(left) > 1:
                return _render_entity_link('character', left[1:], right)

            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', left):
                return _render_entity_link('object', left, right)

            return _render_input_link(left, right)

        def _replace_brace_bare(match):
            inner = match.group(1).strip()
            if not inner or inner.startswith('<'):
                return match.group(0)
            return _render_input_link(inner, "")

        formatted = self._LINK_TOKEN_RE.sub(_replace_token, text)
        formatted = self._BRACE_COLON_LINK_RE.sub(_replace_brace_colon, formatted)
        formatted = self._BRACE_BARE_LINK_RE.sub(_replace_brace_bare, formatted)
        return formatted

    # ---- Observer pattern methods ----

    async def start(self) -> None:
        """Start the web interface."""
        logger.info(f"Starting web interface on {self.host}:{self.port}")
        import uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    async def update_display(self, game_state: GameState, session_id: Optional[str] = None) -> bool:
        """Update the display with current game state.
        
        Args:
            game_state: The current game state.
            session_id: The session ID.
            
        Returns:
            True if successful, False otherwise.
        """
        if session_id:
            logger.info(f"Updating display for session {session_id}")
            
            # Find all players in this session and send individual updates
            players_in_session = self._get_player_ids_in_session(session_id)
            
            for player_id in players_in_session:
                game_state_dict = await build_game_state_dict(
                    game_state, session_id, player_id, self.game_kernel
                )
                self._format_game_state_for_player(game_state_dict, player_id)
                await self.websocket_manager.send_to_player(player_id, {
                    "type": "game_state",
                    "content": game_state_dict
                })
            
            return True
        logger.warning("update_display called with no session_id")
        return False

    def _get_player_ids_in_session(self, session_id: Optional[str]) -> list[str]:
        """Get connected player IDs currently associated with a session."""
        if not session_id:
            return []
        return [
            player_id
            for player_id, session_data in self.player_sessions.items()
            if session_data.get("session_id") == session_id
            and self.websocket_manager.is_connected(player_id)
        ]

    def _get_player_ids_in_location(self, session_id: Optional[str], location_id: Optional[str]) -> list[str]:
        """Get connected player IDs in a session who are at the same location."""
        if not session_id or not location_id or session_id not in self.game_sessions:
            return []
        game_state = self.game_sessions[session_id]["game_state"]
        return [
            player_id
            for player_id in self._get_player_ids_in_session(session_id)
            if game_state.get_player_location(player_id) == location_id
        ]

    def update(self, game_state: GameState, session_id: Optional[str] = None):
        """Receive updates from the game kernel.
        
        Args:
            game_state: The current game state.
            session_id: The session ID.
        """
        asyncio.create_task(self.update_display(game_state, session_id))

    async def send_response(self, response: Dict[str, Any]) -> bool:
        """Send a response to the frontend.
        
        Args:
            response: The response to send.
            
        Returns:
            True if successful, False otherwise.
        """
        player_id = response.get("player_id")
        session_id = self.player_sessions.get(player_id, {}).get("session_id")
        if player_id and session_id:
            return await self.websocket_manager.send_to_player(player_id, {
                "type": "game",
                "content": response.get("content", "")
            })
        return False

    async def send_json_message(self, message: Dict[str, Any], player_id: str) -> bool:
        """Send a JSON message to a specific player.
        
        Args:
            message: The message to send.
            player_id: The player's ID.
            
        Returns:
            True if successful, False otherwise.
        """
        return await self.websocket_manager.send_to_player(player_id, message)

    async def send_game_message(self, message: str, player_id: str, message_type: str = "game", **extra) -> bool:
        """Send a game message to a specific player.

        Text is passed through ``format_for_client`` before sending so that
        abstract link tokens are converted to client-specific markup.

        Args:
            message: The message content.
            player_id: The player's ID.
            message_type: The type of message (default: "game").
            **extra: Additional fields merged into the WebSocket payload.
            
        Returns:
            True if successful, False otherwise.
        """
        audience_scope = extra.pop("audience_scope", "self")
        target_player_ids = list(extra.pop("target_player_ids", []) or [])
        exclude_player_ids = set(extra.pop("exclude_player_ids", []) or [])
        session_id = extra.pop("session_id", None) or self.player_sessions.get(player_id, {}).get("session_id")
        location_id = extra.pop("location_id", None)
        game_state = self.game_sessions.get(session_id, {}).get("game_state") if session_id else None

        if audience_scope == "self":
            resolved_targets = [player_id]
        elif audience_scope == "players_here":
            if not location_id and game_state:
                location_id = game_state.get_player_location(player_id)
            resolved_targets = self._get_player_ids_in_location(
                session_id,
                location_id,
            )
        elif audience_scope == "location_players":
            resolved_targets = self._get_player_ids_in_location(
                session_id,
                location_id,
            )
        elif audience_scope == "session":
            resolved_targets = self._get_player_ids_in_session(session_id)
        elif audience_scope == "specific_players":
            resolved_targets = list(target_player_ids)
        else:
            resolved_targets = [player_id]

        deduped_targets = []
        for target_player_id in resolved_targets:
            if target_player_id in exclude_player_ids:
                continue
            if target_player_id not in deduped_targets:
                deduped_targets.append(target_player_id)

        success = False
        for target_player_id in deduped_targets:
            client_type = self.player_sessions.get(target_player_id, {}).get('client_type', 'web')
            formatted = self.format_for_client(message, client_type)
            payload = {"type": message_type, "content": formatted}
            payload.update(extra)
            sent = await self.websocket_manager.send_to_player(target_player_id, payload)
            success = success or sent
        return success

    async def send_stream_start(self, player_id: str, message_type: str = "game") -> bool:
        """Signal the start of a streaming message to the player."""
        return await self.websocket_manager.send_to_player(player_id, {
            "type": "stream_start",
            "message_type": message_type,
        })

    async def send_stream_token(self, player_id: str, token: str) -> bool:
        """Send a single streaming token to the player."""
        return await self.websocket_manager.send_to_player(player_id, {
            "type": "stream_token",
            "content": token,
        })

    async def send_stream_end(self, player_id: str, final_html: str = None) -> bool:
        """Signal the end of a streaming message.
        
        Args:
            final_html: Optional fully-processed HTML to replace the raw
                        streamed text (includes hyperlink processing, etc.)
        """
        msg = {"type": "stream_end"}
        if final_html is not None:
            msg["final_html"] = final_html
        return await self.websocket_manager.send_to_player(player_id, msg)

    async def send_error(self, message: str, player_id: str) -> None:
        """Send an error message to a specific player.
        
        Args:
            message: The error message.
            player_id: The player's ID.
        """
        await self.notify_error(message, player_id)

    async def notify_error(self, error: str, player_id: Optional[str] = None) -> None:
        """Notify the frontend of an error.
        
        Args:
            error: The error message.
            player_id: Optional specific player to notify.
        """
        message = {"type": "error", "content": error}
        if player_id:
            await self.websocket_manager.send_to_player(player_id, message)
        else:
            await self.websocket_manager.broadcast_to_all(message)
