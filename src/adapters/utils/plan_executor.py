"""Plan-based executor for AI story editing.

This module handles the two-phase approach for AI-assisted story creation:
1. Planning Phase: LLM generates a structured execution plan
2. Execution Phase: Plan is executed step-by-step deterministically

This approach avoids the step-limit issue with tool-calling by having the LLM
generate a complete plan upfront, then executing it without further LLM calls.
"""

from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import time

from .editor_function_executor import EditorFunctionExecutor, SSEEvent, EventType
from .editor_language import EDITOR_PROMPT_LANGUAGE_SECTION

logger = logging.getLogger(__name__)


class PlanType(str, Enum):
    """Types of execution plans."""
    STORY_CREATION = "story_creation"  # Creating a new story from scratch
    STORY_MODIFICATION = "story_modification"  # Modifying existing story
    NODE_EXPANSION = "node_expansion"  # Expanding/splitting nodes
    OUTLINE_REFINEMENT = "outline_refinement"  # Refining story outline


class PlanScope(str, Enum):
    """Scope of the plan's changes."""
    FULL_STORY = "full_story"  # Affects entire story
    SELECTED_NODES = "selected_nodes"  # Affects only selected nodes
    SINGLE_NODE = "single_node"  # Affects a single node
    PARAMETERS_ONLY = "parameters_only"  # Only modifies parameters/lore


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    id: int
    action: str  # Function name: create_node, update_node, etc.
    params: Dict[str, Any]  # Parameters for the function
    description: Optional[str] = None  # Human-readable description
    depends_on: List[int] = field(default_factory=list)  # Step IDs this depends on
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "depends_on": self.depends_on
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanStep':
        """Create from dictionary."""
        return cls(
            id=data.get("id", 0),
            action=data.get("action", ""),
            params=data.get("params", {}),
            description=data.get("description"),
            depends_on=data.get("depends_on", [])
        )


@dataclass
class ExecutionPlan:
    """A complete execution plan for story changes."""
    plan_type: PlanType
    scope: PlanScope
    summary: str  # Human-readable summary
    steps: List[PlanStep]
    
    # Optional metadata
    lore_outline: Optional[str] = None  # Story outline to store
    estimated_changes: Optional[Dict[str, int]] = None  # Estimated counts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "plan_type": self.plan_type.value,
            "scope": self.scope.value,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "lore_outline": self.lore_outline,
            "estimated_changes": self.estimated_changes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPlan':
        """Create from dictionary (e.g., from LLM response)."""
        plan_type = PlanType(data.get("plan_type", "story_modification"))
        scope = PlanScope(data.get("scope", "full_story"))
        
        steps = []
        for step_data in data.get("steps", []):
            steps.append(PlanStep.from_dict(step_data))
        
        return cls(
            plan_type=plan_type,
            scope=scope,
            summary=data.get("summary", ""),
            steps=steps,
            lore_outline=data.get("lore_outline"),
            estimated_changes=data.get("estimated_changes")
        )
    
    def validate(self) -> List[str]:
        """Validate the plan and return list of errors (empty if valid)."""
        errors = []
        
        if not self.steps:
            errors.append("Plan has no steps")
            return errors
        
        # Check step IDs are unique
        step_ids = [s.id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Duplicate step IDs found")
        
        # Check dependencies reference existing steps
        for step in self.steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    errors.append(f"Step {step.id} depends on non-existent step {dep_id}")
                if dep_id >= step.id:
                    errors.append(f"Step {step.id} depends on future step {dep_id}")
        
        # Check all actions are valid
        valid_actions = {
            "create_node", "update_node", "delete_node", "add_action_to_node", "add_object_to_node",
            "create_character", "update_character", "delete_character",
            "create_object", "update_object", "delete_object",
            "set_parameter", "delete_parameter", "create_lorebook_entry"
        }
        for step in self.steps:
            if step.action not in valid_actions:
                errors.append(f"Step {step.id} has invalid action: {step.action}")
        
        return errors


class PlanExecutionResult:
    """Result of executing a plan."""
    
    def __init__(self):
        self.success = True
        self.completed_steps: List[int] = []
        self.failed_step: Optional[int] = None
        self.error_message: Optional[str] = None
        self.final_state: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "error_message": self.error_message
        }


