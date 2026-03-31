"""
Game Kernel - Main orchestrator for the AI Native game engine.

This is the central coordinator that delegates to specialized modules:
- Architect: Unified LLM agent — handles narration and state changes via
  read_game_state / commit_world_event / roll_dice
- NodeGenerator: Dynamic node generation with LLM
- TextProcessor: Text substitution and hyperlinks
- VariableResolver: Variable path resolution
- TickerService: Timed events management
"""

import logging
import asyncio
import json
from typing import Dict, Optional, List, Any, TYPE_CHECKING

from src.models.game_state import GameState
from src.models.story_models import (
    Story,
    Character,
    StoryAction,
    StoryNode,
)
from src.core.story_manager import StoryManager
from src.core.state_manager import StateManager
from src.core.lua_runtime import LuaRuntimeService
from src.core.interfaces import ILLMProvider

# Import specialized modules
from src.core.text_processor import TextProcessor
from src.core.variable_resolver import VariableResolver
from src.core.ticker_service import TickerService
from src.core.node_generator import NodeGenerator
from src.core.architect import Architect, ArchitectTask
from src.core.background_materialization import (
    BackgroundMaterializationJob,
    BackgroundMaterializationScheduler,
)

if TYPE_CHECKING:
    from src.adapters.base import FrontendAdapter
    from src.models.story_models import Trigger

logger = logging.getLogger(__name__)


