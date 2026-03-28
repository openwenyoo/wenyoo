"""
Story models for the AI Native game engine.

This module defines the data structures for representing stories,
including story nodes, connections, and conditions.
"""
from typing import Dict, List, Optional, Any, Union, Tuple, TYPE_CHECKING, Set
from enum import Enum
import hashlib
import json
import yaml
import logging
import os
from pydantic import BaseModel, Field, PrivateAttr, validator, model_validator
import time

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.models.game_state import GameState


def parse_duration_to_seconds(duration: Optional[str]) -> int:
    """Parse compact durations like ``15s``, ``2m``, or ``1h``."""
    if not duration:
        return 0

    value = str(duration).strip().lower()
    if not value:
        return 0

    try:
        if value.endswith('s'):
            return int(value[:-1])
        if value.endswith('m'):
            return int(value[:-1]) * 60
        if value.endswith('h'):
            return int(value[:-1]) * 3600
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid timed duration '%s'", duration)
        return 0


# =============================================================================
# Form Models - For collecting structured data from players
# =============================================================================

class FormFieldOption(BaseModel):
    """An option for select, multiselect, radio, or checkbox group fields."""
    value: str
    text: str
    description: Optional[str] = None
    disabled: bool = False
    disabled_reason: Optional[str] = None


class FormFieldValidation(BaseModel):
    """Validation rules for form fields."""
    # Text validation
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    pattern_error: Optional[str] = None
    
    # Number validation
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    integer_only: bool = False
    
    # Selection validation
    min_selections: Optional[int] = None
    max_selections: Optional[int] = None
    
    # Date/time validation
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    min_time: Optional[str] = None
    max_time: Optional[str] = None
    
    # Slider labels (for display)
    labels: Optional[Dict[int, str]] = None
    
    # Custom validation script (Lua)
    script: Optional[str] = None


class FormFieldShowIf(BaseModel):
    """Conditional display logic for form fields.
    
    Two modes of operation:
    1. Form field check: Set 'field' to check another form field's value (client-side)
    2. Game state check: Set 'variable' to check a game state variable (server-side)
    
    If both 'field' and 'variable' are set, 'variable' takes precedence.
    """
    # Check another form field (client-side evaluation)
    field: Optional[str] = None
    # Check a game state variable (server-side evaluation)
    variable: Optional[str] = None
    operator: str = "eq"  # eq, ne, gt, lt, gte, lte, contains, in, exists, not_exists
    value: Any = None
    
    @model_validator(mode='after')
    def validate_field_or_variable(self):
        """Ensure at least one of field or variable is set."""
        if not self.field and not self.variable:
            raise ValueError("FormFieldShowIf must have either 'field' or 'variable' set")
        return self


class FormField(BaseModel):
    """A field in a form."""
    id: str
    type: str  # text, textarea, number, select, multiselect, checkbox, checkboxgroup, radio, slider, rating, date, time, file, hidden
    label: str
    
    # Optional properties
    required: bool = False
    default: Optional[Any] = None
    placeholder: Optional[str] = None
    hint: Optional[str] = None
    disabled: bool = False
    
    # Conditional display
    show_if: Optional[FormFieldShowIf] = None
    
    # Validation
    validation: Optional[FormFieldValidation] = None
    
    # Options for select, multiselect, radio, checkboxgroup
    options: Optional[List[Union[str, FormFieldOption]]] = None
    
    # Slider specific
    show_value: bool = True
    
    # Rating specific
    max_rating: int = 5
    
    # File specific
    accept: Optional[List[str]] = None  # MIME types: text/plain, application/pdf, etc.
    max_size_mb: float = 20.0
    multiple: bool = False
    max_files: int = 1
    extract_text: bool = True  # Extract text content from file
    max_text_length: int = 100000  # Max characters to extract
    
    # Hidden field value
    value: Optional[Any] = None
    
    # Textarea specific
    rows: int = 4
    
    @model_validator(mode='before')
    def normalize_options(cls, data: Any) -> Any:
        """Convert simple string options to FormFieldOption objects."""
        if isinstance(data, dict) and 'options' in data:
            options = data['options']
            if options and isinstance(options, list):
                normalized = []
                for opt in options:
                    if isinstance(opt, str):
                        normalized.append({'value': opt, 'text': opt})
                    else:
                        normalized.append(opt)
                data['options'] = normalized
        return data


class FormStoreVariable(BaseModel):
    """Configuration for storing form field to a variable."""
    field: str  # Field ID or "*" for all fields
    to: str  # Variable path


class FormLLMProcess(BaseModel):
    """Configuration for LLM processing of form data."""
    prompt: str
    parse_as: str = "text"  # text, json
    store_to: Optional[str] = None
    extract: Optional[List[Dict[str, str]]] = None  # [{path: "...", to: "..."}]


class FormOnSubmit(BaseModel):
    """Actions to perform when a form is submitted."""
    store_variables: Optional[List[FormStoreVariable]] = None
    llm_process: Optional[FormLLMProcess] = None
    script: Optional[str] = None  # Lua script
    effects: Optional[List['Effect']] = None


