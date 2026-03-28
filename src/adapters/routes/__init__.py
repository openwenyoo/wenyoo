"""Route modules for web frontend adapter."""

from .story_routes import register_story_routes
from .llm_routes import register_llm_routes
from .game_routes import register_game_routes
from .plan_routes import register_plan_routes

__all__ = [
    'register_story_routes',
    'register_llm_routes', 
    'register_game_routes',
    'register_plan_routes',
]