class GameKernel:
    """
    Main game orchestrator that coordinates all game systems.
    
    Delegates specialized functionality to separate modules for maintainability.
    """

    def __init__(self, story_manager: StoryManager, state_manager: StateManager, 
                 llm_provider: Optional[ILLMProvider] = None):
        """
        Initialize the game kernel.
        
        Args:
            story_manager: Manager for loading stories
            state_manager: Manager for saving/loading game states
            llm_provider: Optional LLM provider for dynamic content generation
        """
        # Core managers
        self.story_manager = story_manager
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        
        # Story state
        self.story_manifest: Optional[Story] = None
        self.current_game_state = None
        self.current_state = None
        
        # Frontend
        self.frontend_adapter: Optional['FrontendAdapter'] = None
        
        # Lua runtime
        self.lua_runtime = LuaRuntimeService(self)
        
        # Observers
        self._observers = []
        
        # Execution context
        self._generation_in_progress: Dict[str, asyncio.Task] = {}
        self._pending_forms: Dict[str, Dict[str, Any]] = {}
        
        # Initialize specialized modules
        self.text_processor = TextProcessor()
        self.variable_resolver = VariableResolver()
        self.ticker_service = TickerService(self)
        self.node_generator = NodeGenerator(self)
        self.architect = Architect(self)
        self.background_materialization = BackgroundMaterializationScheduler(self)

    # ========================================================================
    # Observer Pattern
    # ========================================================================
    
    def register_observer(self, observer):
        """Register an observer for game state changes."""
        self._observers.append(observer)
    
    def _notify_observers(self, state, session_id: Optional[str] = None):
        """Notify all observers of a state change."""
        for observer in self._observers:
            observer.update(state, session_id=session_id)

    # ========================================================================
    # Ticker Management (delegates to TickerService)
    # ========================================================================
    
    def start_ticker(self, session_id: str):
        """Start the game ticker for a specific session."""
        self.ticker_service.start_ticker(session_id)

    def stop_ticker(self, session_id: str):
        """Stop the game ticker for a specific session."""
        self.ticker_service.stop_ticker(session_id)

    # ========================================================================
    # Game Initialization
    # ========================================================================

    async def _process_and_generate_variables(self, variables: Dict[str, Any], 
                                               game_state: GameState, player_id: str):
        """Process and generate initial variables, including LLM-generated ones."""
        if not self.llm_provider or not variables:
            game_state.variables.update(variables)
            return

        logger.info(f"Starting serial generation for {len(variables)} variables.")
        for key, value in variables.items():
            if isinstance(value, str) and value.startswith("llm_generate:"):
                prompt = value.replace("llm_generate:", "").strip()
                
                # Substitute existing variables into the prompt
                substituted_prompt = self.text_processor.substitute_variables(prompt, game_state, player_id)
                
                logger.info(f"Generating variable '{key}' with prompt: \"{substituted_prompt}\"")
                generated_value = await self.llm_provider.generate_response(substituted_prompt)
                
                game_state.variables[key] = generated_value
                logger.info(f"Generated and set variable '{key}'.")
            else:
                game_state.variables[key] = value

    def start_new_game(self, story_id: str, player_id: str = "default") -> Optional[GameState]:
        """Start a new game (synchronous wrapper)."""
        return self.start_new_game_sync(story_id, player_id)

    @staticmethod
    def _run_coroutine_sync(coro):
        """Run a coroutine from a sync context.

        Uses asyncio.run() when no loop is running.  Falls back to a
        worker thread when called from inside an existing event loop
        (e.g. tests or embedded use) to avoid the RuntimeError from
        nested asyncio.run() calls.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    def start_new_game_sync(self, story_id: str, player_id: str = "default", 
                           character_id: Optional[str] = None) -> Optional[GameState]:
        """
        Start a new game synchronously.
        
        Args:
            story_id: ID of the story to load
            player_id: ID of the player
            character_id: Optional character ID to use
            
        Returns:
            GameState if successful, None otherwise
        """
        try:
            self.story_manifest = self.story_manager.load_story(story_id)
            if not self.story_manifest:
                logger.error(f"Failed to load story with ID: {story_id}")
                return None

            self.current_game_state = GameState(self.story_manifest)
            logger.info(f"start_new_game_sync: Initialized game_state object ID: {id(self.current_game_state)}")

            self._run_coroutine_sync(self._process_and_generate_variables(
                self.story_manifest.initial_variables, self.current_game_state, player_id
            ))

            defaults = self.story_manifest.player_character_defaults
            defaults_dict = None
            if isinstance(defaults, str):
                defaults_dict = self.lua_runtime.execute_script_with_return(defaults, player_id, self.current_game_state)
            elif isinstance(defaults, dict):
                defaults_dict = defaults

            self.current_game_state.add_player(player_id, defaults=defaults_dict)

            if character_id:
                character = next((c for c in self.story_manifest.characters if c.id == character_id), None)
                if character:
                    self.current_game_state.set_player_character(player_id, character)

            self._notify_observers(self.current_game_state)
            
            self._run_coroutine_sync(self._check_and_execute_global_triggers(
                self.current_game_state, player_id, self.story_manifest, "game_start", "game_start"
            ))

            logger.info(f"Started new synchronous game '{story_id}' for player '{player_id}'.")
            return self.current_game_state

        except Exception as e:
            logger.error(f"Error starting new synchronous game: {e}", exc_info=True)
            return None

    async def start_new_game_async(self, story_id: str, player_id: str = "default", 
                                   session_id: Optional[str] = None, 
                                   character_id: Optional[str] = None,
                                   notify_observers: bool = True) -> Optional[GameState]:
        """
        Start a new game asynchronously.
        
        Args:
            story_id: ID of the story to load
            player_id: ID of the player
            session_id: Optional session ID
            character_id: Optional character ID to use
            
        Returns:
            GameState if successful, None otherwise
        """
        try:
            self.story_manifest = self.story_manager.load_story(story_id)
            if not self.story_manifest:
                logger.error(f"Failed to load story with ID: {story_id}")
                return None

            self.current_game_state = GameState(self.story_manifest)
            logger.info(f"start_new_game_async: Initialized game_state object ID: {id(self.current_game_state)}")

            await self._process_and_generate_variables(
                self.story_manifest.initial_variables, self.current_game_state, player_id
            )

            defaults = self.story_manifest.player_character_defaults
            defaults_dict = None
            if isinstance(defaults, str):
                defaults_dict = self.lua_runtime.execute_script_with_return(defaults, player_id, self.current_game_state)
            elif isinstance(defaults, dict):
                defaults_dict = defaults

            self.current_game_state.add_player(player_id, defaults=defaults_dict)

            if character_id:
                character = next((c for c in self.story_manifest.characters if c.id == character_id), None)
                if character:
                    self.current_game_state.set_player_character(player_id, character)

            if notify_observers:
                self._notify_observers(self.current_game_state, session_id=session_id)
            
            # Auto-generate node explicit_state before triggers run
            start_node_id = self.story_manifest.start_node_id
            if start_node_id:
                await self.ensure_node_explicit_state(self.current_game_state, start_node_id, player_id)
            
            # Execute pre_enter triggers for the starting node FIRST
            await self._check_and_execute_global_triggers(
                self.current_game_state, player_id, self.story_manifest, "pre_enter", "pre_enter"
            )
            
            # Execute post_enter triggers for the starting node
            await self._check_and_execute_global_triggers(
                self.current_game_state, player_id, self.story_manifest, "post_enter", "post_enter"
            )
            
            # Run initial triggers (legacy support)
            await self._check_and_execute_global_triggers(
                self.current_game_state, player_id, self.story_manifest, "game_start", "game_start"
            )

            logger.info(f"Started new asynchronous game '{story_id}' for player '{player_id}'.")
            asyncio.create_task(self.node_generator.proactively_generate_linked_nodes_async(
                self.current_game_state, self.current_game_state.story.start_node_id
            ))
            return self.current_game_state

        except Exception as e:
            logger.error(f"Error starting new asynchronous game: {e}", exc_info=True)
            return None

    # ========================================================================
    # Character Placement System
    # ========================================================================

    # ========================================================================
    # Description Generation
    # ========================================================================

    def get_full_node_description(self, game_state: GameState, node_id: str, player_id: str) -> str:
        """
        Get the full description for a node including objects and NPCs.
        
        Reads node.explicit_state directly (explicit_state is mutated in memory).
        """
        node = game_state.nodes.get(node_id)
        if not node:
            return "You are in a place with no description."

        # Read explicit_state directly from node (mutated in memory, persisted via node_states)
        base_description = node.explicit_state or ""

        full_description = self.text_processor.substitute_variables(base_description, game_state, player_id)

        # Collect object explicit_states (using new status-based model)
        object_descriptions = []
        for obj in node.objects:
            if game_state.is_object_visible(obj):
                explicit_state = getattr(obj, 'explicit_state', '')
                if explicit_state:
                    object_descriptions.append(explicit_state)
        
        if object_descriptions:
            full_description += "\n" + "\n".join(object_descriptions)

        story = game_state.story

        # Collect non-playable characters from the character location model.
        npcs_in_node = []
        for char_id in game_state.get_npcs_in_node(node_id):
            char_def = story.get_character(char_id) if story else None
            if char_def and not char_def.is_playable:
                char_state = game_state.character_states.get(char_id, {})
                # Use explicit_state (visible to player) for display
                npcs_in_node.append(char_state.get('explicit_state', char_def.explicit_state) or char_def.definition)
        
        if npcs_in_node:
            full_description += "\n\n" + "\n".join(npcs_in_node)
            
        return self.text_processor.process_text_for_hyperlinks(full_description, game_state, player_id)

    async def get_node_perception(self, game_state: GameState, node_id: str, player_id: str) -> str:
        """
        Render the current scene perception for a player without persisting it.

        This is the DSPP-oriented read path used by reconnect, scene refresh,
        serializer snapshots, and other places that need player-facing text from
        current state rather than a cached node explicit_state.
        """
        node = game_state.nodes.get(node_id)
        if not node:
            return "You are in a place with no description."

        if not self.llm_provider:
            return self.get_full_node_description(game_state, node_id, player_id)

        task = ArchitectTask(
            task_type="render_perception",
            node_id=node_id,
            extra_context={"capture_only": True},
        )
        ctx = await self.architect.handle(
            task,
            game_state,
            player_id,
            self.story_manifest or game_state.story,
        )
        displayed = ctx.get("displayed_messages", []) if isinstance(ctx, dict) else []
        if displayed:
            return displayed[-1].get("text", "")

        logger.warning(
            "Architect render_perception returned no text for node '%s'; falling back to legacy composition",
            node_id,
        )
        return self.get_full_node_description(game_state, node_id, player_id)

    async def generate_node_explicit_state(self, node: 'StoryNode', game_state: 'GameState', 
                                       player_id: str) -> str:
        """
        Generate explicit_state for a node from its definition using LLM.

        Used as a fallback when the Architect's tool-calling loop does not
        produce a explicit_state (e.g., during initial game setup).
        
        Args:
            node: The node to generate explicit_state for
            game_state: Current game state
            player_id: Player ID for variable substitution
            
        Returns:
            Generated explicit_state text, or empty string if generation fails
        """
        if not self.llm_provider or not node.definition:
            return ""
        
        # Get node status for context
        node_status = node.get_status()
        current_status = ', '.join(node_status) if node_status else 'none'
        
        # Substitute variables in definition
        definition_with_vars = self.text_processor.substitute_variables(
            node.definition, game_state, player_id
        )
        
        # Get previous explicit_state if any (for context)
        previous_explicit_state = node.explicit_state or ""
        
        # Build actions list for the prompt
        actions_info = ""
        if node.actions:
            action_entries = []
            for action in node.actions:
                action_text = action.text or action.description or action.id
                action_entries.append(f"  - {{{action.id}: {action_text}}}")
            actions_info = "\n".join(action_entries)

        # Get node implicit_state (hidden context that affects scene generation)
        node_implicit_state = node.implicit_state or ""
        
        prompt = f"""Generate a scene description for this location in this AI native text based game engine.

