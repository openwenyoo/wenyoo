"""
Status display resolver for the game engine.
Handles loading templates, merging configurations, and resolving stat values.
"""

import logging
import os
import re
from typing import Dict, Any, List, Optional, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.models.game_state import GameState
    from src.models.story_models import Story, StatusDisplayConfig, StatsDisplayItem

logger = logging.getLogger(__name__)


class StatusDisplayResolver:
    """Resolves status display configuration and values for the frontend."""
    
    def __init__(self, templates_dir: str = "stories/status_display_templates"):
        """
        Initialize the resolver.
        
        Args:
            templates_dir: Directory containing status display template files
        """
        self.templates_dir = templates_dir
        self._template_cache: Dict[str, Dict[str, Any]] = {}
    
    def load_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a status display template by ID.
        
        Args:
            template_id: The template identifier
            
        Returns:
            Template data dict or None if not found
        """
        if template_id in self._template_cache:
            return self._template_cache[template_id]
        
        if not os.path.exists(self.templates_dir):
            logger.warning(f"Templates directory does not exist: {self.templates_dir}")
            return None
        
        template_file = os.path.join(self.templates_dir, f"{template_id}.yaml")
        if not os.path.exists(template_file):
            logger.warning(f"Template file not found: {template_file}")
            return None
        
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                template_data = yaml.safe_load(f)
            self._template_cache[template_id] = template_data
            logger.info(f"Loaded status display template: {template_id}")
            return template_data
        except Exception as e:
            logger.error(f"Error loading template {template_id}: {e}")
            return None
    
    def resolve_config(self, story: 'Story') -> List[Dict[str, Any]]:
        """
        Resolve the final list of stats items from story config and templates.
        
        Resolution order:
        1. Load template stats (if template specified)
        2. Apply stats_override (match by label, replace)
        3. Append stats (additive)
        
        Args:
            story: The story with status_display_config
            
        Returns:
            List of stats item definitions (not yet resolved values)
        """
        config = story.status_display_config
        if not config:
            return []
        
        # Start with template stats if specified
        stats_items: List[Dict[str, Any]] = []
        
        if config.template:
            template = self.load_template(config.template)
            if template and 'stats' in template:
                stats_items = [item.copy() if isinstance(item, dict) else item 
                              for item in template['stats']]
        
        # Apply overrides (match by label)
        if config.stats_override:
            for override_item in config.stats_override:
                override_label = override_item.label
                found = False
                for i, existing in enumerate(stats_items):
                    existing_label = existing.get('label') if isinstance(existing, dict) else existing.label
                    if existing_label == override_label:
                        # Replace with override
                        stats_items[i] = override_item.model_dump()
                        found = True
                        break
                if not found:
                    logger.warning(f"stats_override label '{override_label}' not found in template")
        
        # Append additive stats
        if config.stats:
            for stat_item in config.stats:
                stats_items.append(stat_item.model_dump())
        
        return stats_items
    
    def resolve_stats_display(
        self, 
        story: 'Story', 
        game_state: 'GameState', 
        player_id: str
    ) -> List[Dict[str, str]]:
        """
        Resolve all stats to their display values.
        
        Args:
            story: The story definition
            game_state: Current game state
            player_id: ID of the player
            
        Returns:
            List of {"label": "...", "display": "..."} dicts ready for frontend
        """
        stats_items = self.resolve_config(story)
        if not stats_items:
            return []
        
        result = []
        for item in stats_items:
            label = item.get('label', '')
            format_str = item.get('format', '')
            values_map = item.get('values', {})
            
            # Resolve each value in the values map
            resolved_values = {}
            for var_name, var_path in values_map.items():
                resolved_value = self._resolve_variable_path(var_path, game_state, player_id)
                resolved_values[var_name] = resolved_value
            
            # Substitute into format string
            display_text = self._substitute_format(format_str, resolved_values)
            
            result.append({
                "label": label,
                "display": display_text
            })
        
        return result
    
    def _resolve_variable_path(
        self, 
        path: str, 
        game_state: 'GameState', 
        player_id: str
    ) -> str:
        """
        Resolve a variable path to its actual value.
        
        Supports patterns like:
        - {$variable_name} or {{variable_name}}
        - {$players.{player_id}.character.stats.hp}
        - Plain variable paths without braces
        
        Args:
            path: The variable path (may include {$...} or {{...}} syntax)
            game_state: Current game state
            player_id: ID of the player
            
        Returns:
            The resolved value as a string
        """
        # First, substitute {player_id} with actual player_id
        path = path.replace("{player_id}", player_id)
        
        # Check if path uses {$...} or {{...}} syntax
        match = re.match(r'^\{\$?(.*?)\}$', path) or re.match(r'^\{\{(.*?)\}\}$', path)
        if match:
            variable_path = match.group(1)
        else:
            # Assume it's a plain path
            variable_path = path
        
        # Handle nested path resolution
        return self._get_nested_value(variable_path, game_state)
    
    def _get_nested_value(self, path: str, game_state: 'GameState') -> str:
        """
        Get a nested value from game state variables.
        
        Args:
            path: Dot-separated path like "players.player1.character.stats.hp"
            game_state: Current game state
            
        Returns:
            The value as a string, or "?" if not found
        """
        parts = path.split('.')
        value = game_state.variables
        
        try:
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return "?"
                
                if value is None:
                    return "?"
            
            return str(value)
        except (KeyError, AttributeError, TypeError) as e:
            logger.debug(f"Failed to resolve path '{path}': {e}")
            return "?"
    
    def _substitute_format(self, format_str: str, values: Dict[str, str]) -> str:
        """
        Substitute local variable names in format string with resolved values.
        
        Args:
            format_str: Format string like "{hp}/{max_hp}"
            values: Dict of resolved values like {"hp": "80", "max_hp": "100"}
            
        Returns:
            Substituted string like "80/100"
        """
        result = format_str
        for var_name, var_value in values.items():
            result = result.replace(f"{{{var_name}}}", var_value)
        return result