class PlanExecutor:
    """Executes an ExecutionPlan step by step.
    
    This class takes a plan (generated by the LLM) and executes each step
    deterministically. No LLM calls are made during execution - just direct
    function calls to the EditorFunctionExecutor.
    """
    
    def __init__(self, initial_nodes: List[Dict] = None, initial_edges: List[Dict] = None,
                 initial_characters: List[Dict] = None, initial_objects: List[Dict] = None,
                 initial_parameters: Dict[str, Any] = None):
        """Initialize with current editor state.
        
        Args:
            initial_nodes: Current nodes from ReactFlow
            initial_edges: Current edges from ReactFlow
            initial_characters: Current characters list
            initial_objects: Current global objects list
            initial_parameters: Current parameters/initial_variables dict
        """
        self.executor = EditorFunctionExecutor(
            initial_nodes=initial_nodes or [],
            initial_edges=initial_edges or [],
            initial_characters=initial_characters or [],
            initial_objects=initial_objects or [],
            initial_parameters=initial_parameters or {}
        )
        self.step_results: Dict[int, Dict[str, Any]] = {}
    
    def execute_plan(self, plan: ExecutionPlan) -> PlanExecutionResult:
        """Execute a plan synchronously.
        
        Args:
            plan: The execution plan to run
            
        Returns:
            PlanExecutionResult with success/failure info
        """
        result = PlanExecutionResult()
        
        # Validate plan first
        errors = plan.validate()
        if errors:
            result.success = False
            result.error_message = f"Plan validation failed: {'; '.join(errors)}"
            return result
        
        # Store lore outline first if provided
        if plan.lore_outline:
            self.executor.execute("set_parameter", {
                "key": "lore_outline",
                "value": plan.lore_outline
            })
        
        # Execute each step
        for step in plan.steps:
            try:
                step_result = self.executor.execute(step.action, step.params)
                self.step_results[step.id] = step_result
                
                if not step_result.get("success", False):
                    result.success = False
                    result.failed_step = step.id
                    result.error_message = step_result.get("error", "Unknown error")
                    break
                
                result.completed_steps.append(step.id)
                
            except Exception as e:
                logger.error(f"Error executing step {step.id}: {e}", exc_info=True)
                result.success = False
                result.failed_step = step.id
                result.error_message = str(e)
                break
        
        result.final_state = self.executor.get_final_state()
        return result
    
    async def execute_plan_streaming(self, plan: ExecutionPlan) -> AsyncGenerator[SSEEvent, None]:
        """Execute a plan with SSE streaming for real-time updates.
        
        Args:
            plan: The execution plan to run
            
        Yields:
            SSEEvent objects for each change
        """
        import asyncio
        
        # Validate plan
        errors = plan.validate()
        if errors:
            yield SSEEvent(EventType.ERROR, {
                "error": f"Plan validation failed: {'; '.join(errors)}"
            })
            return
        
        # Emit plan start event
        yield SSEEvent(EventType.THINKING, {
            "message": f"Starting execution: {plan.summary}",
            "total_steps": len(plan.steps)
        })
        await asyncio.sleep(0.05)
        
        # Store lore outline first if provided
        if plan.lore_outline:
            self.executor.execute("set_parameter", {
                "key": "lore_outline",
                "value": plan.lore_outline
            })
            for event in self.executor.get_pending_events():
                yield event
            await asyncio.sleep(0.05)
        
        completed_steps = []
        failed_step = None
        error_message = None
        
        # Execute each step
        for step in plan.steps:
            # Emit thinking message for this step
            step_desc = step.description or f"{step.action} ({step.params.get('id', 'unknown')})"
            yield SSEEvent(EventType.THINKING, {
                "message": f"Step {step.id}: {step_desc}",
                "current_step": step.id,
                "total_steps": len(plan.steps)
            })
            await asyncio.sleep(0.02)
            
            try:
                step_result = self.executor.execute(step.action, step.params)
                self.step_results[step.id] = step_result
                
                # Yield all events generated by this step
                for event in self.executor.get_pending_events():
                    yield event
                    await asyncio.sleep(0.03)  # Small delay for animation
                
                if not step_result.get("success", False):
                    failed_step = step.id
                    error_message = step_result.get("error", "Unknown error")
                    yield SSEEvent(EventType.ERROR, {
                        "error": error_message,
                        "step_id": step.id
                    })
                    break
                
                completed_steps.append(step.id)
                
            except Exception as e:
                logger.error(f"Error executing step {step.id}: {e}", exc_info=True)
                failed_step = step.id
                error_message = str(e)
                yield SSEEvent(EventType.ERROR, {
                    "error": error_message,
                    "step_id": step.id
                })
                break
        
        # Emit completion event
        final_state = self.executor.get_final_state()
        if failed_step is None:
            yield SSEEvent(EventType.COMPLETE, {
                "message": f"Successfully completed all {len(completed_steps)} steps",
                "summary": final_state["summary"],
                "final_state": final_state
            })
        else:
            yield SSEEvent(EventType.COMPLETE, {
                "message": f"Completed {len(completed_steps)} steps before failure",
                "summary": final_state["summary"],
                "final_state": final_state,
                "failed_step": failed_step,
                "error": error_message
            })
    
    def get_pending_events(self) -> List[SSEEvent]:
        """Get pending events from the underlying executor."""
        return self.executor.get_pending_events()
    
    def get_final_state(self) -> Dict[str, Any]:
        """Get the final state after execution."""
        return self.executor.get_final_state()