Node name: {node.name or node.id}
Definition: {definition_with_vars}
Current status: {current_status}
{f'Scene context: {node_implicit_state}' if node_implicit_state else ''}
{f'Previous explicit_state: {previous_explicit_state}' if previous_explicit_state else ''}

Available actions at this location:
{actions_info if actions_info else "(none)"}

Generate a scene description that:
- Reflects the current status tags if any (e.g., "brawl_aftermath" means a fight just happened)
- Incorporates the scene context if provided (this is hidden context about recent events)
- Is written in second person perspective ("You stand...", "You arrive at...")
- Matches the language of the definition (Chinese if definition is in Chinese, English if in English, etc.)
- Uses markdown formatting: **bold** for NPC roles, paragraph breaks between sections
- Uses hyperlink syntax {{action_id: display_text}} for available actions, woven naturally into prose
  Example: "You could {{order_drink: order a drink}} at the bar."
- Uses hyperlink syntax {{object_id: display_text}} for important interactive objects
  Example: "An ancient {{stone_well: stone well}} stands in the clearing."
- Does NOT mention hidden/secret paths or items not yet discovered
- Only describes what is immediately visible to the player
- Is concise and well-structured (use paragraph breaks, not walls of text)

If the definition contains specific formatting instructions (e.g., word limits, 
structure guidelines, NPC presentation rules), follow those instructions as they 
reflect the author's intent and override the defaults above.

