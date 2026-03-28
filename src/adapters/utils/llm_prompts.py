"""LLM prompt templates for story editing and character interactions."""

from typing import Dict, Any, Optional, List


def create_intent_prompt(user_prompt: str, nodes: Dict[str, Any]) -> str:
    """Create a prompt to determine the user's intent (ADD, UPDATE, DELETE).
    
    Args:
        user_prompt: The user's request.
        nodes: Dict of existing nodes in the story.
        
    Returns:
        The formatted prompt string.
    """
    node_info = []
    for node_id, node_data in nodes.items():
        description = node_data.get('description', 'No description available.')
        node_info.append(f"- ID: {node_id}, Description: {description}")
    
    node_list = "\n".join(node_info)

    return f"""Analyze the user's request to determine the intent (ADD, UPDATE, or DELETE) and the target node.

User Request: "{user_prompt}"

Existing Nodes:
{node_list}

Respond with a JSON object in the following format:

- For ADD: {{ "action": "ADD", "payload": {{ "description": "<brief description of node to add>", "target_node_id": "<optional_target_node_id>" }} }}
- For UPDATE: {{ "action": "UPDATE", "payload": {{ "node_id": "<target_node_id>" }} }}
- For DELETE: {{ "action": "DELETE", "payload": {{ "node_id": "<target_node_id>" }} }}

Your response must be only the JSON object enclosed in a ```json block.
"""


def create_add_prompt(user_prompt: str, target_node_id: Optional[str] = None) -> str:
    """Create a prompt for generating a new story node.
    
    Args:
        user_prompt: The user's request.
        target_node_id: Optional ID of target node to connect to.
        
    Returns:
        The formatted prompt string.
    """
    return f"""You are an intelligent assistant that creates new story nodes in YAML format.

**Story Node Structure Guide:**

*   **`id`**: A unique, snake_case identifier for the node.
*   **`name`**: A human-readable title for the node.
*   **`description`**: The text that is shown to the player when they enter the node.
*   **`actions`**: A list of choices or commands available to the player in this node.
    *   **`id`**: A unique identifier for the action.
    *   **`text`**: The description of the action (used for LLM intent matching with player input).
    *   **`effects`**: A list of things that happen when the action is performed. Each item in the list is a dictionary.
        *   **`type`**: The type of effect. To connect nodes, use `goto_node`.
        *   **`target`**: The ID of the thing being affected (node, item, variable, object).

**YAML Formatting Rules:**
- Pay close attention to indentation. `effects` is a list of dictionaries, so each `- type` should be at the same indentation level.
- `target` is a key-value pair within the effect dictionary, so it must be indented under the `- type` line.

**Example of a Connected Node:**

```yaml
cave_entrance:
  id: cave_entrance
  name: Cave Entrance
  description: You are at the entrance to a dark cave.
  actions:
    - id: enter_cave
      text: Enter the dark cave
      effects:
        - type: goto_node
          target: deep_cave
```

**User Request:** "{user_prompt}"

**Task:**

Create a new story node based on the user's request. If the request mentions connecting to another node, ensure you create an action with a `goto_node` effect pointing to the target node's ID.

If a target node is specified, the new node should have an action that connects back to it.
Target Node ID: {target_node_id if target_node_id else 'N/A'}

Respond with ONLY the new node's YAML content, enclosed in a ```yaml block.
"""


def create_update_prompt(user_prompt: str, node_yaml: str) -> str:
    """Create a prompt for updating an existing story node.
    
    Args:
        user_prompt: The user's request.
        node_yaml: The current YAML content of the node.
        
    Returns:
        The formatted prompt string.
    """
    return f"""Update the provided YAML story node based on the user request.

**VERY IMPORTANT FORMATTING RULES:**
1. For any multi-line text fields like `description` or `text`, you MUST use the YAML literal block scalar style (the pipe `|` character).
2. For any single-line text fields that contain special characters (like apostrophes ' or colons :), you MUST enclose the entire string in double quotes (").

**Example of correct formatting:**
```yaml
name: "The Doctor's Study: A Mess"
description: |
  This is a long description
  that spans multiple lines.
  It preserves the newlines.
```

User Request: "{user_prompt}"

YAML to modify:
```yaml
{node_yaml}
```

Respond with ONLY the updated node's YAML content, enclosed in a ```yaml block.
"""