class FormDefinition(BaseModel):
    """A form that can be presented to players to collect information."""
    id: str
    title: str
    description: Optional[str] = None
    submit_text: str = "Submit"
    
    fields: List[FormField] = Field(default_factory=list)
    on_submit: Optional[FormOnSubmit] = None
    
    def to_frontend_format(self, game_state: Optional[Any] = None, player_id: str = "default",
                           substitute_func: Optional[callable] = None) -> Dict[str, Any]:
        """Convert form to frontend-compatible format with variable substitution.
        
        Args:
            game_state: Current game state for variable resolution
            player_id: Player ID for variable resolution
            substitute_func: Optional function to substitute variables in strings.
                            Signature: (text: str, game_state, player_id) -> str
        
        Returns:
            Dictionary with form data ready for frontend rendering
        """
        def substitute(text: str) -> str:
            """Helper to safely substitute variables in text."""
            if not text or not substitute_func or not game_state:
                return text
            if '{$' in text or '{{' in text or '{@' in text:
                return substitute_func(text, game_state, player_id)
            return text
        
        def evaluate_show_if(show_if: 'FormFieldShowIf') -> bool:
            """Evaluate a show_if condition against game state.
            
            Returns True if the field should be shown, False if hidden.
            For field-based conditions (client-side), always returns True 
            since frontend handles those.
            """
            if not show_if:
                return True
            
            # If checking a game state variable (server-side evaluation)
            if show_if.variable and game_state:
                # Substitute any variable references in the variable path
                var_path = substitute(show_if.variable) if substitute_func else show_if.variable
                
                # Get the variable value from game state
                var_value = game_state.get_variable(var_path, player_id=player_id)
                
                # Handle special operators
                if show_if.operator == "exists":
                    return var_value is not None
                elif show_if.operator == "not_exists":
                    return var_value is None
                
                # Compare with expected value
                expected = show_if.value
                
                if show_if.operator == "eq":
                    return var_value == expected
                elif show_if.operator == "ne":
                    return var_value != expected
                elif show_if.operator == "gt":
                    try:
                        return float(var_value) > float(expected)
                    except (TypeError, ValueError):
                        return False
                elif show_if.operator == "lt":
                    try:
                        return float(var_value) < float(expected)
                    except (TypeError, ValueError):
                        return False
                elif show_if.operator == "gte":
                    try:
                        return float(var_value) >= float(expected)
                    except (TypeError, ValueError):
                        return False
                elif show_if.operator == "lte":
                    try:
                        return float(var_value) <= float(expected)
                    except (TypeError, ValueError):
                        return False
                elif show_if.operator == "contains":
                    if isinstance(var_value, (list, tuple)):
                        return expected in var_value
                    elif isinstance(var_value, str):
                        return str(expected) in var_value
                    return False
                elif show_if.operator == "in":
                    if isinstance(expected, (list, tuple)):
                        return var_value in expected
                    return False
                else:
                    logger.warning(f"Unknown show_if operator: {show_if.operator}")
                    return True
            
            # For field-based conditions, let frontend handle it
            return True
        
        # Build fields list with resolved conditional display and variable substitution
        fields_data = []
        for field in self.fields:
            field_dict = field.model_dump(exclude_none=True)
            
            # Substitute variables in text fields
            if 'label' in field_dict:
                field_dict['label'] = substitute(field_dict['label'])
            if 'placeholder' in field_dict:
                field_dict['placeholder'] = substitute(field_dict['placeholder'])
            if 'hint' in field_dict:
                field_dict['hint'] = substitute(field_dict['hint'])
            if 'default' in field_dict and isinstance(field_dict['default'], str):
                field_dict['default'] = substitute(field_dict['default'])
            
            # Substitute variables in options
            if 'options' in field_dict and field_dict['options']:
                substituted_options = []
                for opt in field_dict['options']:
                    if isinstance(opt, dict):
                        new_opt = opt.copy()
                        if 'text' in new_opt:
                            new_opt['text'] = substitute(new_opt['text'])
                        if 'value' in new_opt and isinstance(new_opt['value'], str):
                            new_opt['value'] = substitute(new_opt['value'])
                        if 'description' in new_opt:
                            new_opt['description'] = substitute(new_opt['description'])
                        if 'disabled_reason' in new_opt:
                            new_opt['disabled_reason'] = substitute(new_opt['disabled_reason'])
                        substituted_options.append(new_opt)
                    else:
                        substituted_options.append(opt)
                field_dict['options'] = substituted_options
            
            # Evaluate show_if conditions against game state
            if field.show_if:
                visible = evaluate_show_if(field.show_if)
                if field.show_if.variable:
                    # Server-side evaluation: add visibility flag
                    field_dict['_server_visible'] = visible
                    # Remove show_if from frontend data since it's already evaluated
                    if not field.show_if.field:
                        # Pure variable-based show_if, remove it from frontend
                        field_dict.pop('show_if', None)
            
            fields_data.append(field_dict)
        
        # Substitute variables in title and description
        title = substitute(self.title) if self.title else self.title
        description = substitute(self.description) if self.description else self.description
        submit_text = substitute(self.submit_text) if self.submit_text else self.submit_text
        
        return {
            "type": "form",
            "form_id": self.id,
            "title": title,
            "description": description,
            "submit_text": submit_text,
            "fields": fields_data
        }


# =============================================================================
# Core Story Models
# =============================================================================