Output ONLY the description text. Do NOT wrap in JSON or any other format."""

        try:
            # Use generate_text_response for plain text output (not JSON mode)
            explicit_state = await self.llm_provider.generate_text_response(prompt)
            return explicit_state.strip()
        except Exception as e:
            logger.error(f"Failed to generate node explicit_state for {node.id}: {e}")
            return ""

    async def ensure_node_explicit_state(self, game_state: 'GameState', node_id: str,
                                     player_id: str, force_regenerate: bool = False) -> bool:
        """Ensure a node has a legacy explicit_state baseline for compatibility.

        DSPP rendering should use `get_node_perception()` instead. This helper
        remains for older code paths that still inspect `node.explicit_state`.
        """
        node = game_state.nodes.get(node_id)
        if not node:
            return False

        has_explicit_state = node.explicit_state and node.explicit_state.strip()

        if has_explicit_state and not force_regenerate:
            return False

        if not node.definition:
            return False

        explicit_state = await self.generate_node_explicit_state(node, game_state, player_id)
        if explicit_state:
            node.explicit_state = explicit_state
            game_state.update_node_explicit_state(node_id, explicit_state)
            logger.debug(f"Generated legacy explicit_state baseline for node '{node_id}'")
            return True

        return False

    async def _push_characters_update(self, game_state: 'GameState', player_id: str, 
                                       materialized_node_id: str) -> None:
        """
        Send an updated character list to the frontend after local entity changes.
        This ensures the @ mention popup reflects newly created or enriched NPCs.
        
        Only pushes if the player is STILL at the node where materialization happened.
        If the player has already moved away, the push is skipped to avoid overwriting
        the correct character list for their new location.
        """
        if not self.frontend_adapter or not game_state.story.characters:
            return
        
        # Use the player's ACTUAL current location, not the stale materialization node
        actual_location = game_state.get_player_location(player_id)
        if actual_location != materialized_node_id:
            logger.debug(f"Skipping characters_update push: player moved from "
                        f"'{materialized_node_id}' to '{actual_location}'")
            return
        
        character_list = []
        for character in game_state.story.characters:
            in_current_node = game_state.is_character_in_node(
                character.id, actual_location
            ) if actual_location else False

            if in_current_node:
                character_list.append({
                    "id": character.id,
                    "name": character.name,
                    "is_playable": character.is_playable
                })
        
        await self.frontend_adapter.send_json_message({
            "type": "characters_update",
            "content": {"characters": character_list}
        }, player_id)

    def schedule_background_materialization(
        self,
        *,
        session_id: str,
        player_id: str,
        base_version: int,
        reason: str,
        source_node_id: Optional[str],
        visible_node_id: Optional[str] = None,
        local_only: bool = True,
        allow_player_facing_narrative: bool = False,
        max_new_entities: int = 2,
        max_nodes_to_touch: int = 1,
        max_actions_to_add: int = 2,
        applied_changes: Optional[List[str]] = None,
    ) -> bool:
        """Queue a deferred world-enrichment pass for the current session."""
        return self.background_materialization.enqueue(
            BackgroundMaterializationJob(
                session_id=session_id,
                player_id=player_id,
                base_version=base_version,
                reason=reason,
                source_node_id=source_node_id,
                visible_node_id=visible_node_id,
                local_only=local_only,
                allow_player_facing_narrative=allow_player_facing_narrative,
                max_new_entities=max_new_entities,
                max_nodes_to_touch=max_nodes_to_touch,
                max_actions_to_add=max_actions_to_add,
                applied_changes=list(applied_changes or []),
            )
        )

    async def get_actions_for_object(self, game_state: GameState, player_id: str, 
                               object_id: str) -> List[StoryAction]:
        """
        Get available actions for an object.
        
        Uses a single LLM call to extract currently-available actions from the
        object's definition, evaluating any embedded conditions against the
        player's current state and returning only clean display text.
        
        If no LLM-derived affordances are available, returns an empty list
        instead of inventing engine-owned default verbs.
        
        Args:
            game_state: Current game state
            player_id: The player's ID
            object_id: The object's ID
            
        Returns:
            List of StoryAction objects
        """
        current_node = game_state.get_current_node(player_id)
        obj = None
        is_in_inventory = False
        
        if current_node:
            obj = next((o for o in current_node.objects if o.id == object_id), None)

        if not obj:
            inventory = game_state.get_player_inventory(player_id)
            if object_id in inventory:
                obj = game_state.resolve_inventory_object(object_id)
                is_in_inventory = True

        if not obj:
            return []

        if self.llm_provider:
            actions = await self._generate_available_actions_for_object(
                obj, game_state, player_id, is_in_inventory
            )
            if actions:
                return actions

        return []
    
    async def _generate_available_actions_for_object(self, obj, game_state: GameState,
                                                      player_id: str,
                                                      is_in_inventory: bool = False) -> List[StoryAction]:
        """
        Use a single LLM call to extract currently-available actions from the
        object's definition, evaluating embedded conditions against the player's
        state and returning only clean display text (no conditions/spoilers).
        """
        definition = getattr(obj, 'definition', '') or ''
        explicit_state = getattr(obj, 'explicit_state', '') or ''
        name = getattr(obj, 'name', obj.id)
        obj_status = obj.get_status() if hasattr(obj, 'get_status') else []

        location_context = "in player's inventory" if is_in_inventory else "in the environment"
        status_str = ', '.join(obj_status) if obj_status else "normal"

        player_status = game_state.get_player_status(player_id) or []
        inventory_items = game_state.get_player_inventory(player_id)
        inventory_names = [
            resolved.name
            for item_id in inventory_items
            for resolved in [game_state.resolve_inventory_object(item_id)]
            if resolved and item_id != obj.id
        ]

        relevant_vars = {k: v for k, v in game_state.variables.items()
                         if k not in ('players', 'nodes') and not k.startswith('_')}

        prompt = f"""You are determining what actions a player can currently perform on a game object.