def build_plan_generation_prompt(
    user_prompt: str,
    nodes: List[Dict],
    edges: List[Dict],
    characters: List[Dict],
    objects: List[Dict],
    parameters: Dict[str, Any],
    selected_node_ids: List[str] = None,
    story_metadata: Dict[str, Any] = None
) -> str:
    """Build a comprehensive prompt for plan generation.
    
    This prompt instructs the LLM to output a structured execution plan
    rather than making direct tool calls.
    
    Args:
        user_prompt: The user's request
        nodes: Current nodes in the story
        edges: Current edges in the story
        characters: Current characters
        objects: Current objects
        parameters: Current parameters including lore entries
        selected_node_ids: IDs of currently selected nodes
        story_metadata: Story title, genre, etc.
        
    Returns:
        Complete system prompt for plan generation
    """
    # Build context about current state
    node_count = len(nodes)
    has_nodes = node_count > 0
    
    # Extract lore outline if exists
    lore_outline = parameters.get("lore_outline", "")
    lore_entries = {k: v for k, v in parameters.items() if k.startswith("lore_")}
    
    # Build node summary
    if nodes:
        node_summary = "\n".join([
            f"  - {n.get('id')}: {n.get('name', n.get('id'))} ({len(n.get('actions', []))} actions)"
            for n in nodes[:20]  # Limit to first 20
        ])
        if len(nodes) > 20:
            node_summary += f"\n  ... and {len(nodes) - 20} more nodes"
    else:
        node_summary = "  (empty - no nodes yet)"
    
    # Build selection context
    if selected_node_ids:
        selection_info = f"""
## SELECTED NODES ({len(selected_node_ids)} selected)
The user has selected these nodes, suggesting they want to modify them specifically:
{json.dumps(selected_node_ids, indent=2)}

Incoming edges to selected nodes: {[e for e in edges if e.get('target') in selected_node_ids]}
Outgoing edges from selected nodes: {[e for e in edges if e.get('source') in selected_node_ids]}
"""
    else:
        selection_info = """
## NO NODES SELECTED
The user has not selected any specific nodes.
- If the story is empty, they likely want to CREATE a new story
- If the story exists, they might want to modify the overall theme or add new content
"""
    
    # Build lore context
    if lore_entries:
        lore_info = "## EXISTING LORE/OUTLINE\n"
        for key, value in lore_entries.items():
            preview = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
            lore_info += f"- {key}: {preview}\n"
    else:
        lore_info = "## NO LORE/OUTLINE YET\nConsider creating a lore_outline to capture the story structure.\n"
    
    # Story metadata
    meta_info = ""
    if story_metadata:
        meta_info = f"""
## STORY METADATA
Title: {story_metadata.get('title', 'Untitled')}
Genre: {story_metadata.get('genre', 'Unknown')}
"""
    
    return f"""You are an intelligent story editor AI. Your task is to analyze the user's request
and generate a structured EXECUTION PLAN that can be executed step-by-step.

# IMPORTANT: OUTPUT FORMAT
You must output a JSON execution plan, NOT make direct tool calls.
The plan will be executed deterministically after you generate it.

# CURRENT STORY STATE
Total nodes: {node_count}
Total characters: {len(characters)}
Total objects: {len(objects)}
{meta_info}
## NODES
{node_summary}

{selection_info}

{lore_info}

# UNDERSTANDING USER INTENT

Based on the context above, determine:
1. SCOPE: What parts of the story does the user want to modify?
   - "full_story" - Creating new or changing entire story
   - "selected_nodes" - Modifying the selected nodes
   - "single_node" - Modifying a specific node
   - "parameters_only" - Just changing settings/lore

2. PLAN TYPE: What kind of operation is this?
   - "story_creation" - Building a new story from scratch
   - "story_modification" - Changing existing content
   - "node_expansion" - Splitting/expanding nodes
   - "outline_refinement" - Refining story outline/lore

# AVAILABLE ACTIONS FOR STEPS

Each step can use one of these actions:

## Node Operations
- create_node: {{"id": "node_id", "name": "Name", "definition": "Static rules and info", "explicit_state": "Player-visible scene description", "implicit_state": "Hidden AI context", "properties": {{"status": []}}, "actions": [...], "objects": [...], "triggers": [...]}}
- update_node: {{"id": "existing_id", "name": "New Name", "explicit_state": "New visible description"}}
- delete_node: {{"id": "node_id"}}
- add_action_to_node: {{"node_id": "id", "action": {{"id": "action_id", "text": "Action text", "intent": "Optional natural-language behavior", "effects": [...]}}}}
- add_object_to_node: {{"node_id": "id", "object": {{"id": "obj_id", "name": "Name", "definition": "Object rules", "explicit_state": "Visible state"}}}}

## Character Operations
- create_character: {{"id": "char_id", "name": "Name", "definition": "Character rules and behavior", "explicit_state": "Visible description", "properties": {{"location": "node_id"}}}}
- update_character: {{"id": "char_id", "name": "New Name"}}
- delete_character: {{"id": "char_id"}}

## Object Operations
- create_object: {{"id": "obj_id", "name": "Name", "definition": "Object rules", "explicit_state": "Visible state", "properties": {{"status": []}}}}
- update_object: {{"id": "obj_id", "explicit_state": "New visible state"}}
- delete_object: {{"id": "obj_id"}}

## Parameter/Lore Operations
- set_parameter: {{"key": "param_name", "value": "..."}}
- delete_parameter: {{"key": "param_name"}}
- create_lorebook_entry: {{"name": "writing_style", "content": "..."}}

# ACTION FORMAT REMINDERS
- Actions use "text" not "name" or "label"
- Actions may use either "intent" or "effects" (or both), but "intent" is preferred for Architect-driven behavior
- Triggers may also use "intent" instead of only structured effects
- Effects use "type" not "effect"
- goto_node uses "target" not "target_node"
- set_variable uses "target" not "variable"

# OUTPUT FORMAT

Return a JSON object with this structure:
{{
  "plan_type": "story_creation" | "story_modification" | "node_expansion" | "outline_refinement",
  "scope": "full_story" | "selected_nodes" | "single_node" | "parameters_only",
  "summary": "Brief description of what this plan will do",
  "lore_outline": "Optional: story outline to save (for new stories or major changes)",
  "estimated_changes": {{
    "nodes_created": 0,
    "nodes_modified": 0,
    "characters_created": 0,
    "parameters_set": 0
  }},
  "steps": [
    {{
      "id": 1,
      "action": "action_name",
      "params": {{ ... }},
      "description": "Human-readable step description"
    }},
    ...
  ]
}}

# USER REQUEST
{user_prompt}

{EDITOR_PROMPT_LANGUAGE_SECTION}

Now analyze the request and generate an appropriate execution plan.
Output ONLY the JSON plan, no additional text."""


