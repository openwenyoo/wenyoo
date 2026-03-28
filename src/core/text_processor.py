"""
Text processing utilities for the game engine.
Handles variable substitution, hyperlink generation, and description building.
"""

import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState

logger = logging.getLogger(__name__)


class TextProcessor:
    """Handles text substitution, hyperlinks, and description generation."""

    def _substitute_character_refs(self, text: str, game_state: 'GameState') -> str:
        """
        Substitute character references in text.
        
        Supports patterns like:
        - {@{$variable}.field} - resolve variable first, then look up character
          Example: {@{$companion_id}.persona} - if companion_id="laozhou", gets laozhou's persona
        - {@character_id.field} - direct character lookup by literal ID
          Example: {@laozhou.persona} - gets laozhou's persona directly
        
        Fields can be top-level (name, description) or from parameters dict (persona, inventory).
        
        Args:
            text: Text containing character references
            game_state: Current game state
            
        Returns:
            Text with character references substituted
        """
        if not text or '{@' not in text:
            return text
        
        # Pattern 1: {@{$variable}.field} - variable-based character lookup
        # This resolves the inner variable first, then uses it as character ID
        pattern_with_var = r'\{@\{\$(\w+)\}\.([^}]+)\}'
        
        def replace_var_char_ref(match):
            var_name = match.group(1)  # Variable name like 'companion_id'
            field_path = match.group(2)  # 'persona', 'name', etc.
            
            # Resolve variable to get character ID
            char_id = game_state.variables.get(var_name)
            if not char_id:
                logger.debug(f"Character ref substitution: variable '{var_name}' not set or empty")
                return match.group(0)
            
            return self._resolve_character_field(game_state, char_id, field_path, match.group(0))
        
        text = re.sub(pattern_with_var, replace_var_char_ref, text)
        
        # Pattern 2: {@character_id.field} - direct character lookup
        pattern_direct = r'\{@(\w+)\.([^}]+)\}'
        
        def replace_direct_char_ref(match):
            char_id = match.group(1)  # Character ID like 'laozhou'
            field_path = match.group(2)  # 'persona', 'name', etc.
            
            return self._resolve_character_field(game_state, char_id, field_path, match.group(0))
        
        text = re.sub(pattern_direct, replace_direct_char_ref, text)
        
        return text
    
    def _resolve_character_field(self, game_state: 'GameState', char_id: str, field_path: str, original: str) -> str:
        """
        Resolve a field from a character by ID.
        
        Args:
            game_state: Current game state
            char_id: Character ID to look up
            field_path: Dot-separated field path (e.g., 'persona', 'name', 'parameters.inventory')
            original: Original match string to return if resolution fails
            
        Returns:
            Resolved field value as string, or original if not found
        """
        # Find the character in story
        story = game_state.story
        if not story or not story.characters:
            logger.debug(f"Character ref substitution: no story or characters")
            return original
        
        character = next((c for c in story.characters if c.id == char_id), None)
        if not character:
            logger.debug(f"Character ref substitution: character '{char_id}' not found")
            return original
        
        # Resolve field path
        field_parts = field_path.split('.')
        value = None
        
        # First part could be a top-level attribute or a parameters key
        first_part = field_parts[0]
        
        # Check top-level attributes first (name, description, id, etc.)
        if hasattr(character, first_part) and first_part not in ('parameters',):
            value = getattr(character, first_part)
            field_parts = field_parts[1:]
        # Check if accessing parameters explicitly
        elif first_part == 'parameters' and len(field_parts) > 1:
            value = character.parameters.get(field_parts[1])
            field_parts = field_parts[2:]
        # Check parameters dict directly (shorthand for parameters.X)
        elif first_part in character.parameters:
            value = character.parameters[first_part]
            field_parts = field_parts[1:]
        else:
            logger.debug(f"Character ref substitution: field '{first_part}' not found on character '{char_id}'")
            return original
        
        if value is None:
            logger.debug(f"Character ref substitution: field '{field_path}' is None on character '{char_id}'")
            return original
        
        # Continue resolving nested path
        for part in field_parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                logger.debug(f"Character ref substitution: cannot resolve '{part}' in path")
                return original
            
            if value is None:
                return original
        
        return str(value)

    def process_text_for_hyperlinks(self, text: str, game_state: 'GameState', player_id: str) -> str:
        """
        Process text to convert hyperlink patterns into abstract link tokens.

        Syntax:
        - {@character_id: display_text}  → character link
        - {object_id: display_text}      → object link (when object_id matches a known object)
        - {display_text: action_hint}    → input link (display_text shown, action_hint sent to Architect)
        - {display_text}                 → input link (no hint)

        The adapter layer converts ``[[type:...|...]]`` tokens into client markup.
        """
        if not text or not game_state or not getattr(game_state, 'story', None):
            return text or ""

        def replace_match(match):
            full_match = match.group(0)
            is_character = match.group(1) == '@'
            label = match.group(2)
            value = match.group(3)
            if value:
                value = value.strip()

            # 1. Character link: {@character_id: display_text}
            if is_character:
                story = game_state.story
                character = next((c for c in story.characters if c.id == label), None)
                if character:
                    final_display_text = value or character.name
                    return f'[[character:{label}|{final_display_text}]]'
                return full_match

            # 2. Object link: {object_id: display_text} when object_id is known
            current_node = game_state.get_current_node(player_id)
            obj = None
            if current_node:
                obj = next((o for o in current_node.objects
                           if o.id == label
                           and game_state.is_object_visible(o)
                           and "taken" not in game_state.get_effective_object_status(o)), None)
            if not obj:
                inventory = game_state.get_player_inventory(player_id)
                if label in inventory:
                    obj = game_state.resolve_inventory_object(label)
            if not obj:
                obj = game_state.story.get_object(label)

            if obj:
                final_display_text = value or obj.name
                return f'[[object:{label}|{final_display_text}]]'

            # 3. Input link: {display_text: action_hint} or {display_text}
            #    label = display_text (what the player sees)
            #    value = action_hint  (context for the Architect, may be empty)
            #    Guard: bare ASCII-only tokens without colon are likely failed
            #    variable substitutions — leave them unchanged.
            if not value and label.isascii():
                return full_match

            display_text = label
            action_hint = value or ""
            return f'[[input:{display_text}|{action_hint}]]'

        return re.sub(r'\{(@)?([\w_]+)(?::\s*([^}]+))?\}', replace_match, text)

    def substitute_variables(self, text: str, game_state: 'GameState', player_id: str) -> str:
        """
        Substitute variable references in text with their actual values.
        
        Supports patterns like:
        - {$variable_name} or {{variable_name}}
        - {$variable[0].property} for array access
        - {$nested.path.to.value} for nested access
        - {@companion.field} for current companion's data
        - {@character_id.field} for specific character's data
        
        Args:
            text: Text containing variable references
            game_state: Current game state
            player_id: ID of the player
            
        Returns:
            Text with variables substituted
        """
        if not text:
            return ""
        
        # First, process character references {@...}
        text = self._substitute_character_refs(text, game_state)
        
        def replace_variable(match):
            variable_path = match.group(1)
            
            # First, substitute {player_id} within the variable path
            # This handles patterns like {$players.{player_id}.character.name}
            variable_path = variable_path.replace("{player_id}", player_id)
            
            # Handle 'player' paths using pointer model
            # 'player' dereferences to the controlled character's state
            if variable_path.startswith('player.') or variable_path == 'player':
                value = game_state.resolve_player_path(variable_path, player_id)
                if value is None:
                    return match.group(0)
                
                # Special handling for inventory - format as list of names
                if variable_path == 'player.properties.inventory' or variable_path == 'player.inventory':
                    if isinstance(value, list):
                        inventory_names = []
                        for item_ref in value:
                            resolved = game_state.resolve_inventory_object(item_ref)
                            inventory_names.append(resolved.name if resolved else str(item_ref))
                        return ", ".join(inventory_names) if inventory_names else "Empty"
                
                return str(value)
            
            # Handle array indexing like variable[0].name
            if '[' in variable_path and ']' in variable_path:
                # Parse array access
                base_var = variable_path.split('[')[0]
                rest = variable_path[len(base_var):]
                
                # Use get_variable() to support derived variables
                value = game_state.get_variable(base_var, player_id=player_id)
                if value is None:
                    return match.group(0)
                
                # Process array indices and property access
                array_pattern = r'\[(\d+)\]'
                property_pattern = r'\.(\w+)'
                
                current_pos = 0
                while current_pos < len(rest):
                    # Check for array index
                    array_match = re.match(array_pattern, rest[current_pos:])
                    if array_match:
                        index = int(array_match.group(1))
                        if isinstance(value, list) and 0 <= index < len(value):
                            value = value[index]
                        else:
                            return match.group(0)
                        current_pos += array_match.end()
                        continue
                    
                    # Check for property access
                    property_match = re.match(property_pattern, rest[current_pos:])
                    if property_match:
                        prop_name = property_match.group(1)
                        if isinstance(value, dict):
                            new_value = value.get(prop_name)
                            if new_value is None:
                                logger.debug(f"Variable substitution: property '{prop_name}' not found in dict with keys: {list(value.keys())}")
                            value = new_value
                        else:
                            try:
                                value = getattr(value, prop_name)
                            except AttributeError:
                                logger.debug(f"Variable substitution: attribute '{prop_name}' not found on object {type(value)}")
                                return match.group(0)
                        if value is None:
                            return match.group(0)
                        current_pos += property_match.end()
                        continue
                    
                    # If we can't match anything, return original
                    return match.group(0)
                
                return str(value)
            else:
                # Handle simple dot notation
                parts = variable_path.split('.')
                
                # Use get_variable() for the first part to support derived variables
                first_part = parts[0]
                value = game_state.get_variable(first_part, player_id=player_id)
                
                # If not found directly, check in variables dict
                if value is None:
                    value = game_state.variables.get(first_part)
                
                if value is None:
                    return match.group(0)
                
                # Continue with remaining path parts
                try:
                    for part in parts[1:]:
                        if isinstance(value, dict):
                            value = value.get(part)
                        else:
                            value = getattr(value, part)
                        if value is None:
                            return match.group(0)
                except (KeyError, AttributeError):
                    return match.group(0)

            return str(value)

        # Run substitution for both patterns
        # Use a pattern that handles nested braces like {$players.{player_id}.name}
        # Pattern explanation:
        # - {\$ matches the opening {$
        # - ([^{}]*(?:\{[^{}]*\}[^{}]*)*) captures content with nested {} pairs
        # - } matches the closing }
        pattern1 = r'{\$([^{}]*(?:\{[^{}]*\}[^{}]*)*)}'
        pattern2 = r'{{([^{}]*(?:\{[^{}]*\}[^{}]*)*)}}'
        
        text = re.sub(pattern1, replace_variable, text)
        text = re.sub(pattern2, replace_variable, text)
        
        # Also support single-brace {variable_name} as a convenience pattern.
        # Only substitutes if the variable actually exists in game state,
        # otherwise leaves it untouched for hyperlink processing by
        # process_text_for_hyperlinks() which also uses {id} and {id: text}.
        def replace_simple_variable(match):
            var_name = match.group(1)
            # Use get_variable() which supports derived variables
            value = game_state.get_variable(var_name, player_id=player_id)
            if value is None:
                value = game_state.variables.get(var_name)
            if value is not None:
                return str(value)
            # Not a known variable - leave for hyperlink processing
            return match.group(0)
        
        pattern_simple = r'\{([a-zA-Z_]\w*(?:\.\w+)*)\}'
        text = re.sub(pattern_simple, replace_simple_variable, text)
            
        return text

    def get_status_bar_text(self, game_state: 'GameState', player_id: str) -> str:
        """
        Get the status bar text for the current node.
        
        Args:
            game_state: Current game state
            player_id: ID of the player
            
        Returns:
            Status bar text string
        """
        current_node = game_state.get_current_node(player_id)
        if not current_node:
            return "Unknown Location"

        status_bar_def = getattr(current_node, 'status_bar', None)
        
        if status_bar_def and 'text' in status_bar_def:
            raw_text = status_bar_def['text']
            return self.substitute_variables(raw_text, game_state, player_id)
        else:
            return current_node.name or current_node.id