def create_intelligent_character_prompt(
    npc_name: str,
    npc_persona: str,
    player_state_context: str,
    conversation_history: str,
    player_input: str,
    npc_inventory: Optional[List[str]] = None,
    node_actions_context: Optional[str] = None
) -> str:
    """
    Create a prompt for intelligent character interaction with state awareness.
    
    The LLM will generate responses grounded in actual game state and can
    return structured effects to modify game state.
    """
    npc_inventory_str = ", ".join(npc_inventory) if npc_inventory else "None"
    
    # Build location services section if node actions are available
    location_services_section = ""
    if node_actions_context:
        location_services_section = f"""
### Location Services (Actions available at this location)
The following game actions exist at this location. When the player asks for something 
that matches one of these services, you MUST fulfill it by generating the appropriate 
effects. Stay in character while doing so.

{node_actions_context}

**CRITICAL — Service Fulfillment Rules:**
- When the player requests a service (ordering food/drink, buying items, asking for work), 
  you MUST generate matching game effects — not just narrative
- If a service costs currency, subtract it from the story's existing currency variable rather than inventing a new one
- If you give/serve the player a physical item (drink, food, letter, package, tool), 
  include: {{"type": "add_to_inventory", "target": "<item_id>"}} — use a snake_case id
  describing the item (e.g., "emberroot_tea", "spiced_ale", "sealed_letter")
- If a service modifies a stat, include the appropriate calculate effect
- NEVER just narrate a service without effects — the game state must reflect what happened
"""
    
    return f"""You are an intelligent game master for an AI native text based game engine. You will roleplay as an NPC while ensuring all responses are grounded in the actual game state.

## NPC Information
Name: {npc_name}

### Character Definition
The definition below contains everything about this character:
- Identity/Description: Who they are, their background
- Personality: Character traits and speech patterns
- Behavior Rules: Interaction rules with "## " headers
  - Each rule may have display text and effect JSON objects
  - Follow these rules when player actions match

{npc_persona}

### Inventory (Items NPC can give)
{npc_inventory_str}
{location_services_section}
## Player's Current State
{player_state_context}

## Recent Conversation
{conversation_history if conversation_history else "(No recent conversation)"}

## Player's Input
"{player_input}"

## Core Principles (MUST FOLLOW)

1. **Reality Grounding**: All responses must be based on the player's actual state. The player cannot use, give, show, or manipulate things they don't actually possess or have access to.

2. **Capability Boundaries**: Player actions are constrained by their current attributes. If a stat (stamina, sanity, money, etc.) is insufficient to support an action, the action should fail or be limited.

3. **Causal Consistency**: Effects can only occur when their preconditions are met. Do not assume success - determine success based on actual state.

4. **State Awareness**: The NPC can "perceive" the player's true state and should react accordingly. If the player claims to have something they don't, the NPC should show confusion or skepticism.

5. **Effect Parity**: The effects array MUST match the narrative. Every game-relevant action in the narrative needs a corresponding effect:
   - NPC serves a drink → `calculate` to charge shells + `add_to_inventory` for the drink
   - NPC gives player an item → `add_to_inventory`
   - Player pays for something → `calculate` to deduct currency
   - If no game state changes, effects can be empty (e.g., pure conversation)

## Available Effect Types (UNIFIED FORMAT)
All effects use "target" for the thing being affected and "value" for the primary value:
- {{"type": "add_to_inventory", "target": "<item_id>"}} - Give item to player
- {{"type": "remove_from_inventory", "target": "<item_id>"}} - Remove item from player (only if player has it!)
- {{"type": "set_variable", "target": "<variable_name>", "value": <value>}} - Set a game variable (string, number, or boolean)
- {{"type": "display_text", "value": "<text>", "speaker": "<optional speaker>"}} - Show additional text
- {{"type": "update_object_status", "target": "<object_id>", "add_status": ["<status_tag>"], "remove_status": ["<status_tag>"]}} - Update object status tags
- {{"type": "set_object_explicit_state", "target": "<object_id>", "value": "<new explicit_state>"}} - Update object description
- {{"type": "goto_node", "target": "<node_id>"}} - Teleport player to another location
- {{"type": "calculate", "target": "<variable_name>", "operation": "<add|subtract|multiply|divide>", "value": <number>}} - Math operation on a variable

## Response Format
Respond with ONLY a JSON object:
{{
  "narrative": "What the NPC SAYS (first-person dialogue). Keep length proportional to player input.",
  "effects": [
    // Array of effects to execute. Can be empty if no state changes occur.
  ],
  "action_valid": true/false,
  "reasoning": "Brief explanation of why this action succeeded or failed based on game state"
}}

## Important Notes

### Response Style
- **First-Person Perspective**: The NPC speaks in first person ("I..." not "She..."). Do NOT use third-person narrator style.
- **Dialogue Format**: Write what the NPC SAYS, not a description of the NPC. 
  - ❌ Wrong: "Sarah stands up and looks at you, saying: 'Hello'"
  - ✅ Correct: "Hello. Are you here to cross the mountain?"

### Adaptive Length
- **Match response length to input complexity**:
  - Simple greeting ("hello") → Short response (1-2 sentences)
  - Simple question → Concise answer (2-3 sentences)
  - Complex question or request → Detailed response (3-5 sentences)
- Do NOT pad responses with unnecessary descriptions or actions

### Language & Immersion
- The narrative MUST be in the SAME LANGUAGE as the player's input
- If player input is in Chinese, respond in Chinese
- If player input is in English, respond in English
- Do not break character in the narrative
- Do not mention "game state" or "inventory" directly - stay immersive
- Follow the persona's speaking style and personality
- Follow the action rules to determine what information to reveal and what effects to generate

Generate your response:"""


def create_action_validation_prompt(
    player_input: str,
    player_state_context: str,
    available_actions: str
) -> str:
    """
    Create a prompt to validate and match player input to available actions.
    
    Args:
        player_input: What the player typed
        player_state_context: Formatted player state
        available_actions: List of available actions
        
    Returns:
        The formatted prompt string
    """
    return f"""You are validating a player's input in this AI native text based game engine.

## Player's Current State
{player_state_context}

## Available Actions
{available_actions}

## Player's Input
"{player_input}"

## Task
1. Determine if the player's intended action is valid given their current state
2. If valid, match to an available action or indicate it's a free-form valid action
3. If invalid, explain why (e.g., "Player doesn't have the required item")

Respond with JSON:
{{
  "is_valid": true/false,
  "matched_action_id": "<action_id or null>",
  "validation_reason": "Why the action is valid or invalid",
  "suggested_response": "If invalid, a brief in-character response explaining the failure"
}}
"""