def get_outline_generation_prompt(user_idea: str, num_options: int = 3) -> str:
    """Build prompt for generating story outline options.
    
    Used in the story creation wizard to generate multiple outline options
    for the user to choose from.
    
    Args:
        user_idea: The user's initial story idea
        num_options: Number of outline options to generate
        
    Returns:
        Prompt for outline generation
    """
    return f"""You are a creative story designer for interactive AI native text based games.

The user has a story idea. Generate {num_options} distinct outline options, each with a different
approach to the concept. Make each option feel unique and interesting.

# ENGINE CAPABILITIES - IMPORTANT
You are designing for a specific AI native text based game engine. Your story MUST be achievable with these features:

## What the engine CAN do:
- **Nodes/Locations**: Scenes the player can visit with descriptions and actions
- **Actions**: Player choices with conditions and effects
- **Branching**: Multiple paths based on player choices (goto_node)
- **Variables**: Track story state (booleans, numbers, strings) for flags and stats
- **Conditions**: Show/hide actions or trigger events based on variables
- **Inventory**: Add/remove items, check item possession
- **Characters/NPCs**: Place characters in locations with dialogue and character-specific actions
- **Objects**: Interactive objects in locations using DSPP fields (`definition`, `explicit_state`, `implicit_state`, `properties`)
- **Triggers**: Automatic events on entering/leaving nodes or when conditions are met
- **LLM Text Generation**: Generate dynamic text descriptions using prompts (stored in variables)
- **Combat System**: Turn-based combat with stats (HP, attacks, enemies)
- **Dice Rolls**: Random skill checks with success/failure outcomes
- **Lua Scripting**: Complex logic via embedded Lua scripts
- **Lorebook/Parameters**: Store world lore, writing style, background info for LLM prompts

## What the engine CANNOT do:
- Real-time mechanics or timers tied to actual clock time
- Dynamic UI changes (the UI is fixed - text + action buttons)
- Memory/save file manipulation beyond normal game state
- Audio, images, or visual effects
- Procedural world generation at runtime
- Multiplayer real-time interaction (only turn-based multiplayer)
- Complex minigames or puzzles beyond text choices
- Meta-game mechanics that break the fourth wall technically

## Design your outlines to be ACHIEVABLE with nodes, actions, variables, and conditions.

# USER'S IDEA
{user_idea}

# OUTPUT FORMAT
Return a JSON object with {num_options} outline options:
{{
  "outlines": [
    {{
      "id": "option_1",
      "title": "Catchy title for this version",
      "theme": "The specific theme/subgenre",
      "setting": {{
        "time_period": "When does it take place",
        "location": "Where does it happen",
        "atmosphere": "The mood/vibe"
      }},
      "protagonist": {{
        "archetype": "Type of main character",
        "motivation": "What drives them"
      }},
      "core_conflict": "The main tension/problem",
      "estimated_length": "short" | "medium" | "long",
      "key_features": ["Feature 1", "Feature 2", "Feature 3"],
      "sample_beats": [
        "Opening scene/hook",
        "First major choice",
        "Midpoint twist",
        "Climax setup",
        "Possible endings"
      ]
    }},
    ...
  ]
}}

IMPORTANT JSON RULES:
- Return STRICT valid JSON only.
- Escape any double quote characters that appear inside string values as \\\".
- Do not include raw dialogue quotes or quoted phrases inside JSON strings unless they are escaped.
- Do not add markdown commentary before or after the JSON.

Generate diverse options that each explore the user's idea from a different angle.
Make each feel like a complete, playable game concept that is ACHIEVABLE with the engine's features.
Focus on branching narrative, meaningful choices, and atmosphere rather than gimmicky mechanics."""


