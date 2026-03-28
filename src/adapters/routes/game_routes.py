"""Game session and save/load routes."""

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
    player_sessions: dict
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

        game_sessions[session_id] = {
            "game_state": game_state,
            "players": {player_id}
        }
        player_sessions[player_id] = {"name": player_name, "session_id": session_id}
        game_kernel.start_ticker(session_id)

        return {"success": True, "session_id": session_id, "player_id": player_id}

    @app.get("/api/saved-games")
    async def get_saved_games(player_name: str, story_id: str):
        """Get list of saved games for a player and story."""
        try:
            saved_games = game_kernel.state_manager.get_saved_games_list(player_name, story_id)
            return {"success": True, "saves": saved_games}
        except Exception as e:
            logger.error(f"Error getting saved games: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.post("/api/load")
    async def load_game(request: Request):
        """Load a saved game."""
        try:
            data = await request.json()
            save_code = data.get("save_code")
            player_name = data.get("player_name")
            story_id = data.get("story_id")
            
            if not all([save_code, player_name, story_id]):
                return {"success": False, "error": "Missing required parameters"}
            
            # Load the saved state
            loaded_state_dict = game_kernel.state_manager.load_state_by_code(
                save_code, player_name, story_id
            )
            
            if not loaded_state_dict:
                return {"success": False, "error": "Failed to load saved game. Save code may be invalid."}
            
            return {"success": True, "game_state": loaded_state_dict}
        except Exception as e:
            logger.error(f"Error loading game: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

