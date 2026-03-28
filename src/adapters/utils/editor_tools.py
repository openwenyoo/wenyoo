"""Editor-specific tool definitions for AI Assistant function calling.

This module defines the tools available to the LLM for editing story graphs
in the visual editor. Each tool has a comprehensive description to help
the LLM understand the correct format and avoid common mistakes.
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Cache for format documentation
_FORMAT_DOCS: str = None


def get_format_documentation() -> str:
    """Load and cache comprehensive format documentation.
    
    Returns:
        Combined node and story format documentation string.
    """
    global _FORMAT_DOCS
    if _FORMAT_DOCS is not None:
        return _FORMAT_DOCS
    
    try:
        with open("prompts/node_format_description.md", 'r', encoding='utf-8') as f:
            node_format = f.read()
        with open("prompts/story_format_description.md", 'r', encoding='utf-8') as f:
            story_format = f.read()
        _FORMAT_DOCS = f"""
# NODE FORMAT SPECIFICATION
{node_format}

# STORY FORMAT SPECIFICATION  
{story_format}
"""
        logger.info("Loaded format documentation for editor tools")
    except FileNotFoundError as e:
        logger.warning(f"Could not load format documentation: {e}")
        _FORMAT_DOCS = "Format documentation not available. Follow standard YAML structure."
    except Exception as e:
        logger.error(f"Error loading format documentation: {e}")
        _FORMAT_DOCS = "Format documentation not available."
    
    return _FORMAT_DOCS


# Effect type examples for tool descriptions - comprehensive list
EFFECT_EXAMPLES = """
EFFECT TYPES - Use variety for engaging gameplay:

📝 Text & Display:
- display_text: {"type": "display_text", "text": "Message", "speaker": "NPC Name"} - Show text/dialogue
- present_choice: {"type": "present_choice", "text": "Question?", "choices": [{"text": "Option", "effects": [...]}]} - Player choices

🚶 Navigation:
- goto_node: {"type": "goto_node", "target": "node_id"} - Move to node (no triggers)
- move_to_node: {"type": "move_to_node", "target": "node_id"} - Move with trigger execution

🔢 Variables & State:
- set_variable: {"type": "set_variable", "target": "var_name", "value": true} - Set variable
- calculate: {"type": "calculate", "target": "sanity", "operation": "subtract", "value": 10} - Math on variables

🎒 Inventory:
- add_to_inventory: {"type": "add_to_inventory", "target": "key"} - Give item
- remove_from_inventory: {"type": "remove_from_inventory", "target": "key"} - Take item

🎭 Objects & Scenes:
- update_object_status: {"type": "update_object_status", "target": "door", "add_status": ["open"], "remove_status": ["locked"]} - Update object status tags
- set_object_explicit_state: {"type": "set_object_explicit_state", "target": "door", "value": "The door stands open."} - Set object display text
- set_node_description: {"type": "set_node_description", "target": "room", "value": "New description"} - Update node text

🎲 Dice & Chance:
- random_number: {"type": "random_number", "target": "roll", "min_value": 1, "max_value": 100} - Random number
- dice_roll: {"type": "dice_roll", "stat": "luck", "difficulty": 50, "success_effects": [...], "failure_effects": [...]} - Skill check

🔀 Control Flow:
- conditional: {"type": "conditional", "condition": {...}, "if_effects": [...], "else_effects": [...]} - Branching logic

🤖 Dynamic Content:
- llm_generate: {"type": "llm_generate", "prompt": "Describe the scene", "output_variable": "scene_desc"} - AI-generated text
"""

# Tips for creating engaging stories
STORY_QUALITY_TIPS = """
TIPS FOR ENGAGING STORIES:

1. Use varied effects to make gameplay interesting:
   - Don't just use goto_node + display_text for everything
   - Add stat changes (sanity, health, reputation) for consequences
   - Use conditional effects for different outcomes based on state
   - Use dice_roll for uncertainty and tension

2. Track meaningful state with variables:
   - Story flags: visited_castle, met_wizard, found_clue
   - Stats: sanity, health, gold, reputation
   - Counters: days_passed, clues_found

3. Make actions have consequences:
   - Successful actions might boost stats or give items
   - Failed checks might decrease stats or block paths
   - Choices should feel meaningful

4. Consider adding atmosphere:
   - pre_enter triggers can generate dynamic descriptions
   - Objects in nodes add interactivity
   - NPCs make locations feel alive