## Object
Name: {name}
Location: {location_context}
Status: {status_str}
Current explicit_state: {explicit_state or '(none)'}
Definition:
{definition}

## Player State
Status tags: {json.dumps(player_status, ensure_ascii=False)}
Inventory: {json.dumps(inventory_names, ensure_ascii=False) if inventory_names else '(empty)'}

## Game Variables
{json.dumps(relevant_vars, ensure_ascii=False, indent=2) if relevant_vars else '(none)'}

## Instructions
1. Read the ## headings in the object's Definition — each heading describes a possible interaction.
2. Some headings embed conditions in natural language (e.g. "when X do Y" or "if player has Z, do W").
   Evaluate every such condition against the current Player State / Inventory / Game Variables.
3. Return ONLY actions whose conditions are currently met (or that have no condition).
4. For the action text, return ONLY the action verb/phrase. NEVER include the condition.
   Example: heading "when condition A, do action B" + condition A IS met → return "do action B".
   Example: heading "when condition A, do action B" + condition A is NOT met → omit entirely.
5. Headings that are purely conditional modifiers with no distinct action verb are NOT player-selectable actions — skip them.
6. Only return actions grounded in the object's authored definition and the current state. Do NOT invent generic default verbs just because the object is nearby or in inventory.

Return ONLY a JSON array of short action strings. No explanation.

