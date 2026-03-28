"""
Variable resolution utilities for the game engine.
Handles extracting values from game state using dot-notation paths.
"""

import re
import logging
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState

logger = logging.getLogger(__name__)


class VariableResolver:
    """Handles variable path resolution and condition evaluation."""

    def resolve_path_in_context(self, path: str, context: Dict) -> Any:
        """
        Resolve a dot-notation path within a given context dictionary.
        
        Args:
            path: Dot-notation path (e.g., "player_character.name")
            context: Dictionary to resolve path in
            
        Returns:
            The resolved value or None if not found
        """
        try:
            logger.debug(f"resolve_path_in_context called with path: '{path}', context keys: {list(context.keys())}")
            
            obj = context
            parts = path.split(".")
            
            for i, part in enumerate(parts):
                logger.debug(f"Processing context part '{part}' (step {i+1}/{len(parts)}), current obj type: {type(obj)}")
                
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                    logger.debug(f"Found attribute '{part}', new obj: {obj}")
                elif isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                    logger.debug(f"Found dict key '{part}', new obj: {obj}")
                elif isinstance(obj, list) and part.isdigit():
                    obj = obj[int(part)]
                    logger.debug(f"Found list index '{part}', new obj: {obj}")
                else:
                    logger.debug(f"Could not find '{part}' in context obj type {type(obj)}")
                    if isinstance(obj, dict):
                        logger.debug(f"Available dict keys: {list(obj.keys())}")
                    elif hasattr(obj, '__dict__'):
                        logger.debug(f"Available attributes: {list(obj.__dict__.keys())}")
                    return None
            
            return obj
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            logger.debug(f"Path resolution failed for '{path}': {e}")
            return None

    def get_variable_value(self, path: str, game_state: 'GameState',
                          user_input: str, player_id: str) -> Any:
        """
        Extract a variable value from game state using a dot-notation path.
        
        Args:
            path: Variable path (e.g., "variables.player_name")
            game_state: Current game state
            user_input: The user's input string
            player_id: ID of the player
            
        Returns:
            The resolved value or None if not found
        """
        try:
            logger.debug(f"get_variable_value called with path: '{path}'")
            
            if path == "user_input":
                return user_input
            
            # Handle 'player' paths using pointer model
            # 'player' dereferences to the controlled character's state
            if path.startswith("player.") or path == "player":
                return game_state.resolve_player_path(path, player_id)
            
            # Handle other paths (game_state, etc.)
            obj = game_state
            parts = path.split(".")
            logger.debug(f"Game state path, parts: {parts}")
            logger.debug(f"Game state variables: {list(game_state.variables.keys()) if hasattr(game_state, 'variables') else 'No variables'}")
            
            # Check if the first part is a variable in game_state.variables
            if parts and hasattr(game_state, 'variables') and parts[0] in game_state.variables:
                logger.debug(f"Found '{parts[0]}' in game_state.variables")
                obj = game_state.variables[parts[0]]
                parts = parts[1:]  # Remove the first part since we've resolved it
                logger.debug(f"Starting from variable, obj type: {type(obj)}, remaining parts: {parts}")
            
            for i, part in enumerate(parts):
                logger.debug(f"Processing part '{part}' (step {i+1}/{len(parts)}), current obj type: {type(obj)}")
                
                # Special handling for 'variables' - go directly to the variables dict
                if part == "variables" and hasattr(obj, 'variables'):
                    obj = obj.variables
                    logger.debug(f"Switched to variables dict: {obj}")
                    continue
                
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                    logger.debug(f"Found attribute '{part}', new obj type: {type(obj)}, value: {obj}")
                elif isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                    logger.debug(f"Found dict key '{part}', new obj type: {type(obj)}, value: {obj}")
                elif isinstance(obj, list) and part.isdigit():
                    obj = obj[int(part)]
                    logger.debug(f"Found list index '{part}', new obj type: {type(obj)}, value: {obj}")
                else:
                    logger.debug(f"Could not find '{part}' in obj type {type(obj)}")
                    if isinstance(obj, dict):
                        logger.debug(f"Available dict keys: {list(obj.keys())}")
                    elif hasattr(obj, '__dict__'):
                        logger.debug(f"Available attributes: {list(obj.__dict__.keys())}")
                    return None
            
            logger.debug(f"Final result for path '{path}': {obj} (type: {type(obj)})")
            return obj
            
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            logger.debug(f"Variable resolution failed for '{path}': {e}")
            return None

    def evaluate_condition(self, condition_str: str, game_state: 'GameState', player_id: str) -> bool:
        """
        Evaluate a condition string.
        
        Supported conditions:
        - player.stats.<stat_name> <operator> <value>
        - player.properties.stats.<stat_name> <operator> <value> (pointer model)
        - player.inventory.has <item_id>
        - player.inventory.not_has <item_id>
        """
        logger.debug(f"Evaluating condition: {condition_str}")
        
        # player.stats.<stat_name> or player.properties.stats.<stat_name> <operator> <value>
        # Use pointer model to resolve stats
        match = re.match(r"player\.(?:properties\.)?stats\.(\w+)\s*([<>=!]+)\s*(\d+)", condition_str)
        if match:
            stat_name, operator, value = match.groups()
            value = int(value)
            
            # Use pointer model to get stats
            stats = game_state.resolve_player_path('player.properties.stats', player_id)
            if not stats:
                stats = {}
            stat_value = stats.get(stat_name, 0) if isinstance(stats, dict) else 0
            
            op_map = {
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                ">": lambda a, b: a > b,
                "<": lambda a, b: a < b,
                ">=": lambda a, b: a >= b,
                "<=": lambda a, b: a <= b,
            }
            
            if operator in op_map:
                return op_map[operator](stat_value, value)
            else:
                logger.warning(f"Unsupported operator in condition: {operator}")
                return False

        # player.inventory.has <item_id>
        match = re.match(r"player\.(?:properties\.)?inventory\.has\s+(\w+)", condition_str)
        if match:
            item_id = match.groups()[0]
            inventory = game_state.get_player_inventory(player_id)
            return any(getattr(item, 'id', item) == item_id for item in inventory)

        # player.inventory.not_has <item_id>
        match = re.match(r"player\.(?:properties\.)?inventory\.not_has\s+(\w+)", condition_str)
        if match:
            item_id = match.groups()[0]
            inventory = game_state.get_player_inventory(player_id)
            return not any(getattr(item, 'id', item) == item_id for item in inventory)
            
        logger.warning(f"Unsupported condition format: {condition_str}")
        return False

