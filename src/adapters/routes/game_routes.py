"""Game session routes."""

from fastapi import FastAPI, Request
from typing import Any
import logging
import uuid

from src.utils.name_generator import generate_name

logger = logging.getLogger(__name__)


def register_game_routes(
    app: FastAPI, 
    game_kernel: Any, 
    story_manager: Any,
    game_sessions: dict,
    player_sessions: dict,
    frontend_adapter: Any,
):
    """Register game-related routes on the FastAPI app.
    
    Args:
        app: The FastAPI application.
        game_kernel: The game kernel instance.
        story_manager: The story manager instance.
        game_sessions: Dict of active game sessions.
        player_sessions: Dict of player sessions.
    """
    
    @app.post("/api/game/start")
    async def start_game(request: Request):
        """Start a new game session."""
        data = await request.json()
        story_id = data.get("story_id")
        player_name = data.get("player_name")
        character_id = data.get("character_id")

        if not story_id or not player_name:
            return {"success": False, "error": "Story ID and player name are required."}

        player_id = str(uuid.uuid4())
        session_id = generate_name()
        
        story = story_manager.load_story(story_id)
        if not story:
            return {"success": False, "error": "Story not found."}

        game_state = await game_kernel.start_new_game_async(
            story_id,
            player_id,
            session_id=session_id,
            character_id=character_id,
            notify_observers=False,
        )
        if not game_state:
            return {"success": False, "error": "Failed to start new game."}

        game_state.variables['players'][player_id]['name'] = player_name
        game_state.save_metadata["room_id"] = session_id

        game_sessions[session_id] = {
            "game_state": game_state,
            "players": {player_id},
            "lock": None,
            "loaded_from_save": False,
            "reserved_player_ids": set(),
        }
        player_sessions[player_id] = {"name": player_name, "session_id": session_id}
        game_kernel.start_ticker(session_id)
        frontend_adapter._persist_room_snapshot(session_id, status="active")

        return {"success": True, "session_id": session_id, "player_id": player_id}

    @app.get("/api/sessions")
    async def get_persistent_sessions(player_id: str, story_id: str = None):
        """Get resumable room sessions for a player."""
        try:
            sessions = game_kernel.state_manager.list_persistent_rooms(
                player_id=player_id,
                story_id=story_id,
            )
            return {"success": True, "sessions": sessions}
        except Exception as e:
            logger.error(f"Error getting persistent sessions: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.post("/api/sessions/delete")
    async def delete_persistent_session(request: Request):
        """Delete a resumable room if the requester is a participant."""
        try:
            data = await request.json()
            room_id = data.get("room_id")
            player_id = data.get("player_id")
            if not room_id or not player_id:
                return {"success": False, "error": "Missing required parameters"}

            room_record = game_kernel.state_manager.load_persistent_room(room_id)
            if not room_record:
                return {"success": False, "error": "Room not found"}

            participant_ids = set(room_record.get("participant_ids") or [])
            if player_id not in participant_ids:
                return {"success": False, "error": "You are not allowed to delete this room"}

            deleted = await frontend_adapter.session_handler.delete_room(room_id)
            return {"success": deleted}
        except Exception as e:
            logger.error(f"Error deleting persistent session: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