class Connection(BaseModel):
    """A semantic or structural relationship between story entities."""
    id: str
    source: str
    targets: List[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_targets(self):
        if not self.targets:
            raise ValueError("Connection.targets must contain at least one entity ID")
        return self


class ConnectionGraph(BaseModel):
    """Lightweight adjacency helper for compiled story connections."""
    connections: List[Connection] = Field(default_factory=list)
    _by_entity: Dict[str, List[Connection]] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        index: Dict[str, List[Connection]] = {}
        for conn in self.connections:
            touched_ids = {conn.source, *conn.targets}
            for entity_id in touched_ids:
                index.setdefault(entity_id, []).append(conn)
        self._by_entity = index

    def get(self, entity_id: str) -> List[Connection]:
        return list(self._by_entity.get(entity_id, []))

    def all_connections(self) -> List[Connection]:
        return list(self.connections)

    def collect_neighborhood(self, entity_ids: Set[str]) -> List[Connection]:
        if not entity_ids:
            return []
        seen_ids: Set[str] = set()
        neighborhood: List[Connection] = []
        for entity_id in entity_ids:
            for conn in self._by_entity.get(entity_id, []):
                if conn.id in seen_ids:
                    continue
                seen_ids.add(conn.id)
                neighborhood.append(conn)
        return neighborhood

    def format_summary(self, entity_ids: Set[str]) -> List[str]:
        lines: List[str] = []
        for conn in self.collect_neighborhood(entity_ids):
            lines.append(
                f"{conn.source} -> [{', '.join(conn.targets)}] ({conn.id})"
            )
        return lines

    def to_serializable_neighborhood(self, entity_ids: Set[str]) -> List[Dict[str, Any]]:
        return [conn.model_dump() for conn in self.collect_neighborhood(entity_ids)]


class Function(BaseModel):
    """A reusable function that can be called from effects."""
    id: str
    parameters: List[str] = Field(default_factory=list)
    effects: List['Effect'] = Field(default_factory=list)
    conditions: List['StoryCondition'] = Field(default_factory=list)


class StoryAction(BaseModel):
    """Action that a player can perform in the game.
    
    Actions are matched to player input using LLM intent matching based on
    the action's `text` or `description` field. The LLM determines if the
    player's input matches the action's intent.
    
    The ``intent`` field contains natural language describing what should happen
    when this action is triggered. The Architect interprets it at runtime
    using ``read_game_state`` and ``commit_world_event``.
    When ``intent`` is provided, ``effects`` is ignored.
    """
    id: str
    text: Optional[str] = None
    description: Optional[str] = None
    intent: Optional[str] = None
    conditions: List['StoryCondition'] = Field(default_factory=list)
    effects: List['Effect'] = Field(default_factory=list)
    feedback: Dict[str, List[str]] = Field(default_factory=dict)

    @model_validator(mode='before')
    def _text_or_description_to_text(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if 'text' not in data and 'description' in data:
                data['text'] = data['description']
            if 'keywords' in data:
                del data['keywords']
        return data

    def is_available(self, game_state: 'GameState', player_id: str) -> Tuple[bool, Optional[str]]:
        if not self.conditions:
            return True, None
        for condition in self.conditions:
            success, response = condition.evaluate(game_state, player_id)
            if not success:
                return False, response
        return True, None

class StoryObject(BaseModel):
    """
    A self-contained object in the game world.
    
    Entity model:
    - definition: Static - what the object IS (material, capabilities, behavior)
    - explicit_state: Dynamic, visible - current appearance shown to player
    - implicit_state: Dynamic, hidden - internal state not shown to player
    
    Properties (Mechanical State):
    - properties: Flexible dict for story-specific mechanics
      - status: List of status tags (e.g., ["locked", "broken", "glowing"])
      - contains: List of contained object IDs
      - Any other story-specific data
    
    Example definition format:
    ```
    [Description]
    An ancient stone well, built from weathered stones.
    The rim is covered with thick moss and lichen.
    
    [Properties]
    The well is about 10 meters deep with clear spring water.
    A bucket can be used to draw water.
    Items may be hidden at the bottom.
    
    [Interaction Rules]
    ## Examine the well
    When the player examines the well:
    - Display: You peer into the dark well...
    - Effect: {"type": "set_variable", "target": "well_examined", "value": true}
    ```
    """
    id: str
    name: str
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Narrative State
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Static: what the object IS (material, capabilities, behavior)
    definition: str = ""
    
    # Dynamic, visible: current appearance shown to player
    explicit_state: str = ""
    
    # Dynamic, hidden: internal state not shown to player (e.g., "this chest is trapped")
    implicit_state: str = ""
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Properties - Mechanical State (story-specific)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Flexible dict for game mechanics: status, contains, custom data
    properties: Dict[str, Any] = Field(default_factory=dict)

    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value with optional default."""
        return self.properties.get(key, default)
    
    def get_status(self) -> List[str]:
        """Get current status tags from properties."""
        return self.properties.get('status', [])
    
    def has_status(self, status: str) -> bool:
        """Check if object has a specific status tag."""
        return status in self.get_status()
    
    def get_contains(self) -> List[str]:
        """Get list of contained object IDs."""
        return self.properties.get('contains', [])
    
    def __init__(self, **data):
        # Initialize properties with defaults if not provided
        if 'properties' not in data:
            data['properties'] = {}
        
        # Ensure status exists in properties
        if 'status' not in data['properties']:
            data['properties']['status'] = []
        
        super().__init__(**data)

class TimedEvent(BaseModel):
    """A timed event that triggers after a certain duration."""
    id: str
    trigger_timestamp: float
    event_type: str = "timed_event"
    scope: str = "player"
    object_id: Optional[str] = None
    rule_id: Optional[str] = None
    event_context: Optional[str] = None
    intended_state_changes: Dict[str, Any] = Field(default_factory=dict)
    audience: Optional[str] = None
    location_id: Optional[str] = None
    effects: List['Effect'] = Field(default_factory=list)
    response: Optional[str] = None
    player_id: Optional[str] = None # The player who triggered the event
    node_id: Optional[str] = None # The node where the event was triggered


class StoryCondition(BaseModel):
    """Condition for story connections and nodes."""
    type: str
    variable: Optional[str] = None
    operator: Optional[str] = None
    value: Any = None
    has: Optional[str] = None
    target: Optional[str] = None
    state: Optional[str] = None
    response: Optional[str] = None
    # For type: compare (left/right comparison with variable references)
    left: Optional[str] = None
    right: Any = None
    # For type: and / type: or (compound conditions)
    conditions: Optional[List['StoryCondition']] = None

    @validator('variable', always=True)
    def variable_is_required_for_state_type(cls, v, values):
        if values.get('type') == 'state' and v is None:
            raise ValueError('variable is required for type "state"')
        return v
    
    def evaluate(self, game_state: 'GameState', player_id: str) -> Tuple[bool, Optional[str]]:
        """Evaluate the condition against the current state.
        
        Args:
            game_state (GameState): The current game state object.
            player_id (str): The ID of the player to evaluate the condition for.
            
        Returns:
            (bool, Optional[str]): A tuple containing the success status and an optional failure response.
        """
        variables = game_state.variables.copy()
        if hasattr(game_state, 'function_parameters') and player_id in game_state.function_parameters:
            variables['parameters'] = game_state.function_parameters[player_id]
        player_data = variables.get("players", {}).get(player_id, {})
        character = player_data.get("character")

        # Handle compound conditions (and / or)
        if self.type == "and":
            if not self.conditions:
                return True, None
            for sub_cond in self.conditions:
                if isinstance(sub_cond, dict):
                    sub_cond = StoryCondition(**sub_cond)
                result, resp = sub_cond.evaluate(game_state, player_id)
                if not result:
                    return False, resp or self.response
            return True, None

        if self.type == "or":
            if not self.conditions:
                return False, self.response
            for sub_cond in self.conditions:
                if isinstance(sub_cond, dict):
                    sub_cond = StoryCondition(**sub_cond)
                result, _ = sub_cond.evaluate(game_state, player_id)
                if result:
                    return True, None
            return False, self.response

        # Handle compare conditions with left/right variable references
        if self.type == "compare":
            return self._evaluate_compare(variables, game_state, player_id)

        if self.type == "stat":
            if not character or "stats" not in character:
                return False, self.response
            stat_value = character["stats"].get(self.variable)
            if stat_value is None:
                return False, self.response
            
            op_map = {
                "eq": lambda a, b: a == b,
                "neq": lambda a, b: a != b,
                "gt": lambda a, b: a > b,
                "lt": lambda a, b: a < b,
                "gte": lambda a, b: a >= b,
                "lte": lambda a, b: a <= b,
            }
            if self.operator not in op_map or not op_map[self.operator](stat_value, self.value):
                return False, self.response
            return True, None

        if self.type == "character":
            if not character or character.get("id") != self.value:
                return False, self.response
            return True, None

        if self.type == "object_status":
            # Check if object has a specific status tag
            target_object = game_state.find_object_in_world(self.target)
            if not target_object:
                return False, self.response
            # Check if required status tag is present in object's status list
            required_status = self.state or self.value  # Support both 'state' and 'value' fields
            object_status = game_state.get_effective_object_status(self.target)
            if required_status and required_status not in object_status:
                return False, self.response
            return True, None

        if self.type == "inventory":
            inventory_ids = list(game_state.get_player_inventory(player_id))
            if self.operator == "has" and self.value not in inventory_ids:
                return False, self.response
            elif self.operator == "not_has" and self.value in inventory_ids:
                return False, self.response
            return True, None

        if not self.variable:
            return False, self.response
            
        var_path = self.variable.split(".")
        var_value = variables
        path_exists = True
        for part in var_path:
            if isinstance(var_value, dict) and part in var_value:
                var_value = var_value[part]
            elif hasattr(var_value, part):
                var_value = getattr(var_value, part)
            else:
                path_exists = False
                break
        
        op_map = {
            "eq": lambda a, b: a == b,
            "neq": lambda a, b: a != b,
            "gt": lambda a, b: a > b,
            "lt": lambda a, b: a < b,
            "gte": lambda a, b: a >= b,
            "lte": lambda a, b: a <= b,
            "contains": lambda a, b: b in a,
            "not_contains": lambda a, b: b not in a,
            "exists": lambda a, b: True,
            "not_exists": lambda a, b: False,
        }

        if self.operator == "exists":
            return path_exists, self.response
        if self.operator == "not_exists":
            return not path_exists, self.response

        if not path_exists:
            return False, self.response

        # Resolve variable references in the comparison value
        compare_value = self.value
        if isinstance(compare_value, str) and compare_value.startswith("{$") and compare_value.endswith("}"):
            # Extract variable name and resolve it
            ref_var_name = compare_value[2:-1]  # Remove {$ and }
            ref_path = ref_var_name.split(".")
            ref_value = variables
            for part in ref_path:
                if isinstance(ref_value, dict) and part in ref_value:
                    ref_value = ref_value[part]
                else:
                    ref_value = None
                    break
            compare_value = ref_value
        
        # Try to match types for numeric comparisons
        if compare_value is not None:
            if isinstance(var_value, (int, float)) and isinstance(compare_value, str):
                try:
                    compare_value = type(var_value)(compare_value)
                except (ValueError, TypeError):
                    pass
            elif isinstance(compare_value, (int, float)) and isinstance(var_value, str):
                try:
                    var_value = type(compare_value)(var_value)
                except (ValueError, TypeError):
                    pass

        if self.operator not in op_map or not op_map[self.operator](var_value, compare_value):
            return False, self.response
        
        return True, None

    def _resolve_value(self, val: Any, variables: dict, game_state: 'GameState' = None, player_id: str = None) -> Any:
        """Resolve a value that may be a {variable_name} reference.
        
        Supports player.properties.* paths when game_state and player_id are provided,
        resolving through the controlled character's properties.
        """
        if isinstance(val, str) and val.startswith("{") and val.endswith("}"):
            var_name = val[1:-1]  # Remove { and }
            
            # Handle player.properties.* paths via game_state
            if var_name.startswith("player.") and game_state and player_id:
                resolved = game_state.resolve_player_path(var_name, player_id)
                if resolved is not None:
                    return resolved
                # Fall through to standard resolution if not found
            
            var_path = var_name.split(".")
            resolved = variables
            for part in var_path:
                if isinstance(resolved, dict) and part in resolved:
                    resolved = resolved[part]
                else:
                    return val  # Can't resolve, return as-is
            return resolved
        return val

    def _evaluate_compare(self, variables: dict, game_state: 'GameState', player_id: str) -> Tuple[bool, Optional[str]]:
        """Evaluate a compare condition with left/right and standard operators."""
        left_val = self._resolve_value(self.left, variables, game_state, player_id)
        right_val = self._resolve_value(self.right, variables, game_state, player_id)

        # Try to convert to matching numeric types for comparison
        if isinstance(left_val, str) and isinstance(right_val, (int, float)):
            try:
                left_val = type(right_val)(left_val)
            except (ValueError, TypeError):
                pass
        elif isinstance(right_val, str) and isinstance(left_val, (int, float)):
            try:
                right_val = type(left_val)(right_val)
            except (ValueError, TypeError):
                pass

        op_map = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
            # Also support word-form operators
            "eq": lambda a, b: a == b,
            "neq": lambda a, b: a != b,
            "lt": lambda a, b: a < b,
            "gt": lambda a, b: a > b,
            "lte": lambda a, b: a <= b,
            "gte": lambda a, b: a >= b,
        }

        op_func = op_map.get(self.operator)
        if not op_func:
            return False, self.response

        try:
            result = op_func(left_val, right_val)
        except TypeError:
            return False, self.response

        return result, (None if result else self.response)


class Effect(BaseModel):
    """
    A unified effect that can modify game state or present information.
    
    UNIFIED FIELD NAMING CONVENTION:
    - target: Always the ID of the thing being affected (item, variable, object, node, character)
    - value: Always the primary value being set/applied
    
    Effect format examples:
    - {"type": "add_to_inventory", "target": "item_id"}
    - {"type": "remove_from_inventory", "target": "item_id"}
    - {"type": "set_variable", "target": "var_name", "value": any_value}
    - {"type": "update_object_status", "target": "object_id", "add_status": [...], "remove_status": [...]}
    - {"type": "set_object_explicit_state", "target": "object_id", "value": "new explicit_state text"}
    - {"type": "goto_node", "target": "node_id"}
    - {"type": "calculate", "target": "var_name", "operation": "add/subtract/multiply/divide", "value": number}
    - {"type": "display_text", "value": "text to display"}
    """
    type: str
    conditions: Optional[List['StoryCondition']] = None
    
    # UNIFIED FIELDS - use these for all effects
    target: Optional[str] = None  # The thing being affected (item_id, var_name, object_id, node_id)
    value: Any = None  # The primary value being set/applied (any type: str, int, bool, etc.)
    
    # Common fields
    owner: str = "player"
    duration: Optional[str] = None
    effects: List['Effect'] = Field(default_factory=list)
    response: Optional[str] = None
    id: Optional[str] = None
    text: Optional[str] = None  # For display_text (value is an alias for this)
    message: Optional[str] = None
    name: Optional[str] = None
    choices: Optional[List['DialogueChoice']] = None
    speaker: Optional[str] = None
    audience_scope: Optional[str] = None
    player_id: Optional[str] = None
    target_player_id: Optional[str] = None
    target_player_ids: Optional[List[str]] = None
    location_id: Optional[str] = None
    exclude_player_ids: Optional[List[str]] = None
    
    # For dice_roll
    dice: Optional[str] = None
    target_number: Optional[int] = None
    bonus: Optional[int] = None
    success_response: Optional[str] = None
    failure_response: Optional[str] = None
    success_effects: List['Effect'] = Field(default_factory=list)
    failure_effects: List['Effect'] = Field(default_factory=list)
    
    # For lua_script
    script: Optional[str] = None
    
    items: List[str] = Field(default_factory=list)
    action_id: Optional[str] = None
    
    # For call_function
    function: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    
    # For llm_generate
    prompt: Optional[str] = None
    output_format: Optional[str] = None  # "json", "text", "yaml"
    output_variable: Optional[str] = None
    regenerate: bool = False
    use_tools: bool = False
    
    # For apply_json_to_variables
    source_variable: Optional[str] = None
    fields: Optional[List[str]] = None
    
    # For calculate / modify_variable
    operation: Optional[str] = None  # "add", "subtract", "multiply", "divide", "set"
    
    # For random_branch
    branches: Optional[List[Dict[str, Any]]] = None  # [{weight: int, effects: [Effect]}]
    
    # For conditional
    condition: Optional['StoryCondition'] = None
    if_effects: List['Effect'] = Field(default_factory=list)
    else_effects: List['Effect'] = Field(default_factory=list)
    
    # For for_each
    array_variable: Optional[str] = None
    item_variable: Optional[str] = None
    index_variable: Optional[str] = None
    
    # For trigger_character_prompt
    # Sends a situation to a character's intelligent mode for LLM-driven response
    character_id: Optional[str] = None  # The character to prompt
    situation: Optional[str] = None  # Description of the situation for the character to react to
    context_vars: Optional[List[str]] = None  # Optional list of variable names to include in context
    
    # For random_number
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    
    # For generate_object and generate_character
    brief: Optional[str] = None  # Brief description/context for LLM generation
    hints: Optional[List[str]] = None  # Optional guidance hints for generation
    
    # For generate_character
    location: Optional[str] = None  # Node ID where the generated character starts (default: current node)
    
    # For update_object_status
    add_status: Optional[List[str]] = None  # Status tags to add to object
    remove_status: Optional[List[str]] = None  # Status tags to remove from object
    regenerate_explicit_state: bool = False  # Whether to regenerate object explicit_state via LLM
    
    # For set_object_explicit_state
    explicit_state: Optional[str] = None  # Direct explicit_state text to set
    
    # For present_form
    form_id: Optional[str] = None  # ID of the form to present
    prefill: Optional[Dict[str, Any]] = None  # Pre-fill values for form fields
    on_submit_override: Optional['FormOnSubmit'] = None  # Override form's on_submit for this instance

    def apply(self, state: Dict[str, Any], current_player_id: str = "default") -> Dict[str, Any]:
        """Apply the state modifier to the current state.
        
        Args:
            state (Dict[str, Any]): The current game state.
            current_player_id (str): The ID of the player performing this action.
            
        Returns:
            Dict[str, Any]: The updated game state.
        """
        # Create a copy of the state to avoid modifying the original
        new_state = state.copy()
        if 'variables' not in new_state:
            new_state['variables'] = {}
        variables = new_state['variables']

        def get_inventory(owner: str):
            """A nested helper function to get the inventory of a player or NPC."""
            effective_owner = f"player:{current_player_id}" if owner == "player" else owner
            
            if effective_owner.startswith("player:"):
                player_id = effective_owner[7:]
                if "players" not in variables:
                    variables["players"] = {}
                if player_id not in variables["players"]:
                    variables["players"][player_id] = {}
                if "inventory" not in variables["players"][player_id]:
                    variables["players"][player_id]["inventory"] = []
                return variables["players"][player_id]["inventory"]
            
            elif owner.startswith("npc:"):
                npc_id = owner[4:]
                if "npcs" not in variables:
                    variables["npcs"] = {}
                if npc_id not in variables["npcs"]:
                    variables["npcs"][npc_id] = {}
                if "inventory" not in variables["npcs"][npc_id]:
                    variables["npcs"][npc_id]["inventory"] = []
                return variables["npcs"][npc_id]["inventory"]
            
            return []

        # Handle dynamic node description changes
        if self.type == "set_node_description":
            if 'node_states' not in new_state:
                new_state['node_states'] = {}
            if self.target not in new_state['node_states']:
                new_state['node_states'][self.target] = {}
            new_state['node_states'][self.target]['explicit_state'] = self.value
            return new_state
        
        elif self.type == "start_timed_event":
            if not self.duration or not self.id:
                return new_state

            duration_in_seconds = parse_duration_to_seconds(self.duration)
            logger.info(f"duration_in_seconds: {duration_in_seconds} for event {self.id}")

            if duration_in_seconds > 0:
                if 'timed_events' not in new_state:
                    new_state['timed_events'] = []
                
                event = TimedEvent(
                    id=self.id,
                    trigger_timestamp=time.time() + duration_in_seconds,
                    event_type="legacy_timed_effect",
                    scope="player",
                    event_context=self.response or self.message or "A timed event is ready to resolve.",
                    audience="self",
                    location_id=variables.get('players', {}).get(current_player_id, {}).get('location'),
                    effects=self.effects,
                    response=self.response,
                    player_id=current_player_id,
                    node_id=variables.get('players', {}).get(current_player_id, {}).get('location')
                )
                new_state['timed_events'].append(event.model_dump())
                logger.info(f"Started timed event '{self.id}' for player {current_player_id}, triggers at {event.trigger_timestamp}")
            return new_state
        elif self.type == "remove_from_inventory":
            if self.value:
                player_inventory = get_inventory(self.owner)
                # Find the item by its ID and remove it
                item_removed = False
                for i, item in enumerate(player_inventory):
                    if item['id'] == self.value:
                        player_inventory.pop(i)
                        item_removed = True
                        logger.info(f"Removed item '{self.value}' from {self.owner} inventory.")
                        break
                if not item_removed:
                    logger.warning(f"Attempted to remove non-existent item '{self.value}' from {self.owner} inventory.")
        elif self.type == "set_variable":
            if self.target is None:
                logger.warning(f"StateModifier: 'set_variable' effect has no target, Skipping.")
                return new_state
            # Set a variable in the variables dict
            var_path = self.target.split(".")
            target_dict = variables
            for part in var_path[:-1]:
                if part not in target_dict:
                    target_dict[part] = {}
                target_dict = target_dict[part]
            target_dict[var_path[-1]] = self.value
            logger.debug(f"StateModifier: set_variable '{self.target}' to '{self.value}'. Current variables: {variables}")
        elif self.type == "set_flag":
            # Set a flag in the state
            if "flags" not in variables:
                variables["flags"] = {}
            
            variables["flags"][self.target] = self.value
        elif self.type == "update_npc":
            # Update an NPC's state
            if "npcs" not in variables:
                variables["npcs"] = {}
            if self.target not in variables["npcs"]:
                variables["npcs"][self.target] = {}
            
            # Update with the provided value (which should be a dict)
            if isinstance(self.value, dict):
                variables["npcs"][self.target].update(self.value)
        
        return new_state

class DialogueChoice(BaseModel):
    text: str
    effects: List['Effect'] = Field(default_factory=list)
    conditions: Optional[List[StoryCondition]] = Field(default_factory=list)


class Trigger(BaseModel):
    id: str
    type: Optional[str] = None  # FSM trigger type: pre_enter, post_enter, pre_leave, post_leave
    intent: Optional[str] = None
    conditions: List[StoryCondition] = Field(default_factory=list)
    effects: List['Effect'] = Field(default_factory=list)



class StoryNode(BaseModel):
    """
    Node in a story graph.
    
    Entity model:
    - definition: Static - what the node IS (setting, atmosphere, rules)
    - explicit_state: Dynamic, visible - current scene description shown to player
    - implicit_state: Dynamic, hidden - internal state not shown to player
    
    Properties (Mechanical State):
    - properties: Flexible dict for story-specific mechanics
      - status: List of status tags (e.g., ["dark", "flooded", "on_fire"])
      - visit_count: Number of times visited
      - Any other story-specific data
    
    Example definition format:
    ```
    【Description】
    A grand temple entrance with stone steps and bronze doors.
    The architecture reflects ancient ceremonial design.
    
    【State Conditions】
    - If "doors_open" in status: The massive doors stand open.
    - If "ritual_active" in status: Chanting echoes from within.
    - Default: The doors are sealed with ancient glyphs.
    
    【Interaction Rules】
    ## Examine the glyphs
    When player examines the glyphs:
    - Display: The glyphs speak of an ancient ritual...
    - Effect: {"type": "set_variable", "target": "glyphs_read", "value": true}
    ```
    
    If explicit_state is None/empty and definition exists, explicit_state will be
    generated on-the-fly using LLM based on definition and current state.
    """
    id: str
    name: Optional[str] = None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Narrative State
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Static: what the node IS (setting, atmosphere, interaction rules)
    definition: str = ""
    
    # Dynamic, visible: current scene description shown to player
    # If None/empty and definition exists, will be generated via LLM
    explicit_state: Optional[str] = None
    
    # Dynamic, hidden: internal state not shown to player (plot secrets, AI hints)
    implicit_state: str = ""
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Properties - Mechanical State (story-specific)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Flexible dict for game mechanics: status, visit_count, custom data
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Architect Hints
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Free-form guidance for the Architect: NPC catalogues, scene rules,
    # pricing tables, and other context that was previously embedded in
    # llm_generate prompt templates.  Included in read_game_state() output.
    hints: Optional[str] = None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Node Configuration
    # ═══════════════════════════════════════════════════════════════════════════
    
    objects: List[StoryObject] = Field(default_factory=list)
    actions: Optional[List[StoryAction]] = Field(default_factory=list)
    initial_variables: Optional[Dict[str, Any]] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    conditions: List[StoryCondition] = Field(default_factory=list)
    is_ending: bool = False
    triggers: List['Trigger'] = Field(default_factory=list)
    status_bar: Optional[Dict[str, Any]] = None
    type: Optional[str] = None  # Can be 'generated'
    generation_prompt: Optional[str] = None
    generation_hints: Optional[Dict[str, Any]] = None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value with optional default."""
        return self.properties.get(key, default)
    
    def get_status(self) -> List[str]:
        """Get current status tags from properties."""
        return self.properties.get('status', [])
    
    def has_status(self, status: str) -> bool:
        """Check if node has a specific status tag."""
        return status in self.get_status()

    def apply_overrides(self, overrides: Optional[Dict[str, Any]] = None) -> 'StoryNode':
        """Apply overrides to create a new node instance with modified state.
        
        Args:
            overrides (Optional[Dict[str, Any]]): Dictionary containing node state overrides
            
        Returns:
            StoryNode: A new node instance with overrides applied
        """
        if not overrides:
            return self

        # Create a new node instance with basic properties
        new_node = StoryNode(
            id=self.id,
            name=self.name,
            definition=overrides.get('definition', self.definition),
            explicit_state=overrides.get('explicit_state', self.explicit_state),
            implicit_state=overrides.get('implicit_state', self.implicit_state),
            properties=overrides.get('properties', self.properties.copy()),
            content=self.content.copy(),
            metadata=self.metadata.copy(),
            conditions=self.conditions.copy(),
            is_ending=self.is_ending
        )

        # Handle actions
        action_overrides = overrides.get('actions', {})
        existing_actions = {a.id: a for a in self.actions}
        new_actions = []
        
        # Keep or modify existing actions
        for action in self.actions:
            if action.id in action_overrides:
                if action_overrides[action.id] is not None:
                    # Add modified action
                    new_actions.append(StoryAction(**action_overrides[action.id]))
            else:
                # Keep original action
                new_actions.append(action)
                
        # Add new actions
        for action_id, action_data in action_overrides.items():
            if action_id not in existing_actions and action_data is not None:
                new_actions.append(StoryAction(**action_data))
        
        new_node.actions = new_actions
        return new_node
    
    def __init__(self, **data):
        # Initialize properties with defaults if not provided
        if 'properties' not in data:
            data['properties'] = {}
        
        # Ensure status exists in properties
        if 'status' not in data['properties']:
            data['properties']['status'] = []
        
        # Convert conditions dict to list of StoryCondition objects
        if 'conditions' in data and isinstance(data['conditions'], dict):
            data['conditions'] = [
                StoryCondition(
                    type="variable",
                    variable=key,
                    operator="eq",
                    value=value
                )
                for key, value in data['conditions'].items()
            ]
        
        if 'triggers' in data and isinstance(data['triggers'], list):
            data['triggers'] = [Trigger(**trigger_data) for trigger_data in data['triggers']]

        super().__init__(**data)
    
    def is_accessible(self, game_state: 'GameState', player_id: str = "default") -> bool:
        """Check if the node is accessible in the current state.
        
        Args:
            game_state (GameState): The current game state.
            player_id (str): The ID of the player to check accessibility for.
            
        Returns:
            bool: True if the node is accessible, False otherwise.
        """
        # If there are no conditions, the node is always accessible
        if not self.conditions:
            return True
        
        # Check all conditions
        for condition in self.conditions:
            success, _ = condition.evaluate(game_state, player_id)
            if not success:
                return False
        
        return True
    
    def get_available_actions(self, game_state: 'GameState', player_id: str) -> List[StoryAction]:
        """Get the available actions from this node in the current state."""
        available_actions = []
        
        # 1. Location-specific actions
        for action in self.actions:
            is_avail, _ = action.is_available(game_state, player_id)
            if is_avail:
                available_actions.append(action)

        # Note: Objects no longer have actions - they use definition field with interaction rules
        # The LLM interprets object interactions based on their definition
        
        return available_actions
    
    def get_action_by_id(self, action_id: str) -> Optional[StoryAction]:
        """Get an action by ID.
        
        Args:
            action_id (str): The ID of the action.
            
        Returns:
            Optional[StoryAction]: The action, or None if not found.
        """
        for action in self.actions:
            if action.id == action_id:
                return action
        return None
    
    def enter(self, game_state: Any) -> None:
        """Called when the player enters this node.
        
        Args:
            game_state: The current game state.
        """
        # Execute any entry actions or state changes
        # This is a placeholder for custom logic
        pass
    
    def exit(self, game_state: Any) -> None:
        """Called when the player exits this node.
        
        Args:
            game_state: The current game state.
        """
        # Execute any exit actions or state changes
        # This is a placeholder for custom logic
        pass
    
class Character(BaseModel):
    """
    Represents a character in the story (playable or NPC).
    
    Entity model:
    - definition: Static, immutable - WHO the character is, including persona and behavior rules
    - explicit_state: Dynamic, visible - what the player SEES about the character
    
    Properties (Mechanical State):
    - properties: Flexible dict for story-specific game mechanics
      - status: List of status tags (e.g., ["giant", "hallucinating"])
      - inventory: List of item IDs
      - affinity: Relationship score (default 50)
      - Any other story-specific data
    
    The definition field contains ALL static character information:
    - Physical description
    - Personality/persona for AI
    - Behavior rules/action_rules for AI
    - Capabilities and limitations
    
    Example definition format:
    ```
    [Identity]
    Old Master Pine, a hermit sage of the mysterious forest...
    
    [Personality]
    Gentle and kind, likes to teach through metaphors and stories...
    
    [Behavior Rules]
    ## Greeting
    When the player greets you:
    - Respond with a gentle, wise demeanor
    - Effect: {"type": "set_variable", ...}
    ```
    """
    id: str
    name: str
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Narrative State
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Static: WHO the character is - includes description, persona, action_rules
    definition: str = ""
    
    # Dynamic, visible: what the player SEES about the character currently
    explicit_state: str = ""
    
    # Dynamic, hidden: internal state not shown to player (for AI/game logic)
    implicit_state: str = ""
    
    # Dynamic, accumulated: list of past experiences/interactions
    memory: List[str] = Field(default_factory=list)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Properties - Mechanical State (story-specific)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Flexible dict for game mechanics: status, inventory, affinity, etc.
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    is_playable: bool = False  # True for player-controlled characters
    is_hittable: bool = False  # True if can be attacked in combat
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Character Flags
    # ═══════════════════════════════════════════════════════════════════════════
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value with optional default."""
        return self.properties.get(key, default)
    
    def get_status(self) -> List[str]:
        """Get current status tags from properties."""
        return self.properties.get('status', [])
    
    def has_status(self, status: str) -> bool:
        """Check if character has a specific status tag."""
        return status in self.get_status()
    
    def get_inventory(self) -> List[str]:
        """Get inventory from properties."""
        return self.properties.get('inventory', [])
    
    def has_item(self, item_id: str) -> bool:
        """Check if character has a specific item."""
        return item_id in self.get_inventory()
    
    def get_affinity(self) -> int:
        """Get relationship/affinity score (default 50)."""
        return self.properties.get('affinity', 50)
    
    def get_fallback_prompt(self) -> Optional[str]:
        """Get fallback prompt for when no action matches.
        
        Returns the definition which contains all behavior rules.
        """
        return self.definition if self.definition else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stats dict from properties."""
        return self.properties.get('stats', {})
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Shorthand accessor for properties['stats']."""
        if 'stats' not in self.properties:
            self.properties['stats'] = {}
        return self.properties['stats']
    
    def add_memory(self, memory_entry: str) -> None:
        """Add a memory entry to the character's memory."""
        self.memory.append(memory_entry)
    
    def __init__(self, **data):
        props = dict(data.get('properties') or {})

        if 'definition' not in data and data.get('description'):
            data['definition'] = data.get('description')

        if 'stats' in data and 'stats' not in props:
            props['stats'] = dict(data.get('stats') or {})

        if 'inventory' in data and 'inventory' not in props:
            props['inventory'] = list(data.get('inventory') or [])

        if 'status' in data and 'status' not in props:
            props['status'] = list(data.get('status') or [])

        data['properties'] = props
        
        # Ensure status exists in properties
        if 'status' not in data['properties']:
            data['properties']['status'] = []
        
        super().__init__(**data)


class StatsDisplayItem(BaseModel):
    """A single stat item to display in the status panel."""
    label: str
    format: str  # e.g., "{hp}/{max_hp}"
    values: Dict[str, str] = Field(default_factory=dict)  # e.g., {"hp": "{$players...}", "max_hp": "..."}


class StatusDisplayConfig(BaseModel):
    """Configuration for the status display panel."""
    template: Optional[str] = None  # Template ID to inherit from
    stats: List[StatsDisplayItem] = Field(default_factory=list)  # Additive stats
    stats_override: List[StatsDisplayItem] = Field(default_factory=list)  # Override template stats by label


class Story(BaseModel):
    """A complete story with nodes and actions."""
    id: str
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    start_node_id: str
    initial_variables: Dict[str, Any] = Field(default_factory=dict)
    triggers: List[Trigger] = Field(default_factory=list)
    nodes: Dict[str, StoryNode] = Field(default_factory=dict)
    objects: Optional[List[StoryObject]] = Field(default_factory=list)
    actions: List[StoryAction] = Field(default_factory=list)
    functions: Dict[str, Function] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    characters: Optional[List[Character]] = None
    player_character_defaults: Optional[Union[Dict[str, Any], str]] = None
    status_display_config: Optional[StatusDisplayConfig] = None
    forms: Dict[str, 'FormDefinition'] = Field(default_factory=dict)  # Form definitions
    genre: Optional[str] = None  # e.g., "open-world fantasy adventure", "fairy tale for kids"
    connections: Optional[ConnectionGraph] = None
    connection_graph_source_md5: Optional[str] = None
    
    def get_node(self, node_id: str) -> Optional[StoryNode]:
        """Get a node by ID.
        
        Args:
            node_id (str): The ID of the node.
            
        Returns:
            Optional[StoryNode]: The node, or None if not found.
        """
        return self.nodes.get(node_id)
    
    def get_npc(self, npc_id: str) -> Optional[Character]:
        """Get an NPC (non-playable Character) by ID."""
        if self.characters:
            for char in self.characters:
                if char.id == npc_id and not char.is_playable:
                    return char
        return None

    def get_character(self, character_id: str) -> Optional[Character]:
        """Get a character by ID."""
        if self.characters:
            for char in self.characters:
                if char.id == character_id:
                    return char
        return None

    def get_object(self, object_id: str) -> Optional[StoryObject]:
        """Get an object definition by ID from any node or the global object list."""
        # First, check in the global objects list
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        # If not found, check in all nodes
        for node in self.nodes.values():
            for obj in node.objects:
                if obj.id == object_id:
                    return obj
        return None

    def get_form(self, form_id: str) -> Optional['FormDefinition']:
        """Get a form definition by ID.
        
        Args:
            form_id: The ID of the form.
            
        Returns:
            The form definition, or None if not found.
        """
        return self.forms.get(form_id)

    def get_connections_for_entities(self, entity_ids: Set[str]) -> List[Connection]:
        if not self.connections:
            return []
        return self.connections.collect_neighborhood(entity_ids)

    def get_action(self, node_id: Optional[str], action_id: str) -> Optional[StoryAction]:
        """Get an action by ID, checking the node first, then the global list."""
        logger.debug(f"Searching for action '{action_id}' in node '{node_id}'. Global actions available: {[a.id for a in self.actions]}")
        if node_id:
            node = self.get_node(node_id)
            if node:
                action = node.get_action_by_id(action_id)
                if action:
                    return action
        
        # Fallback to global actions
        for action in self.actions:
            if action.id == action_id:
                return action
        
        return None
    
    def get_available_actions(self, node_id: str, game_state: 'GameState', player_id: str) -> List[StoryAction]:
        """Get the available actions from a node in the current state."""
        node = self.get_node(node_id)
        if node:
            return node.get_available_actions(game_state, player_id)
        return []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the story to a dictionary."""
        return self.dict()

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert the story to a JSON schema."""
        return self.schema()

    def validate(self) -> List[str]:
        """Validate the story structure.
        
        Returns:
            List[str]: A list of validation errors, or an empty list if valid.
        """
        errors = []
        
        # Check if start node exists
        if self.start_node_id not in self.nodes:
            errors.append(f"Start node '{self.start_node_id}' not found")
        
        return errors



def _merge_story_data(base_data: Dict[str, Any], include_data: Dict[str, Any]) -> Dict[str, Any]:
    """Merge included story data into base story data.
    
    - Dict values (like 'nodes') are merged by key
    - List values (like 'characters', 'objects') are extended
    - Scalar values from includes do not override base values
    
    Args:
        base_data: The base story data (from main.yaml)
        include_data: The included file data to merge
        
    Returns:
        Merged story data
    """
    # Keys that should be merged as dicts
    dict_merge_keys = {'nodes', 'functions', 'forms', 'initial_variables', 'metadata'}
    
    # Keys that should be merged as lists
    list_merge_keys = {'characters', 'objects', 'triggers', 'actions', 'connections'}
    
    for key, value in include_data.items():
        if key in dict_merge_keys and isinstance(value, dict):
            # Merge dict values
            if key not in base_data:
                base_data[key] = {}
            if isinstance(base_data[key], dict):
                base_data[key].update(value)
        elif key in list_merge_keys and isinstance(value, list):
            # Extend list values
            if key not in base_data:
                base_data[key] = []
            if isinstance(base_data[key], list):
                base_data[key].extend(value)
        elif key not in base_data:
            # Only add new keys, don't override existing ones
            base_data[key] = value
    
    return base_data


def _canonicalize_for_connection_graph_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize_for_connection_graph_hash(value[key])
            for key in sorted(value.keys(), key=str)
            if key not in {"connections", "connection_graph_source_md5"}
        }
    if isinstance(value, list):
        return [_canonicalize_for_connection_graph_hash(item) for item in value]
    return value


def compute_connection_graph_source_md5(story_data: Dict[str, Any]) -> str:
    canonical = _canonicalize_for_connection_graph_hash(story_data or {})
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def describe_connection_graph_status(story_data: Dict[str, Any]) -> Dict[str, Any]:
    current_md5 = compute_connection_graph_source_md5(story_data)
    stored_md5 = story_data.get("connection_graph_source_md5")
    connections = story_data.get("connections")
    has_connections = isinstance(connections, list) and len(connections) > 0

    if not has_connections or not stored_md5:
        status = "missing"
    elif stored_md5 != current_md5:
        status = "stale"
    else:
        status = "current"

    return {
        "current_connection_graph_source_md5": current_md5,
        "connection_graph_source_md5": stored_md5,
        "connection_graph_status": status,
    }


def _load_yaml_with_includes(file_path: str, loaded_files: Optional[set] = None) -> Dict[str, Any]:
    """Load a YAML file and process any 'includes' directive.
    
    Args:
        file_path: Path to the YAML file
        loaded_files: Set of already loaded file paths (for circular dependency detection)
        
    Returns:
        Merged story data from main file and all includes
    """
    if loaded_files is None:
        loaded_files = set()
    
    # Normalize path for comparison
    normalized_path = os.path.normpath(os.path.abspath(file_path))
    
    if normalized_path in loaded_files:
        logger.warning(f"Circular include detected, skipping: {file_path}")
        return {}
    
    loaded_files.add(normalized_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        story_data = yaml.safe_load(f) or {}
    
    # Process includes
    includes = story_data.pop('includes', None)
    if includes and isinstance(includes, list):
        base_dir = os.path.dirname(file_path)
        
        for include_file in includes:
            include_path = os.path.join(base_dir, include_file)
            
            if not os.path.exists(include_path):
                logger.warning(f"Included file not found: {include_path}")
                continue
                
            try:
                logger.debug(f"Loading included file: {include_path}")
                include_data = _load_yaml_with_includes(include_path, loaded_files)
                story_data = _merge_story_data(story_data, include_data)
            except Exception as e:
                logger.error(f"Error loading included file {include_path}: {e}")
    
    return story_data


def load_story_from_file(file_path: str) -> Story:
    """Load a story from a YAML or JSON file.
    
    Supports the 'includes' directive for modular story organization.
    When 'includes' is present, the listed files are loaded and merged.
    
    Args:
        file_path (str): The path to the story file.
        
    Returns:
        Story: The loaded story.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Story file not found: {file_path}")
    
    if file_path.endswith(".yaml") or file_path.endswith(".yml"):
        # Use include-aware loader for YAML files
        story_data = _load_yaml_with_includes(file_path)
    elif file_path.endswith(".json"):
        with open(file_path, 'r', encoding='utf-8') as f:
            story_data = json.load(f)
    else:
        raise ValueError("Unsupported file format. Use YAML or JSON.")
    
    # Extract story metadata
    story_id = story_data.get("id", os.path.splitext(os.path.basename(file_path))[0])
    name = story_data.get("name", story_data.get("title", "Untitled Story"))
    description = story_data.get("description", "")
    version = story_data.get("version", "1.0")
    author = story_data.get("author", "Unknown")
    start_node_id = story_data.get("start_node_id", "start")
    metadata = story_data.get("metadata", {})
    initial_variables = story_data.get("initial_variables", {})
    player_character_defaults = story_data.get("player_character_defaults")
    raw_connections = story_data.get("connections") or []
    connection_graph_source_md5 = story_data.get("connection_graph_source_md5")

    # Load triggers
    triggers_data = story_data.get("triggers", [])
    triggers = [Trigger(**trigger_data) for trigger_data in triggers_data]
    
    # Load objects
    objects_data = story_data.get("objects") or []
    objects = [StoryObject(**obj_data) for obj_data in objects_data]

    # Load actions
    actions_data = story_data.get("actions", [])
    actions = [StoryAction(**action_data) for action_data in actions_data]

    # Load compiled connections
    connections = None
    if isinstance(raw_connections, list) and raw_connections:
        connection_entries = [Connection(**conn_data) for conn_data in raw_connections]
        connections = ConnectionGraph(connections=connection_entries)

    # Load functions (supports both list and dict formats)
    functions_data = story_data.get("functions") or {}
    if isinstance(functions_data, list):
        functions = {func_data["id"]: Function(**func_data) for func_data in functions_data}
    elif isinstance(functions_data, dict):
        functions = {}
        for func_id, func_data in functions_data.items():
            if isinstance(func_data, dict):
                if "id" not in func_data:
                    func_data["id"] = func_id
                functions[func_id] = Function(**func_data)
    else:
        functions = {}

    # Load nodes
    nodes = {}
    nodes_data = story_data.get("nodes", {}) or {}
    for node_id, node_data in nodes_data.items():
        # Load actions for the node
        node_actions_data = node_data.get("actions") or []
        node_actions = [StoryAction(**action_data) for action_data in node_actions_data]
        
        # Load object instances for the node
        node_objects_data = node_data.get("objects") or []
        node_objects = [StoryObject(**obj_data) for obj_data in node_objects_data]

        # Create the node
        node_init_data = node_data.copy()
        node_init_data['id'] = node_id
        if 'objects' not in node_init_data:
            node_init_data['objects'] = []
        if 'actions' not in node_init_data:
            node_init_data['actions'] = []

        # Assign the loaded objects to the node
        node_init_data['objects'] = node_objects

        nodes[node_id] = StoryNode(**node_init_data)
    
    # Load Characters
    characters_data = story_data.get("characters") or []
    characters = [Character(**char_data) for char_data in characters_data]

    # Load status display config
    status_display_config_data = story_data.get("status_display_config")
    status_display_config = StatusDisplayConfig(**status_display_config_data) if status_display_config_data else None

    # Load forms
    forms_data = story_data.get("forms", {})
    forms = {}
    for form_id, form_data in forms_data.items():
        try:
            # Add the id to the form data if not present
            form_data_with_id = form_data.copy()
            form_data_with_id['id'] = form_id
            
            # Parse on_submit if present
            if 'on_submit' in form_data_with_id and isinstance(form_data_with_id['on_submit'], dict):
                on_submit_data = form_data_with_id['on_submit']
                # Convert effects to Effect objects if present
                if 'effects' in on_submit_data and isinstance(on_submit_data['effects'], list):
                    on_submit_data['effects'] = [Effect(**e) if isinstance(e, dict) else e for e in on_submit_data['effects']]
                form_data_with_id['on_submit'] = FormOnSubmit(**on_submit_data)
            
            forms[form_id] = FormDefinition(**form_data_with_id)
            logger.debug(f"Loaded form '{form_id}' with {len(form_data.get('fields', []))} fields")
        except Exception as e:
            logger.error(f"Failed to load form '{form_id}': {e}")

    # Create the story object
    story = Story(
        id=story_id,
        name=name,
        description=description,
        version=version,
        author=author,
        start_node_id=start_node_id,
        initial_variables=initial_variables,
        triggers=triggers,
        nodes=nodes,
        objects=objects,
        actions=actions,
        functions=functions,
        metadata=metadata,
        characters=characters,
        player_character_defaults=player_character_defaults,
        status_display_config=status_display_config,
        forms=forms,
        connections=connections,
        connection_graph_source_md5=connection_graph_source_md5,
    )

    errors = story.validate()
    if errors:
        logger.warning(f"Story validation errors for '{file_path}':")
        for error in errors:
            logger.warning(f"  - {error}")
    
    return story


StoryAction.update_forward_refs()
StoryNode.update_forward_refs()
Story.update_forward_refs()
StoryCondition.update_forward_refs()
DialogueChoice.update_forward_refs()
TimedEvent.update_forward_refs()
Effect.update_forward_refs()
Trigger.update_forward_refs()
Character.update_forward_refs()
FormDefinition.update_forward_refs()
FormOnSubmit.update_forward_refs()
FormField.update_forward_refs()