def get_outline_expansion_prompt(selected_outline: Dict[str, Any], user_modifications: str = None) -> str:
    """Build prompt for expanding a selected outline into detailed story beats.
    
    Args:
        selected_outline: The outline option the user selected
        user_modifications: Any changes the user requested
        
    Returns:
        Prompt for detailed outline generation
    """
    modifications_text = ""
    if user_modifications:
        modifications_text = f"""
# USER MODIFICATIONS
The user requested these changes to the outline:
{user_modifications}
"""
    
    return f"""You are a story designer creating a high-level story bible for an interactive AI native text based game engine.

# IMPORTANT: Keep this CONCISE and HIGH-LEVEL
- Do NOT list every location/node - just describe the major areas
- Focus on KEY elements that define the story experience
- Actual node creation will be handled separately

# SELECTED OUTLINE
{json.dumps(selected_outline, indent=2)}
{modifications_text}
# YOUR TASK
Create a compact story bible with:
1. Core narrative elements (theme, setting, tone)
2. Key game mechanics and variables
3. Main characters (3-5 max)
4. Critical objects/items
5. Major story beats (5-7 max)
6. Possible endings (2-4)

# OUTPUT FORMAT
{{
  "detailed_outline": {{
    "title": "Story title",
    "theme": "Core theme in one sentence",
    "setting": "Where and when, brief",
    "tone": "Narrative tone/atmosphere",
    "writing_style": "How to write descriptions (2-3 sentences)",
    
    "game_mechanics": {{
      "key_variables": [
        {{"name": "variable_name", "type": "number/boolean/string", "purpose": "What it tracks"}}
      ],
      "core_loop": "What the player repeatedly does",
      "win_condition": "How to win/complete",
      "fail_conditions": ["How the player can lose"]
    }},
    
    "characters": [
      {{
        "id": "char_id",
        "name": "Name",
        "role": "protagonist/antagonist/ally/npc",
        "one_liner": "Character in one sentence"
      }}
    ],
    
    "key_items": [
      {{"id": "item_id", "name": "Name", "purpose": "Why it matters"}}
    ],
    
    "story_structure": {{
      "act_1": "Setup - what happens at the start",
      "act_2": "Confrontation - main challenges",
      "act_3": "Resolution - how it can end"
    }},
    
    "major_locations": ["Location 1 name", "Location 2 name", "Location 3 name"],
    
    "endings": [
      {{"type": "good/bad/neutral", "title": "Ending name", "trigger": "How to reach it"}}
    ]
  }},
  
  "lore_outline": "A 3-5 paragraph text summary of the story for LLM context"
}}

Keep the output COMPACT. Quality over quantity."""


