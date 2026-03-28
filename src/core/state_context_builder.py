"""
State Context Builder for LLM-powered character interactions.

This module builds comprehensive player state context for LLM prompts,
enabling the LLM to make informed decisions about what actions are valid.
"""

import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState
    from src.models.story_models import Story, Character

logger = logging.getLogger(__name__)


class StateContextBuilder:
    """
    Builds comprehensive player state context for LLM prompts.
    
    This enables the LLM to understand:
    - What the player has (inventory)
    - What the player can do (stats, abilities)
    - Where the player is (location, available objects)
    - Who is present (characters nearby and their generic runtime state)
    """
    
    def build_context(
        self, 
        game_state: 'GameState', 
        player_id: str, 
        story: 'Story',
        target_character: Optional['Character'] = None
    ) -> Dict[str, Any]:
        """
        Build complete player state context for LLM.
        
        Args:
            game_state: Current game state
            player_id: The player's ID
            story: The story definition
            target_character: Optional target character for interaction context
            
        Returns:
            Dictionary containing all relevant state information
        """
        characters_present = self._get_characters_present_context(game_state, player_id, story)
        return {
            "inventory": self._get_inventory_context(game_state, player_id),
            "stats": self._get_stats_context(game_state, player_id),
            "location": self._get_location_context(game_state, player_id),
            "available_objects": self._get_objects_context(game_state, player_id),
            "characters_present": characters_present,
            "npcs_present": characters_present,
            "variables": self._get_relevant_variables(game_state, player_id),
            "target_character": self._get_target_character_context(target_character, game_state, player_id) if target_character else None,
        }
    
    def _get_inventory_context(self, game_state: 'GameState', player_id: str) -> Dict[str, Any]:
        """Get player inventory information using pointer model."""
        inventory = game_state.get_player_inventory(player_id)
        items = []
        for item_id in inventory:
            resolved = game_state.resolve_inventory_object(item_id)
            items.append({
                "id": item_id,
                "name": resolved.name if resolved else item_id,
                "definition": (
                    getattr(resolved, 'definition', '') or getattr(resolved, 'explicit_state', '')
                ) if resolved else ''
            })
        
        item_names = [item["name"] for item in items]
        item_ids = [item["id"] for item in items]
        
        return {
            "items": items,
            "item_names": item_names,
            "item_ids": item_ids,
            "is_empty": len(items) == 0
        }
    
    def _get_stats_context(self, game_state: 'GameState', player_id: str) -> Dict[str, Any]:
        """Get player stats/attributes using pointer model."""
        # Use pointer model to get stats from character_states
        char_id = game_state.get_controlled_character_id(player_id)
        
        stats = {}
        character_name = None
        
        if char_id:
            # Get from character_states (pointer model)
            char_state = game_state.character_states.get(char_id, {})
            props = char_state.get('properties', {})
            stats = props.get('stats', {})
            
            # Get character name from story definition
            if game_state.story and game_state.story.characters:
                for char in game_state.story.characters:
                    if char.id == char_id:
                        character_name = char.name
                        break
        
        return {
            "stats": stats,
            "character_id": char_id,
            "character_name": character_name
        }
    
    def _get_location_context(self, game_state: 'GameState', player_id: str) -> Dict[str, Any]:
        """Get current location information using pointer model."""
        # Use pointer model to get location
        location_id = game_state.get_player_location(player_id)
        
        current_node = game_state.nodes.get(location_id) if location_id else None
        
        if not current_node:
            return {"id": location_id, "name": "Unknown", "explicit_state": ""}
        
        return {
            "id": location_id,
            "name": current_node.name or location_id,
            "explicit_state": current_node.explicit_state or ""
        }
    
    def _get_objects_context(self, game_state: 'GameState', player_id: str) -> List[Dict[str, Any]]:
        """Get objects available at current location using pointer model."""
        location_id = game_state.get_player_location(player_id)
        
        current_node = game_state.nodes.get(location_id) if location_id else None
        if not current_node or not current_node.objects:
            return []
        
        objects = []
        for obj in current_node.objects:
            if game_state.is_object_visible(obj):
                objects.append({
                    "id": obj.id,
                    "name": obj.name,
                    "status": obj.get_status() if hasattr(obj, 'get_status') else [],
                    "definition": getattr(obj, 'definition', ''),
                    "explicit_state": getattr(obj, 'explicit_state', ''),
                    "properties": getattr(obj, 'properties', {}),
                })
        
        return objects
    
    def _get_characters_present_context(
        self, 
        game_state: 'GameState', 
        player_id: str, 
        story: 'Story'
    ) -> List[Dict[str, Any]]:
        """Get non-playable characters present at current location."""
        location_id = game_state.get_player_location(player_id)
        
        if not story.characters:
            return []
        
        characters = []
        for char in story.characters:
            if char.is_playable:
                continue

            if game_state.get_character_location(char.id) == location_id:
                char_state = game_state.character_states.get(char.id, {})
                characters.append({
                    "id": char.id,
                    "name": char.name,
                    "definition": char.definition,
                    "explicit_state": char_state.get("explicit_state", char.explicit_state),
                    "properties": char_state.get("properties", {}),
                })
        
        return characters
    
    def _get_target_character_context(
        self, 
        character: 'Character', 
        game_state: 'GameState',
        player_id: str,
    ) -> Dict[str, Any]:
        """Get generic context for the target character."""
        char_state = game_state.character_states.get(character.id, {})
        properties = char_state.get("properties", {})
        inventory = properties.get("inventory", character.get_inventory())
        memory = char_state.get("memory", character.memory)
        
        return {
            "id": character.id,
            "name": character.name,
            "definition": character.definition,
            "explicit_state": char_state.get("explicit_state", character.explicit_state),
            "implicit_state": char_state.get("implicit_state", character.implicit_state),
            "inventory": inventory,
            "properties": properties,
            "memory": memory,
        }
    
    def _get_relevant_variables(self, game_state: 'GameState', player_id: str) -> Dict[str, Any]:
        """Get relevant game variables (excluding internal/system ones)."""
        # Filter out internal variables, keep story-relevant ones
        excluded_prefixes = ('players', '_', 'system_')
        
        relevant = {}
        for key, value in game_state.variables.items():
            if not any(key.startswith(prefix) for prefix in excluded_prefixes):
                # Only include simple types, not complex objects
                if isinstance(value, (str, int, float, bool, list)):
                    relevant[key] = value
                elif isinstance(value, dict) and len(str(value)) < 500:
                    relevant[key] = value
        
        return relevant
    
    def format_for_prompt(self, context: Dict[str, Any], user_input: str = "") -> str:
        """
        Format context as readable text for LLM prompt.
        
        Args:
            context: The context dictionary from build_context()
            user_input: The player's input (to detect mentioned items)
            
        Returns:
            Formatted string for inclusion in LLM prompt
        """
        lines = []
        
        # Inventory section
        inventory = context.get("inventory", {})
        if inventory.get("is_empty"):
            lines.append("Inventory: Empty")
        else:
            item_names = inventory.get("item_names", [])
            lines.append(f"Inventory: {', '.join(item_names)}")
        
        # Check if user mentioned items not in inventory
        if user_input and inventory.get("item_ids"):
            # This is a simple check - could be enhanced with NLP
            mentioned_not_owned = self._detect_mentioned_items(
                user_input, 
                inventory.get("item_ids", []),
                inventory.get("item_names", [])
            )
            if mentioned_not_owned:
                lines.append(f"⚠ Items mentioned but NOT in inventory: {', '.join(mentioned_not_owned)}")
        
        # Stats section
        stats = context.get("stats", {}).get("stats", {})
        if stats:
            stats_str = ", ".join([f"{k}: {v}" for k, v in stats.items() 
                                   if isinstance(v, (int, float, str))])
            if stats_str:
                lines.append(f"Stats: {stats_str}")
        
        # Location section
        location = context.get("location", {})
        lines.append(f"Location: {location.get('name', 'Unknown')}")
        
        # Available objects
        objects = context.get("available_objects", [])
        if objects:
            obj_names = [obj.get("name", obj.get("id")) for obj in objects]
            lines.append(f"Objects here: {', '.join(obj_names)}")
        
        # Nearby characters
        characters_present = context.get("characters_present", context.get("npcs_present", []))
        if characters_present:
            character_names = [char.get("name", char.get("id")) for char in characters_present]
            lines.append(f"Characters here: {', '.join(character_names)}")

        # Target character info
        target_character = context.get("target_character")
        if target_character:
            lines.append(f"\nTarget character: {target_character.get('name')}")
            if target_character.get("definition"):
                lines.append(f"Definition: {target_character.get('definition')}")
            if target_character.get("explicit_state"):
                lines.append(f"Visible state: {target_character.get('explicit_state')}")
            if target_character.get("inventory"):
                lines.append(f"Inventory: {', '.join(target_character.get('inventory', []))}")
        
        # Relevant variables
        variables = context.get("variables", {})
        if variables:
            # Only show a few most relevant ones
            var_items = list(variables.items())[:10]
            if var_items:
                var_str = ", ".join([f"{k}={v}" for k, v in var_items])
                lines.append(f"Game state: {var_str}")
        
        return "\n".join(lines)
    
    def _detect_mentioned_items(
        self, 
        user_input: str, 
        owned_ids: List[str], 
        owned_names: List[str]
    ) -> List[str]:
        """
        Detect items mentioned in user input that player doesn't own.
        
        This is a simple keyword-based detection. Could be enhanced with NLP.
        """
        # Common item-related words to look for after
        # This is a simple heuristic - the LLM will do the real validation
        user_lower = user_input.lower()
        
        # Check if any owned items are mentioned (if so, probably valid)
        for name in owned_names:
            if name.lower() in user_lower:
                return []  # Player is referring to something they have
        
        for item_id in owned_ids:
            if item_id.lower() in user_lower:
                return []
        
        # If we reach here and the input contains give/use/show type words,
        # the LLM should be aware the player might be trying to use something they don't have
        # We don't try to extract the exact item name here - let the LLM figure it out
        return []
