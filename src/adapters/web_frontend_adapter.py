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
from typing import Optional, Dict, Any, List
import copy
import hmac
import json
import logging
import secrets
import asyncio
import os
import re
import tempfile
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
        self._room_autosave_tasks: Dict[str, asyncio.Task] = {}
        self._stream_message_types: Dict[str, str] = {}

        if self.game_kernel and self.game_kernel.state_manager:
            self.game_kernel.state_manager.archive_all_persistent_rooms()
            self._load_player_tokens()
            self._rebuild_player_to_session_mapping()

        # Initialize handlers
        self._init_handlers()
        
        # Set up routes
        self._setup_routes()
        
        # Start background tasks
        asyncio.create_task(self._reaper_task())
        
        logger.info(f"Web Frontend Adapter initialized on {host}:{port}")

    def _get_player_tokens_path(self) -> str:
        return os.path.join(self.game_kernel.state_manager.save_dir, "player_tokens.json")

    def _load_player_tokens(self) -> None:
        """Load persisted player tokens from disk so rejoin works across restarts.

        The file maps player_id -> {"token": str, "player_name": str | None}.
        Legacy files that stored bare token strings are migrated transparently.
        """
        path = self._get_player_tokens_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                migrated: Dict[str, Dict[str, Any]] = {}
                for pid, value in data.items():
                    if isinstance(value, str):
                        migrated[pid] = {"token": value, "player_name": None}
                    elif isinstance(value, dict):
                        migrated[pid] = value
                self._player_tokens = migrated
                logger.info("Loaded %d player token(s) from disk.", len(migrated))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Failed to load player tokens from %s: %s", path, exc)

    def find_player_id_by_name(self, name: str, exclude_player_id: str = "") -> Optional[tuple]:
        """Find an existing player ID and token by display name.

        Returns (player_id, token) if found, else None.
        """
        for pid, entry in self._player_tokens.items():
            if pid == exclude_player_id:
                continue
            if isinstance(entry, dict) and entry.get("player_name") == name:
                return pid, entry.get("token")
        return None

    def cleanup_ephemeral_player(self, player_id: str) -> None:
        """Remove a temporary player entry that was created during registration
        but is being replaced by an existing identity."""
        self._player_tokens.pop(player_id, None)
        self.player_sessions.pop(player_id, None)
        self.websocket_manager.disconnect(player_id)
        self._save_player_tokens()

    def update_player_name_in_token(self, player_id: str, player_name: str) -> None:
        """Update the stored player name in the token registry and persist."""
        entry = self._player_tokens.get(player_id)
        if isinstance(entry, dict):
            entry["player_name"] = player_name
            self._save_player_tokens()

    def _save_player_tokens(self) -> None:
        """Atomically persist the player token registry to disk."""
        path = self._get_player_tokens_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=os.path.dirname(path), delete=False
            ) as tmp:
                json.dump(self._player_tokens, tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            os.replace(tmp_path, path)
        except Exception as exc:
            logger.warning("Failed to save player tokens: %s", exc)

    def _rebuild_player_to_session_mapping(self) -> None:
        """Reconstruct persistent_player_to_session from room files on disk.

        Each room file stores participant_ids. For every player that appears in
        at least one room, map them to the most recently updated room.
        """
        if not self.game_kernel or not self.game_kernel.state_manager:
            return

        rooms = self.game_kernel.state_manager.list_persistent_rooms()
        best: Dict[str, tuple] = {}
        for room in rooms:
            room_id = room.get("room_id")
            updated_at = room.get("updated_at", "")
            for pid in room.get("participant_ids") or []:
                prev = best.get(pid)
                if prev is None or updated_at > prev[1]:
                    best[pid] = (room_id, updated_at)

        for pid, (room_id, _) in best.items():
            if pid in self._player_tokens:
                self.persistent_player_to_session[pid] = room_id

        if self.persistent_player_to_session:
            logger.info(
                "Rebuilt player-to-session mapping for %d player(s).",
                len(self.persistent_player_to_session),
            )

    def _init_handlers(self):
        """Initialize the handler instances."""
        self.session_handler = SessionHandler(
            game_kernel=self.game_kernel,
            websocket_manager=self.websocket_manager,
            game_sessions=self.game_sessions,
            player_sessions=self.player_sessions,
            persistent_player_to_session=self.persistent_player_to_session,
            frontend_adapter=self,
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
            self.player_sessions,
            self,
        )
        register_plan_routes(self.app, self.game_kernel, self.story_manager)
        
        # Register WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket(websocket)

    def _get_room_member_ids(self, room_id: str) -> list[str]:
        if room_id not in self.game_sessions:
            return []
        game_state = self.game_sessions[room_id].get("game_state")
        if not game_state:
            return []
        return list((game_state.variables.get("players") or {}).keys())

    def _serialize_pending_forms_for_room(self, room_id: str) -> Dict[str, Dict[str, Any]]:
        pending_forms: Dict[str, Dict[str, Any]] = {}
        session_entry = self.game_sessions.get(room_id) or {}
        pending_forms.update(copy.deepcopy(session_entry.get("pending_forms") or {}))
        game_kernel = self.game_kernel
        if not game_kernel:
            return pending_forms

        for player_id in self._get_room_member_ids(room_id):
            form_context = game_kernel._pending_forms.get(player_id)
            if not form_context:
                continue

            on_submit_override = form_context.get("on_submit_override")
            pending_forms[player_id] = {
                "form_id": form_context.get("form_id"),
                "prefill": copy.deepcopy(form_context.get("prefill") or {}),
                "on_submit_override": (
                    on_submit_override.dict()
                    if hasattr(on_submit_override, "dict")
                    else copy.deepcopy(on_submit_override)
                ),
            }

        return pending_forms

    def _build_room_record(self, room_id: str, status: str = "active") -> Optional[Dict[str, Any]]:
        session_entry = self.game_sessions.get(room_id)
        if not session_entry:
            return None

        game_state = session_entry.get("game_state")
        if not game_state:
            return None

        metadata = game_state.ensure_save_metadata()
        transcript = [
            entry for entry in game_state.transcript_history
            if isinstance(entry, dict)
        ]
        preview = ""
        if transcript:
            last_entry = transcript[-1]
            preview = str(last_entry.get("content") or "")

        return {
            "room_id": room_id,
            "story_id": game_state.story_id,
            "story_title": getattr(game_state.story, "title", game_state.story_id),
            "room_name": getattr(game_state.story, "title", room_id),
            "status": status,
            "created_at": game_state.created_at,
            "updated_at": game_state.updated_at,
            "participant_manifest": copy.deepcopy(metadata.get("participant_manifest", [])),
            "participant_names": list(metadata.get("participant_names", [])),
            "participant_ids": [
                pid for entry in metadata.get("participant_manifest", [])
                if (pid := entry.get("player_id"))
                and self.persistent_player_to_session.get(pid) == room_id
            ],
            "current_node": game_state.current_node_id,
            "preview": preview,
            "snapshot": game_state.to_dict(),
            "transcript": copy.deepcopy(transcript),
            "pending_forms": self._serialize_pending_forms_for_room(room_id),
        }

    def _persist_room_snapshot(self, room_id: str, status: str = "active") -> None:
        if not self.game_kernel or room_id not in self.game_sessions:
            return
        record = self._build_room_record(room_id, status=status)
        if not record:
            return
        self.game_kernel.state_manager.save_persistent_room(room_id, record)

    def remove_player_from_persisted_room(self, player_id: str, room_id: str) -> None:
        """Remove a player from a room's participant_ids on disk so they
        won't be auto-rejoined on server restart."""
        if not self.game_kernel or not self.game_kernel.state_manager:
            return
        record = self.game_kernel.state_manager.load_persistent_room(room_id)
        if not record:
            return
        pids = record.get("participant_ids") or []
        if player_id in pids:
            pids.remove(player_id)
            record["participant_ids"] = pids
            self.game_kernel.state_manager.save_persistent_room(room_id, record)

    def _cancel_room_autosave(self, room_id: str) -> None:
        task = self._room_autosave_tasks.pop(room_id, None)
        if task:
            task.cancel()

    async def _debounced_room_autosave(self, room_id: str, delay_seconds: float = 0.75) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            if room_id in self.game_sessions:
                self._persist_room_snapshot(room_id, status="active")
        except asyncio.CancelledError:
            return
        finally:
            current_task = self._room_autosave_tasks.get(room_id)
            if current_task is asyncio.current_task():
                self._room_autosave_tasks.pop(room_id, None)

    def _schedule_room_autosave(self, room_id: Optional[str]) -> None:
        if not room_id or room_id not in self.game_sessions:
            return
        self._cancel_room_autosave(room_id)
        self._room_autosave_tasks[room_id] = asyncio.create_task(
            self._debounced_room_autosave(room_id)
        )

    def _restore_pending_form_for_player(self, room_id: str, player_id: str) -> None:
        if not self.game_kernel or room_id not in self.game_sessions:
            return
        pending_forms = self.game_sessions[room_id].get("pending_forms") or {}
        pending = pending_forms.get(player_id)
        if not pending:
            self.game_kernel._pending_forms.pop(player_id, None)
            return

        form_id = (pending or {}).get("form_id")
        if not form_id:
            self.game_kernel._pending_forms.pop(player_id, None)
            return

        story = self.game_sessions[room_id]["game_state"].story
        form_def = story.get_form(form_id) if story else None
        if not form_def:
            self.game_kernel._pending_forms.pop(player_id, None)
            return

        on_submit_override = copy.deepcopy((pending or {}).get("on_submit_override"))
        if on_submit_override and isinstance(on_submit_override, dict):
            from src.models.story_models import FormOnSubmit

            on_submit_override = FormOnSubmit(**on_submit_override)

        self.game_kernel._pending_forms[player_id] = {
            "form_id": form_id,
            "form_def": form_def,
            "prefill": dict((pending or {}).get("prefill") or {}),
            "on_submit_override": on_submit_override,
        }

    def _activate_persisted_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        if room_id in self.game_sessions:
            return self.game_sessions[room_id]
        if not self.game_kernel:
            return None

        room_record = self.game_kernel.state_manager.load_persistent_room(room_id)
        if not room_record:
            return None

        snapshot = room_record.get("snapshot") or {}
        story_id = room_record.get("story_id") or snapshot.get("story_id")
        story = self.story_manager.load_story(story_id) if story_id else None
        if not story:
            logger.warning("Could not load story '%s' while restoring room %s", story_id, room_id)
            return None

        game_state = GameState.from_dict(snapshot, story)
        self.game_sessions[room_id] = {
            "room_id": room_id,
            "game_state": game_state,
            "players": set(),
            "lock": asyncio.Lock(),
            "loaded_from_save": True,
            "reserved_player_ids": set(),
            "pending_forms": copy.deepcopy(room_record.get("pending_forms") or {}),
        }
        return self.game_sessions[room_id]

    def _archive_room(self, room_id: str) -> None:
        if room_id not in self.game_sessions:
            return
        self._cancel_room_autosave(room_id)
        self._persist_room_snapshot(room_id, status="archived")
        for player_id in self._get_room_member_ids(room_id):
            self.game_kernel._pending_forms.pop(player_id, None)
        self.game_kernel.stop_ticker(room_id)
        del self.game_sessions[room_id]

    async def _build_room_start_content(
        self,
        room_id: str,
        player_id: str,
        game_state: GameState,
        *,
        full_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        transcript = game_state.get_transcript_for_player(player_id)
        has_visible_game_transcript = any(
            isinstance(entry, dict) and entry.get("message_type") == "game"
            for entry in transcript
        )

        player_location = game_state.get_player_location(player_id)
        if full_description is None and not has_visible_game_transcript:
            full_description = await self.game_kernel.get_node_perception(
                game_state,
                player_location,
                player_id,
            )

        game_state_dict = await build_game_state_dict(
            game_state,
            room_id,
            player_id,
            self.game_kernel,
            current_perception=full_description,
        )
        self._format_game_state_for_player(game_state_dict, player_id)
        pending_form_payload = None
        pending_form = self.game_kernel._pending_forms.get(player_id) if self.game_kernel else None
        if pending_form:
            form_def = pending_form.get("form_def")
            if form_def:
                pending_form_payload = form_def.to_frontend_format(
                    game_state=game_state,
                    player_id=player_id,
                    substitute_func=self.game_kernel.text_processor.substitute_variables,
                )
                prefill = pending_form.get("prefill") or {}
                if prefill:
                    pending_form_payload["prefill"] = dict(prefill)

        client_type = self.player_sessions.get(player_id, {}).get("client_type", "web")
        response = ""
        if not has_visible_game_transcript:
            response = self.format_for_client(full_description, client_type)

        return {
            "game_state": game_state_dict,
            "response": response,
            "transcript": transcript,
            "pending_form": pending_form_payload,
        }

    async def _reaper_task(self):
        """Periodically clears stale disconnect markers."""
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            now = time.time()
            reaped_players = []
            
            for player_id, disconnected_time in list(self.disconnected_players.items()):
                if now - disconnected_time > 300:  # 5-minute grace period
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
            token_entry = self._player_tokens.get(player_id)
            existing_token = token_entry.get("token") if isinstance(token_entry, dict) else None
            if existing_token:
                if not client_token or not hmac.compare_digest(client_token, existing_token):
                    logger.warning(f"Session token mismatch for player {player_id}. Rejecting rejoin, treating as new player.")
                    self._player_tokens.pop(player_id, None)
                    self._save_player_tokens()
                    self.persistent_player_to_session.pop(player_id, None)
                    token_entry = None

            await self.websocket_manager.connect(websocket, player_id)

            # Main connection loop
            current_session_id = None

            # Check if player is rejoining an active or archived room
            session_id = self.persistent_player_to_session.get(player_id)
            if session_id and (session_id in self.game_sessions or self.game_kernel.state_manager.persistent_room_exists(session_id)):
                logger.info(f"Player {player_id} is rejoining session {session_id}.")
                if player_id in self.disconnected_players:
                    del self.disconnected_players[player_id]

                self._activate_persisted_room(session_id)
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
                    self._restore_pending_form_for_player(session_id, player_id)
                    self._schedule_room_autosave(session_id)
                    if self.game_sessions[session_id]["players"] == {player_id}:
                        self.game_kernel.start_ticker(session_id)
                    await self.send_game_message(
                        f"{player_name} has reconnected.",
                        player_id,
                        message_type="multiplayer",
                        audience_scope="session",
                        session_id=session_id,
                        exclude_player_ids=[player_id],
                    )
                    start_content = await self._build_room_start_content(
                        session_id,
                        player_id,
                        game_state,
                    )
                    await websocket.send_json({
                        "type": "rejoined",
                        "content": start_content,
                    })
                    
                    current_session_id = session_id
            else:
                # Returning player (valid token, no active room) or brand-new player
                if token_entry and existing_token:
                    logger.info(f"Returning player {player_id} (no active room).")
                    player_name = token_entry.get("player_name")
                    self.player_sessions[player_id] = {"name": player_name, "websocket": websocket}
                    await websocket.send_json({
                        "type": "registered",
                        "player_id": player_id,
                        "player_name": player_name,
                        "session_token": existing_token,
                    })
                else:
                    logger.info(f"Registering new player {player_id}.")
                    new_token = secrets.token_urlsafe(32)
                    self._player_tokens[player_id] = {"token": new_token, "player_name": None}
                    self._save_player_tokens()
                    self.player_sessions[player_id] = {"name": None, "websocket": websocket}
                    await websocket.send_json({
                        "type": "registered",
                        "player_id": player_id,
                        "player_name": None,
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

        except (WebSocketDisconnect, ConnectionError):
            logger.info(f"Player {player_id} disconnected.")
            session_id = self.persistent_player_to_session.get(player_id)
            if session_id and session_id in self.game_sessions:
                logger.info(f"Player {player_id} detached from session {session_id}.")
                self.disconnected_players[player_id] = time.time()
                await self.session_handler.detach_player_from_room(
                    player_id,
                    session_id,
                    clear_persistent_mapping=False,
                    announce=True,
                )

        except Exception as e:
            if "ConnectionClosed" in type(e).__name__:
                logger.info(f"Player {player_id} disconnected (ws closed).")
            else:
                logger.error(f"Error in WebSocket endpoint for player {player_id}: {e}", exc_info=True)

        finally:
            logger.info(f"Closing WebSocket connection for player {player_id}.")
            if player_id:
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

    def _get_room_member_ids_in_location(self, session_id: Optional[str], location_id: Optional[str]) -> list[str]:
        """Get all room member IDs at a location, including detached players."""
        if not session_id or not location_id or session_id not in self.game_sessions:
            return []
        game_state = self.game_sessions[session_id]["game_state"]
        return [
            player_id
            for player_id in (game_state.variables.get("players") or {})
            if game_state.get_player_location(player_id) == location_id
        ]

    def update(self, game_state: GameState, session_id: Optional[str] = None):
        """Receive updates from the game kernel.
        
        Args:
            game_state: The current game state.
            session_id: The session ID.
        """
        if session_id:
            self._schedule_room_autosave(session_id)
        asyncio.create_task(self.update_display(game_state, session_id))

    def _record_transcript_entry(
        self,
        room_id: Optional[str],
        *,
        message_type: str,
        content: str,
        is_html: bool,
        player_ids: Optional[list[str]] = None,
        speaker: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not room_id or room_id not in self.game_sessions:
            return
        game_state = self.game_sessions[room_id].get("game_state")
        if not game_state:
            return
        location = None
        target_player_ids = list(player_ids or [])
        if target_player_ids:
            location = game_state.get_player_location(target_player_ids[0])
        game_state.add_transcript_entry(
            message_type,
            content,
            is_html=is_html,
            player_ids=target_player_ids or None,
            speaker=speaker,
            location=location,
            metadata=metadata,
        )
        self._schedule_room_autosave(room_id)

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
        sent = await self.websocket_manager.send_to_player(player_id, message)
        if sent:
            room_id = self.player_sessions.get(player_id, {}).get("session_id")
            message_type = message.get("type")
            if message_type == "form":
                form_title = message.get("title") or message.get("form_id") or "Form"
                description = message.get("description") or ""
                transcript_text = f"**{form_title}**"
                if description:
                    transcript_text += f"\n\n{description}"
                self._record_transcript_entry(
                    room_id,
                    message_type="form",
                    content=transcript_text,
                    is_html=False,
                    player_ids=[player_id],
                    metadata={"form_payload": copy.deepcopy(message)},
                )
        return sent

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
        transcript_targets: list[str]
        if audience_scope == "session":
            transcript_targets = self._get_room_member_ids(room_id=session_id)
        elif audience_scope in {"players_here", "location_players"}:
            transcript_targets = self._get_room_member_ids_in_location(session_id, location_id)
        elif audience_scope == "specific_players":
            transcript_targets = list(target_player_ids)
        else:
            transcript_targets = [player_id]

        if transcript_targets:
            transcript_content = self.format_for_client(message, "web")
            self._record_transcript_entry(
                session_id,
                message_type=message_type,
                content=transcript_content,
                is_html=True,
                player_ids=transcript_targets,
                metadata={"formatted_via_client": True},
            )
        return success

    async def send_stream_start(self, player_id: str, message_type: str = "game") -> bool:
        """Signal the start of a streaming message to the player."""
        self._stream_message_types[player_id] = message_type
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
        sent = await self.websocket_manager.send_to_player(player_id, msg)
        if sent and final_html is not None:
            room_id = self.player_sessions.get(player_id, {}).get("session_id")
            message_type = self._stream_message_types.get(player_id, "game")
            self._record_transcript_entry(
                room_id,
                message_type=message_type,
                content=final_html,
                is_html=True,
                player_ids=[player_id],
            )
        self._stream_message_types.pop(player_id, None)
        return sent

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