"""

# Action structure reminder
ACTION_STRUCTURE = """
Action structure (CRITICAL):
{
  "id": "snake_case_id",
  "text": "Description shown to player",  // NOT 'name' or 'label'!
  "intent": "Optional natural-language behavior interpreted by the Architect",
  "conditions": [],                        // Optional
  "effects": [{"type": "goto_node", "target": "next"}]  // Optional when intent is provided
}
"""


EDITOR_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_node",
            "description": f"""Create a new story node in the graph.

CRITICAL FORMAT RULES:
- id: Use snake_case (e.g., 'forest_clearing', 'dark_cave')
- name: Human-readable title
- explicit_state: Text shown when player enters this location
- definition: Static rules and background the Architect reads
- actions: Array of available player actions

{ACTION_STRUCTURE}

{EFFECT_EXAMPLES}

COMMON MISTAKES TO AVOID:
- Using 'name' instead of 'text' for actions
- Using wrong field names (always use 'target' for the thing being affected)
- Using 'effect' instead of 'type' in effects""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier (e.g., 'forest_clearing', 'secret_room')"
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable display name (e.g., 'Forest Clearing', 'The Secret Room')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Legacy alias for explicit_state. Main text shown when player enters."
                    },
                    "definition": {
                        "type": "string",
                        "description": "Static rules, lore, and interaction guidance for the Architect."
                    },
                    "explicit_state": {
                        "type": "string",
                        "description": "Current player-visible scene description."
                    },
                    "implicit_state": {
                        "type": "string",
                        "description": "Hidden AI-only state and context."
                    },
                    "properties": {
                        "type": "object",
                        "description": "Mechanical state such as status tags and custom flags."
                    },
                    "actions": {
                        "type": "array",
                        "description": "Actions available to player. Each needs: id, text (NOT name!), plus either intent or effects.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Unique snake_case identifier"},
                                "text": {"type": "string", "description": "Action description (NOT 'name' or 'label')"},
                                "intent": {"type": "string", "description": "Optional natural-language behavior interpreted by the Architect"},
                                "conditions": {"type": "array", "description": "Optional conditions"},
                                "effects": {
                                    "type": "array",
                                    "description": "Effects when action is taken. Use 'type' not 'effect'. Optional if intent is provided."
                                }
                            },
                            "required": ["id", "text"]
                        }
                    },
                    "objects": {
                        "type": "array",
                        "description": "Objects in this location using the DSPP model",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "definition": {"type": "string", "description": "Static description and interaction rules"},
                                "explicit_state": {"type": "string", "description": "Current visible state"},
                                "implicit_state": {"type": "string", "description": "Hidden internal state"},
                                "properties": {"type": "object", "description": "Mechanical state: status, contains, custom data"}
                            }
                        }
                    },
                    "triggers": {
                        "type": "array",
                        "description": "Automatic triggers. Types: pre_enter, post_enter, pre_leave, post_leave",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["pre_enter", "post_enter", "pre_leave", "post_leave"]
                                },
                                "intent": {"type": "string", "description": "Optional natural-language behavior interpreted by the Architect"},
                                "conditions": {"type": "array"},
                                "effects": {"type": "array"}
                            }
                        }
                    },
                    "is_ending": {
                        "type": "boolean",
                        "description": "True if this node ends the game",
                        "default": False
                    }
                },
                "required": ["id", "name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": """Update an existing node's properties.

IMPORTANT: Only provide fields you want to change.
For arrays (actions, objects, triggers), the provided array REPLACES the existing one.

RECOMMENDED WORKFLOW:
1. First call get_node to see current content
2. Then call update_node with the complete arrays you want

This ensures you don't accidentally delete existing actions.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID of the node to update (required)"
                    },
                    "name": {
                        "type": "string",
                        "description": "New display name (optional)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Legacy alias for explicit_state (optional)"
                    },
                    "definition": {
                        "type": "string",
                        "description": "Static rules and lore for the node"
                    },
                    "explicit_state": {
                        "type": "string",
                        "description": "Current player-visible description"
                    },
                    "implicit_state": {
                        "type": "string",
                        "description": "Hidden AI-only state"
                    },
                    "properties": {
                        "type": "object",
                        "description": "Mechanical state for the node"
                    },
                    "actions": {
                        "type": "array",
                        "description": "Complete actions array - REPLACES existing actions"
                    },
                    "objects": {
                        "type": "array",
                        "description": "Complete objects array - REPLACES existing objects"
                    },
                    "triggers": {
                        "type": "array",
                        "description": "Complete triggers array - REPLACES existing triggers"
                    },
                    "is_ending": {
                        "type": "boolean",
                        "description": "Whether this is an ending node"
                    }
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_action_to_node",
            "description": f"""Add a single action to an existing node WITHOUT replacing other actions.

Use this when you want to add a new action while preserving all existing ones.
This is safer than update_node when you just need to add one action.

{ACTION_STRUCTURE}

Example: Adding a link to a new location:
{{
  "node_id": "library",
  "action": {{
    "id": "go_to_secret_room",
    "text": "Push the hidden bookshelf",
    "intent": "Optional natural-language behavior interpreted by the Architect",
    "effects": [
      {{"type": "display_text", "text": "The bookshelf swings open!"}},
      {{"type": "goto_node", "target": "secret_room"}}
    ]
  }}
}}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "ID of the node to add the action to"
                    },
                    "action": {
                        "type": "object",
                        "description": "The action to add",
                        "properties": {
                            "id": {"type": "string", "description": "Unique action ID"},
                            "text": {"type": "string", "description": "Action text (NOT 'name')"},
                            "intent": {"type": "string", "description": "Optional natural-language behavior interpreted by the Architect"},
                            "conditions": {"type": "array"},
                            "effects": {"type": "array", "description": "Effects to execute. Optional when intent is provided."}
                        },
                        "required": ["id", "text"]
                    }
                },
                "required": ["node_id", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": """Delete a node from the story graph.

This also removes all edges (connections) to and from this node.
Use with caution - this action cannot be undone within the AI session.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID of the node to delete"
                    }
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_node",
            "description": """Get the current data of a node.

ALWAYS use this before update_node to see existing content!
This prevents accidentally deleting existing actions, objects, or triggers.

Returns the complete node data including all actions, objects, and triggers.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID of the node to retrieve"
                    }
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_nodes",
            "description": """List all nodes in the story graph.

