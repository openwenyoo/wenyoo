"""
Game state models for the AI Native game engine.

This module defines the data structures for representing game state,
including player location, inventory, and game variables.
"""
from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING, Set
import copy
import time
from datetime import datetime
import logging

from src.models.story_models import (
    Story,
    StoryObject,
    StoryAction,
    StoryNode,
    Character,
    TimedEvent,
    parse_duration_to_seconds,
)

if TYPE_CHECKING:
    from src.core.lua_runtime import LuaRuntimeService

logger = logging.getLogger(__name__)
MAX_SAVED_MESSAGE_HISTORY = 50

# Prefix for derived variables that are evaluated as Lua expressions
DERIVED_VAR_PREFIX = "$lua:"


class GameState:
    """
    Represents the current state of the game, including player location,
    inventory, and game variables.
    """

    def __init__(self, story: Story, player_id: Optional[str] = None):
        """
        Initialize a new game state.

        Args:
            story: The Story object being played
            player_id: The player ID to initialize state for. If None, an empty state is created (for loading).
        """
        self.story = story
        self.story_id = story.id
        self.nodes = copy.deepcopy(story.nodes)
        logger.debug(f"GameState initialized with nodes: {list(self.nodes.keys())}")
        self.variables: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.visited_nodes: List[str] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.version = 0
        self.last_modified_by = None
        
        # Current node tracking
        self.current_node_id = story.start_node_id or "start"
        self.current_node = story.get_node(self.current_node_id)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # Node State Tracking
        # ═══════════════════════════════════════════════════════════════════════════
        
        # Runtime DIP changes for nodes. Only populated when a node is modified
        # at runtime (e.g., LLM-generated explicit_state). Used for save/load persistence.
        # At runtime, node.explicit_state/implicit_state/properties are mutated directly.
        self.node_states: Dict[str, Dict[str, Any]] = {}

        # Add timed events list
        self.timed_events: List[Dict[str, Any]] = []
        self.runtime_connections: List[Dict[str, Any]] = []

        # ═══════════════════════════════════════════════════════════════════════════
        # Character State Tracking
        # ═══════════════════════════════════════════════════════════════════════════
        
        # Runtime state for each character (explicit_state, implicit_state, memory, properties changes)
        # Keys are character IDs, values are dicts with runtime state
        self.character_states: Dict[str, Dict[str, Any]] = {}
        
        # Initialize character states from story definition
        if story.characters:
            for char in story.characters:
                self.character_states[char.id] = {
                    'explicit_state': char.explicit_state,
                    'implicit_state': char.implicit_state,
                    'memory': list(char.memory),  # Copy to avoid mutating story
                    # Properties runtime state (can override story definition)
                    'properties': dict(char.properties),  # Copy to avoid mutating story
                }

        # Character location tracking cache
        self.character_locations: Dict[str, str] = {}  # character_id -> node_id
        self.current_node_characters: List[str] = []  # character IDs in current node
        
        # ═══════════════════════════════════════════════════════════════════════════
        # Object State Tracking
        # ═══════════════════════════════════════════════════════════════════════════
        
        # Runtime state for each object (explicit_state, implicit_state, properties changes)
        # Keys are object IDs, values are dicts with runtime state
        # Note: Objects don't have memory since they don't "remember" interactions
        self.object_states: Dict[str, Dict[str, Any]] = {}
        
        # Initialize object states from story definition (global objects + node objects)
        self._init_object_states_from_story(story)

        # Message history for conversation context tracking
        # Used by LLM to understand player responses like "yes" or "no"
        self.message_history: List[Dict[str, Any]] = []
        self.transcript_history: List[Dict[str, Any]] = []
        self.save_metadata: Dict[str, Any] = {}

        # Lazy-initialized Lua runtime for evaluating derived variables
        self._lua_runtime: Optional['LuaRuntimeService'] = None
        
        # Track which derived variables are currently being evaluated (prevents recursion)
        self._evaluating_derived: set = set()

        self.variables["players"] = {}

    def _serialize_json_safe(self, value: Any) -> Any:
        """Convert nested runtime values into JSON-safe data."""
        if isinstance(value, list):
            return [self._serialize_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize_json_safe(item) for key, item in value.items()}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return str(value)
        return value

    def _serialize_inventory_refs(self, inventory: List[Any]) -> List[Any]:
        """Persist inventory items as stable object IDs when possible."""
        serialized: List[Any] = []
        for item in inventory or []:
            if hasattr(item, "id"):
                serialized.append(item.id)
            else:
                serialized.append(self._serialize_json_safe(item))
        return serialized

    def _hydrate_inventory_refs(self, inventory: List[Any]) -> List[Any]:
        """Rebuild inventory object references from saved IDs."""
        hydrated: List[Any] = []
        for item_ref in inventory or []:
            if isinstance(item_ref, str):
                item_obj = self.story.get_object(item_ref)
                if item_obj:
                    hydrated.append(item_obj.copy(deep=True))
                else:
                    hydrated.append(item_ref)
            elif isinstance(item_ref, dict):
                item_id = item_ref.get("id")
                item_obj = self.story.get_object(item_id) if item_id else None
                hydrated.append(item_obj.copy(deep=True) if item_obj else item_ref)
            else:
                hydrated.append(item_ref)
        return hydrated

    def _serialize_player_state_for_save(self, player_data: Dict[str, Any]) -> Dict[str, Any]:
        serialized = self._serialize_json_safe(copy.deepcopy(player_data))
        if isinstance(serialized, dict):
            serialized.pop("inventory", None)
        return serialized

    def _serialize_character_states_for_save(self) -> Dict[str, Dict[str, Any]]:
        serialized_states: Dict[str, Dict[str, Any]] = {}
        for char_id, char_state in self.character_states.items():
            serialized_state = self._serialize_json_safe(copy.deepcopy(char_state))
            props = char_state.get("properties", {})
            if "inventory" in props:
                serialized_state.setdefault("properties", {})["inventory"] = self._serialize_inventory_refs(
                    props.get("inventory", [])
                )
            serialized_states[char_id] = serialized_state
        return serialized_states

    def _serialize_message_history_for_save(self) -> List[Dict[str, Any]]:
        recent_history = self.message_history[-MAX_SAVED_MESSAGE_HISTORY:]
        serialized_history: List[Dict[str, Any]] = []
        for message in recent_history:
            entry = self._serialize_json_safe(copy.deepcopy(message))
            if "player_ids" in message and message.get("player_ids") is not None:
                entry["player_ids"] = list(message.get("player_ids") or [])
            if "character_ids" in message and message.get("character_ids") is not None:
                entry["character_ids"] = list(message.get("character_ids") or [])
            if "timestamp" not in entry:
                entry["timestamp"] = time.time()
            serialized_history.append(entry)
        return serialized_history

    def get_character_ids_for_players(self, player_ids: Optional[List[str]]) -> List[str]:
        """Resolve the currently controlled character IDs for a set of players."""
        character_ids: List[str] = []
        for player_id in player_ids or []:
            character_id = self.get_controlled_character_id(player_id)
            if character_id and character_id not in character_ids:
                character_ids.append(character_id)
        return character_ids

    def _normalize_message_history_entry(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Backfill message history with stable character-perspective visibility."""
        normalized = self._serialize_json_safe(copy.deepcopy(message))

        player_ids = normalized.get("player_ids")
        if player_ids is not None:
            normalized["player_ids"] = list(player_ids)

        character_ids = normalized.get("character_ids")
        if character_ids is not None:
            normalized["character_ids"] = list(character_ids)
        elif normalized.get("player_ids"):
            derived_character_ids = self.get_character_ids_for_players(normalized.get("player_ids"))
            normalized["character_ids"] = derived_character_ids or None

        if "metadata" not in normalized or normalized.get("metadata") is None:
            normalized["metadata"] = {}
        if "timestamp" not in normalized:
            normalized["timestamp"] = time.time()

        return normalized

    def _normalize_transcript_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a persisted transcript entry."""
        normalized = self._serialize_json_safe(copy.deepcopy(entry))

        player_ids = normalized.get("player_ids")
        if player_ids is not None:
            normalized["player_ids"] = list(player_ids)

        character_ids = normalized.get("character_ids")
        if character_ids is not None:
            normalized["character_ids"] = list(character_ids)
        elif normalized.get("player_ids"):
            derived_character_ids = self.get_character_ids_for_players(normalized.get("player_ids"))
            normalized["character_ids"] = derived_character_ids or None

        normalized["message_type"] = normalized.get("message_type") or "game"
        normalized["content"] = str(normalized.get("content") or "")
        normalized["is_html"] = bool(normalized.get("is_html"))
        if "metadata" not in normalized or normalized.get("metadata") is None:
            normalized["metadata"] = {}
        if "timestamp" not in normalized:
            normalized["timestamp"] = time.time()

        return normalized

    def _build_participant_manifest(self) -> List[Dict[str, Any]]:
        participants: List[Dict[str, Any]] = []
        for player_id, player_data in self.variables.get("players", {}).items():
            participants.append({
                "player_id": player_id,
                "name": player_data.get("name"),
                "controlled_character_id": self.get_controlled_character_id(player_id),
                "client_type": player_data.get("client_type"),
                "location": self.get_player_location(player_id),
            })
        return participants

    def ensure_save_metadata(self) -> Dict[str, Any]:
        """Build or refresh multiplayer-aware slot metadata."""
        metadata = copy.deepcopy(self.save_metadata) if self.save_metadata else {}
        participants = self._build_participant_manifest()
        metadata["slot_id"] = metadata.get("slot_id") or f"{self.story_id}_{self.created_at.replace(':', '-')}"
        metadata["save_format_version"] = 2
        metadata["mode"] = "multiplayer" if len(participants) > 1 else "singleplayer"
        metadata["created_by_player_id"] = (
            metadata.get("created_by_player_id")
            or (participants[0]["player_id"] if participants else None)
        )
        metadata["participant_manifest"] = participants
        metadata["participant_names"] = [p["name"] for p in participants if p.get("name")]
        metadata["updated_at"] = self.updated_at
        self.save_metadata = metadata
        return metadata

    def rebind_player_id(
        self,
        old_player_id: str,
        new_player_id: str,
        *,
        player_name: Optional[str] = None,
        client_type: Optional[str] = None,
    ) -> bool:
        """Move a saved participant slot onto the current live player ID."""
        players = self.variables.setdefault("players", {})
        if old_player_id not in players:
            return False

        if old_player_id == new_player_id:
            player_state = players[old_player_id]
        else:
            player_state = players.pop(old_player_id)
            players[new_player_id] = player_state

        if player_name:
            player_state["name"] = player_name
        if client_type:
            player_state["client_type"] = client_type

        for event in self.timed_events:
            if event.get("player_id") == old_player_id:
                event["player_id"] = new_player_id

        for message in self.message_history:
            visible_to = message.get("player_ids")
            if visible_to:
                message["player_ids"] = [new_player_id if pid == old_player_id else pid for pid in visible_to]

        for participant in self.ensure_save_metadata().get("participant_manifest", []):
            if participant.get("player_id") == old_player_id:
                participant["player_id"] = new_player_id
                if player_name:
                    participant["name"] = player_name
                if client_type:
                    participant["client_type"] = client_type

        return True

    def find_saved_participant_id(
        self,
        player_id: str,
        player_name: Optional[str] = None,
        occupied_player_ids: Optional[Set[str]] = None,
    ) -> Optional[str]:
        """Find the most likely saved participant slot for a live player."""
        players = self.variables.get("players", {})
        if player_id in players:
            return player_id

        metadata = self.ensure_save_metadata()
        participants = metadata.get("participant_manifest", [])
        occupied = set(occupied_player_ids or set())

        if player_name:
            exact_name_matches = [
                participant["player_id"]
                for participant in participants
                if (
                    participant.get("name") == player_name
                    and participant.get("player_id") in players
                    and participant.get("player_id") not in occupied
                )
            ]
            if len(exact_name_matches) == 1:
                return exact_name_matches[0]
        return None

    def claim_next_saved_participant(
        self,
        player_id: str,
        player_name: Optional[str] = None,
        client_type: Optional[str] = None,
        occupied_player_ids: Optional[Set[str]] = None,
    ) -> Optional[str]:
        """Claim a saved participant slot for a live player."""
        claimed_player_id = self.find_saved_participant_id(
            player_id,
            player_name=player_name,
            occupied_player_ids=occupied_player_ids,
        )
        if claimed_player_id:
            if claimed_player_id != player_id:
                self.rebind_player_id(
                    claimed_player_id,
                    player_id,
                    player_name=player_name,
                    client_type=client_type,
                )
            else:
                player_state = self.variables["players"][player_id]
                if player_name:
                    player_state["name"] = player_name
                if client_type:
                    player_state["client_type"] = client_type
            return player_id

        occupied = set(occupied_player_ids or set())
        available_saved_ids = [
            saved_player_id
            for saved_player_id in self.variables.get("players", {})
            if saved_player_id not in occupied
        ]
        if len(available_saved_ids) == 1:
            self.rebind_player_id(
                available_saved_ids[0],
                player_id,
                player_name=player_name,
                client_type=client_type,
            )
            return player_id
        return None

    def _mark_world_changed(self, actor_id: Optional[str] = None) -> None:
        """Record that visible shared world state changed."""
        self.version += 1
        self.last_modified_by = actor_id
        self.updated_at = datetime.now().isoformat()

    def remove_player(self, player_id: str, drop_timed_events: bool = False) -> None:
        """Forget a player from the active game state."""
        players = self.variables.get("players", {})
        if player_id in players:
            del players[player_id]

        if drop_timed_events:
            self.timed_events = [
                event
                for event in self.timed_events
                if not (
                    event.get("player_id") == player_id
                    and event.get("scope", "player") == "player"
                )
            ]

        self.ensure_save_metadata()

    def add_player(self, player_id: str, defaults: Optional[Dict[str, Any]] = None):
        logger.info(f"add_player: Called for player_id: {player_id}")
        if player_id in self.variables.get('players', {}):
            logger.info(f"add_player: Player {player_id} already exists.")
            return

        player_data = {
            "controlled_character_id": None,
            "location": self.story.start_node_id,
        }

        if defaults:
            player_data.update(defaults)
        
        if 'players' not in self.variables:
            self.variables['players'] = {}
        self.variables['players'][player_id] = player_data
        logger.info(f"add_player: Added player {player_id} to game state with initial data.")

    def _init_object_states_from_story(self, story: Story) -> None:
        """Initialize object states from story definition.
        
        Collects all objects from global objects and node objects,
        and initializes their runtime state.
        """
        # Initialize from global objects
        if story.objects:
            for obj in story.objects:
                self._init_single_object_state(obj)
        
        # Initialize from node objects
        for node in story.nodes.values():
            for obj in node.objects:
                if obj.id not in self.object_states:
                    self._init_single_object_state(obj)
    
    def _init_single_object_state(self, obj: StoryObject) -> None:
        """Initialize runtime state for a single object."""
        self.object_states[obj.id] = {
            'explicit_state': obj.explicit_state,
            'implicit_state': getattr(obj, 'implicit_state', ''),
            # Properties runtime state
            'properties': dict(getattr(obj, 'properties', {})),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # Node State Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def update_node_explicit_state(self, node_id: str, explicit_state: str) -> None:
        """Update a node's explicit_state directly and track the change for save/load.
        
        Args:
            node_id: The node ID to update
            explicit_state: The new explicit_state text
        """
        node = self.nodes.get(node_id)
        if not node:
            logger.warning(f"update_node_explicit_state: Node '{node_id}' not found")
            return
        node.explicit_state = explicit_state
        # Track in node_states for save/load persistence
        if node_id not in self.node_states:
            self.node_states[node_id] = {}
        self.node_states[node_id]['explicit_state'] = explicit_state
        self._mark_world_changed()
        logger.debug(f"update_node_explicit_state: Updated '{node_id}' explicit_state")

    def update_node_state(self, node_id: str, explicit_state: str = None, 
                          implicit_state: str = None, properties: Dict[str, Any] = None) -> None:
        """Update a node's DIP state directly and track changes for save/load.
        
        Args:
            node_id: The node ID to update
            explicit_state: Optional new explicit_state text
            implicit_state: Optional new implicit_state text
            properties: Optional properties dict to merge
        """
        node = self.nodes.get(node_id)
        if not node:
            logger.warning(f"update_node_state: Node '{node_id}' not found")
            return
        
        if explicit_state is not None:
            node.explicit_state = explicit_state
        if implicit_state is not None:
            node.implicit_state = implicit_state
        if properties is not None:
            node.properties.update(properties)
        
        # Track in node_states for save/load persistence
        self.node_states[node_id] = {
            'explicit_state': node.explicit_state,
            'implicit_state': node.implicit_state,
            'properties': dict(node.properties),
        }
        if explicit_state is not None or properties is not None:
            self._mark_world_changed()
        logger.debug(f"update_node_state: Updated '{node_id}' state")

    def set_player_character(self, player_id: str, character: Character) -> None:
        """
        Set a character for a specific player.

        Args:
            player_id: The ID of the player
            character: The Character object to assign to the player
        """
        logger.info(f"set_player_character: Setting character {character.id} for player {player_id}")
        
        # Ensure player exists
        if 'players' not in self.variables:
            self.variables['players'] = {}
        if player_id not in self.variables['players']:
            self.add_player(player_id)

        # Keep controlled characters unique across players.
        for other_player_id, other_player_data in self.variables['players'].items():
            if other_player_id == player_id:
                continue
            if other_player_data.get('controlled_character_id') == character.id:
                other_player_data['controlled_character_id'] = None
                logger.warning(
                    f"set_player_character: released character {character.id} from player {other_player_id} "
                    f"before assigning it to {player_id}"
                )
        
        self.variables['players'][player_id]['controlled_character_id'] = character.id
        
        # Initialize character state if not exists
        if character.id not in self.character_states:
            self.character_states[character.id] = {
                'explicit_state': character.explicit_state,
                'implicit_state': character.implicit_state,
                'memory': list(character.memory),
                'properties': dict(character.properties),
            }
        
        # Ensure properties has inventory and location
        props = self.character_states[character.id]['properties']
        if 'inventory' not in props:
            props['inventory'] = []
        if 'location' not in props:
            props['location'] = self.story.start_node_id
        self.variables['players'][player_id]['location'] = props['location']
        
        logger.info(f"set_player_character: Successfully set character {character.id} for player {player_id}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Pointer-Based Character Control
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_controlled_character_id(self, player_id: str) -> Optional[str]:
        """
        Get the ID of the character this player currently controls.
        
        This is the core "pointer" - dereference this to access the character's state.
        
        Args:
            player_id: The player's ID
            
        Returns:
            The character ID or None if no character is controlled
        """
        player_data = self.variables.get('players', {}).get(player_id, {})
        return player_data.get('controlled_character_id')
    
    def get_controlled_character_state(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full state of the character this player controls.
        
        This dereferences the pointer and returns the character's state from character_states.
        
        Args:
            player_id: The player's ID
            
        Returns:
            The character state dict or None
        """
        char_id = self.get_controlled_character_id(player_id)
        if not char_id:
            return None
        return self.character_states.get(char_id)
    
    def resolve_player_path(self, path: str, player_id: str) -> Any:
        """
        Resolve a path starting with 'player' by dereferencing through the controlled character.
        
        This is the elegant pointer dereference - 'player' simply becomes the controlled character's state.
        
        Examples:
            'player.properties.stats.health' -> character_states[controlled_id]['properties']['stats']['health']
            'player.explicit_state' -> character_states[controlled_id]['explicit_state']
            'player.properties.inventory' -> character_states[controlled_id]['properties']['inventory']
        
        Args:
            path: The path starting with 'player'
            player_id: The player's ID
            
        Returns:
            The resolved value or None
        """
        parts = path.split('.')
        
        # 'player' is just a pointer - dereference it
        if parts[0] == 'player':
            char_state = self.get_controlled_character_state(player_id)
            if not char_state:
                return None
            root = char_state
            parts = parts[1:]  # Continue from character state
        else:
            # Not a player path, use variables
            root = self.variables
        
        # Generic path navigation
        value = root
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
            if value is None:
                return None
        
        return value

    def set_variable(self, key: str, value: Any) -> None:
        """
        Set a game variable. Supports nested paths like 'players.{player_id}.character.name'.

        Args:
            key: The variable name (can be a dot-separated path)
            value: The variable value
        """
        if '.' not in key:
            # Simple key, set directly
            self.variables[key] = value
            return
        
        # Handle nested path
        parts = key.split('.')
        
        # Navigate to the parent, creating dicts as needed
        current = self.variables
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif current[part] is None:
                # Replace None with an empty dict
                current[part] = {}
            elif not isinstance(current[part], dict):
                # Can't navigate into a non-dict, log warning and return
                logger.warning(f"Cannot set nested variable '{key}': '{part}' is not a dict")
                return
            current = current[part]
        
        # Set the final value
        current[parts[-1]] = value

    def get_variable(self, key: str, default: Any = None, player_id: str = "default") -> Any:
        """
        Get a game variable. Supports derived variables with $lua: prefix.

        Args:
            key: The variable name
            default: The default value to return if the variable doesn't exist
            player_id: The player ID for context when evaluating derived variables

        Returns:
            The variable value or the default value
        """
        value = self.variables.get(key, default)
        
        # Check if this is a derived variable (Lua expression)
        if isinstance(value, str) and value.startswith(DERIVED_VAR_PREFIX):
            # Prevent infinite recursion
            if key in self._evaluating_derived:
                logger.warning(f"Circular dependency detected in derived variable '{key}'")
                return default
            
            try:
                self._evaluating_derived.add(key)
                expression = value[len(DERIVED_VAR_PREFIX):].strip()
                result = self._evaluate_lua_expression(expression, player_id)
                return result if result is not None else default
            finally:
                self._evaluating_derived.discard(key)
        
        return value

    def _get_lua_runtime(self) -> Optional['LuaRuntimeService']:
        """Get or create the Lua runtime for evaluating derived variables."""
        if self._lua_runtime is None:
            try:
                from src.core.lua_runtime import LuaRuntimeService
                # Create a minimal LuaRuntimeService without game_kernel
                # We'll use a lightweight version for expression evaluation only
                self._lua_runtime = _DerivedVarLuaRuntime()
            except ImportError as e:
                logger.warning(f"Could not import LuaRuntimeService: {e}")
                return None
        return self._lua_runtime

    def _evaluate_lua_expression(self, expression: str, player_id: str) -> Any:
        """
        Evaluate a Lua expression for derived variables.
        
        Args:
            expression: The Lua expression to evaluate
            player_id: The player ID for context
            
        Returns:
            The evaluated result or None if evaluation fails
        """
        lua_runtime = self._get_lua_runtime()
        if lua_runtime is None:
            return None
        
        return lua_runtime.evaluate_expression(expression, self, player_id)

    def add_message_to_history(
        self,
        role: str,
        content: str,
        speaker: Optional[str] = None,
        max_history: int = 20,
        player_ids: Optional[List[str]] = None,
        character_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a message to the conversation history.
        
        This is used to track displayed messages so the LLM can understand
        context when the player responds with things like "yes" or "no".
        
        Args:
            role: The role of the message sender ("system", "companion", "npc", "player")
            content: The message content
            speaker: Optional speaker name (e.g., companion name)
            max_history: Maximum number of messages to keep
            player_ids: Optional list of players who can see this message. None means public.
            character_ids: Optional list of controlled characters who witnessed this
                message when it happened. If omitted, it is derived from player_ids.
            location: Optional node ID where the event occurred.
            metadata: Optional structured metadata for downstream filtering.
        """
        resolved_character_ids = list(character_ids) if character_ids else None
        if resolved_character_ids is None and player_ids:
            resolved_character_ids = self.get_character_ids_for_players(player_ids)

        self.message_history.append({
            "role": role,
            "content": content,
            "speaker": speaker,
            "timestamp": time.time(),
            "player_ids": list(player_ids) if player_ids else None,
            "character_ids": resolved_character_ids or None,
            "location": location,
            "metadata": metadata or {},
        })
        # Keep only the last N messages
        if len(self.message_history) > max_history:
            self.message_history = self.message_history[-max_history:]

    def add_transcript_entry(
        self,
        message_type: str,
        content: str,
        *,
        is_html: bool = False,
        speaker: Optional[str] = None,
        player_ids: Optional[List[str]] = None,
        character_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a player-visible transcript entry for future session restore."""
        resolved_character_ids = list(character_ids) if character_ids else None
        if resolved_character_ids is None and player_ids:
            resolved_character_ids = self.get_character_ids_for_players(player_ids)

        self.transcript_history.append({
            "message_type": message_type,
            "content": content,
            "is_html": is_html,
            "speaker": speaker,
            "timestamp": time.time(),
            "player_ids": list(player_ids) if player_ids else None,
            "character_ids": resolved_character_ids or None,
            "location": location,
            "metadata": metadata or {},
        })

    def get_transcript_for_player(
        self,
        player_id: str,
        *,
        character_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the visible transcript for a specific player."""
        effective_character_id = character_id or self.get_controlled_character_id(player_id)
        visible_entries: List[Dict[str, Any]] = []

        for entry in self.transcript_history:
            visible_to = entry.get("player_ids")
            if visible_to and player_id not in visible_to:
                continue

            visible_characters = entry.get("character_ids")
            if effective_character_id and visible_characters and effective_character_id not in visible_characters:
                continue

            visible_entries.append(self._normalize_transcript_entry(entry))

        return visible_entries

    def get_recent_messages(
        self,
        count: int = 5,
        player_id: Optional[str] = None,
        character_id: Optional[str] = None,
        location: Optional[str] = None,
        include_locationless: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent messages from history.
        
        Args:
            count: Number of recent messages to return
            player_id: Optional player used to filter private messages
            character_id: Optional character used to filter perspective-specific history
            location: Optional node ID used to filter local events
            include_locationless: Whether to include messages with no location metadata
            
        Returns:
            List of recent message dictionaries
        """
        if not self.message_history:
            return []

        effective_character_id = character_id or (
            self.get_controlled_character_id(player_id) if player_id else None
        )
        filtered: List[Dict[str, Any]] = []
        for message in self.message_history:
            visible_to = message.get("player_ids")
            if player_id and visible_to and player_id not in visible_to:
                continue

            visible_characters = message.get("character_ids")
            if effective_character_id and visible_characters and effective_character_id not in visible_characters:
                continue

            message_location = message.get("location")
            if location is not None:
                if message_location is None and not include_locationless:
                    continue
                if message_location is not None and message_location != location:
                    continue

            filtered.append(message)

        return filtered[-count:]

    def get_players_in_location(self, node_id: str, exclude_player_id: Optional[str] = None) -> List[str]:
        """Get player IDs whose controlled characters are currently at a node."""
        player_ids = []
        for player_id in self.variables.get("players", {}):
            if exclude_player_id and player_id == exclude_player_id:
                continue
            if self.get_player_location(player_id) == node_id:
                player_ids.append(player_id)
        return player_ids

    def get_controlled_player_ids(self) -> Set[str]:
        """Return the set of all controlled character IDs currently assigned to players."""
        controlled_ids: Set[str] = set()
        for player_data in self.variables.get("players", {}).values():
            char_id = player_data.get("controlled_character_id")
            if char_id:
                controlled_ids.add(char_id)
        return controlled_ids

    def move_to_node(self, node_id: str, player_id: str) -> bool:
        """
        Move the player to a new story node.

        Args:
            node_id: The ID of the node to move to
            player_id: The ID of the player moving
            
        Returns:
            bool: True if the move was successful, False otherwise
        """
        logger.info(f"Attempting to move player {player_id} to node {node_id}")
        if not node_id:
            logger.error("move_to_node failed: node_id is None or empty.")
            return False
            
        new_node = self.nodes.get(node_id)
        if not new_node:
            logger.error(f"move_to_node failed: could not find node with id {node_id}")
            return False
        
        try:
            # Get the player's current location for the history record
            current_location = self.get_player_location(player_id)
            logger.info(f"Player {player_id} current location is {current_location}")

            # Add the previous location to history before moving
            self.history.append({
                "node_id": current_location,
                "inventory": list(self.get_player_inventory(player_id)),
                "variables": self.variables.copy(),
                "version": self.version,
                "player": player_id
            })
            
            # Update location using pointer model
            self.set_player_location(player_id, node_id)
            logger.info(f"Player {player_id} new location set to {node_id}")
                
            # Add to visited nodes if not already there
            if node_id not in self.visited_nodes:
                self.visited_nodes.append(node_id)
            
            # Update current node tracking attributes
            self.current_node_id = node_id
            self.current_node = new_node
            
            # Update version and timestamps
            self.version += 1
            self.last_modified_by = player_id
            self.updated_at = datetime.now().isoformat()
            
            logger.info(f"Successfully moved player {player_id} to node {node_id}")
            return True
                
        except Exception as e:
            # Log error and restore previous state if needed
            logger.error(f"Error moving to node {node_id}: {str(e)}", exc_info=True)
            return False

    def has_visited(self, node_id: str) -> bool:
        """
        Check if the player has visited a specific node.

        Args:
            node_id: The ID of the node to check

        Returns:
            bool: True if the node has been visited, False otherwise
        """
        return node_id in self.visited_nodes

    def check_action_conditions(self, action: StoryAction) -> bool:
        """
        Check if an action's conditions are met.

        Args:
            action: The action to check

        Returns:
            bool: True if all conditions are met, False otherwise
        """
        if not action.conditions:
            return True
            
        for condition in action.conditions:
            if condition.type == "state":
                current_value = self.get_variable(condition.variable)
                if condition.operator == "eq" and current_value != condition.value:
                    return False
                elif condition.operator == "neq" and current_value == condition.value:
                    return False
                elif condition.operator == "gt" and not (current_value > condition.value):
                    return False
                elif condition.operator == "lt" and not (current_value < condition.value):
                    return False
            elif condition.type == "inventory":
                if condition.operator == "has" and not self.has_item(condition.value, owner="player:default"):
                    return False
                elif condition.operator == "not_has" and self.has_item(condition.value, owner="player:default"):
                    return False
            elif condition.type == "object_status":
                target_object = self.find_object_in_world(condition.target)
                required_status = condition.state or condition.value
                object_status = self.get_effective_object_status(condition.target)
                logger.debug(f"Checking condition for action '{action.id}': object '{condition.target}' status is '{object_status}' (required '{required_status}')")
                if not target_object or required_status not in object_status:
                    return False
                    
        return True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the game state to a dictionary, storing only differences from the initial story state.

        Returns:
            Dict[str, Any]: A dictionary representing the state diff.
        """
        metadata = self.ensure_save_metadata()
        player_name = metadata.get("participant_names", ["unknown_player"])[0] if metadata.get("participant_names") else "unknown_player"

        state_id = f"{self.story_id}_{self.created_at.replace(':', '-')}"

        serializable_vars = copy.deepcopy(self.variables)
        if 'players' in serializable_vars:
            for p_id, p_data in serializable_vars['players'].items():
                serializable_vars['players'][p_id] = self._serialize_player_state_for_save(p_data)

        # Track object status and explicit_state changes
        object_status_changes = {}
        object_explicit_state_changes = {}
        for node_id, current_node in self.nodes.items():
            original_node = self.story.nodes.get(node_id)
            if not original_node:
                continue

            current_objects = {obj.id: obj for obj in current_node.objects}
            original_objects = {obj.id: obj for obj in original_node.objects}

            for obj_id, current_obj in current_objects.items():
                if obj_id in original_objects:
                    original_obj = original_objects[obj_id]
                    # Check status changes
                    current_status = self.get_effective_object_status(obj_id)
                    original_status = original_obj.get_status() if hasattr(original_obj, 'get_status') else []
                    if current_status != original_status:
                        object_status_changes[obj_id] = current_status
                    # Check explicit_state changes
                    current_explicit_state = getattr(current_obj, 'explicit_state', '')
                    original_explicit_state = getattr(original_obj, 'explicit_state', '')
                    if current_explicit_state != original_explicit_state:
                        object_explicit_state_changes[obj_id] = current_explicit_state

        # Collect all object definitions from the story
        all_object_definitions = {}
        # Add global objects
        if self.story.objects:
            for obj in self.story.objects:
                all_object_definitions[obj.id] = obj.dict()
        # Add node-specific objects
        for node in self.story.nodes.values():
            for obj in node.objects:
                all_object_definitions[obj.id] = obj.dict()

        # Collect all character definitions from the story (including generated ones)
        all_character_definitions = {}
        if self.story.characters:
            for char in self.story.characters:
                all_character_definitions[char.id] = char.dict()

        # Collect dynamically created nodes (nodes not in the original story)
        all_node_definitions = {}
        original_node_ids = set(self.story.nodes.keys())
        for node_id, node in self.nodes.items():
            if node_id not in original_node_ids:
                all_node_definitions[node_id] = node.dict()

        # Collect dynamically added actions on existing nodes
        # (actions that weren't in the original story's nodes)
        dynamic_actions = {}
        for node_id, node in self.nodes.items():
            if node_id in original_node_ids and node.actions:
                original_node = self.story.nodes.get(node_id)
                original_action_ids = set()
                if original_node and original_node.actions:
                    original_action_ids = {a.id for a in original_node.actions}
                new_actions = [a.dict() for a in node.actions if a.id not in original_action_ids]
                if new_actions:
                    dynamic_actions[node_id] = new_actions

        diff = {
            "variables": serializable_vars,
            "object_status_changes": object_status_changes,
            "object_explicit_state_changes": object_explicit_state_changes,
            "visited_nodes": list(self.visited_nodes),
            "timed_events": self.timed_events,
            "runtime_connections": self._serialize_json_safe(copy.deepcopy(self.runtime_connections)),
            "node_states": copy.deepcopy(self.node_states),
            "all_object_definitions": all_object_definitions,
            "all_character_definitions": all_character_definitions,  # For generated character persistence
            "all_node_definitions": all_node_definitions,  # For dynamically created nodes
            "dynamic_actions": dynamic_actions,  # For dynamically added actions on existing nodes
            "character_states": self._serialize_character_states_for_save(),
            "object_states": self._serialize_json_safe(copy.deepcopy(self.object_states)),
            "message_history": self._serialize_message_history_for_save(),
        }

        result = {
            "id": state_id,
            "story_id": self.story_id,
            "player_name": player_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "save_metadata": metadata,
            "transcript_history": [
                self._normalize_transcript_entry(entry)
                for entry in self.transcript_history
                if isinstance(entry, dict)
            ],
            "diff": diff
        }
            
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Architect-Facing Serialization
    # ═══════════════════════════════════════════════════════════════════════════

    def _collect_local_graph_seed_ids(self, player_id: str) -> Set[str]:
        """Collect local entity IDs that anchor graph-neighborhood retrieval."""
        seed_ids: Set[str] = set()
        controlled_char_id = self.get_controlled_character_id(player_id)
        current_location = self.get_player_location(player_id)
        if controlled_char_id:
            seed_ids.add(controlled_char_id)
        if current_location:
            seed_ids.add(current_location)

        current_node = self.nodes.get(current_location) if current_location else None
        if current_node:
            seed_ids.update(obj.id for obj in current_node.objects)

        for item_ref in self._serialize_inventory_refs(self.get_player_inventory(player_id)):
            if isinstance(item_ref, str):
                seed_ids.add(item_ref)

        for char_id, state in self.character_states.items():
            if state.get('properties', {}).get('location') == current_location:
                seed_ids.add(char_id)

        return seed_ids

    def _collect_connection_neighborhood(self, entity_ids: Set[str]) -> List[Dict[str, Any]]:
        """Collect story and runtime connection edges touching the given entities."""
        if not entity_ids:
            return []

        serialized: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        if self.story and self.story.connections:
            for entry in self.story.connections.to_serializable_neighborhood(entity_ids):
                conn_id = str(entry.get("id") or "")
                if conn_id and conn_id not in seen_ids:
                    seen_ids.add(conn_id)
                    serialized.append(entry)

        for entry in self.runtime_connections:
            if not isinstance(entry, dict):
                continue
            touched = {entry.get("source"), *(entry.get("targets") or [])}
            if not entity_ids.intersection({value for value in touched if isinstance(value, str) and value}):
                continue
            entry_id = str(entry.get("id") or "")
            if entry_id and entry_id in seen_ids:
                continue
            if entry_id:
                seen_ids.add(entry_id)
            runtime_entry = copy.deepcopy(entry)
            serialized.append(runtime_entry)

        return serialized

    @staticmethod
    def _collect_related_entity_ids(connection_neighborhood: List[Dict[str, Any]]) -> Set[str]:
        related_ids: Set[str] = set()
        for entry in connection_neighborhood:
            source = entry.get("source")
            if isinstance(source, str) and source:
                related_ids.add(source)
            for target in entry.get("targets") or []:
                if isinstance(target, str) and target:
                    related_ids.add(target)
        return related_ids

    def to_architect_json(
        self,
        player_id: str,
        *,
        view: str = "full",
        max_history: int = 10,
        include_message_history: bool = True,
    ) -> Dict[str, Any]:
        """Serialize full game state for the Architect's ``read_game_state`` tool.

        Returns a compact JSON-safe dict containing:
        - variables (excluding internal prefixes)
        - character_states (enriched with name/definition from story)
        - object_states (enriched with name/definition from story)
        - nodes (with actions, object IDs, triggers, hints)
        - visited_nodes, version, message_history (capped)
        """
        # TODO(graph-context): "view" currently controls a hand-built heuristic
        # serializer. After graph-based context management is implemented, keep
        # the same interface but reinterpret these modes as graph retrieval
        # scopes (for example, local neighborhood vs broader expansion).
        local_only = view == "local"

        # -- variables (filter out internal bookkeeping and lore/quest defs
        #    already injected as LOREBOOK in the task prompt) --
        safe_vars: Dict[str, Any] = {}
        for k, v in self.variables.items():
            if k.startswith('_') or k.startswith('lore_') or k.startswith('quest_def_'):
                continue
            safe_vars[k] = self._serialize_json_safe(v)

        # TODO(graph-context): The connection graph is available via
        # _collect_connection_neighborhood() but currently most compiled edges
        # duplicate information already visible in the game state (containment,
        # navigation, character location, player-state propagation encoded in
        # node definitions).  Re-enable connection_neighborhood injection once
        # we have a smarter filter that only surfaces cross-entity causal edges
        # not derivable from existing state.

        # -- character_states (only full detail for controlled char + NPCs at
        #    current location; compact stubs for everyone else) --
        # TODO(graph-context): Find an intelligent way to use the connection
        # graph to selectively pull in non-co-located characters when they are
        # structurally relevant, without blowing up context size via star
        # topologies (e.g. player-state propagation connecting to every node).
        controlled_char_id = self.get_controlled_character_id(player_id)
        current_location = self.get_player_location(player_id)

        char_json: Dict[str, Any] = {}
        for char_id, state in self.character_states.items():
            char_def = self.story.get_character(char_id) if self.story else None
            char_loc = state.get('properties', {}).get('location', '')

            is_relevant = (
                char_id == controlled_char_id
                or char_loc == current_location
            )
            if is_relevant:
                props = dict(state.get('properties', {}))
                if 'inventory' in props:
                    props['inventory'] = self._serialize_inventory_refs(props['inventory'])
                entry: Dict[str, Any] = {
                    'name': char_def.name if char_def else char_id,
                    'explicit_state': state.get('explicit_state', ''),
                    'implicit_state': state.get('implicit_state', ''),
                    'memory': list(state.get('memory', [])),
                    'properties': props,
                }
                if char_def:
                    entry['definition'] = char_def.definition
                    entry['is_playable'] = char_def.is_playable
                char_json[char_id] = entry
            else:
                char_json[char_id] = {
                    'name': char_def.name if char_def else char_id,
                    'location': char_loc,
                    'is_playable': char_def.is_playable if char_def else False,
                }

        # -- object_states (merge story object defs + runtime state) --
        # TODO(graph-context): Find an intelligent way to use connection graph
        # edges to include offscreen objects when structurally relevant,
        # without pulling in the entire object set via fan-out connections.
        relevant_object_ids: Optional[Set[str]] = None
        if local_only:
            relevant_object_ids = set(
                item_ref for item_ref in self._serialize_inventory_refs(self.get_player_inventory(player_id))
                if isinstance(item_ref, str)
            )
            current_node = self.nodes.get(current_location) if current_location else None
            if current_node:
                relevant_object_ids.update(obj.id for obj in current_node.objects)

        obj_json: Dict[str, Any] = {}
        seen_obj_ids: set = set()
        # Include objects from runtime object_states
        for obj_id, state in self.object_states.items():
            if relevant_object_ids is not None and obj_id not in relevant_object_ids:
                continue
            obj_def = self.story.get_object(obj_id) if self.story else None
            entry = {
                'name': obj_def.name if obj_def else obj_id,
                'explicit_state': state.get('explicit_state', obj_def.explicit_state if obj_def else ''),
                'implicit_state': state.get('implicit_state', getattr(obj_def, 'implicit_state', '') if obj_def else ''),
                'properties': state.get('properties', {}),
            }
            if obj_def and obj_def.definition:
                entry['definition'] = obj_def.definition
            obj_json[obj_id] = entry
            seen_obj_ids.add(obj_id)
        # Include node objects not yet in object_states
        for node in self.nodes.values():
            for obj in node.objects:
                if relevant_object_ids is not None and obj.id not in relevant_object_ids:
                    continue
                if obj.id not in seen_obj_ids:
                    entry = {
                        'name': obj.name,
                        'explicit_state': obj.explicit_state or '',
                    }
                    if obj.definition:
                        entry['definition'] = obj.definition
                    obj_json[obj.id] = entry
                    seen_obj_ids.add(obj.id)

        timed_events_json: List[Dict[str, Any]] = []
        for event_data in self.timed_events:
            try:
                event = TimedEvent(**event_data)
            except Exception:
                continue

            event_location = event.location_id or event.node_id
            if local_only and event.scope != "session":
                is_player_event = event.player_id == player_id
                is_local_event = bool(event_location and event_location == current_location)
                if not is_player_event and not is_local_event:
                    continue

            timed_events_json.append({
                "id": event.id,
                "event_type": event.event_type,
                "scope": event.scope,
                "object_id": event.object_id,
                "rule_id": event.rule_id,
                "player_id": event.player_id,
                "location_id": event_location,
                "trigger_timestamp": event.trigger_timestamp,
                "seconds_remaining": max(0.0, event.trigger_timestamp - time.time()),
                "event_context": event.event_context,
                "intended_state_changes": self._serialize_json_safe(event.intended_state_changes),
                "audience": event.audience,
            })

        # -- nodes (full detail only for current node; compact stubs for rest) --
        # TODO(graph-context): Find an intelligent way to expand a small number
        # of graph-adjacent nodes (e.g. direct navigation targets) to full
        # detail, avoiding star-topology fan-out that would include all nodes.
        # For now, only the current node is fully expanded; the Architect can
        # call read_node() for others when needed.
        full_detail_node_ids = {current_location} if current_location else set()

        nodes_json: Dict[str, Any] = {}
        for node_id, node in self.nodes.items():
            if node_id in full_detail_node_ids:
                actions_list = []
                if node.actions:
                    for action in node.actions:
                        a_entry: Dict[str, Any] = {
                            'id': action.id,
                            'text': action.text or action.description or action.id,
                        }
                        if action.intent:
                            a_entry['intent'] = action.intent
                        actions_list.append(a_entry)

                triggers_list = []
                if node.triggers:
                    for trigger in node.triggers:
                        t_entry: Dict[str, Any] = {
                            'id': trigger.id,
                            'type': trigger.type,
                        }
                        if trigger.intent:
                            t_entry['intent'] = trigger.intent
                        if trigger.conditions:
                            t_entry['conditions'] = [c.dict() for c in trigger.conditions]
                        triggers_list.append(t_entry)

                object_ids = [obj.id for obj in node.objects]

                n_entry: Dict[str, Any] = {
                    'id': node_id,
                    'name': node.name or node_id,
                    'definition': node.definition,
                    'explicit_state': node.explicit_state or '',
                    'implicit_state': node.implicit_state or '',
                    'properties': dict(node.properties),
                    'actions': actions_list,
                    'objects': object_ids,
                }
                if triggers_list:
                    n_entry['triggers'] = triggers_list
                if node.hints:
                    n_entry['hints'] = node.hints
                nodes_json[node_id] = n_entry
            else:
                nodes_json[node_id] = {'id': node_id, 'name': node.name or node_id}

        # -- message_history (capped) --
        controlled_char_id = self.get_controlled_character_id(player_id)
        recent: List[Dict[str, Any]] = []
        if include_message_history and max_history > 0:
            recent = self.get_recent_messages(
                max_history,
                player_id=player_id,
                character_id=controlled_char_id,
            )

        result = {
            'variables': safe_vars,
            'character_states': char_json,
            'object_states': obj_json,
            'timed_events': timed_events_json,
            'nodes': nodes_json,
            'visited_nodes': list(self.visited_nodes),
            'version': self.version,
        }
        if include_message_history:
            result['message_history'] = recent
        return result

    def apply_merge_patch(self, patch: Dict[str, Any], player_id: str) -> List[str]:
        """Apply a JSON merge-patch to the game state (RFC 7386 semantics).

        Returns a list of human-readable descriptions of what was applied.
        Engine-side hooks (version bump, node_states tracking) are performed
        after all fields are merged.
        """
        from src.models.story_models import StoryNode, StoryAction, StoryObject, Character

        applied: List[str] = []
        read_only = {'story_id', 'created_at', 'version', 'updated_at'}

        for top_key in patch:
            if top_key in read_only:
                logger.warning(f"apply_merge_patch: ignoring write to read-only field '{top_key}'")
                continue

        # ── variables ──
        if 'variables' in patch and isinstance(patch['variables'], dict):
            for k, v in patch['variables'].items():
                if v is None:
                    self.variables.pop(k, None)
                    applied.append(f"variables.{k} (deleted)")
                elif isinstance(v, dict) and isinstance(self.variables.get(k), dict):
                    self._deep_merge_dict(self.variables[k], v)
                    applied.append(f"variables.{k}")
                else:
                    self.variables[k] = v
                    applied.append(f"variables.{k}")

        # ── character_states ──
        if 'character_states' in patch and isinstance(patch['character_states'], dict):
            for char_id, char_patch in patch['character_states'].items():
                if not isinstance(char_patch, dict):
                    continue
                if char_id not in self.character_states:
                    self.character_states[char_id] = {
                        'explicit_state': '', 'implicit_state': '', 'memory': [], 'properties': {},
                    }
                    # Register stub in story if needed
                    if self.story and not self.story.get_character(char_id):
                        name = char_patch.get('name', char_id)
                        location = (char_patch.get('properties') or {}).get('location', '')
                        stub = Character(
                            id=char_id, name=name, definition=char_patch.get('definition', ''),
                            explicit_state=char_patch.get('explicit_state', ''),
                            properties={'location': location} if location else {},
                            is_playable=char_patch.get('is_playable', False),
                        )
                        if self.story.characters is None:
                            self.story.characters = []
                        self.story.characters.append(stub)
                    applied.append(f"character_states.{char_id} (created)")

                state = self.character_states[char_id]
                story_char = self.story.get_character(char_id) if self.story else None
                if story_char:
                    if 'name' in char_patch:
                        story_char.name = char_patch['name']
                    if 'definition' in char_patch:
                        story_char.definition = char_patch['definition']
                    if 'is_playable' in char_patch:
                        story_char.is_playable = bool(char_patch['is_playable'])
                    if 'properties' in char_patch and isinstance(char_patch['properties'], dict):
                        story_char.properties = dict(story_char.properties or {})
                        if 'location' in char_patch['properties']:
                            story_char.properties['location'] = char_patch['properties']['location']
                for field in ('explicit_state', 'implicit_state'):
                    if field in char_patch:
                        state[field] = char_patch[field]
                        applied.append(f"character_states.{char_id}.{field}")
                if 'memory' in char_patch:
                    state['memory'] = list(char_patch['memory'])
                    applied.append(f"character_states.{char_id}.memory")
                if 'properties' in char_patch and isinstance(char_patch['properties'], dict):
                    props = state.setdefault('properties', {})
                    self._deep_merge_dict(props, char_patch['properties'])
                    # Sync character location to engine tracking
                    if 'location' in char_patch['properties']:
                        new_loc = char_patch['properties']['location']
                        self.character_locations[char_id] = new_loc
                        for pid, pdata in self.variables.get('players', {}).items():
                            if pdata.get('controlled_character_id') == char_id:
                                self.current_node_id = new_loc
                                self.current_node = self.nodes.get(new_loc)
                    # Normalize inventory entries if present
                    if 'inventory' in char_patch['properties']:
                        inv = props.get('inventory', [])
                        props['inventory'] = self._normalize_inventory_entries(inv)
                    applied.append(f"character_states.{char_id}.properties")

        # ── nodes ──
        if 'nodes' in patch and isinstance(patch['nodes'], dict):
            for node_id, node_patch in patch['nodes'].items():
                if not isinstance(node_patch, dict):
                    continue
                node = self.nodes.get(node_id)
                if node is None:
                    node = StoryNode(
                        id=node_id,
                        name=node_patch.get('name', node_id),
                        definition=node_patch.get('definition', ''),
                    )
                    self.nodes[node_id] = node
                    applied.append(f"nodes.{node_id} (created)")

                if 'name' in node_patch:
                    node.name = node_patch['name']
                if 'definition' in node_patch:
                    node.definition = node_patch['definition']
                if 'explicit_state' in node_patch:
                    self.update_node_explicit_state(node_id, node_patch['explicit_state'])
                    applied.append(f"nodes.{node_id}.explicit_state")
                if 'implicit_state' in node_patch:
                    self.update_node_state(node_id, implicit_state=node_patch['implicit_state'])
                    applied.append(f"nodes.{node_id}.implicit_state")
                if 'hints' in node_patch:
                    node.hints = node_patch['hints']
                    applied.append(f"nodes.{node_id}.hints")
                if 'properties' in node_patch and isinstance(node_patch['properties'], dict):
                    self._deep_merge_dict(node.properties, node_patch['properties'])
                    applied.append(f"nodes.{node_id}.properties")
                if 'actions' in node_patch and isinstance(node_patch['actions'], list):
                    new_actions = []
                    for a_data in node_patch['actions']:
                        if isinstance(a_data, dict) and 'id' in a_data:
                            new_actions.append(StoryAction(
                                id=a_data['id'],
                                text=a_data.get('text', a_data['id']),
                                intent=a_data.get('intent'),
                            ))
                    node.actions = new_actions
                    applied.append(f"nodes.{node_id}.actions")
                if 'objects' in node_patch and isinstance(node_patch['objects'], list):
                    new_objs = []
                    for obj_ref in node_patch['objects']:
                        if isinstance(obj_ref, str):
                            existing = self.find_object_anywhere(obj_ref)
                            if existing:
                                new_objs.append(existing)
                            else:
                                new_objs.append(StoryObject(id=obj_ref, name=obj_ref))
                        elif isinstance(obj_ref, dict) and 'id' in obj_ref:
                            new_objs.append(StoryObject(**obj_ref))
                    node.objects = new_objs
                    applied.append(f"nodes.{node_id}.objects")

        # ── object_states ──
        if 'object_states' in patch and isinstance(patch['object_states'], dict):
            for obj_id, obj_patch in patch['object_states'].items():
                if not isinstance(obj_patch, dict):
                    continue
                if obj_id not in self.object_states:
                    self.object_states[obj_id] = {}
                    # Register stub in story if needed
                    if self.story:
                        existing = self.story.get_object(obj_id) if hasattr(self.story, 'get_object') else None
                        if not existing:
                            stub = StoryObject(
                                id=obj_id,
                                name=obj_patch.get('name', obj_id),
                                explicit_state=obj_patch.get('explicit_state', ''),
                                definition=obj_patch.get('definition', ''),
                            )
                            if self.story.objects is None:
                                self.story.objects = []
                            self.story.objects.append(stub)
                    applied.append(f"object_states.{obj_id} (created)")
                story_obj = self.story.get_object(obj_id) if self.story and hasattr(self.story, 'get_object') else None
                if story_obj:
                    if 'name' in obj_patch:
                        story_obj.name = obj_patch['name']
                    if 'definition' in obj_patch:
                        story_obj.definition = obj_patch['definition']
                self._deep_merge_dict(self.object_states[obj_id], obj_patch)
                applied.append(f"object_states.{obj_id}")

        # ── visited_nodes ──
        if 'visited_nodes' in patch and isinstance(patch['visited_nodes'], list):
            self.visited_nodes = list(patch['visited_nodes'])
            applied.append("visited_nodes")

        # ── timed_events (merge-by-id: upsert new, preserve unmentioned) ──
        if 'timed_events' in patch and isinstance(patch['timed_events'], list):
            now_ts = time.time()
            incoming_by_id: Dict[str, Dict[str, Any]] = {}
            cancelled_ids: set = set()
            for event_patch in patch['timed_events']:
                if not isinstance(event_patch, dict):
                    continue
                event_data = copy.deepcopy(event_patch)
                event_id = event_data.get("id")
                if not event_id:
                    continue
                if event_data.get("cancelled"):
                    cancelled_ids.add(event_id)
                    continue
                delay_seconds = event_data.pop("delay_seconds", None)
                delay = event_data.pop("delay", None)
                if "trigger_timestamp" not in event_data:
                    if isinstance(delay_seconds, (int, float)):
                        event_data["trigger_timestamp"] = now_ts + float(delay_seconds)
                    elif delay:
                        parsed_delay = parse_duration_to_seconds(str(delay))
                        if parsed_delay > 0:
                            event_data["trigger_timestamp"] = now_ts + parsed_delay
                if "trigger_timestamp" not in event_data:
                    continue
                incoming_by_id[event_id] = event_data

            merged: List[Dict[str, Any]] = []
            seen_ids: set = set()
            for existing in self.timed_events:
                eid = existing.get("id")
                if eid in cancelled_ids:
                    continue
                if eid in incoming_by_id:
                    merged.append(incoming_by_id[eid])
                    seen_ids.add(eid)
                else:
                    merged.append(existing)
                    seen_ids.add(eid)
            for eid, event_data in incoming_by_id.items():
                if eid not in seen_ids:
                    merged.append(event_data)
            self.timed_events = merged
            applied.append("timed_events")

        # ── runtime_connections (full replacement for now) ──
        if 'runtime_connections' in patch and isinstance(patch['runtime_connections'], list):
            self.runtime_connections = [
                copy.deepcopy(entry) for entry in patch['runtime_connections']
                if isinstance(entry, dict)
            ]
            applied.append("runtime_connections")

        # ── Engine-side hooks ──
        if applied:
            self.version += 1
            self.updated_at = datetime.now().isoformat()
            self.last_modified_by = player_id

        return applied

    @staticmethod
    def _deep_merge_dict(target: Dict, source: Dict) -> None:
        """Recursively merge *source* into *target* (RFC 7386 merge-patch)."""
        for key, value in source.items():
            if value is None:
                target.pop(key, None)
            elif isinstance(value, dict) and isinstance(target.get(key), dict):
                GameState._deep_merge_dict(target[key], value)
            else:
                target[key] = value

    def _extract_changed_variables(self) -> Dict[str, Any]:
        """
        Extract only the variables that have changed from the initial state.
        
        Returns:
            Dict[str, Any]: Dictionary of changed variables
        """
        def _serialize_pydantic_objects(data: Any) -> Any:
            if isinstance(data, list):
                return [_serialize_pydantic_objects(item) for item in data]
            if isinstance(data, dict):
                return {key: _serialize_pydantic_objects(value) for key, value in data.items()}
            if hasattr(data, 'dict'):
                try:
                    return data.dict()
                except Exception:
                    return str(data)
            return data

        # Create a serializable copy of variables to avoid modifying the live game state
        serializable_variables = copy.deepcopy(self.variables)
        players = serializable_variables.get("players")
        if isinstance(players, dict):
            for player_data in players.values():
                if isinstance(player_data, dict):
                    player_data.pop("inventory", None)
        
        # Recursively serialize any Pydantic models within the variables
        return _serialize_pydantic_objects(serializable_variables)
    
    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update the game state from a dictionary.
        
        Args:
            data: Dictionary containing game state data
        """
        if "nodes" in data:
            for node_id, node_data in data["nodes"].items():
                if node_id in self.nodes:
                    self.nodes[node_id] = self.nodes[node_id].parse_obj(node_data)

        if "visited_nodes" in data:
            self.visited_nodes = data["visited_nodes"]
        
        if "variables" in data:
            # Deep merge variables
            for key, value in data["variables"].items():
                # Special handling for players structure
                if key == "players":
                    if "players" not in self.variables:
                        self.variables["players"] = {}
                    
                    for player_id, player_data in value.items():
                        if player_id not in self.variables["players"]:
                            self.variables["players"][player_id] = {}
                        if isinstance(player_data, dict):
                            player_data = {k: v for k, v in player_data.items() if k != "inventory"}
                        self.variables["players"][player_id].update(player_data)
                else:
                    # For other keys, do a direct replacement
                    self.variables[key] = value

        if "node_states" in data:
            self.node_states = data["node_states"]
            # Apply node DIP changes to the deep-copied nodes
            for node_id, state in self.node_states.items():
                node = self.nodes.get(node_id)
                if node:
                    if 'explicit_state' in state:
                        node.explicit_state = state['explicit_state']
                    if 'implicit_state' in state:
                        node.implicit_state = state['implicit_state']
                    if 'properties' in state:
                        node.properties.update(state['properties'])
        if "timed_events" in data:
            self.timed_events = data["timed_events"]
        if "runtime_connections" in data:
            self.runtime_connections = data["runtime_connections"]

        if "history" in data:
            self.history = data["history"]

        # Update timestamps
        self.updated_at = datetime.now().isoformat()
        self.version += 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any], story: Story) -> "GameState":
        """
        Create a GameState instance from a dictionary containing a state diff.

        Args:
            data: Dictionary containing game state data.
            story: The Story object for this game state.

        Returns:
            A new GameState instance with the loaded data.
        """
        game_state = cls(story)
        logger.info(f"GameState.from_dict: Created new game_state object ID: {id(game_state)}")

        diff = data["diff"]

        game_state.variables = diff.get("variables", {})
        for player_data in game_state.variables.get("players", {}).values():
            if isinstance(player_data, dict):
                player_data.pop("inventory", None)
        game_state.visited_nodes = diff.get("visited_nodes", [])
        game_state.timed_events = diff.get("timed_events", [])
        game_state.runtime_connections = diff.get("runtime_connections", [])
        raw_message_history = diff.get("message_history", data.get("message_history", []))
        game_state.message_history = [
            game_state._normalize_message_history_entry(message)
            for message in raw_message_history
            if isinstance(message, dict)
        ]
        raw_transcript_history = data.get("transcript_history", diff.get("transcript_history", []))
        game_state.transcript_history = [
            game_state._normalize_transcript_entry(entry)
            for entry in raw_transcript_history
            if isinstance(entry, dict)
        ]
        game_state.save_metadata = copy.deepcopy(data.get("save_metadata", {}))
        # Restore node states
        saved_node_states = diff.get("node_states", {})
        if saved_node_states:
            game_state.node_states = saved_node_states
            # Apply DIP changes to the deep-copied nodes
            for node_id, state in saved_node_states.items():
                node = game_state.nodes.get(node_id)
                if node:
                    if 'explicit_state' in state:
                        node.explicit_state = state['explicit_state']
                    if 'implicit_state' in state:
                        node.implicit_state = state['implicit_state']
                    if 'properties' in state:
                        node.properties.update(state['properties'])
                    logger.debug(f"Restored node state for '{node_id}'")

        # Apply object status changes (now in properties)
        object_status_changes = diff.get("object_status_changes", {})
        for obj_id, new_status in object_status_changes.items():
            obj = game_state.find_object_in_world(obj_id)
            if obj and hasattr(obj, 'properties'):
                obj.properties['status'] = new_status
        
        # Apply object explicit_state changes
        object_explicit_state_changes = diff.get("object_explicit_state_changes", {})
        for obj_id, new_explicit_state in object_explicit_state_changes.items():
            obj = game_state.find_object_in_world(obj_id)
            if obj:
                obj.explicit_state = new_explicit_state

        # Restore character states
        saved_character_states = diff.get("character_states", {})
        if saved_character_states:
            for char_id, char_state in saved_character_states.items():
                props = char_state.get("properties", {})
                if "inventory" in props:
                    char_state.setdefault("properties", {})["inventory"] = game_state._normalize_inventory_entries(
                        props.get("inventory", [])
                    )
                game_state.character_states[char_id] = char_state
                logger.debug(f"Restored character state for '{char_id}'")

        # Restore object states
        saved_object_states = diff.get("object_states", {})
        if saved_object_states:
            for obj_id, obj_state in saved_object_states.items():
                game_state.object_states[obj_id] = obj_state
                logger.debug(f"Restored object state for '{obj_id}'")

        # Restore generated objects (objects in save but not in original story)
        saved_object_defs = diff.get("all_object_definitions", {})
        if saved_object_defs:
            # Build set of original object IDs from the pristine story
            original_object_ids = {obj.id for obj in story.objects} if story.objects else set()
            for node in story.nodes.values():
                original_object_ids.update(obj.id for obj in node.objects)
            
            # Restore any objects that were generated at runtime
            for obj_id, obj_data in saved_object_defs.items():
                if obj_id not in original_object_ids:
                    # This was a generated object - restore it to story.objects
                    generated_obj = StoryObject(**obj_data)
                    story.objects.append(generated_obj)
                    logger.info(f"Restored generated object '{obj_id}' from save")

        # Restore generated characters (characters in save but not in original story)
        saved_char_defs = diff.get("all_character_definitions", {})
        if saved_char_defs:
            # Build set of original character IDs from the pristine story
            original_char_ids = {char.id for char in story.characters} if story.characters else set()
            
            # Restore any characters that were generated at runtime
            for char_id, char_data in saved_char_defs.items():
                if char_id not in original_char_ids:
                    # This was a generated character - restore it to story.characters
                    generated_char = Character(**char_data)
                    if story.characters is None:
                        story.characters = []
                    story.characters.append(generated_char)
                    logger.info(f"Restored generated character '{char_id}' from save")

        # Restore dynamically created nodes (nodes in save but not in original story)
        saved_node_defs = diff.get("all_node_definitions", {})
        if saved_node_defs:
            for node_id, node_data in saved_node_defs.items():
                if node_id not in game_state.nodes:
                    game_state.nodes[node_id] = StoryNode(**node_data)
                    logger.info(f"Restored generated node '{node_id}' from save")

        # Restore dynamically added actions on existing nodes
        saved_dynamic_actions = diff.get("dynamic_actions", {})
        if saved_dynamic_actions:
            for node_id, actions_data in saved_dynamic_actions.items():
                node = game_state.nodes.get(node_id)
                if not node:
                    continue
                existing_action_ids = {a.id for a in (node.actions or [])}
                for action_data in actions_data:
                    action = StoryAction(**action_data)
                    if action.id not in existing_action_ids:
                        if node.actions is None:
                            node.actions = []
                        node.actions.append(action)
                        logger.info(f"Restored dynamic action '{action.id}' on node '{node_id}' from save")

        game_state.ensure_save_metadata()

        game_state.created_at = data.get("created_at", datetime.now().isoformat())
        game_state.updated_at = data.get("updated_at", game_state.created_at)
        game_state.version = data.get("version", 0)

        return game_state

    def save_game(self, save_path: str) -> None:
        """
        Save the current game state to a file.

        Args:
            save_path: Path where to save the game state
        """
        import json
        import os

        # Ensure the saves directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Save the game state
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    def load_game(self, save_path: str) -> None:
        """
        Load game state from a file.

        Args:
            save_path: Path to the save file

        Raises:
            FileNotFoundError: If the save file doesn't exist
            ValueError: If the save file is invalid or story ID doesn't match
        """
        import json
        with open(save_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Verify that the save file matches the current story
        if data["story_id"] != self.story.id:
            raise ValueError(f"Save file is for story '{data['story_id']}', but current story is '{self.story.id}'")
        
        # Load the saved state into this instance
        self.current_node_id = data["current_node_id"]
        self.current_node = self.story.get_node(self.current_node_id)
        if not self.current_node:
            raise ValueError(f"Invalid node ID in save file: {self.current_node_id}")
            
        self.variables = data["variables"]
        self.history = data["history"]
        self.visited_nodes = data["visited_nodes"]
        self.created_at = data.get("created_at", datetime.now().isoformat())
        self.updated_at = data.get("updated_at", self.created_at)
        self.timed_events = data.get("timed_events", [])
        self.runtime_connections = data.get("runtime_connections", [])

    def reset_game(self) -> None:
        """
        Reset the game state to its initial state.
        """
        self.current_node_id = self.story.start_node_id or "start"
        self.current_node = self.story.get_node(self.current_node_id)
        if not self.current_node:
            raise ValueError(f"Invalid start node ID: {self.current_node_id}")
            
        self.variables = {}
        self.variables["players"] = {}
        self.history = []
        self.visited_nodes = []
        self.timed_events = []
        self.runtime_connections = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.version = 0
        self.last_modified_by = None
        
        # Reset character states from story definition
        self.character_states = {}
        if self.story.characters:
            for char in self.story.characters:
                self.character_states[char.id] = {
                    'explicit_state': char.explicit_state,
                    'implicit_state': char.implicit_state,
                    'memory': list(char.memory),
                    'properties': dict(char.properties),
                }
        
        # Reset object states from story definition
        self.object_states = {}
        self._init_object_states_from_story(self.story)

    def _inventory_entry_to_id(self, item_ref: Any) -> Optional[str]:
        """Normalize a mixed inventory entry to a stable object ID string."""
        if isinstance(item_ref, str):
            return item_ref
        if isinstance(item_ref, dict):
            item_id = item_ref.get("id")
            return str(item_id) if item_id else None
        item_id = getattr(item_ref, "id", None)
        return str(item_id) if item_id else None

    def _normalize_inventory_entries(self, inventory: Optional[List[Any]]) -> List[str]:
        """Normalize inventory entries to plain object ID strings."""
        normalized: List[str] = []
        for item_ref in inventory or []:
            item_id = self._inventory_entry_to_id(item_ref)
            if item_id:
                normalized.append(item_id)
        return normalized

    def resolve_inventory_object(self, item_ref: Any) -> Optional[StoryObject]:
        """Resolve an inventory entry to its object definition when possible."""
        item_id = self._inventory_entry_to_id(item_ref)
        if not item_id or not self.story:
            return None
        return self.story.get_object(item_id) or self.find_object_in_world(item_id)

    def get_player_inventory(self, player_id: str = "default") -> List[str]:
        """Get the inventory for a player's controlled character as object IDs."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id and char_id in self.character_states:
            char_props = self.character_states[char_id].get('properties', {})
            inventory = char_props.setdefault('inventory', [])
            normalized = self._normalize_inventory_entries(inventory)
            if normalized != inventory:
                char_props['inventory'] = normalized
            return char_props['inventory']
        return []

    def get_player_inventory_objects(self, player_id: str = "default") -> List[StoryObject]:
        """Resolve a player's inventory IDs to story object definitions."""
        resolved: List[StoryObject] = []
        for item_id in self.get_player_inventory(player_id):
            obj = self.resolve_inventory_object(item_id)
            if obj:
                resolved.append(obj)
        return resolved

    def get_player_status(self, player_id: str) -> List[str]:
        """Get status tags for a player's controlled character."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id:
            return self.get_character_status(char_id)
        return []

    def get_player_explicit_state(self, player_id: str) -> str:
        """Get the current explicit_state for a player's controlled character."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id:
            char_state = self.character_states.get(char_id, {})
            story_character = self.story.get_character(char_id) if self.story else None
            return char_state.get("explicit_state", story_character.explicit_state if story_character else "")
        return ""
    
    def set_player_inventory(self, player_id: str, inventory: List[Any]) -> None:
        """Set the inventory for a player's controlled character."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id and char_id in self.character_states:
            normalized = self._normalize_inventory_entries(inventory)
            self.character_states[char_id].setdefault('properties', {})['inventory'] = normalized
    
    def get_player_location(self, player_id: str) -> Optional[str]:
        """Get the location of a player's controlled character."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id and char_id in self.character_states:
            char_props = self.character_states[char_id].get('properties', {})
            if 'location' in char_props:
                return char_props['location']
        player_data = self.variables.get('players', {}).get(player_id, {})
        if player_data.get('location'):
            return player_data['location']
        return self.current_node_id or self.story.start_node_id
    
    def set_player_location(self, player_id: str, location: str) -> None:
        """Set the location for a player's controlled character."""
        char_id = self.get_controlled_character_id(player_id)
        if char_id and char_id in self.character_states:
            self.character_states[char_id].setdefault('properties', {})['location'] = location
        if player_id in self.variables.get('players', {}):
            self.variables['players'][player_id]['location'] = location

    def find_object_in_world(self, object_id: str) -> Any:
        """Find an object in any node in the current game state."""
        for node in self.nodes.values():
            for obj in node.objects:
                if obj.id == object_id:
                    return obj
        return None

    def get_object_location_id(self, object_id: str) -> Optional[str]:
        """Return the node ID currently containing an object, if any."""
        for node in self.nodes.values():
            for obj in node.objects:
                if obj.id == object_id:
                    return node.id
        return None
    
    def find_object_anywhere(self, object_id: str) -> Any:
        """Find an object in nodes or any player's inventory."""
        # Check nodes first
        obj = self.find_object_in_world(object_id)
        if obj:
            return obj
        
        # Check all player inventories
        for player_id in self.variables.get('players', {}):
            for item_id in self.get_player_inventory(player_id):
                if item_id == object_id:
                    return self.resolve_inventory_object(item_id)
        
        return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Object State Management
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_object_state(self, object_id: str) -> Optional[Dict[str, Any]]:
        """Get the runtime state for an object.
        
        Returns dict with: explicit_state, implicit_state, properties
        """
        return self.object_states.get(object_id)
    
    def get_object_explicit_state(self, object_id: str) -> str:
        """Get an object's current explicit_state."""
        state = self.object_states.get(object_id, {})
        return state.get('explicit_state', '')
    
    def set_object_explicit_state(self, object_id: str, explicit_state: str) -> bool:
        """Set an object's explicit_state.
        
        Updates both the runtime state and the actual object.
        Returns True if successful.
        """
        # Initialize state if not exists
        if object_id not in self.object_states:
            self.object_states[object_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'properties': {'status': []}
            }
        
        self.object_states[object_id]['explicit_state'] = explicit_state
        
        # Also update the actual object for consistency
        obj = self.find_object_anywhere(object_id)
        if obj:
            obj.explicit_state = explicit_state
        
        self._mark_world_changed()
        logger.debug(f"Set explicit_state for object '{object_id}': {explicit_state[:50]}...")
        return True
    
    def get_object_implicit_state(self, object_id: str) -> str:
        """Get an object's current implicit_state (hidden state)."""
        state = self.object_states.get(object_id, {})
        return state.get('implicit_state', '')
    
    def set_object_implicit_state(self, object_id: str, implicit_state: str) -> bool:
        """Set an object's implicit_state (hidden state).
        
        Returns True if successful.
        """
        if object_id not in self.object_states:
            self.object_states[object_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'properties': {'status': []}
            }
        
        self.object_states[object_id]['implicit_state'] = implicit_state
        
        # Also update the actual object if it has implicit_state attribute
        obj = self.find_object_anywhere(object_id)
        if obj and hasattr(obj, 'implicit_state'):
            obj.implicit_state = implicit_state
        
        logger.debug(f"Set implicit_state for object '{object_id}': {implicit_state[:50]}...")
        return True
    
    def get_object_property(self, object_id: str, key: str, default: Any = None) -> Any:
        """Get a property value for an object.
        
        Supports dot notation for nested properties.
        """
        state = self.object_states.get(object_id, {})
        properties = state.get('properties', {})
        
        # Handle dot notation
        if '.' in key:
            parts = key.split('.')
            value = properties
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value
        
        return properties.get(key, default)
    
    def set_object_property(self, object_id: str, key: str, value: Any) -> bool:
        """Set a property value for an object.
        
        Supports dot notation for nested properties.
        Returns True if successful.
        """
        if object_id not in self.object_states:
            self.object_states[object_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'properties': {'status': []}
            }
        
        properties = self.object_states[object_id]['properties']
        
        # Handle dot notation
        if '.' in key:
            parts = key.split('.')
            current = properties
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            properties[key] = value
        
        logger.debug(f"Set property '{key}' for object '{object_id}': {value}")
        return True
    
    def update_object_status(self, object_id: str,
                             add_status: list = None,
                             remove_status: list = None) -> Any:
        """Update an object's status tags.
        
        Updates both the runtime state (object_states) and the actual object.
        
        Args:
            object_id: The object to update
            add_status: Status tags to add
            remove_status: Status tags to remove
            
        Returns:
            The updated object, or None if not found
        """
        # Initialize state if not exists
        if object_id not in self.object_states:
            self.object_states[object_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'properties': {'status': []}
            }
        
        properties = self.object_states[object_id]['properties']
        if 'status' not in properties:
            properties['status'] = []
        
        status = properties['status']
        
        # Remove status tags
        if remove_status:
            properties['status'] = [s for s in status if s not in remove_status]
        
        # Add status tags
        if add_status:
            for s in add_status:
                if s not in properties['status']:
                    properties['status'].append(s)
        
        # Also update the actual object for consistency
        obj = self.find_object_anywhere(object_id)
        if obj:
            # Update object's properties if it has them
            if hasattr(obj, 'properties') and isinstance(obj.properties, dict):
                obj.properties['status'] = list(properties['status'])
        
        self._mark_world_changed()
        logger.debug(f"Updated status for object '{object_id}': {properties['status']}")
        return obj
    
    def get_object_status(self, object_id: str) -> List[str]:
        """Get an object's current status tags."""
        return self.get_object_property(object_id, 'status', [])

    def get_effective_object_status(self, object_ref: Any) -> List[str]:
        """Get runtime-aware status tags for an object or object ID."""
        object_id = object_ref if isinstance(object_ref, str) else getattr(object_ref, "id", None)
        if not object_id:
            return []
        runtime_status = self.get_object_status(object_id)
        if runtime_status:
            return runtime_status
        obj = self.find_object_anywhere(object_id)
        if obj and hasattr(obj, "get_status"):
            return list(obj.get_status())
        return []

    def is_object_visible(self, object_ref: Any) -> bool:
        """Check whether an object should currently be visible."""
        obj = object_ref if hasattr(object_ref, "id") else self.find_object_anywhere(object_ref)
        if not obj:
            return False
        status = self.get_effective_object_status(obj)
        return "hidden" not in status
    
    def object_has_status(self, object_id: str, status: str) -> bool:
        """Check if an object has a specific status tag."""
        return status in self.get_object_status(object_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # Character State Management
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_character_state(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Get the runtime state for a character.
        
        Returns dict with: explicit_state, implicit_state, memory, properties
        """
        return self.character_states.get(character_id)
    
    def get_character_explicit_state(self, character_id: str) -> str:
        """Get a character's current explicit_state."""
        state = self.character_states.get(character_id, {})
        return state.get('explicit_state', '')
    
    def set_character_explicit_state(self, character_id: str, explicit_state: str) -> bool:
        """Set a character's explicit_state.
        
        Returns True if successful, False if character not found.
        """
        if character_id not in self.character_states:
            # Initialize state for this character
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {}
            }
        
        self.character_states[character_id]['explicit_state'] = explicit_state
        self._mark_world_changed()
        logger.debug(f"Set explicit_state for character '{character_id}': {explicit_state[:50]}...")
        return True
    
    def get_character_implicit_state(self, character_id: str) -> str:
        """Get a character's current implicit_state (hidden state)."""
        state = self.character_states.get(character_id, {})
        return state.get('implicit_state', '')
    
    def set_character_implicit_state(self, character_id: str, implicit_state: str) -> bool:
        """Set a character's implicit_state (hidden state).
        
        Returns True if successful.
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {}
            }
        
        self.character_states[character_id]['implicit_state'] = implicit_state
        self._mark_world_changed()
        logger.debug(f"Set implicit_state for character '{character_id}': {implicit_state[:50]}...")
        return True
    
    def get_character_memory(self, character_id: str) -> List[str]:
        """Get a character's memory list."""
        state = self.character_states.get(character_id, {})
        return state.get('memory', [])
    
    def add_character_memory(self, character_id: str, memory_entry: str) -> bool:
        """Add a memory entry to a character's memory.
        
        Returns True if successful.
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {}
            }
        
        self.character_states[character_id]['memory'].append(memory_entry)
        self._mark_world_changed()
        logger.debug(f"Added memory for character '{character_id}': {memory_entry[:50]}...")
        return True
    
    def get_character_property(self, character_id: str, key: str, default: Any = None) -> Any:
        """Get a property value for a character.
        
        Supports dot notation for nested properties (e.g., 'stats.hp').
        """
        state = self.character_states.get(character_id, {})
        properties = state.get('properties', {})
        
        # Handle dot notation
        if '.' in key:
            parts = key.split('.')
            value = properties
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value
        
        return properties.get(key, default)
    
    def set_character_property(self, character_id: str, key: str, value: Any) -> bool:
        """Set a property value for a character.
        
        Supports dot notation for nested properties.
        Returns True if successful.
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {}
            }
        
        properties = self.character_states[character_id]['properties']
        
        # Handle dot notation
        if '.' in key:
            parts = key.split('.')
            current = properties
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            properties[key] = value
        
        self._mark_world_changed()
        logger.debug(f"Set property '{key}' for character '{character_id}': {value}")
        return True

    def modify_character_property(self, character_id: str, key: str, operation: str, value: Any,
                                  minimum: Optional[float] = None,
                                  maximum: Optional[float] = None) -> Any:
        """Apply an arithmetic update to a character property and return the new value."""
        current_value = self.get_character_property(character_id, key, 0)
        if current_value is None:
            current_value = 0

        try:
            current_num = float(current_value)
        except (TypeError, ValueError):
            current_num = 0.0

        try:
            operand_num = float(value)
        except (TypeError, ValueError):
            operand_num = 0.0

        if operation == "add":
            new_value = current_num + operand_num
        elif operation == "subtract":
            new_value = current_num - operand_num
        elif operation == "multiply":
            new_value = current_num * operand_num
        elif operation == "divide":
            new_value = current_num / operand_num if operand_num != 0 else current_num
        elif operation == "set":
            new_value = operand_num
        else:
            raise ValueError(f"Unsupported operation '{operation}'")

        if minimum is not None:
            new_value = max(minimum, new_value)
        if maximum is not None:
            new_value = min(maximum, new_value)

        if isinstance(current_value, int) and new_value.is_integer():
            stored_value = int(new_value)
        else:
            stored_value = new_value

        self.set_character_property(character_id, key, stored_value)
        return stored_value
    
    def update_character_status(self, character_id: str, 
                                add_status: List[str] = None,
                                remove_status: List[str] = None) -> bool:
        """Update a character's status tags.
        
        Args:
            character_id: The character to update
            add_status: Status tags to add
            remove_status: Status tags to remove
            
        Returns:
            True if successful, False if character not found.
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {'status': []}
            }
        
        properties = self.character_states[character_id]['properties']
        if 'status' not in properties:
            properties['status'] = []
        
        status = properties['status']
        
        # Remove status tags
        if remove_status:
            properties['status'] = [s for s in status if s not in remove_status]
        
        # Add status tags
        if add_status:
            for s in add_status:
                if s not in properties['status']:
                    properties['status'].append(s)
        
        self._mark_world_changed()
        logger.debug(f"Updated status for character '{character_id}': {properties['status']}")
        return True
    
    def get_character_status(self, character_id: str) -> List[str]:
        """Get a character's current status tags."""
        return self.get_character_property(character_id, 'status', [])
    
    def character_has_status(self, character_id: str, status: str) -> bool:
        """Check if a character has a specific status tag."""
        return status in self.get_character_status(character_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # Character Location Management (Single Source of Truth)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_character_location(self, character_id: str) -> Optional[str]:
        """
        Get a character's current location (node_id).
        
        The character's location is stored in character_states[char_id].properties.location.
        This is the single source of truth for character locations.
        
        Args:
            character_id: The character's ID
            
        Returns:
            The node_id where the character is, or None if not set
        """
        state = self.character_states.get(character_id, {})
        return state.get('properties', {}).get('location')
    
    def set_character_location(self, character_id: str, node_id: str) -> bool:
        """
        Set a character's location.
        
        This is the single source of truth for character locations.
        Use this method to move characters between nodes.
        
        Args:
            character_id: The character's ID
            node_id: The node_id to move the character to
            
        Returns:
            True if successful
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = {
                'explicit_state': '',
                'implicit_state': '',
                'memory': [],
                'properties': {}
            }
        
        self.character_states[character_id].setdefault('properties', {})['location'] = node_id
        
        self.character_locations[character_id] = node_id
        
        logger.debug(f"Set location for character '{character_id}' to '{node_id}'")
        return True
    
    def move_character_to_node(self, character_id: str, node_id: str) -> bool:
        """
        Move a character to a node.
        
        Alias for set_character_location() with a more descriptive name.
        
        Args:
            character_id: The character's ID
            node_id: The node_id to move the character to
            
        Returns:
            True if successful
        """
        return self.set_character_location(character_id, node_id)
    
    def get_characters_in_node(self, node_id: str) -> List[str]:
        """
        Get all characters currently in a node.
        
        This is derived from the single source of truth (character locations).
        
        Args:
            node_id: The node_id to check
            
        Returns:
            List of character IDs in the node
        """
        return [
            char_id for char_id, state in self.character_states.items()
            if state.get('properties', {}).get('location') == node_id
        ]
    
    def get_npcs_in_node(self, node_id: str) -> List[str]:
        """
        Get all NPCs (non-player characters) currently in a node.
        
        Excludes characters that are currently controlled by players.
        
        Args:
            node_id: The node_id to check
            
        Returns:
            List of NPC character IDs in the node
        """
        controlled_chars = set()
        for player_data in self.variables.get('players', {}).values():
            char_id = player_data.get('controlled_character_id')
            if char_id:
                controlled_chars.add(char_id)
        
        # Return characters in node that are not controlled by players
        return [
            char_id for char_id in self.get_characters_in_node(node_id)
            if char_id not in controlled_chars
        ]
    
    def is_character_in_node(self, character_id: str, node_id: str) -> bool:
        """
        Check if a character is in a specific node.
        
        Args:
            character_id: The character's ID
            node_id: The node_id to check
            
        Returns:
            True if the character is in the node
        """
        return self.get_character_location(character_id) == node_id

    def add_to_inventory(self, player_id: str, item_id: str):
        """Moves an item from a node to the player's inventory."""
        player_inventory = self.get_player_inventory(player_id)
        
        # Find the object in the world
        obj_to_take = None
        node_to_remove_from = None
        for node in self.nodes.values():
            for obj in node.objects:
                if obj.id == item_id:
                    obj_to_take = obj
                    node_to_remove_from = node
                    break
            if obj_to_take:
                break
        
        if obj_to_take and node_to_remove_from:
            logger.debug(f"GameState.add_to_inventory: Moving StoryObject '{obj_to_take.id}' to player '{player_id}' inventory.")
            node_to_remove_from.objects.remove(obj_to_take)
            player_inventory.append(obj_to_take.id)
            self.version += 1
            self.last_modified_by = player_id
            self.updated_at = datetime.now().isoformat()
            logger.info(f"Moved object '{item_id}' from node '{node_to_remove_from.id}' to player '{player_id}' inventory.")
        else:
            logger.warning(f"Could not find object '{item_id}' to add to inventory for player '{player_id}'.")

    def add_item(self, item_name: str, player_id: str = "default") -> bool:
        """
        Add an item to the shared world inventory (for multiplayer).

        Args:
            item_name: The name of the item to add
            player_id: The ID of the player taking the item

        Returns:
            bool: True if item was added, False if item already exists
        """
        player_inventory = self.get_player_inventory(player_id)
        if item_name not in player_inventory:
            player_inventory.append(item_name)

        # Update version and timestamps
        self.version += 1
        self.last_modified_by = player_id
        self.updated_at = datetime.now().isoformat()
        return True

    def remove_item(self, item_name: str, player_id: str = "default") -> bool:
        """
        Remove an item from a player's inventory.

        Args:
            item_name: The name of the item to remove
            player_id: The ID of the player losing the item

        Returns:
            bool: True if item was removed, False if item wasn't found
        """
        try:
            inventory = self.get_player_inventory(player_id)
            if item_name in inventory:
                inventory.remove(item_name)
            else:
                lowered = item_name.lower()
                matching_item_id = next(
                    (
                        item_id for item_id in inventory
                        if item_id.lower() == lowered
                        or (
                            (obj := self.resolve_inventory_object(item_id)) is not None
                            and obj.name.lower() == lowered
                        )
                    ),
                    None,
                )
                if matching_item_id is None:
                    return False
                inventory.remove(matching_item_id)
            # Update version and timestamps
            self.version += 1
            self.last_modified_by = player_id
            self.updated_at = datetime.now().isoformat()
            return True
        except ValueError:
            return False

    def get_current_node(self, player_id: str) -> 'StoryNode':
        """Get the current node for a given player."""
        player_location = self.get_player_location(player_id)
        return self.nodes.get(player_location)
    
    def get_current_node_id(self, player_id: str) -> Optional[str]:
        """Get the current node ID for a given player."""
        return self.get_player_location(player_id)

    def transfer_item(self, item_name: str, sender_id: str, recipient_id: str) -> bool:
        """
        Transfer an item from one player to another.
        """
        sender_inventory = self.get_player_inventory(sender_id)
        lowered = item_name.lower()
        item_to_transfer = next(
            (
                item_id for item_id in sender_inventory
                if item_id.lower() == lowered
                or (
                    (obj := self.resolve_inventory_object(item_id)) is not None
                    and obj.name.lower() == lowered
                )
            ),
            None,
        )

        if item_to_transfer is None:
            logger.error(f"Item '{item_name}' not found in sender's inventory.")
            return False

        recipient_inventory = self.get_player_inventory(recipient_id)
        sender_inventory.remove(item_to_transfer)
        recipient_inventory.append(item_to_transfer)
        
        self.version += 1
        self.last_modified_by = sender_id
        self.updated_at = datetime.now().isoformat()
        logger.info(f"Transferred item '{item_name}' from player '{sender_id}' to '{recipient_id}'.")
        return True

    def has_item(self, item: str, owner: str = "player") -> bool:
        """
        Check if the specified owner has the given item in their inventory.
        For shared world, checks the global inventory.
        Args:
            item: The item to check
            owner: The inventory owner (default: 'player')
        Returns:
            bool: True if the item is in the inventory, False otherwise
        """
        normalized_item = str(item)
        if owner == "player":
            return self.has_item(normalized_item, owner="player:default")
        elif owner.startswith("npc:"):
            npc_id = owner[4:]
            inventory = self.variables.get("npcs", {}).get(npc_id, {}).get("inventory", [])
            return normalized_item in self._normalize_inventory_entries(inventory)
        elif owner.startswith("player:"):
            player_id = owner[7:]
            for item_id in self.get_player_inventory(player_id):
                if item_id == normalized_item:
                    return True
                obj = self.resolve_inventory_object(item_id)
                if obj and obj.name.lower() == normalized_item.lower():
                    return True
        return False

class _DerivedVarLuaRuntime:
    """
    Lightweight Lua runtime for evaluating derived variable expressions.
    
    This is a standalone runtime that doesn't require GameKernel,
    used specifically for computed/derived variables with $lua: prefix.
    
    Example usage in initial_variables:
        initial_variables:
          base_attack: 10
          weapon_bonus: 5
          strength: 14
          effective_attack: "$lua: base_attack + weapon_bonus + math.floor(strength / 2)"
    """
    
    def __init__(self):
        try:
            from lupa import LuaRuntime
            import lupa
            self.lupa = lupa
            self.lua = LuaRuntime(unpack_returned_tuples=True)
        except ImportError:
            logger.warning("lupa not installed, derived variables will not work")
            self.lua = None
            self.lupa = None
    
    def evaluate_expression(self, expression: str, game_state: 'GameState', player_id: str = "default") -> Any:
        """
        Evaluate a Lua expression and return the result.
        
        The expression has access to all game variables as global Lua variables.
        
        Args:
            expression: A Lua expression string (e.g., "base_attack + weapon_bonus")
            game_state: The current game state
            player_id: The player ID for context
            
        Returns:
            The evaluated result (number, string, bool, or dict/list)
        """
        if self.lua is None:
            logger.warning("Lua runtime not available for derived variable evaluation")
            return None
        
        lua_globals = self.lua.globals()
        
        # Expose variables as Lua globals for easy access
        for key, value in game_state.variables.items():
            if key == 'players':
                # Handle players specially to avoid issues
                continue
            if isinstance(value, str) and value.startswith(DERIVED_VAR_PREFIX):
                # Skip other derived variables to prevent issues
                continue
            try:
                if isinstance(value, dict):
                    lua_globals[key] = self.lua.table_from(value)
                elif isinstance(value, list):
                    lua_globals[key] = self.lua.table_from(value)
                else:
                    lua_globals[key] = value
            except Exception as e:
                logger.debug(f"Could not expose variable '{key}' to Lua: {e}")
        
        # Expose player character data via pointer model
        if player_id:
            lua_globals['player_id'] = player_id
            char_id = game_state.get_controlled_character_id(player_id)
            if char_id and char_id in game_state.character_states:
                char_state = game_state.character_states[char_id]
                try:
                    char_dict = {k: v for k, v in char_state.items() if isinstance(v, (str, int, float, bool, list, dict))}
                    lua_globals['player_character'] = self.lua.table_from(char_dict)
                    stats = char_state.get('properties', {}).get('stats', {})
                    if stats:
                        lua_globals['player_stats'] = self.lua.table_from(stats)
                except Exception:
                    pass
        
        # Wrap expression in return statement
        wrapped_script = f"return ({expression})"
        
        try:
            result = self.lua.execute(wrapped_script)
            
            # Convert Lua table back to Python
            if self.lupa.lua_type(result) == 'table':
                return self._lua_table_to_python(result)
            
            return result
        except Exception as e:
            logger.warning(f"Failed to evaluate derived variable expression '{expression}': {e}")
            return None
    
    def _lua_table_to_python(self, lua_obj) -> Any:
        """Convert a Lua table to Python dict or list."""
        if self.lupa.lua_type(lua_obj) != 'table':
            return lua_obj
        
        # Check if array-like (sequential integer keys starting at 1)
        is_array = True
        max_index = 0
        for k, v in lua_obj.items():
            if not isinstance(k, int) or k < 1:
                is_array = False
                break
            max_index = max(max_index, k)
        
        if is_array and max_index > 0:
            result = [None] * max_index
            for k, v in lua_obj.items():
                result[k - 1] = self._lua_table_to_python(v)
            return result
        else:
            result = {}
            for k, v in lua_obj.items():
                result[k] = self._lua_table_to_python(v)
            return result