def get_outline_refinement_prompt(outline: Dict[str, Any], feedback: str) -> str:
    """Build prompt for refining a single outline based on user feedback.
    
    Args:
        outline: The current outline to refine
        feedback: User's modification request
        
    Returns:
        Prompt for outline refinement
    """
    return f"""You are a creative story designer refining a story outline based on user feedback.

# CURRENT OUTLINE
{json.dumps(outline, indent=2)}

# USER'S FEEDBACK
The user wants these changes:
{feedback}

# ENGINE CAPABILITIES REMINDER
Design for an AI native text based game engine that supports:
- Nodes (locations/scenes) with descriptions and actions
- Player actions with conditions (variable checks, inventory)
- Variables to track story state (flags, counters, stats)
- Branching paths and multiple endings
- Characters with dialogue and starting locations
- Objects with DSPP fields and interaction rules in `definition`

Keep features achievable with text-based choices and variables.

# YOUR TASK
Modify the outline based on the user's feedback. Keep the same structure but update
the relevant fields to incorporate their suggestions.

# OUTPUT FORMAT
Return a JSON object with the refined outline:
{{
  "refined_outline": {{
    "id": "{outline.get('id', 'option_1')}",
    "title": "Updated title if changed",
    "theme": "Updated theme",
    "setting": {{
      "time_period": "...",
      "location": "...",
      "atmosphere": "..."
    }},
    "protagonist": {{
      "archetype": "...",
      "motivation": "..."
    }},
    "core_conflict": "Updated conflict",
    "estimated_length": "short" | "medium" | "long",
    "key_features": ["Feature 1", "Feature 2", "Feature 3"],
    "sample_beats": [
      "Opening scene/hook",
      "First major choice",
      "Midpoint twist",
      "Climax setup",
      "Possible endings"
    ]
  }}
}}

Apply the user's feedback thoughtfully while maintaining story coherence."""