Returns a list of {id, name} for all nodes.
Use this to understand the story structure before making changes.""",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_object_to_node",
            "description": """Add an object to a node without replacing existing objects.

Object structure:
{
  "id": "old_chest",
  "name": "Old Chest",
  "definition": "[Description]\\nA dusty wooden chest.\\n\\n[Interaction Rules]\\n## Open the chest\\nWhen player opens:\\n- Display: The chest opens...\\n- Effect: {\\"type\\": \\"update_object_status\\", ...}",
  "explicit_state": "A dusty wooden chest sits in the corner, its lock rusted but intact.",
  "implicit_state": "",
  "properties": {"status": ["closed", "locked"]}
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "ID of the node to add the object to"
                    },
                    "object": {
                        "type": "object",
                        "description": "The object to add",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "definition": {"type": "string", "description": "Static description and interaction rules"},
                            "explicit_state": {"type": "string", "description": "Current visible state"},
                            "implicit_state": {"type": "string", "description": "Hidden internal state"},
                            "properties": {"type": "object", "description": "Mechanical state: status, contains, etc."}
                        },
                        "required": ["id", "name"]
                    }
                },
                "required": ["node_id", "object"]
            }
        }
    }
]


# =============================================================================
# CHARACTER TOOLS - For managing NPCs and playable characters
# =============================================================================

CHARACTER_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": """Create a new character (NPC or playable).

