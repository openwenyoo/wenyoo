"""Game state serialization utilities."""

from typing import Dict, Any, Optional, List
from src.models.game_state import GameState
from src.core.status_display_resolver import StatusDisplayResolver

# Module-level resolver instance (lazy initialization)
_status_display_resolver: Optional[StatusDisplayResolver] = None


def get_status_display_resolver() -> StatusDisplayResolver:
    """Get or create the status display resolver singleton."""
    global _status_display_resolver
    if _status_display_resolver is None:
        _status_display_resolver = StatusDisplayResolver()
    return _status_display_resolver


def build_object_definitions(game_state: GameState) -> Dict[str, Any]:
    """Build a dictionary of all object definitions from the story.
    
    Args:
        game_state: The current game state.
        
    Returns:
        Dict mapping object IDs to their definitions.
    """
    all_object_definitions = {}
    
    # Add story-level objects
    if game_state.story.objects:
        for obj in game_state.story.objects:
            all_object_definitions[obj.id] = obj.dict()
    
    # Add node-level objects
    for node in game_state.story.nodes.values():
        for obj in node.objects:
            all_object_definitions[obj.id] = obj.dict()
    
    return all_object_definitions


async def build_game_state_dict(
    game_state: GameState, 
    session_id: str,
    player_id: Optional[str] = None,
    game_kernel: Optional[Any] = None,
    include_diff: bool = True,
    current_perception: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a standardized game state dictionary for sending to clients.
    
    Args:
        game_state: The current game state.
        session_id: The session ID.
        player_id: Optional player ID for player-specific data.
        game_kernel: Optional game kernel for getting player-specific perception.
        include_diff: Whether to include object definitions in a 'diff' key.
        current_perception: Optional precomputed player-facing scene text.
        
    Returns:
        A dictionary representation of the game state.
    """
    all_object_definitions = build_object_definitions(game_state)
    
    game_state_dict = {
        "story_id": game_state.story_id,
        "variables": game_state._extract_changed_variables(),
        "nodes": {node_id: node.dict() for node_id, node in game_state.nodes.items()},
        "session_id": session_id,
        "visited_nodes": game_state.visited_nodes,
    }

    if player_id:
        inventory = []
        for item_id in game_state.get_player_inventory(player_id):
            obj = game_state.resolve_inventory_object(item_id)
            inventory.append({
                "id": item_id,
                "name": obj.name if obj else item_id,
            })
        game_state_dict["player_state"] = {
            "player_id": player_id,
            "controlled_character_id": game_state.get_controlled_character_id(player_id),
            "location": game_state.get_player_location(player_id),
            "inventory": inventory,
            "status": game_state.get_player_status(player_id),
        }

    # Add processed description for player's current location.
    current_node_id = None
    if player_id and game_kernel:
        player_location = game_state.get_player_location(player_id)
        if player_location:
            current_node_id = player_location
            full_description = current_perception
            if full_description is None:
                full_description = await game_kernel.get_node_perception(
                    game_state, player_location, player_id
                )
            if player_location in game_state_dict['nodes']:
                game_state_dict['nodes'][player_location]['processed_description'] = full_description
    
    if game_state.story.characters:
        character_list = []
        for character in game_state.story.characters:
            in_current_node = game_state.is_character_in_node(character.id, current_node_id) if current_node_id else False
            if in_current_node:
                character_list.append({
                    "id": character.id,
                    "name": character.name,
                    "is_playable": character.is_playable
                })
                
        game_state_dict["characters"] = character_list
    
    if include_diff:
        game_state_dict["diff"] = {
            "all_object_definitions": all_object_definitions
        }
    else:
        game_state_dict["all_object_definitions"] = all_object_definitions
    
    # Add resolved stats display if configured
    if player_id and game_state.story.status_display_config:
        resolver = get_status_display_resolver()
        stats_display = resolver.resolve_stats_display(game_state.story, game_state, player_id)
        if stats_display:
            game_state_dict['stats_display'] = stats_display
    
    return game_state_dict


def format_stories_list(stories: list) -> list:
    """Format a list of stories for sending to clients.
    
    Args:
        stories: Raw story list from story manager.
        
    Returns:
        Formatted list with id, title, description.
    """
    return [{"id": s['id'], "title": s['title'], "description": s.get('description', '')} for s in stories]



