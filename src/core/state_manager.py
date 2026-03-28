"""
State Manager for the AI Native game engine.

This module implements the state manager that handles game state persistence,
including saving and loading game states.
"""
from typing import List, Dict, Optional, Any, Union

# Import GameState at the top of the file
from src.models.game_state import GameState
import copy
import os
import json
import uuid
import shutil
import threading
from datetime import datetime
import logging
import re

from src.models.story_models import Story

logger = logging.getLogger(__name__)
SAVE_CODE_PATTERN = re.compile(r"^[A-Z0-9]{8}$")

class StateManager:
    """Manages game state persistence and loading."""
    
    def __init__(self, save_dir: str):
        """Initialize a new state manager.

        Args:
            save_dir (str): Directory to use for saving game states.
        """
        self.save_dir = save_dir
        self.lock = threading.Lock()
        self.active_states = {}  # type: Dict[str, GameState]
        self.observers = {}  # type: Dict[str, List[callable]]
        
        # Create save directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)
        
        logger.info(f"State manager initialized with save directory: {save_dir}")

    def _sanitize_filename_part(self, value: Optional[str]) -> str:
        """Create a filesystem-safe filename segment."""
        raw = (value or "unknown").strip()
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
        return sanitized or "unknown"

    def _is_state_payload(self, data: Any) -> bool:
        """Return True when a JSON blob looks like a save payload."""
        return isinstance(data, dict) and "story_id" in data and ("diff" in data or "variables" in data)

    def _read_json_file(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as exc:
            logger.error(f"Failed to read JSON file {path}: {exc}")
            return None

    def _iter_save_payloads(self) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        for filename in os.listdir(self.save_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.save_dir, filename)
            data = self._read_json_file(path)
            if not self._is_state_payload(data):
                continue
            payloads.append({"filename": filename, "path": path, "state": data})
        return payloads

    def _extract_save_metadata(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return state.get("save_metadata") or {}

    def _extract_participant_names(self, state: Dict[str, Any]) -> List[str]:
        metadata = self._extract_save_metadata(state)
        participant_names = metadata.get("participant_names")
        if participant_names:
            return [name for name in participant_names if name]

        participants = metadata.get("participant_manifest", [])
        if participants:
            return [entry.get("name") for entry in participants if entry.get("name")]

        fallback_name = state.get("player_name")
        return [fallback_name] if fallback_name else []

    def _matches_save_filters(
        self,
        state: Dict[str, Any],
        player_name: Optional[str] = None,
        story_id: Optional[str] = None,
    ) -> bool:
        if story_id and state.get("story_id") != story_id:
            return False
        if player_name:
            participant_names = self._extract_participant_names(state)
            if player_name not in participant_names:
                return False
        return True

    def _build_save_listing(self, state: Dict[str, Any], filename: str) -> Dict[str, Any]:
        metadata = self._extract_save_metadata(state)
        participant_names = self._extract_participant_names(state)
        diff = state.get("diff", state)
        return {
            "filename": filename,
            "id": state.get("id"),
            "story_id": state.get("story_id"),
            "player_name": participant_names[0] if participant_names else state.get("player_name"),
            "participant_names": participant_names,
            "slot_id": metadata.get("slot_id"),
            "save_code": state.get("save_code") or metadata.get("save_code", ""),
            "updated_at": state.get("updated_at", ""),
            "created_at": state.get("created_at", ""),
            "current_node": state.get("current_node") or diff.get("current_node"),
        }

    def _resolve_save_path_by_code(self, save_code: str) -> Optional[str]:
        if not save_code or not SAVE_CODE_PATTERN.match(save_code):
            return None

        code_mapping_path = os.path.join(self.save_dir, f"savecode-{save_code}.json")
        mapping_data = self._read_json_file(code_mapping_path)
        if mapping_data:
            save_filename = mapping_data.get("save_filename")
            if save_filename:
                save_path = os.path.join(self.save_dir, save_filename)
                if os.path.exists(save_path):
                    return save_path

        for payload in self._iter_save_payloads():
            state = payload["state"]
            metadata = self._extract_save_metadata(state)
            state_save_code = state.get("save_code") or metadata.get("save_code")
            if state_save_code == save_code:
                return payload["path"]

            filename = payload["filename"]
            if filename.endswith(f"-{save_code}.json"):
                return payload["path"]
        return None

    def get_active_state(self, state_id: str) -> Optional[GameState]:
        """Get an active game state from memory.
        
        Args:
            state_id (str): The ID of the state to retrieve
            
        Returns:
            Optional[GameState]: The active game state, or None if not found
        """
        with self.lock:
            return self.active_states.get(state_id)

    def set_active_state(self, state_id: str, state: GameState) -> None:
        """Set an active game state in memory.
        
        Args:
            state_id (str): The ID of the state
            state (GameState): The game state to cache
        """
        with self.lock:
            self.active_states[state_id] = state

    def add_observer(self, state_id: str, callback: callable) -> None:
        """Add a state change observer.
        
        Args:
            state_id (str): The state ID to observe
            callback (callable): Function to call on state changes
        """
        with self.lock:
            if state_id not in self.observers:
                self.observers[state_id] = []
            self.observers[state_id].append(callback)

    def remove_observer(self, state_id: str, callback: callable) -> None:
        """Remove a state change observer.
        
        Args:
            state_id (str): The observed state ID
            callback (callable): Function to remove
        """
        with self.lock:
            if state_id in self.observers:
                try:
                    self.observers[state_id].remove(callback)
                except ValueError:
                    pass

    def _notify_observers(self, state_id: str, changes: Dict[str, Any]) -> None:
        """Notify all observers of state changes.
        
        Args:
            state_id (str): The changed state ID
            changes (Dict[str, Any]): The state changes
        """
        with self.lock:
            if state_id in self.observers:
                for callback in self.observers[state_id]:
                    try:
                        callback(changes)
                    except Exception as e:
                        logger.error(f"Observer callback failed: {e}")
    
    def save_game_state(self, game_state):
        """Save a game state object.

        Args:
            game_state: The game state to save, either a GameState object or a dictionary
    
        Returns:
            bool: True if the state was saved successfully, False otherwise.
        """
        # Convert game_state to dictionary if it's a GameState object
        if hasattr(game_state, 'to_dict'):
            state_dict = game_state.to_dict()
        else:
            state_dict = game_state
    
        return self.save_state(state_dict)
    
    def load_game_state(self, state_id: str, story: Story, expected_version: Optional[int] = None) -> Optional[GameState]:
        """Load a GameState object by ID.
        
        Args:
            state_id (str): The ID of the state to load.
            story (Story): The Story object for this game state.
            expected_version (Optional[int]): Expected state version for consistency check.
            
        Returns:
            Optional[GameState]: The loaded game state, or None if not found or version mismatch.
        """
        state_dict = self.load_state(state_id, expected_version)
        if state_dict:
            return GameState.from_dict(state_dict, story)
        return None
    
    def save_state(self, state: Dict[str, Any]) -> str:
        """Save the current game state.
        
        Args:
            state (Dict[str, Any]): The game state to save.
            
        Returns:
            str: The save code for the saved state
        """
        try:
            state_id = state.get("id")
            player_name = state.get("player_name")
            story_id = state.get("story_id")
            save_metadata = copy.deepcopy(state.get("save_metadata") or {})
            
            if not state_id:
                logger.error("State ID is required")
                return ""
            
            # Generate a unique save code
            save_code = str(uuid.uuid4())[:8].upper()
            
            slot_id = save_metadata.get("slot_id") or state_id
            save_metadata["slot_id"] = slot_id
            save_metadata["save_code"] = save_code
            save_metadata["updated_at"] = datetime.now().isoformat()
            save_metadata["participant_names"] = save_metadata.get("participant_names") or ([player_name] if player_name else [])

            # Create save file name with slot identity, not mutable player names
            save_filename = f"slot-{self._sanitize_filename_part(slot_id)}-{save_code}.json"
            
            # Update timestamp
            state["updated_at"] = datetime.now().isoformat()
            state["save_code"] = save_code
            state["save_metadata"] = save_metadata
            
            # Remove nodes from the state to save space (they're loaded from the story)
            if "nodes" in state:
                del state["nodes"]
            
            # Create save file path
            save_path = os.path.join(self.save_dir, save_filename)
            
            # Write state to file
            with open(save_path, "w") as f:
                json.dump(state, f, indent=2)
            
            # Also save a mapping file that maps state_id to save_code
            mapping_filename = f"{state_id}.json"
            mapping_path = os.path.join(self.save_dir, mapping_filename)
            mapping_data = {
                "state_id": state_id,
                "slot_id": slot_id,
                "save_code": save_code,
                "save_filename": save_filename,
                "created_at": datetime.now().isoformat()
            }
            with open(mapping_path, "w") as f:
                json.dump(mapping_data, f, indent=2)

            code_mapping_path = os.path.join(self.save_dir, f"savecode-{save_code}.json")
            with open(code_mapping_path, "w") as f:
                json.dump(mapping_data, f, indent=2)
            
            # Update in-memory state
            self.set_active_state(state_id, state)
            
            # Notify observers of changes
            self._notify_observers(state_id, state)
            
            logger.info(f"Saved state: {state_id} with code: {save_code}")
            return save_code
            
        except Exception as e:
            logger.error(f"Error saving state: {e}", exc_info=True)
            return ""
    
    def load_state(self, state_id: str, expected_version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Load a game state by ID.
        
        Args:
            state_id (str): The ID of the state to load.
            expected_version (Optional[int]): Expected state version for consistency check.
            
        Returns:
            Optional[Dict[str, Any]]: The loaded game state, or None if not found or version mismatch.
        """
        try:
            # First check in-memory cache
            cached_state = self.get_active_state(state_id)
            if cached_state:
                if expected_version is not None and cached_state.get("version") != expected_version:
                    logger.warning(f"State version mismatch for {state_id}")
                    return None
                logger.info(f"Loaded state from cache: {state_id}")
                return cached_state
            
            # Look for mapping file first
            mapping_path = os.path.join(self.save_dir, f"{state_id}.json")
            
            # Check if mapping file exists
            if not os.path.exists(mapping_path):
                logger.error(f"Mapping file not found: {mapping_path}")
                return None
            
            # Read mapping file
            with open(mapping_path, "r") as f:
                mapping_data = json.load(f)
            
            # Get the actual save file name
            save_filename = mapping_data.get("save_filename")
            if not save_filename:
                logger.error(f"Invalid mapping file: {mapping_path}")
                return None
            
            # Create save file path
            save_path = os.path.join(self.save_dir, save_filename)
            
            # Check if save file exists
            if not os.path.exists(save_path):
                logger.error(f"Save file not found: {save_path}")
                return None
            
            # Read state from file
            with open(save_path, "r") as f:
                state = json.load(f)
            
            # Verify version if specified
            if expected_version is not None and state.get("version") != expected_version:
                logger.warning(f"State version mismatch for {state_id}")
                return None
            
            # Cache the loaded state
            self.set_active_state(state_id, state)
            
            logger.info(f"Loaded state from disk: {state_id}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to load state {state_id}: {e}")
            return None
    
    def update_state(self, state_id: str, updates: Dict[str, Any], actor_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Update a game state with new values.
        
        Args:
            state_id (str): The ID of the state to update.
            updates (Dict[str, Any]): The updates to apply.
            actor_id (Optional[str]): ID of the actor making the changes.
            
        Returns:
            Optional[Dict[str, Any]]: The updated game state, or None if not found.
        """
        try:
            # Load existing state
            state = self.load_state(state_id)
            if not state:
                return None
            
            # Apply updates (deep merge)
            self._deep_update(state, updates)
            
            # Update timestamp
            state["updated_at"] = datetime.now().isoformat()
            
            # Save updated state
            self.save_state(state)
            
            logger.info(f"Updated state: {state_id}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to update state {state_id}: {e}")
            return None
    
    def update_game_state(self, state_id: str, updates: Dict[str, Any], story: Story) -> Optional[GameState]:
        """Update a game state with new values and return a GameState object.
        
        Args:
            state_id (str): The ID of the state to update.
            updates (Dict[str, Any]): The updates to apply.
            story (Story): The Story object for this game state.
            
        Returns:
            Optional[GameState]: The updated game state, or None if not found.
        """
        state_dict = self.update_state(state_id, updates)
        if state_dict:
            return GameState.from_dict(state_dict, story)
        return None
    
    def list_saved_states(self, player_name: str = None, story_id: str = None) -> List[Dict[str, Any]]:
        """List all saved game states.
        
        Args:
            player_name (str, optional): Filter by player name
            story_id (str, optional): Filter by story ID
            
        Returns:
            List[Dict[str, Any]]: A list of saved game states metadata.
        """
        try:
            states = []
            for payload in self._iter_save_payloads():
                state = payload["state"]
                if not self._matches_save_filters(state, player_name=player_name, story_id=story_id):
                    continue
                states.append(self._build_save_listing(state, payload["filename"]))
            
            # Sort by updated_at (newest first)
            states.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            
            logger.info(f"Listed {len(states)} saved states")
            return states
            
        except Exception as e:
            logger.error(f"Failed to list saved states: {e}")
            return []
    
    def load_state_by_code(self, save_code: str, player_name: str, story_id: str) -> Optional[Dict[str, Any]]:
        """Load a game state by save code.
        
        Args:
            save_code (str): The save code to load.
            player_name (str): The player name.
            story_id (str): The story ID.
            
        Returns:
            Optional[Dict[str, Any]]: The loaded game state, or None if not found.
        """
        try:
            save_path = self._resolve_save_path_by_code(save_code)
            if not save_path:
                logger.error(f"Save file not found for code: {save_code}")
                return None

            state = self._read_json_file(save_path)
            if not state:
                return None

            if not self._matches_save_filters(state, player_name=player_name, story_id=story_id):
                logger.error(
                    f"Save code {save_code} does not match filters player_name={player_name}, story_id={story_id}"
                )
                return None
            
            # Cache the loaded state
            self.set_active_state(state.get("id"), state)
            
            logger.info(f"Loaded state from disk by code: {save_code}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to load state by code {save_code}: {e}")
            return None
    
    def delete_state(self, state_id: str) -> bool:
        """Delete a saved game state.
        
        Args:
            state_id (str): The ID of the state to delete.
            
        Returns:
            bool: True if the state was deleted successfully, False otherwise.
        """
        try:
            # Create save file path
            save_path = os.path.join(self.save_dir, f"{state_id}.json")
            
            # Check if file exists
            if not os.path.exists(save_path):
                logger.error(f"Save file not found: {save_path}")
                return False
            
            # Delete file
            os.remove(save_path)
            
            logger.info(f"Deleted state: {state_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete state {state_id}: {e}")
            return False
    
    def create_backup(self, backup_dir: str = None) -> bool:
        """Create a backup of all saved states.
        
        Args:
            backup_dir (str, optional): Directory for the backup. Defaults to a timestamped directory.
            
        Returns:
            bool: True if the backup was created successfully, False otherwise.
        """
        try:
            # Create backup directory
            if not backup_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(self.save_dir, f"backup_{timestamp}")
            
            os.makedirs(backup_dir, exist_ok=True)
            
            # Copy all save files to backup directory
            for filename in os.listdir(self.save_dir):
                if filename.endswith(".json"):
                    src_path = os.path.join(self.save_dir, filename)
                    dst_path = os.path.join(backup_dir, filename)
                    shutil.copy2(src_path, dst_path)
            
            logger.info(f"Created backup in {backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    def restore_backup(self, backup_dir: str) -> bool:
        """Restore saved states from a backup.
        
        Args:
            backup_dir (str): Directory containing the backup.
            
        Returns:
            bool: True if the backup was restored successfully, False otherwise.
        """
        try:
            # Check if backup directory exists
            if not os.path.exists(backup_dir):
                logger.error(f"Backup directory not found: {backup_dir}")
                return False
            
            # Create backup of current saves before restoring
            self.create_backup()
            
            # Copy all backup files to save directory
            for filename in os.listdir(backup_dir):
                if filename.endswith(".json"):
                    src_path = os.path.join(backup_dir, filename)
                    dst_path = os.path.join(self.save_dir, filename)
                    shutil.copy2(src_path, dst_path)
            
            logger.info(f"Restored backup from {backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def _deep_update(self, d: Dict[str, Any], u: Dict[str, Any]) -> None:
        """Deep update a dictionary with another dictionary.
        
        Args:
            d (Dict[str, Any]): The dictionary to update.
            u (Dict[str, Any]): The updates to apply.
        """
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v

    def initialize_new_game(self, player_name: str, start_node_id: str = None) -> None:
        """Initialize a new game state for a player.
        
        Args:
            player_name (str): Name of the player starting the game.
            start_node_id (str, optional): Starting node ID from story. Defaults to "start".
        """
        # Generate unique state ID
        state_id = str(uuid.uuid4())
        
        # Create initial state
        initial_state = {
            "id": state_id,
            "player_name": player_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": 1,  # Initial version
            "inventory": [],
            "current_node_id": start_node_id if start_node_id else "start",  # Use consistent field name
            "flags": {},  # Game state flags
            "variables": {},  # Game variables
            "choices": []  # Player choices
        }
        
        # Save the initial state
        self.save_state(initial_state)
        
        logger.info(f"Initialized new game state for player: {player_name} (ID: {state_id})")

    def find_save_by_code(self, save_code: str) -> Optional[Dict[str, Any]]:
        """Find a save file by its code.
        
        Args:
            save_code (str): The save code to search for.
            
        Returns:
            Optional[Dict[str, Any]]: Information about the save file, or None if not found.
        """
        try:
            save_path = self._resolve_save_path_by_code(save_code)
            if save_path:
                save_data = self._read_json_file(save_path)
                if save_data:
                    listing = self._build_save_listing(save_data, os.path.basename(save_path))
                    listing["data"] = save_data
                    return listing
            
            return None
        except Exception as e:
            logger.error(f"Error finding save by code {save_code}: {e}")
            return None
    
    def get_saved_games_list(self, player_name: str = None, story_id: str = None) -> List[Dict[str, Any]]:
        """Get a list of saved games, optionally filtered by player name and/or story ID.
        
        Args:
            player_name (str, optional): Filter by player name.
            story_id (str, optional): Filter by story ID.
            
        Returns:
            List[Dict[str, Any]]: List of saved game information.
        """
        saved_games = []
        try:
            for payload in self._iter_save_payloads():
                state = payload["state"]
                if not self._matches_save_filters(state, player_name=player_name, story_id=story_id):
                    continue
                saved_games.append(self._build_save_listing(state, payload["filename"]))

            saved_games.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return saved_games
        except Exception as e:
            logger.error(f"Error getting saved games list: {e}")
            return []