Character structure:
{
  "id": "unique_snake_case_id",
  "name": "Display Name",
  "definition": "[Identity]\\nCharacter background and identity...\\n\\n[Behavior Rules]\\nDescribe how the character behaves and responds in this story.",
  "explicit_state": "Current visible state of the character",
  "implicit_state": "Hidden internal state (for AI context)",
  "is_playable": false,
  "properties": {
    "location": "location_id",
    "status": [],
    "inventory": [],
    "affinity": 50,
    "stats": {"hp": 100, "max_hp": 100}
  }
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique snake_case identifier"},
                    "name": {"type": "string", "description": "Display name"},
                    "definition": {"type": "string", "description": "Static character information and behavior rules"},
                    "explicit_state": {"type": "string", "description": "Dynamic, player-visible current state"},
                    "implicit_state": {"type": "string", "description": "Dynamic, hidden internal state"},
                    "is_playable": {"type": "boolean", "default": False},
                    "properties": {
                        "type": "object",
                        "description": "Mechanical state (location, status, inventory, affinity, stats)"
                    }
                },
                "required": ["id", "name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_character",
            "description": """Update an existing character's properties.

Use get_character first to see current content if you need to preserve existing data.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of character to update (required)"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "definition": {"type": "string", "description": "Static character information and behavior rules"},
                    "is_playable": {"type": "boolean"},
                    "properties": {"type": "object"},
                    "parameters": {"type": "object"},
                    "stats": {"type": "object"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_character",
            "description": "Delete a character from the story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of character to delete"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_character",
            "description": "Get the current data of a character. Use before update_character to see existing content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of character to retrieve"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "List all characters in the story. Returns {id, name, is_playable} for each.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]

# =============================================================================
# OBJECT TOOLS - For managing global objects
# =============================================================================

OBJECT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_object",
            "description": """Create a new global object definition.

Entity fields:
- definition: Static description of what the object IS (material, capabilities, interaction rules)
- explicit_state: Dynamic, player-visible current appearance
- implicit_state: Dynamic, hidden internal state
- properties: Mechanical state (status tags, contains, custom data)

Object structure:
{
  "id": "unique_snake_case_id",
  "name": "Display Name",
  "definition": "Description of the object, its properties, and interaction rules",
  "explicit_state": "Current visible state shown to player",
  "properties": {"status": []}
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique snake_case identifier"},
                    "name": {"type": "string", "description": "Display name"},
                    "definition": {"type": "string", "description": "Static description of object and interaction rules"},
                    "explicit_state": {"type": "string", "description": "Current visible state"},
                    "implicit_state": {"type": "string", "description": "Hidden internal state"},
                    "properties": {"type": "object", "description": "Mechanical state: status, contains, custom data"}
                },
                "required": ["id", "name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_object",
            "description": "Update an existing object. Only provide fields you want to change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of object to update (required)"},
                    "name": {"type": "string"},
                    "definition": {"type": "string", "description": "Static description and interaction rules"},
                    "explicit_state": {"type": "string", "description": "Current visible state"},
                    "implicit_state": {"type": "string", "description": "Hidden internal state"},
                    "properties": {"type": "object", "description": "Mechanical state: status, contains, custom data"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_object",
            "description": "Delete an object from the story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of object to delete"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_object",
            "description": "Get the current data of an object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID of object to retrieve"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_objects",
            "description": "List all global objects. Returns {id, name, has_definition} for each.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

# =============================================================================
# PARAMETER TOOLS - For managing initial_variables / game parameters
# =============================================================================

PARAMETER_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_parameter",
            "description": """Set a game parameter (initial_variable).

Parameters can be:
- Strings: "player_name": "Hero"
- Numbers: "starting_gold": 100
- Booleans: "has_tutorial": true
- Multiline text (lorebook): "lore_world": "A fantasy world..."

For lorebook entries, use lore_ prefix (e.g., lore_writing_style, lore_world_setting).""",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Parameter name (snake_case)"},
                    "value": {
                        "description": "Parameter value (string, number, boolean, or object)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of what this parameter does"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_parameter",
            "description": "Delete a game parameter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Parameter name to delete"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_parameter",
            "description": "Get the value of a parameter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Parameter name to retrieve"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_parameters",
            "description": "List all parameters. Returns {key, type, preview} for each.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_lorebook_entry",
            "description": """Create a lorebook entry (multiline text parameter for LLM prompts).

Lorebook entries are used to provide context to LLM-generated content.
Common entries: lore_writing_style, lore_world_setting, lore_protagonist, lore_npc_guidelines""",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entry name without lore_ prefix (e.g., 'writing_style' becomes 'lore_writing_style')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Multiline content for the lorebook entry"
                    }
                },
                "required": ["name", "content"]
            }
        }
    }
]


# =============================================================================
# TOOL RETRIEVAL FUNCTIONS
# =============================================================================

# All tools combined
ALL_TOOLS = EDITOR_TOOLS + CHARACTER_TOOLS + OBJECT_TOOLS + PARAMETER_TOOLS

# Mode to tools mapping
TOOLS_BY_MODE = {
    "nodes": EDITOR_TOOLS,
    "characters": CHARACTER_TOOLS,
    "objects": OBJECT_TOOLS,
    "parameters": PARAMETER_TOOLS,
    "story_creation": ALL_TOOLS,  # Full story creation with all tools
    "all": ALL_TOOLS
}


def get_tools_for_mode(mode: str) -> List[Dict[str, Any]]:
    """Get tools appropriate for the editing mode.
    
    Args:
        mode: One of 'nodes', 'characters', 'objects', 'parameters', 'all'
        
    Returns:
        List of tool definitions for that mode
    """
    return TOOLS_BY_MODE.get(mode, EDITOR_TOOLS)


def get_tool_names(mode: str = "all") -> List[str]:
    """Get list of available tool names for a mode."""
    tools = get_tools_for_mode(mode)
    return [tool["function"]["name"] for tool in tools]


def get_all_tool_names() -> List[str]:
    """Get list of all available tool names."""
    return [tool["function"]["name"] for tool in ALL_TOOLS]
