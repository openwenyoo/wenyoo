"""LLM generation and story editing routes."""

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from typing import Any, Optional, List, Dict, AsyncGenerator
import os
import re
import json
import tempfile
import yaml
import logging
import asyncio

from ..utils.llm_prompts import create_intent_prompt, create_add_prompt, create_update_prompt
from ..utils.editor_tools import get_format_documentation, get_tools_for_mode
from ..utils.editor_function_executor import EditorFunctionExecutor, SSEEvent, EventType
from ..utils.editor_language import EDITOR_PROMPT_LANGUAGE_SECTION
from src.utils.name_generator import generate_name

logger = logging.getLogger(__name__)


def register_llm_routes(app: FastAPI, game_kernel: Any, story_manager: Any):
    """Register LLM-related routes on the FastAPI app.
    
    Args:
        app: The FastAPI application.
        game_kernel: The game kernel instance.
        story_manager: The story manager instance.
    """
    
    @app.post("/api/llm/generate")
    async def llm_generate(request: Request):
        """Generate content using LLM for AI Assistant (editor only).
        
        This endpoint is intended for the story editor's AI features.
        Requests are validated to ensure they originate from the editor.
        """
        try:
            json_data = await request.json()
            prompt = json_data.get("prompt")
            
            if not prompt:
                return {"error": "Prompt is required"}

            MAX_PROMPT_LENGTH = 50000
            if len(prompt) > MAX_PROMPT_LENGTH:
                return {"error": f"Prompt too long (max {MAX_PROMPT_LENGTH} characters)."}
            
            if not game_kernel or not game_kernel.llm_provider:
                return {"error": "LLM provider not configured"}
            
            result = await game_kernel.llm_provider.generate_response(prompt)
            
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/api/story/{story_id}/edit-with-llm")
    async def edit_story_with_llm(story_id: str, request: Request):
        """Edit a story using LLM based on user prompt."""
        json_data = await request.json()
        prompt = json_data.get("prompt")
        temp_path = json_data.get("temp_path")

        path_to_read = _get_story_path(temp_path, story_id, story_manager)
        if isinstance(path_to_read, dict):  # Error response
            return path_to_read

        with open(path_to_read, "r", encoding="utf-8") as f:
            story_yaml = f.read()

        if not game_kernel.llm_provider:
            return {"error": "LLM provider not configured"}

        try:
            story_data = yaml.safe_load(story_yaml)
            nodes = story_data.get('nodes', {})

            # 1. Determine user intent (ADD, UPDATE, DELETE)
            intent_prompt = create_intent_prompt(prompt, nodes)
            intent_response_str = await game_kernel.llm_provider.generate_response(intent_prompt)
            
            match = re.search(r"```json(.*?)```", intent_response_str, re.DOTALL)
            json_str = match.group(1) if match else intent_response_str
            
            try:
                intent_data = json.loads(json_str)
                action = intent_data.get("action")
                payload = intent_data.get("payload")
            except json.JSONDecodeError:
                logger.error(f"LLM intent response is not valid JSON: {json_str}")
                return {"error": "Failed to understand the requested change. Could you be more specific?"}

            # 2. Perform the action
            if action == "ADD":
                target_node_id = payload.get("target_node_id")
                add_prompt = create_add_prompt(prompt, target_node_id=target_node_id)
                new_node_yaml = await game_kernel.llm_provider.generate_response(add_prompt)
                
                match = re.search(r"```yaml(.*?)```", new_node_yaml, re.DOTALL)
                yaml_str = match.group(1) if match else new_node_yaml
                new_node_data = yaml.safe_load(yaml_str)

                if isinstance(new_node_data, dict) and len(new_node_data) == 1:
                    new_node_data = next(iter(new_node_data.values()))

                new_node_id = new_node_data.get("id", generate_name())
                if "id" not in new_node_data:
                    new_node_data["id"] = new_node_id
                
                story_data.setdefault('nodes', {})[new_node_id] = new_node_data

            elif action == "UPDATE":
                node_id = payload.get("node_id")
                if not node_id or node_id not in story_data.get('nodes', {}):
                    return {"error": f"Node '{node_id}' not found for update."}

                node_to_update = story_data['nodes'][node_id]
                node_yaml = yaml.dump(node_to_update, allow_unicode=True, sort_keys=False)
                
                update_prompt = create_update_prompt(prompt, node_yaml)
                modified_node_yaml = await game_kernel.llm_provider.generate_response(update_prompt)

                match = re.search(r"```yaml(.*?)```", modified_node_yaml, re.DOTALL)
                yaml_str = match.group(1) if match else modified_node_yaml
                modified_node_data = yaml.safe_load(yaml_str)

                new_id = modified_node_data.get('id', node_id)
                if node_id != new_id:
                    del story_data['nodes'][node_id]
                
                story_data['nodes'][new_id] = modified_node_data

            elif action == "DELETE":
                node_id = payload.get("node_id")
                if not node_id or node_id not in story_data.get('nodes', {}):
                    return {"error": f"Node '{node_id}' not found for deletion."}
                del story_data['nodes'][node_id]

            else:
                return {"error": "Could not determine the action to perform (ADD, UPDATE, DELETE)."}

            # 3. Validation and Saving
            new_story_yaml = yaml.dump(story_data, allow_unicode=True, sort_keys=False)
            from src.models.story_models import Story
            validated_data = yaml.safe_load(new_story_yaml)
            Story(**validated_data)

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml', encoding='utf-8') as temp_file:
                temp_file.write(new_story_yaml)
                new_temp_path = temp_file.name
            
            logger.info(f"AI generated story draft saved to temporary file: {new_temp_path}")
            return {"success": True, "temp_path": new_temp_path}

        except Exception as e:
            logger.error(f"Error editing story {story_id} with LLM: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/api/story/{story_id}/edit-nodes-with-llm")
    async def edit_nodes_with_llm(story_id: str, request: Request):
        """Edit specific nodes using LLM."""
        json_data = await request.json()
        prompt = json_data.get("prompt")
        nodes = json_data.get("nodes")
        temp_path = json_data.get("temp_path")

        path_to_read = _get_story_path(temp_path, story_id, story_manager)
        if isinstance(path_to_read, dict):  # Error response
            return path_to_read

        with open(path_to_read, "r", encoding="utf-8") as f:
            story_yaml = f.read()

        if not game_kernel.llm_provider:
            return {"error": "LLM provider not configured"}

        try:
            story_data = yaml.safe_load(story_yaml)
            
            # Create a focused prompt for the LLM
            nodes_yaml = yaml.dump(nodes, allow_unicode=True, sort_keys=False)
            update_prompt = create_update_prompt(prompt, nodes_yaml)
            modified_nodes_yaml = await game_kernel.llm_provider.generate_response(update_prompt)

            match = re.search(r"```yaml(.*?)```", modified_nodes_yaml, re.DOTALL)
            yaml_str = match.group(1) if match else modified_nodes_yaml
            modified_nodes_data = yaml.safe_load(yaml_str)

            # Merge the modified nodes back into the story data
            for modified_node in modified_nodes_data:
                for i, original_node in enumerate(story_data['nodes']):
                    if original_node['id'] == modified_node['id']:
                        story_data['nodes'][i] = modified_node
                        break

            # Validation and Saving
            new_story_yaml = yaml.dump(story_data, allow_unicode=True, sort_keys=False)
            from src.models.story_models import Story
            validated_data = yaml.safe_load(new_story_yaml)
            Story(**validated_data)

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml', encoding='utf-8') as temp_file:
                temp_file.write(new_story_yaml)
                new_temp_path = temp_file.name
            
            logger.info(f"AI generated story draft saved to temporary file: {new_temp_path}")
            return {"success": True, "temp_path": new_temp_path}

        except Exception as e:
            logger.error(f"Error editing story {story_id} with LLM: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/api/story/{story_id}/commit")
    async def commit_story_changes(story_id: str, request: Request):
        """Commit temporary story changes to the original file."""
        json_data = await request.json()
        temp_path = json_data.get("temp_path")

        if not temp_path:
            return {"error": "No temporary path provided."}

        real_temp = os.path.realpath(temp_path)
        if os.path.commonpath([real_temp, tempfile.gettempdir()]) != tempfile.gettempdir():
            return {"error": "Invalid temporary path specified."}
        temp_path = real_temp
        
        if not os.path.exists(temp_path):
            return {"error": "Temporary file not found."}

        story_path = story_manager.get_story_path(story_id)
        if not story_path:
            return {"error": "Original story file not found."}

        try:
            with open(temp_path, 'r', encoding='utf-8') as temp_f:
                content = temp_f.read()
            with open(story_path, 'w', encoding='utf-8') as original_f:
                original_f.write(content)
            
            os.remove(temp_path)
            
            logger.info(f"Committed changes from {temp_path} to {story_path}")
            return {"success": True}
        except Exception as e:
            logger.error(f"Error committing changes for story {story_id}: {e}")
            return {"error": str(e)}

    # =========================================================================
    # NEW: Function Calling AI Edit with SSE Streaming
    # =========================================================================
    
    @app.post("/api/editor/ai-edit-stream")
    async def editor_ai_edit_stream(request: Request):
        """Stream AI edit operations via SSE for real-time updates.
        
        This endpoint uses function calling to let the LLM make structured
        edits to the story. Changes are streamed in real-time so the
        frontend can update the UI as operations complete.
        
        Supports multiple editing modes:
        - nodes: Edit story nodes and edges (default)
        - characters: Edit NPCs and playable characters
        - objects: Edit global object definitions
        - parameters: Edit initial_variables/parameters
        - all: Access to all tools
        
        Request body:
            - prompt: User's edit request
            - mode: Editing mode ('nodes', 'characters', 'objects', 'parameters', 'all')
            - nodes: Current nodes from ReactFlow (for node mode)
            - edges: Current edges from ReactFlow (for node mode)
            - characters: Current characters list (for character mode)
            - objects: Current global objects list (for object mode)
            - parameters: Current initial_variables (for parameter mode)
            - context: Additional context (storyData, source)
            
        Response: SSE stream with events for the appropriate entity type.
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return {"error": f"Invalid JSON: {e}"}
        
        prompt = json_data.get("prompt")
        mode = json_data.get("mode", "nodes")
        nodes = json_data.get("nodes", [])
        edges = json_data.get("edges", [])
        characters = json_data.get("characters", [])
        objects = json_data.get("objects", [])
        parameters = json_data.get("parameters", {})
        context = json_data.get("context", {})
        
        if not prompt:
            return {"error": "Prompt is required"}
        
        if not game_kernel or not game_kernel.llm_provider:
            return {"error": "LLM provider not configured"}
        
        # Check if LLM provider supports tool calling
        if not hasattr(game_kernel.llm_provider, 'client'):
            return {"error": "LLM provider does not support function calling"}
        
        return StreamingResponse(
            _stream_editor_ai_edit(
                llm_provider=game_kernel.llm_provider,
                prompt=prompt,
                mode=mode,
                nodes=nodes,
                edges=edges,
                characters=characters,
                objects=objects,
                parameters=parameters,
                context=context
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )


async def _stream_editor_ai_edit(
    llm_provider: Any,
    prompt: str,
    mode: str,
    nodes: List[Dict],
    edges: List[Dict],
    characters: List[Dict],
    objects: List[Dict],
    parameters: Dict[str, Any],
    context: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Generator that yields SSE events as AI makes changes.
    
    Args:
        llm_provider: The LLM provider with OpenAI-compatible client
        prompt: User's edit request
        mode: Editing mode (nodes, characters, objects, parameters, all)
        nodes: Current nodes from frontend
        edges: Current edges from frontend
        characters: Current characters list
        objects: Current global objects list
        parameters: Current initial_variables
        context: Additional context including storyData
        
    Yields:
        SSE formatted strings for each event
    """
    # Initialize executor with all entity types
    executor = EditorFunctionExecutor(
        initial_nodes=nodes,
        initial_edges=edges,
        initial_characters=characters,
        initial_objects=objects,
        initial_parameters=parameters
    )
    
    # Get appropriate tools for the mode
    tools = get_tools_for_mode(mode)
    
    # Build system prompt with mode-specific context
    system_prompt = _build_editor_system_prompt(context, mode)
    
    # Initial thinking event
    mode_labels = {
        "nodes": "story graph",
        "characters": "characters",
        "objects": "objects",
        "parameters": "parameters",
        "all": "story"
    }
    yield SSEEvent(EventType.THINKING, {
        "message": f"Analyzing your request for {mode_labels.get(mode, mode)}..."
    }).to_sse()
    await asyncio.sleep(0.05)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    max_iterations = 20
    iteration = 0
    final_message = "Changes complete."
    
    try:
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM with mode-specific tools
            try:
                completion = llm_provider.client.chat.completions.create(
                    model=llm_provider.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                logger.error(f"LLM API error: {e}", exc_info=True)
                yield SSEEvent(EventType.ERROR, {"error": f"LLM API error: {e}"}).to_sse()
                return
            
            response_message = completion.choices[0].message
            
            if response_message.tool_calls:
                # Add assistant message to history
                messages.append(response_message)
                
                # Process each tool call
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid tool arguments: {e}")
                        arguments = {}
                    
                    logger.info(f"AI calling tool: {function_name}({json.dumps(arguments, ensure_ascii=False)[:200]}...)")
                    
                    # Execute the function
                    result = executor.execute(function_name, arguments)
                    
                    # Yield all pending events
                    for event in executor.get_pending_events():
                        yield event.to_sse()
                        await asyncio.sleep(0.05)  # Small delay for animation
                    
                    # Add result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                
                # Continue the loop to get next response
                continue
            else:
                # No more tool calls - LLM is done
                final_message = response_message.content or "Changes complete."
                break
        
        if iteration >= max_iterations:
            logger.warning(f"AI edit reached max iterations ({max_iterations})")
            final_message = "Reached maximum operations limit."
        
        # Emit completion event with final state
        final_state = executor.get_final_state()
        yield SSEEvent(EventType.COMPLETE, {
            "message": final_message,
            "summary": final_state["summary"],
            "final_state": final_state
        }).to_sse()
        
    except Exception as e:
        logger.error(f"Error in AI edit stream: {e}", exc_info=True)
        yield SSEEvent(EventType.ERROR, {"error": str(e)}).to_sse()


def _build_editor_system_prompt(context: Dict[str, Any], mode: str = "nodes") -> str:
    """Build comprehensive system prompt with format documentation.
    
    Args:
        context: Context from frontend including storyData
        mode: Editing mode (nodes, characters, objects, parameters, all)
        
    Returns:
        System prompt string for the LLM
    """
    format_docs = get_format_documentation()
    
    story_data = context.get('storyData', {})
    metadata = story_data.get('metadata', {})
    analysis = metadata.get('analysis', {})
    
    # Base context
    story_context = f"""
# STORY CONTEXT
Title: {metadata.get('title', 'Untitled Story')}
Genre: {metadata.get('genre', 'Unknown')}
Vibe: {analysis.get('vibe', 'Not analyzed')}
Tone: {analysis.get('tone', 'Not analyzed')}
"""
    
    # Mode-specific instructions
    if mode == "nodes":
        mode_instructions = """
# YOUR ROLE
You help users create and modify story nodes. Create engaging, interactive content
that makes good use of the engine's capabilities.

# AVAILABLE TOOLS
- create_node: Create new story nodes with descriptions, actions, objects, triggers
- update_node: Modify existing nodes (REPLACES arrays - use carefully!)
- add_action_to_node: Add a single action to a node (PRESERVES existing actions)
- add_object_to_node: Add a single object to a node (PRESERVES existing objects)
- delete_node: Remove a node and its connections
- get_node: Inspect a node's current content (ALWAYS use before update_node!)
- list_nodes: See all nodes in the story

# USE VARIED EFFECTS FOR ENGAGING GAMEPLAY
Don't just use goto_node + display_text. The engine supports rich mechanics:

- **set_variable / calculate**: Track and modify game state (sanity, gold, flags)
- **dice_roll**: Skill checks with success/failure branches
- **conditional**: Different outcomes based on player state
- **present_choice**: Meaningful player decisions
- **add_to_inventory**: Give/take items
- **update_object_status**: Interactive objects (doors, switches, containers)
- **llm_generate**: Dynamic AI-generated content

Example of a richer action:
{"text": "Pick the lock", "effects": [
  {"type": "dice_roll", "stat": "dexterity", "difficulty": 50,
   "success_effects": [{"type": "display_text", "text": "Click! The lock opens."},
                       {"type": "update_object_status", "target": "door", "add_status": ["open"], "remove_status": ["locked"]}],
   "failure_effects": [{"type": "display_text", "text": "The pick snaps. You'll need another way."}]}
]}

# WORKFLOW RULES

## When Adding Content to Existing Nodes:
1. ALWAYS call get_node FIRST to see current content
2. Then use add_action_to_node or add_object_to_node to ADD content
3. This preserves existing actions/objects

## When Creating Linked Content:
1. Create the new node first with create_node
2. Then use add_action_to_node to add a link from the existing node

# COMMON MISTAKES TO AVOID
1. Using 'name' instead of 'text' for actions - WRONG!
2. Using 'target_node' instead of 'target' in goto_node - WRONG!
3. Using 'effect' instead of 'type' in effects - WRONG!
4. Using 'variable' instead of 'target' in set_variable - WRONG!
5. Calling update_node without first calling get_node - DANGEROUS!
"""
    elif mode == "characters":
        mode_instructions = """
# YOUR ROLE
You help users create and modify NPCs and characters in the story.
Use the character tools to make changes.

# AVAILABLE TOOLS
- create_character: Create new NPCs or playable characters
- update_character: Modify existing characters (REPLACES arrays - use carefully!)
- delete_character: Remove a character
- get_character: Inspect a character's current content (use before update!)
- list_characters: See all characters in the story

# CHARACTER STRUCTURE
Characters have these fields:
- id: Unique snake_case identifier
- name: Display name
- definition: Static character information and behavior rules
- is_playable: true if player can be this character
- properties.location: Starting location for the character, if any
- parameters: {persona, fallback_prompt} for LLM-based dialogue
- stats: {hp, max_hp, strength, ...} for combat/RPG systems

# WORKFLOW
1. Use create_character for new characters with full details
2. Use update_character to modify properties such as `properties.location` (get first if needed)
"""
    elif mode == "objects":
        mode_instructions = """
# YOUR ROLE
You help users create and modify global object definitions.
Objects are items, scenery, or interactive elements that can exist in locations.

# AVAILABLE TOOLS
- create_object: Create new object definitions
- update_object: Modify existing objects (REPLACES arrays - use carefully!)
- delete_object: Remove an object
- get_object: Inspect an object's current content
- list_objects: See all global objects

# OBJECT STRUCTURE
Objects have these fields:
- id: Unique snake_case identifier
- name: Display name
- definition: Static description and interaction rules
- explicit_state: Current player-visible state
- implicit_state: Hidden AI-only context
- properties: Mechanical state such as status tags and custom data
- interactions belong in definition, not in a separate actions array

# WORKFLOW
1. Use create_object for new objects with full details
2. Use update_object to change explicit_state or properties as the story evolves
3. Objects can be placed in nodes using the node editor
"""
    elif mode == "parameters":
        mode_instructions = """
# YOUR ROLE
You help users manage initial_variables (parameters) for the game.
Parameters define starting values, lorebook entries, and configuration.

# AVAILABLE TOOLS
- set_parameter: Create or update a parameter value
- delete_parameter: Remove a parameter
- get_parameter: Get current value of a parameter
- list_parameters: See all parameters
- create_lorebook_entry: Create lore_ prefixed entries for LLM context

# PARAMETER TYPES
- Strings: "player_name": "Hero"
- Numbers: "starting_gold": 100
- Booleans: "has_tutorial": true
- Objects: {"max_inventory": 20, "difficulty": "normal"}

# LOREBOOK ENTRIES
Lorebook entries are prefixed with lore_ and provide context to LLM-generated content:
- lore_writing_style: "Write in a dark fantasy style..."
- lore_world_setting: "The world is a post-apocalyptic wasteland..."
- lore_protagonist: "The player is a wandering mercenary..."

Use create_lorebook_entry for these (automatically adds lore_ prefix).
"""
    elif mode == "story_creation":
        mode_instructions = """
# YOUR ROLE: STORY CREATOR
You are creating an engaging, interactive AI native text based game engine. Your goal is to craft a story
that is fun to play, not just read. Think like a game designer, not just a writer.

# WHAT MAKES A GREAT WENYOO

## Use Varied Effects for Engaging Gameplay
Don't just use goto_node + display_text for everything. The engine supports rich mechanics:

📝 **Text & Choices:**
- display_text: Show narrative, dialogue, descriptions
- present_choice: Give players meaningful decisions with different outcomes

🔢 **State & Consequences:**
- set_variable: Track story state (visited_castle, met_npc, found_clue)
- calculate: Change stats (sanity -= 10, gold += 50, reputation changes)
- Use conditions on actions to unlock/lock paths based on state

🎲 **Uncertainty & Tension:**
- dice_roll: Skill checks with success/failure branches
- random_number: Add unpredictability
- conditional: Different outcomes based on player state

🎭 **Interactive World:**
- update_object_status: Objects change state (doors open, levers activate, items transform)
- set_object_explicit_state: Update how objects appear to players
- add_to_inventory / remove_from_inventory: Items the player carries

🤖 **Dynamic Content:**
- llm_generate: Generate atmospheric descriptions, NPC dialogue, dynamic events

## Example: A Well-Designed Action
Instead of just:
```
{"text": "Open the door", "effects": [{"type": "goto_node", "target": "next_room"}]}
```

Consider:
```
{"text": "Try to open the ancient door", "intent": "Attempt to force the ancient door open. If it succeeds, reveal the treasure chamber and mark the door as opened. If it fails, describe the strain and hint that another approach may help.", "effects": [
  {"type": "dice_roll", "stat": "strength", "difficulty": 40,
   "success_effects": [
     {"type": "display_text", "text": "The door groans open!"},
     {"type": "set_variable", "target": "opened_ancient_door", "value": true},
     {"type": "goto_node", "target": "treasure_chamber"}
   ],
   "failure_effects": [
     {"type": "display_text", "text": "The door won't budge. You'll need to find another way."},
     {"type": "modify_variable", "target": "stamina", "operation": "subtract", "value": 5}
   ]}
]}
```

# AVAILABLE TOOLS

## Story Structure (Nodes)
- create_node: Create locations/scenes with DSPP fields (`definition`, `explicit_state`, `implicit_state`, `properties`), actions, objects, triggers
- update_node: Modify existing nodes
- add_action_to_node: Add player actions (preserves existing)
- add_object_to_node: Add interactive objects to locations
- delete_node, get_node, list_nodes

## Characters (Optional but adds life)
- create_character: NPCs with personalities, dialogue, and optional `properties.location`
- update_character, delete_character, get_character, list_characters

## Objects (Optional but adds interactivity)
- create_object: DSPP-style items with definition, explicit_state, implicit_state, and properties
- update_object, delete_object, get_object, list_objects

## Parameters (For state tracking)
- set_parameter: Initial variables (stats, flags, lorebook)
- delete_parameter, get_parameter, list_parameters
- create_lorebook_entry: Context for LLM-generated content

# WORKFLOW FOR CREATING A STORY

1. **Create the node structure** - Locations and how they connect
2. **Add actions with varied effects** - Not just navigation, but consequences
3. **Set up initial variables** - Stats to track (if the story uses them)
4. **Optionally add characters** - NPCs in key locations
5. **Optionally add objects** - Interactive elements

# REMEMBER
- Every effect uses "type" field (not "effect")
- goto_node uses "target" (not "target_node")
- set_variable uses "target" (not "variable")
- Actions use "text" (not "name" or "label")
- Actions and triggers may use `intent` when natural-language behavior is clearer than only structured effects
- Object interactions belong in an object's `definition`, not a separate object actions array
- Use get_* before update_* to avoid overwriting content
"""
    else:  # mode == "all"
        mode_instructions = """
# YOUR ROLE
You have access to all story editing tools. You can modify:
- Story nodes (locations, scenes)
- Characters (NPCs, playable characters)
- Objects (items, interactive elements)
- Parameters (game settings, lorebook)

# NODES TOOLS
- create_node, update_node, add_action_to_node, add_object_to_node
- delete_node, get_node, list_nodes

# CHARACTER TOOLS
- create_character, update_character, delete_character
- get_character, list_characters

# OBJECT TOOLS
- create_object, update_object, delete_object
- get_object, list_objects

# PARAMETER TOOLS
- set_parameter, delete_parameter, get_parameter
- list_parameters, create_lorebook_entry

Choose the appropriate tools based on what the user is asking to change.
Use get_* functions before update_* to see current content and avoid data loss.
"""

    return f"""You are an expert story editor AI assistant for an AI native text based game engine.
{mode_instructions}
{story_context}

{EDITOR_PROMPT_LANGUAGE_SECTION}

# FORMAT SPECIFICATION
{format_docs}


Now help the user with their request. Use the tools to make the necessary changes."""


def _get_story_path(temp_path: Optional[str], story_id: str, story_manager: Any):
    """Get the path to read a story from.
    
    Args:
        temp_path: Optional temporary path.
        story_id: The story ID.
        story_manager: The story manager instance.
        
    Returns:
        The path string, or an error dict.
    """
    if temp_path:
        real_temp = os.path.realpath(temp_path)
        if os.path.commonpath([real_temp, tempfile.gettempdir()]) != tempfile.gettempdir():
            return {"error": "Invalid temporary path specified."}
        if os.path.exists(real_temp):
            return real_temp
        else:
            return {"error": "Temporary file not found."}
    else:
        path = story_manager.get_story_path(story_id)
        if not path or not os.path.exists(path):
            return {"error": "Story not found"}
        return path