JSON array:"""

        try:
            response = await self.llm_provider.generate_response(prompt)
            response = response.strip()

            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            actions = json.loads(response)

            if isinstance(actions, list) and actions:
                return [
                    StoryAction(id=f"action_{i}", text=str(action))
                    for i, action in enumerate(actions)
                    if action
                ]
        except Exception as e:
            logger.warning(f"Failed to generate available actions for {obj.id}: {e}")

        return []
    
    # ========================================================================
    # Trigger System
    # ========================================================================

    async def _check_and_execute_global_triggers(self, game_state: GameState, player_id: str, 
                                                  story: Story, action_taken: Optional[str] = None, 
                                                  trigger_type: Optional[str] = None,
                                                  target_node_id: Optional[str] = None) -> bool:
        """Check and execute both node-specific and global triggers.
        
        Trigger type filtering:
        - If trigger_type is specified: only run triggers with that exact type
        - If trigger_type is None: only run legacy triggers (those without a type field)
        
        Args:
            target_node_id: If specified, check triggers for this node instead of current node.
                           Used for pre_enter triggers before the player has moved.
        
        This prevents FSM triggers (pre_enter, post_enter, etc.) from accidentally
        running during action-based trigger checks.
        """
        def should_run_trigger(trigger) -> bool:
            """Check if trigger should run based on trigger_type filter."""
            trig_type = getattr(trigger, 'type', None)
            if trigger_type:
                # Looking for a specific type - must match exactly
                return trig_type == trigger_type
            else:
                # No type specified - only run legacy triggers (no type field)
                return not trig_type
        
        # First, check node-specific triggers
        # Use target_node_id if specified (for pre_enter), otherwise current node
        if target_node_id:
            current_node = game_state.nodes.get(target_node_id)
        else:
            current_node = game_state.get_current_node(player_id)
        if current_node and current_node.triggers:
            for trigger in current_node.triggers:
                if not should_run_trigger(trigger):
                    continue
                    
                if self._evaluate_trigger_conditions(trigger, game_state, player_id, action_taken):
                    if trigger.intent:
                        logger.info(f"Node trigger '{trigger.id}' has intent — Architect handles via Node Transition Protocol.")
                    elif trigger.effects:
                        logger.warning(f"Node trigger '{trigger.id}' has legacy effects. Skipping.")

        # Then, check global triggers
        if story.triggers:
            for trigger in story.triggers:
                if not should_run_trigger(trigger):
                    continue

                if self._evaluate_trigger_conditions(trigger, game_state, player_id, action_taken):
                    if trigger.intent:
                        logger.info(f"Global trigger '{trigger.id}' has intent — Architect handles.")
                    elif trigger.effects:
                        logger.warning(f"Global trigger '{trigger.id}' has legacy effects. Skipping.")
        
        return False

    def _evaluate_trigger_conditions(self, trigger: 'Trigger', game_state: GameState, 
                                     player_id: str, action_taken: Optional[str]) -> bool:
        """Evaluate if all conditions for a trigger are met."""
        for condition in trigger.conditions:
            success, _ = condition.evaluate(game_state, player_id)
            if not success:
                return False
        return True

    # ========================================================================
    # Character/Player Management
    # ========================================================================

    def _get_player_character(self, game_state: GameState, player_id: str, 
                              story: Story) -> Optional[Character]:
        """Get the character for a player using pointer model."""
        # Use pointer model to get controlled character ID
        player_character_id = game_state.get_controlled_character_id(player_id)
        
        if not player_character_id:
            # Fallback: only auto-assign if there's exactly one playable character
            playable = [c for c in (story.characters or []) if c.is_playable]
            if len(playable) == 1:
                game_state.set_player_character(player_id, playable[0])
                return playable[0]
            return None
        
        for char in story.characters:
            if char.id == player_character_id:
                char_copy = char.copy(deep=True)
                
                # Merge runtime state from character_states (pointer model)
                char_state = game_state.character_states.get(player_character_id, {})
                props = char_state.get('properties', {})
                
                if char_state.get('explicit_state'):
                    char_copy.explicit_state = char_state.get('explicit_state')
                if props.get('status'):
                    char_copy.properties['status'] = list(props.get('status', []))

                # Update stats from character_states
                if props.get('stats'):
                    char_copy.stats.update(props.get('stats', {}))
                
                return char_copy
        return None

    # ========================================================================
    # Story Access
    # ========================================================================

    def _get_story(self, story_id: str) -> Story:
        """Load and return a story by ID."""
        story = self.story_manager.load_story(story_id)
        if not story:
            logger.error(f"Story with id {story_id} not found.")
            raise ValueError(f"Story with id {story_id} not found.")
        return story

    def load_prompt(self, prompt_name: str) -> str:
        """Load a prompt file by name."""
        prompt_path = f"prompts/{prompt_name}.txt"
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Prompt file not found: {prompt_path}")
            return ""

    # ========================================================================
    # Input Processing
    # ========================================================================

    async def process_input(self, user_input: str, game_state: GameState, story: 'Story', 
                           player_id: str, session_id: Optional[str] = None,
                           input_type: str = "typed",
                           action_hint: str = "",
                           display_text: Optional[str] = None) -> Dict[str, Any]:
        """Process player input.
        
        The engine only keeps meta/infrastructure handling here.
        Story-facing input is routed to the Architect as ``player_input``.
        
        Args:
            input_type: 'typed' for input-box text, 'action_click' for link clicks.
            action_hint: Optional hint from story author (from {display: hint} links).
        """
        player_location = game_state.get_player_location(player_id)

        # Track player input in message history
        if user_input and user_input.strip():
            game_state.add_message_to_history(
                role="player",
                content=user_input.strip(),
                player_ids=[player_id],
                location=player_location,
                metadata={"event_type": "player_input", "input_type": input_type},
            )
            game_state.add_transcript_entry(
                "user",
                (display_text or user_input).strip(),
                player_ids=[player_id],
                location=player_location,
                metadata={"event_type": "player_input", "input_type": input_type},
            )

        user_input_lower = user_input.lower().strip() if user_input else ""
        frontend_adapter = self.frontend_adapter
        
        # Pending forms
        if player_id in self._pending_forms:
            form_context = self._pending_forms[player_id]
            form_id = form_context.get("form_id", "")
            if frontend_adapter:
                await frontend_adapter.send_game_message(
                    f"Please complete the form before continuing. (Form: {form_id})", 
                    player_id
                )
            return {"narrative_response": "", "script_paused": True}

        # --- Architect path ---
        extra = {"input_type": input_type}
        if session_id:
            extra["session_id"] = session_id
        if action_hint:
            extra["action_hint"] = action_hint
        if user_input_lower.startswith("say:"):
            extra["social_intent"] = {
                "type": "say",
                "message": user_input.split(":", 1)[1].strip(),
            }
        elif user_input_lower.startswith("give:"):
            give_parts = user_input.split(":", 2)
            if len(give_parts) == 3:
                extra["social_intent"] = {
                    "type": "give",
                    "target_player_name": give_parts[1].strip(),
                    "item_name": give_parts[2].strip(),
                }
        elif user_input_lower == "list_players":
            extra["social_intent"] = {"type": "list_players"}
        task = ArchitectTask(
            task_type="player_input",
            player_input=user_input,
            extra_context=extra,
        )
        ctx = await self.architect.handle(task, game_state, player_id, story)
        last_narrative = ""
        if isinstance(ctx, dict):
            displayed = ctx.get("displayed_messages", [])
            if displayed:
                last_narrative = displayed[-1].get("text", "")
        return {"narrative_response": last_narrative, "script_paused": False}

    # ========================================================================
    # Form Submission Processing
    # ========================================================================

    async def process_form_submission(self, form_id: str, form_data: dict,
                                      files_data: dict, game_state: 'GameState',
                                      player_id: str, story: 'Story') -> dict:
        """Process a form submission from the player.

        Validates input, stores variables per on_submit config,
        then invokes the Architect to narrate the result.

        Returns:
            Dict with success status and any error messages.
        """
        form_context = self._pending_forms.get(player_id)
        if not form_context or form_context.get("form_id") != form_id:
            logger.warning(f"No pending form '{form_id}' for player '{player_id}'")
            return {"success": False, "error": "No pending form found"}

        form_def = form_context["form_def"]
        on_submit = form_context.get("on_submit_override") or form_def.on_submit

        validation_errors = self._validate_form_data(form_def, form_data, files_data)
        if validation_errors:
            return {"success": False, "errors": validation_errors}

        processed_data = form_data.copy()
        processed_metadata: Dict[str, Any] = {}

        for field_id, file_info in files_data.items():
            field = next((f for f in form_def.fields if f.id == field_id), None)
            if field and field.type == "file":
                try:
                    from src.utils.file_text_extractor import extract_text_from_file
                    extracted_text, metadata = extract_text_from_file(
                        file_info.get("data", ""),
                        file_info.get("mime_type", ""),
                        file_info.get("filename", ""),
                        field.max_text_length,
                    )
                    processed_data[field_id] = extracted_text
                    processed_metadata[f"{field_id}_meta"] = metadata
                except Exception as e:
                    logger.error(f"Failed to process file for field '{field_id}': {e}")
                    return {"success": False, "errors": {field_id: f"Failed to process file: {e}"}}

        game_state.set_variable(f"_form_{form_id}", processed_data)
        game_state.set_variable(f"_form_{form_id}_meta", processed_metadata)
        game_state.set_variable("form", processed_data)

        if on_submit:
            if on_submit.store_variables:
                for store_config in on_submit.store_variables:
                    var_path = store_config.to.replace("{player_id}", player_id)
                    if store_config.field == "*":
                        game_state.set_variable(var_path, processed_data)
                    elif store_config.field in processed_data:
                        game_state.set_variable(var_path, processed_data[store_config.field])

            if on_submit.llm_process and self.llm_provider:
                llm_config = on_submit.llm_process
                prompt = llm_config.prompt
                for fid, val in processed_data.items():
                    prompt = prompt.replace(f"{{$form.{fid}}}", str(val))
                prompt = prompt.replace("{$form_data_json}", json.dumps(processed_data, ensure_ascii=False))
                prompt = self.text_processor.substitute_variables(prompt, game_state, player_id)
                try:
                    response = await self.llm_provider.generate_response(prompt)
                    result = response.strip()
                    if llm_config.store_to:
                        var_path = llm_config.store_to.replace("{player_id}", player_id)
                        game_state.set_variable(var_path, result)
                except Exception as e:
                    logger.error(f"LLM processing failed for form: {e}")

            if on_submit.script:
                if not self.lua_runtime:
                    from src.core.lua_runtime import LuaRuntimeService
                    self.lua_runtime = LuaRuntimeService(self)
                self.lua_runtime.execute_script(on_submit.script, player_id, game_state)

        if self.llm_provider:
            try:
                on_submit_summary = self._summarize_on_submit(on_submit) if on_submit else ""
                task = ArchitectTask(
                    task_type="process_form_result",
                    form_data={
                        "form_id": form_id,
                        "form_title": form_def.title,
                        "submitted_data": processed_data,
                        "on_submit_summary": on_submit_summary,
                    },
                    extra_context={"session_id": self.frontend_adapter.player_sessions.get(player_id, {}).get("session_id")} if self.frontend_adapter else {},
                )
                await self.architect.handle(task, game_state, player_id, story)
            except Exception as e:
                logger.error(f"Architect process_form_result failed: {e}", exc_info=True)

        del self._pending_forms[player_id]

        return {"success": True, "script_paused": False}

    async def present_form(
        self,
        form_id: str,
        game_state: 'GameState',
        player_id: str,
        story: 'Story',
        *,
        prefill: Optional[Dict[str, Any]] = None,
        on_submit_override: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Register and send a form to the active player's frontend client."""
        form_def = story.get_form(form_id) if story else None
        if not form_def:
            logger.warning("Form '%s' not found for player '%s'", form_id, player_id)
            return {"success": False, "error": f"Form '{form_id}' not found"}

        if on_submit_override and isinstance(on_submit_override, dict):
            from src.models.story_models import FormOnSubmit

            on_submit_override = FormOnSubmit(**on_submit_override)

        frontend_payload = form_def.to_frontend_format(
            game_state=game_state,
            player_id=player_id,
            substitute_func=self.text_processor.substitute_variables,
        )
        if prefill:
            frontend_payload["prefill"] = prefill

        self._pending_forms[player_id] = {
            "form_id": form_id,
            "form_def": form_def,
            "prefill": dict(prefill or {}),
            "on_submit_override": on_submit_override,
        }

        if self.frontend_adapter:
            await self.frontend_adapter.send_json_message(frontend_payload, player_id)

        return {
            "success": True,
            "form_id": form_id,
            "field_count": len(form_def.fields),
        }

    def _validate_form_data(self, form_def, form_data: dict, files_data: dict) -> dict:
        """Validate form data against field definitions. Returns {field_id: error} or {}."""
        import re as _re
        errors: Dict[str, str] = {}
        for field in form_def.fields:
            fid = field.id
            value = form_data.get(fid) if field.type != "file" else files_data.get(fid)
            if field.type == "hidden":
                continue
            if field.required and (value is None or value == "" or value == []):
                errors[fid] = f"{field.label} is required"
                continue
            if value is None or value == "" or value == []:
                continue
            v = field.validation
            if not v:
                continue
            if field.type in ("text", "textarea"):
                if v.min_length and len(str(value)) < v.min_length:
                    errors[fid] = f"Minimum length is {v.min_length}"
                elif v.max_length and len(str(value)) > v.max_length:
                    errors[fid] = f"Maximum length is {v.max_length}"
                elif v.pattern and not _re.match(v.pattern, str(value)):
                    errors[fid] = v.pattern_error or "Invalid format"
            elif field.type == "number":
                try:
                    num = float(value)
                    if v.min is not None and num < v.min:
                        errors[fid] = f"Minimum value is {v.min}"
                    elif v.max is not None and num > v.max:
                        errors[fid] = f"Maximum value is {v.max}"
                    elif v.integer_only and num != int(num):
                        errors[fid] = "Must be an integer"
                except (ValueError, TypeError):
                    errors[fid] = "Must be a number"
            elif field.type in ("multiselect", "checkboxgroup") and isinstance(value, list):
                if v.min_selections and len(value) < v.min_selections:
                    errors[fid] = f"Select at least {v.min_selections}"
                elif v.max_selections and len(value) > v.max_selections:
                    errors[fid] = f"Select at most {v.max_selections}"
            elif field.type == "file" and value:
                file_size = len(value.get("data", "")) * 3 / 4
                if file_size > field.max_size_mb * 1024 * 1024:
                    errors[fid] = f"File too large (max {field.max_size_mb}MB)"
                mime_type = value.get("mime_type", "")
                if field.accept and mime_type not in field.accept:
                    errors[fid] = "File type not allowed"
        return errors

    @staticmethod
    def _summarize_on_submit(on_submit) -> str:
        """Produce a summary of a FormOnSubmit for the Architect prompt."""
        parts = []
        if on_submit.store_variables:
            mappings = [f"{sv.field} -> {sv.to}" for sv in on_submit.store_variables]
            parts.append(f"Stored variables: {', '.join(mappings)}")
        if on_submit.llm_process:
            parts.append("LLM processing was applied to form data")
        if on_submit.script:
            parts.append("A Lua script was executed")
        if on_submit.effects:
            effect_summaries = []
            for effect in on_submit.effects:
                details = []
                for field_name in ("target", "form_id", "value", "owner", "function", "location_id"):
                    field_value = getattr(effect, field_name, None)
                    if field_name == "owner" and field_value == "player":
                        continue
                    if field_value not in (None, "", [], {}):
                        details.append(f"{field_name}={field_value}")
                effect_type = getattr(effect, "type", None) or "unknown"
                effect_summaries.append(
                    f"{effect_type}({', '.join(details)})" if details else effect_type
                )
            parts.append(f"Writer effects: {' -> '.join(effect_summaries)}")
        return ". ".join(parts) if parts else "No on_submit actions defined"

    # ========================================================================
    # Response Sending
    # ========================================================================

    async def send_response(self, player_id: str, message_type: str, data: Dict[str, Any]):
        """Send a response to the frontend."""
        if self.frontend_adapter:
            if message_type == "message":
                extra = {}
                for key in ("audience_scope", "target_player_ids", "exclude_player_ids", "session_id", "location_id"):
                    if key in data:
                        extra[key] = data[key]
                await self.frontend_adapter.send_game_message(
                    data["text"], player_id, message_type=data.get("message_type", "game"), **extra
                )
            else:
                # Include type in the message for frontend routing
                message = {"type": message_type, **data}
                await self.frontend_adapter.send_json_message(message, player_id)