def get_outline_set_refinement_prompt(
    outlines: List[Dict[str, Any]],
    feedback: str,
    selected_index: Optional[int] = None
) -> str:
    """Build prompt for refining the current outline set in place."""
    selected_hint = (
        f"\n# CURRENTLY SELECTED OUTLINE INDEX\n{selected_index}\n"
        if selected_index is not None else ""
    )

    return f"""You are a creative story designer refining the current set of story directions.

# CURRENT OUTLINE OPTIONS
{json.dumps(outlines, indent=2)}
{selected_hint}
# USER INSTRUCTION
The user wants these changes applied while staying on the same wizard step:
{feedback}

# YOUR TASK
Modify the current directions in place.
- Keep the same overall array structure and IDs whenever possible.
- Update whichever outline(s) the user's instruction refers to.
- If the instruction refers to an ordinal like "second direction", apply it correctly.
- Preserve unrelated outlines unless the user clearly asks to change them.

# OUTPUT FORMAT
Return a JSON object:
{{
  "updated_outlines": [
    {{
      "id": "option_1",
      "title": "Updated title if changed",
      "theme": "Updated theme",
      "setting": {{
        "time_period": "...",
        "location": "...",
        "atmosphere": "..."
      }},
      "protagonist": {{
        "archetype": "...",
        "motivation": "..."
      }},
      "core_conflict": "...",
      "estimated_length": "short" | "medium" | "long",
      "key_features": ["Feature 1", "Feature 2"],
      "sample_beats": [
        "Beat 1",
        "Beat 2",
        "Beat 3"
      ]
    }}
  ],
  "selected_index": 0
}}

Set `selected_index` to the outline that best matches the user's updated focus.
Output only JSON."""


def get_detailed_outline_refinement_prompt(
    detailed_outline: Dict[str, Any],
    feedback: str
) -> str:
    """Build prompt for refining the detailed outline in place."""
    return f"""You are a story designer refining a detailed story outline and execution review draft.

# CURRENT DETAILED OUTLINE
{json.dumps(detailed_outline, indent=2)}

# USER INSTRUCTION
The user wants these changes applied while staying on the same review step:
{feedback}

# ENGINE REMINDER
Design for an AI native text based game engine with:
- nodes/locations, actions, branching, variables, conditions
- characters with dialogue and starting locations
- objects, triggers, endings, and story-level parameters/lore

# YOUR TASK
Refine the detailed outline based on the user's instruction.
- Keep the same high-level structure.
- Update the relevant sections only.
- If the user requests more NPCs, locations, mechanics, or endings, reflect that clearly.
- Ensure the output remains suitable for plan generation.

# OUTPUT FORMAT
Return a JSON object:
{{
  "detailed_outline": {{
    "title": "Story title",
    "theme": "Core theme",
    "setting": "Where and when, brief",
    "tone": "Narrative tone/atmosphere",
    "writing_style": "How to write descriptions",
    "game_mechanics": {{
      "key_variables": [
        {{"name": "variable_name", "type": "number/boolean/string", "purpose": "What it tracks"}}
      ],
      "core_loop": "What the player repeatedly does",
      "win_condition": "How to win/complete",
      "fail_conditions": ["How the player can lose"]
    }},
    "characters": [
      {{
        "id": "char_id",
        "name": "Name",
        "role": "protagonist/antagonist/ally/npc",
        "one_liner": "Character in one sentence"
      }}
    ],
    "key_items": [
      {{"id": "item_id", "name": "Name", "purpose": "Why it matters"}}
    ],
    "story_structure": {{
      "act_1": "Setup",
      "act_2": "Confrontation",
      "act_3": "Resolution"
    }},
    "major_locations": ["Location 1", "Location 2"],
    "endings": [
      {{"type": "good/bad/neutral", "title": "Ending name", "trigger": "How to reach it"}}
    ]
  }},
  "lore_outline": "A 3-5 paragraph text summary of the updated story for LLM context"
}}

Output only JSON."""
