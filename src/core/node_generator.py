"""
Dynamic node generation system for the game engine.
Handles LLM-based node generation for procedural content.
"""

import asyncio
import json
import re
import yaml
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

from src.models.story_models import StoryNode

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel
    from src.models.game_state import GameState

logger = logging.getLogger(__name__)


class NodeGenerator:
    """Handles dynamic generation of story nodes using LLM."""

    def __init__(self, game_kernel: 'GameKernel'):
        """
        Initialize the node generator.
        
        Args:
            game_kernel: Reference to the main game kernel
        """
        self.game_kernel = game_kernel

    async def proactively_generate_linked_nodes_async(self, game_state: 'GameState', node_id: str):
        """
        Proactively generate linked nodes in the background to improve performance.
        
        Args:
            game_state: Current game state
            node_id: ID of the current node to check for linked nodes
        """
        node = game_state.nodes.get(node_id)
        if not node:
            logger.warning(f"Proactive check failed: Node '{node_id}' not found in game state.")
            return

        logger.info(f"Proactively checking for linked nodes from '{node_id}'...")
        
        # Get actions from the node (objects no longer have actions - they use definition field)
        all_actions = list(node.actions)

        for action in all_actions:
            logger.debug(f"Proactive check: Inspecting action '{action.id}' in node '{node_id}'.")
            for effect in action.effects:
                if effect.type == "goto_node":
                    target_node_id = effect.target
                    logger.debug(f"Proactive check: Found goto_node effect targeting '{target_node_id}'.")
                    
                    target_node = game_state.nodes.get(target_node_id)
                    if target_node and getattr(target_node, 'type', None) == 'generated' and target_node_id not in self.game_kernel._generation_in_progress:
                        logger.info(f"Found ungenerated linked node '{target_node_id}'. Generating in background.")
                        task = asyncio.create_task(self.generate_and_replace_node_async(game_state, target_node_id))
                        self.game_kernel._generation_in_progress[target_node_id] = task

    def _load_generation_prompt(self) -> str:
        """Load the node generation prompt template from file."""
        prompt_path = "prompts/generate_node.txt"
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Node generation prompt not found: {prompt_path}")
            # Return minimal fallback
            return """Generate a story node in YAML format.
            
=== STORY CONTEXT ===
{story_context}

=== NODE TO GENERATE ===
{generation_prompt}

=== AVAILABLE CONNECTIONS ===
{available_locations}

=== HINTS ===
{hints}

Output valid YAML with: id, name, explicit_state, objects, actions."""

    def _parse_node_from_yaml(self, yaml_str: str) -> Optional[StoryNode]:
        """
        Parse a node from YAML string.
        
        Args:
            yaml_str: YAML string to parse
            
        Returns:
            StoryNode if parsing successful, None otherwise
        """
        try:
            # First, extract the YAML block from the response
            match = re.search(r"```yaml\n(.*\n)```", yaml_str, re.DOTALL)
            if match:
                yaml_str = match.group(1).strip()
            else:
                yaml_str = yaml_str.strip()

            node_data = yaml.safe_load(yaml_str)

            # Handle cases where the LLM wraps the node in a top-level key
            if isinstance(node_data, dict) and len(node_data) == 1:
                node_data = next(iter(node_data.values()))
            
            # Handle a second level of nesting
            if isinstance(node_data, dict) and len(node_data) == 1:
                node_data = next(iter(node_data.values()))

            if not node_data or not isinstance(node_data, dict):
                logger.error("YAML parsing resulted in empty or invalid data.")
                return None

            if 'id' not in node_data:
                logger.error("Generated node YAML is missing required 'id' field.")
                logger.debug(f"Invalid node data: {node_data}")
                return None

            has_content = any(k in node_data for k in ('description', 'definition', 'explicit_state'))
            if not has_content:
                logger.error("Generated node YAML has no content field (description/definition/explicit_state).")
                logger.debug(f"Invalid node data: {node_data}")
                return None

            return StoryNode(**node_data)
        except Exception as e:
            logger.error(f"Error parsing generated node YAML: {e}", exc_info=True)
            logger.debug(f"Problematic YAML string:\n---\n{yaml_str}\n---")
            return None

    async def generate_and_replace_node_async(self, game_state: 'GameState', node_id: str):
        """
        Generate a node from a prompt and replace the placeholder in the game state.
        
        Args:
            game_state: Current game state
            node_id: ID of the placeholder node to replace
        """
        placeholder_node = game_state.nodes.get(node_id)
        if not placeholder_node or getattr(placeholder_node, 'type', None) != 'generated':
            return

        try:
            prompt = self._build_hybrid_node_generation_prompt(game_state, placeholder_node)
            if not prompt:
                return

            response_yaml = await self.game_kernel.llm_provider.generate_response(prompt)
            new_node = self._parse_node_from_yaml(response_yaml)
            
            if new_node:
                self._validate_and_correct_node_conditions(new_node)
                game_state.nodes[new_node.id] = new_node
                if new_node.id != node_id and node_id in game_state.nodes:
                    del game_state.nodes[node_id]
                    logger.info(f"Removed stale placeholder '{node_id}' (replaced by '{new_node.id}').")
                logger.info(f"Successfully generated and replaced node '{new_node.id}'.")
                # Proactively generate nodes linked from this new node
                await self.proactively_generate_linked_nodes_async(game_state, new_node.id)
            else:
                logger.error(f"Failed to generate or parse node '{node_id}'. It will remain a placeholder.")
        finally:
            if node_id in self.game_kernel._generation_in_progress:
                self.game_kernel._generation_in_progress.pop(node_id)

    def _build_hybrid_node_generation_prompt(self, game_state: 'GameState', 
                                             placeholder_node: StoryNode) -> str:
        """
        Build the prompt for generating a hybrid story node.
        
        Args:
            game_state: Current game state
            placeholder_node: The placeholder node with generation hints
            
        Returns:
            The generation prompt string
        """
        # Load prompt template
        prompt_template = self._load_generation_prompt()
        
        # Build story context
        player_id = list(game_state.variables.get("players", {}).keys())[0] if game_state.variables.get("players") else "default"
        player_char = self.game_kernel._get_player_character(game_state, player_id, game_state.story)
        inventory_str = ", ".join([
            (resolved.name if resolved else item_id)
            for item_id in game_state.get_player_inventory(player_id)
            for resolved in [game_state.resolve_inventory_object(item_id)]
        ])
        
        story_context = f"""- Title: {game_state.story.name}
- Description: {game_state.story.description}
- Player Character: {player_char.name if player_char else 'Unknown'}
- Player Inventory: {inventory_str if inventory_str else 'Empty'}"""
        
        # Build generation prompt
        generation_prompt = f"""- Node ID: {placeholder_node.id}
- Writer's Prompt: {placeholder_node.generation_prompt}"""
        
        # Build hints from generation_hints
        hints_parts = []
        hints_data = placeholder_node.generation_hints or {}
        if hints_data.get('actions'):
            hints_parts.append(f"Required Actions: {json.dumps(hints_data['actions'])}")
        if hints_data.get('objects'):
            hints_parts.append(f"Suggested Objects: {json.dumps(hints_data['objects'])}")
        if hints_data.get('characters'):
            hints_parts.append(f"Suggested Characters: {json.dumps(hints_data['characters'])}")
        if hints_data.get('triggers'):
            hints_parts.append(f"Suggested Triggers: {json.dumps(hints_data['triggers'])}")
        
        # Get available locations from story
        available_locations = [node_id for node_id in game_state.nodes.keys() 
                               if node_id != placeholder_node.id][:10]  # Limit to 10
        
        return prompt_template.format(
            story_context=story_context,
            generation_prompt=generation_prompt,
            available_locations=", ".join(available_locations) if available_locations else "Create new connections as needed",
            hints="\n".join(hints_parts) if hints_parts else "None"
        )

    def _validate_and_correct_node_conditions(self, node: StoryNode):
        """
        Validate and correct conditions within a generated node.
        
        Args:
            node: The node to validate
        """
        for action in node.actions:
            for condition in action.conditions:
                if condition.type == "object_status":
                    # Validate that the object exists (status tags are freeform, no validation needed)
                    target_object = next((obj for obj in node.objects if obj.id == condition.target), None)
                    if not target_object:
                        logger.warning(f"Object '{condition.target}' in condition for action '{action.id}' of node '{node.id}' not found.")


