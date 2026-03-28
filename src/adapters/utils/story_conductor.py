"""Story Conductor - Parallel LLM-based story generation.

This module handles the "conducting" phase of story creation, where a skeleton
story structure is expanded into a full, playable story using parallel LLM calls.

The conductor:
1. Takes a skeleton story (parameters, characters, objects, placeholder nodes)
2. Expands each node in parallel using LLM
3. Generates rich descriptions, actions, triggers, and object details
4. Returns a complete, playable story

Enhanced with intelligent coordination:
- Uses ExpansionCoordinator for rich context passing
- Tracks narrative consistency across nodes
- Monitors economy balance
- Validates expanded content
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum

# Import intelligent coordination components
try:
    from .expansion_coordinator import ExpansionCoordinator, RichExpansionContext
    from .world_blueprint import WorldBlueprint, BlueprintGenerator
    from .numerical_design import NumericalDesign
    from .narrative_tracker import NarrativeTracker
    COORDINATOR_AVAILABLE = True
except ImportError:
    COORDINATOR_AVAILABLE = False

logger = logging.getLogger(__name__)


class ConductorEventType(str, Enum):
    """Types of events emitted during story conducting."""
    PHASE_START = "phase_start"
    NODE_EXPANDING = "node_expanding"
    NODE_COMPLETE = "node_complete"
    NODE_ERROR = "node_error"
    CHARACTER_PLACING = "character_placing"
    CHARACTER_PLACED = "character_placed"
    CONNECTIONS_CREATING = "connections_creating"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ConductorEvent:
    """An event emitted during story conducting."""
    event_type: ConductorEventType
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps({'type': self.event_type.value, **self.data})}\n\n"


@dataclass
class NodeExpansionContext:
    """Context for expanding a single node."""
    node_id: str
    node_name: str
    placeholder_description: str
    story_context: Dict[str, Any]  # lore_outline, writing_style, theme, etc.
    adjacent_nodes: List[Dict[str, str]]  # [{id, name, direction}]
    characters_here: List[Dict[str, Any]]  # Characters that should be in this node
    objects_here: List[Dict[str, Any]]  # Objects that should be in this node
    story_beat: Optional[str] = None  # What happens in the story at this point
    is_ending: bool = False
    ending_type: Optional[str] = None  # good, bad, neutral


class StoryConductor:
    """Conducts story generation with parallel LLM calls.
    
    The conductor takes a skeleton story and expands it into a complete story
    by calling the LLM to generate content for each node in parallel.
    
    Enhanced with ExpansionCoordinator for:
    - Rich context passing between node expansions
    - Narrative consistency tracking
    - Economy balance monitoring
    - Post-expansion validation
    """
    
    def __init__(
        self,
        llm_provider: Any,
        max_concurrent: int = 3,
        timeout_per_node: float = 60.0,
        use_coordinator: bool = True
    ):
        """Initialize the conductor.
        
        Args:
            llm_provider: The LLM provider instance with generate_response method
            max_concurrent: Maximum number of parallel LLM calls
            timeout_per_node: Timeout in seconds for each node expansion
            use_coordinator: Whether to use intelligent coordination (default True)
        """
        self.llm_provider = llm_provider
        self.max_concurrent = max_concurrent
        self.timeout_per_node = timeout_per_node
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Intelligent coordination
        self.use_coordinator = use_coordinator and COORDINATOR_AVAILABLE
        self.coordinator: Optional['ExpansionCoordinator'] = None
    
    async def conduct_story(
        self,
        skeleton: Dict[str, Any],
        detailed_outline: Dict[str, Any]
    ) -> AsyncGenerator[ConductorEvent, None]:
        """Conduct a story from skeleton to completion.
        
        Args:
            skeleton: The skeleton story with placeholder nodes
            detailed_outline: The detailed outline with story structure, characters, etc.
            
        Yields:
            ConductorEvent objects for each step
        """
        # Extract context from skeleton and outline
        parameters = skeleton.get("parameters", skeleton.get("initial_variables", {}))
        
        # Handle nodes as either list or dict
        raw_nodes = skeleton.get("nodes", {})
        if isinstance(raw_nodes, list):
            # Convert list to dict keyed by node id
            nodes = {n.get("id", f"node_{i}"): n for i, n in enumerate(raw_nodes)}
        else:
            nodes = raw_nodes
            
        characters = skeleton.get("characters", [])
        objects = skeleton.get("objects", [])
        
        story_context = {
            "lore_outline": parameters.get("lore_outline", ""),
            "writing_style": parameters.get("lore_writing_style", ""),
            "theme": parameters.get("lore_theme", ""),
            "title": detailed_outline.get("title", skeleton.get("title", "")),
            "setting": detailed_outline.get("setting", ""),
            "tone": detailed_outline.get("tone", ""),
            "game_mechanics": detailed_outline.get("game_mechanics", {}),
            "story_structure": detailed_outline.get("story_structure", {}),
        }
        
        # Initialize intelligent coordinator if available
        if self.use_coordinator:
            try:
                self.coordinator = ExpansionCoordinator.from_outline(detailed_outline, skeleton)
                logger.info("Initialized ExpansionCoordinator for intelligent story generation")
            except Exception as e:
                logger.warning(f"Failed to initialize coordinator: {e}, falling back to basic mode")
                self.coordinator = None
        
        # Phase 1: Identify nodes that need expansion
        yield ConductorEvent(ConductorEventType.PHASE_START, {
            "phase": "analyzing",
            "message": "Analyzing story structure...",
            "using_coordinator": self.coordinator is not None
        })
        
        nodes_to_expand = self._identify_nodes_to_expand(nodes, detailed_outline)
        total_nodes = len(nodes_to_expand)
        
        if total_nodes == 0:
            yield ConductorEvent(ConductorEventType.COMPLETE, {
                "message": "No nodes need expansion",
                "nodes_expanded": 0
            })
            return
        
        yield ConductorEvent(ConductorEventType.PHASE_START, {
            "phase": "expanding",
            "message": f"Expanding {total_nodes} nodes...",
            "total_nodes": total_nodes
        })
        
        # Phase 2: Expand nodes sequentially (one by one for better UI feedback)
        expanded_nodes = {}
        errors = []
        completed = 0
        
        # Process nodes one at a time
        validation_issues = []
        for ctx in nodes_to_expand:
            # Emit expanding event for current node
            yield ConductorEvent(ConductorEventType.NODE_EXPANDING, {
                "node_id": ctx.node_id,
                "node_name": ctx.node_name,
                "progress": f"{completed}/{total_nodes}"
            })
            
            try:
                # Get rich context from coordinator if available
                if self.coordinator:
                    rich_ctx = self.coordinator.get_expansion_context(
                        node_id=ctx.node_id,
                        node_name=ctx.node_name,
                        placeholder_description=ctx.placeholder_description,
                        story_context=story_context,
                        adjacent_nodes=ctx.adjacent_nodes,
                        characters_here=ctx.characters_here,
                        objects_here=ctx.objects_here,
                        is_ending=ctx.is_ending,
                        ending_type=ctx.ending_type
                    )
                    # Expand with rich context
                    result = await asyncio.wait_for(
                        self._expand_with_rich_context(rich_ctx, story_context),
                        timeout=self.timeout_per_node
                    )
                else:
                    # Expand with basic context (legacy)
                    result = await asyncio.wait_for(
                        self._expand_single_node(ctx, story_context),
                        timeout=self.timeout_per_node
                    )
                
                expanded_nodes[ctx.node_id] = result
                completed += 1
                
                # Record expansion and validate with coordinator
                if self.coordinator:
                    self.coordinator.record_expansion(ctx.node_id, result)
                    issues = self.coordinator.validate_expansion(ctx.node_id, result)
                    if issues:
                        validation_issues.extend(issues)
                        logger.info(f"Node {ctx.node_id} has {len(issues)} validation notes")
                
                # Emit complete event with full node data for immediate graph update
                yield ConductorEvent(ConductorEventType.NODE_COMPLETE, {
                    "node_id": ctx.node_id,
                    "node_name": result.get("name", ctx.node_name),
                    "actions_count": len(result.get("actions", [])),
                    "objects_count": len(result.get("objects", [])),
                    "progress": f"{completed}/{total_nodes}",
                    "node_data": result,  # Include full node data for graph update
                    "validation_issues": [i for i in validation_issues if i.get("node_id") == ctx.node_id] if self.coordinator else []
                })
                
            except asyncio.TimeoutError:
                errors.append({"node_id": ctx.node_id, "error": "Timeout"})
                yield ConductorEvent(ConductorEventType.NODE_ERROR, {
                    "node_id": ctx.node_id,
                    "error": "Timeout while generating content"
                })
            except Exception as e:
                error_msg = str(e)
                errors.append({"node_id": ctx.node_id, "error": error_msg})
                yield ConductorEvent(ConductorEventType.NODE_ERROR, {
                    "node_id": ctx.node_id,
                    "error": error_msg
                })
        
        # Phase 3: Set character starting locations
        yield ConductorEvent(ConductorEventType.PHASE_START, {
            "phase": "placing_characters",
            "message": "Placing characters in locations..."
        })
        
        character_locations = await self._generate_character_locations(
            characters, expanded_nodes, detailed_outline, story_context
        )
        
        for placement in character_locations:
            yield ConductorEvent(ConductorEventType.CHARACTER_PLACED, {
                "character_id": placement["character_id"],
                "node_id": placement["node_id"]
            })
        
        # Phase 4: Generate node connections
        yield ConductorEvent(ConductorEventType.PHASE_START, {
            "phase": "connecting",
            "message": "Creating story flow connections..."
        })
        
        connections = await self._generate_connections(
            expanded_nodes, detailed_outline, story_context
        )
        
        yield ConductorEvent(ConductorEventType.CONNECTIONS_CREATING, {
            "connections_count": len(connections)
        })
        
        # Compile final result
        final_story = self._compile_final_story(
            skeleton, expanded_nodes, character_locations, connections
        )
        
        # Include coordinator summary if available
        coordinator_summary = None
        if self.coordinator:
            coordinator_summary = self.coordinator.get_summary()
        
        yield ConductorEvent(ConductorEventType.COMPLETE, {
            "message": f"Story completed! Expanded {completed} nodes with {len(errors)} errors.",
            "nodes_expanded": completed,
            "errors": errors,
            "validation_issues": validation_issues if self.coordinator else [],
            "coordinator_summary": coordinator_summary,
            "final_story": final_story
        })
    
    def _identify_nodes_to_expand(
        self,
        nodes: Dict[str, Any],
        detailed_outline: Dict[str, Any]
    ) -> List[NodeExpansionContext]:
        """Identify which nodes need expansion and gather context for each.
        
        Args:
            nodes: Current nodes dictionary
            detailed_outline: The detailed story outline
            
        Returns:
            List of NodeExpansionContext for each node needing expansion
        """
        contexts = []
        story_structure = detailed_outline.get("story_structure", {})
        endings = detailed_outline.get("endings", [])
        major_locations = detailed_outline.get("major_locations", [])
        characters = detailed_outline.get("characters", [])
        key_items = detailed_outline.get("key_items", [])
        
        # Build location-to-act mapping based on story structure
        location_beats = self._map_locations_to_beats(major_locations, story_structure)
        
        for node_id, node_data in nodes.items():
            description = node_data.get("description", "")
            
            # Check if this is a placeholder node (needs expansion)
            needs_expansion = (
                "[To be expanded]" in description or
                len(description) < 50 or
                not node_data.get("actions")
            )
            
            if not needs_expansion:
                continue
            
            # Find adjacent nodes
            adjacent = self._find_adjacent_nodes(node_id, nodes)
            
            # Determine which characters should be here
            chars_here = self._assign_characters_to_node(node_id, characters, major_locations)
            
            # Determine which objects should be here
            objects_here = self._assign_objects_to_node(node_id, key_items, major_locations)
            
            # Check if this is an ending node
            ending_info = next((e for e in endings if self._normalize_id(e.get("title", "")) == node_id), None)
            
            ctx = NodeExpansionContext(
                node_id=node_id,
                node_name=node_data.get("name", node_id),
                placeholder_description=description,
                story_context={},  # Will be filled in during expansion
                adjacent_nodes=adjacent,
                characters_here=chars_here,
                objects_here=objects_here,
                story_beat=location_beats.get(node_id, ""),
                is_ending=ending_info is not None or node_data.get("is_ending", False),
                ending_type=ending_info.get("type") if ending_info else None
            )
            contexts.append(ctx)
        
        return contexts
    
    def _map_locations_to_beats(
        self,
        locations: List[str],
        story_structure: Dict[str, str]
    ) -> Dict[str, str]:
        """Map location IDs to story beats from the structure."""
        beats = {}
        
        # Simple heuristic: first third is Act 1, middle is Act 2, last third is Act 3
        n = len(locations)
        for i, loc in enumerate(locations):
            loc_id = self._normalize_id(loc)
            if i < n / 3:
                beats[loc_id] = story_structure.get("act_1", "")
            elif i < 2 * n / 3:
                beats[loc_id] = story_structure.get("act_2", "")
            else:
                beats[loc_id] = story_structure.get("act_3", "")
        
        # Start node is always Act 1
        beats["start"] = story_structure.get("act_1", "")
        
        return beats
    
    def _find_adjacent_nodes(
        self,
        node_id: str,
        nodes: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Find nodes connected to this node."""
        adjacent = []
        for nid, ndata in nodes.items():
            if nid == node_id:
                continue
            # Check if any action in this node leads to our node
            for action in ndata.get("actions", []):
                for effect in action.get("effects", []):
                    # Handle both "target" (canonical) and "target_node" (legacy/LLM may generate)
                    goto_target = effect.get("target") or effect.get("target_node")
                    if effect.get("type") == "goto_node" and goto_target == node_id:
                        adjacent.append({"id": nid, "name": ndata.get("name", nid), "direction": "from"})
            # Check if any action in our node leads to this node
            current_node = nodes.get(node_id, {})
            for action in current_node.get("actions", []):
                for effect in action.get("effects", []):
                    goto_target = effect.get("target") or effect.get("target_node")
                    if effect.get("type") == "goto_node" and goto_target == nid:
                        adjacent.append({"id": nid, "name": ndata.get("name", nid), "direction": "to"})
        return adjacent
    
    def _assign_characters_to_node(
        self,
        node_id: str,
        characters: List[Dict[str, Any]],
        locations: List[str]
    ) -> List[Dict[str, Any]]:
        """Determine which characters should appear in this node."""
        chars = []
        for char in characters:
            role = char.get("role", "").lower()
            # Protagonist is always with the player, not placed
            if role == "protagonist":
                continue
            # Antagonist typically appears near the end
            if role == "antagonist" and node_id not in ["start"]:
                # Place antagonist in later locations or ending-related nodes
                if any(loc_id in node_id for loc_id in ["final", "end", "boss", "climax"]):
                    chars.append(char)
            # Allies/NPCs can be placed based on name matching or early locations
            elif role in ["ally", "npc", "ally/unknown"]:
                # Simple heuristic: NPCs in middle locations
                chars.append(char)
        return chars[:2]  # Limit to 2 characters per node
    
    def _assign_objects_to_node(
        self,
        node_id: str,
        items: List[Dict[str, Any]],
        locations: List[str]
    ) -> List[Dict[str, Any]]:
        """Determine which objects should appear in this node."""
        # Simple distribution: spread items across locations
        objects = []
        for i, item in enumerate(items):
            # Hash-based assignment for deterministic distribution
            loc_index = hash(item.get("id", "")) % max(len(locations), 1)
            if loc_index < len(locations):
                assigned_loc = self._normalize_id(locations[loc_index])
                if assigned_loc == node_id or node_id == "start":
                    objects.append(item)
        return objects[:3]  # Limit to 3 objects per node
    
    def _normalize_id(self, name: str) -> str:
        """Normalize a name to a valid ID."""
        return name.lower().replace(" ", "_").replace("'", "").replace("-", "_").replace("(", "").replace(")", "").replace(",", "")
    
    async def _expand_node_with_semaphore(
        self,
        ctx: NodeExpansionContext,
        story_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Expand a node with semaphore-controlled concurrency."""
        async with self.semaphore:
            return await asyncio.wait_for(
                self._expand_single_node(ctx, story_context),
                timeout=self.timeout_per_node
            )
    
    async def _expand_single_node(
        self,
        ctx: NodeExpansionContext,
        story_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Expand a single node using LLM.
        
        Args:
            ctx: The node expansion context
            story_context: Global story context (lore, style, etc.)
            
        Returns:
            Expanded node data
        """
        prompt = self._build_node_expansion_prompt(ctx, story_context)
        
        try:
            response = await self.llm_provider.generate_response(prompt)
            node_data = self._parse_node_response(response, ctx)
            return node_data
        except Exception as e:
            logger.error(f"Error expanding node {ctx.node_id}: {e}")
            # Return a basic expansion on error
            return {
                "id": ctx.node_id,
                "name": ctx.node_name,
                "definition": f"Location: {ctx.node_name}",
                "explicit_state": f"You are in {ctx.node_name}. {ctx.story_beat or 'The story continues here.'}",
                "implicit_state": "",
                "properties": {"status": []},
                "actions": [],
                "objects": [],
                "triggers": [],
                "is_ending": ctx.is_ending
            }
    
    async def _expand_with_rich_context(
        self,
        rich_ctx: 'RichExpansionContext',
        story_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Expand a node using rich context from the coordinator.
        
        This method uses the enhanced context from ExpansionCoordinator
        which includes narrative state, economy balance, and constraints.
        
        Args:
            rich_ctx: Rich expansion context from coordinator
            story_context: Basic story context (for fallback)
            
        Returns:
            Expanded node data
        """
        # Build enhanced prompt using rich context
        prompt = self._build_rich_expansion_prompt(rich_ctx)
        
        try:
            response = await self.llm_provider.generate_response(prompt)
            node_data = self._parse_rich_response(response, rich_ctx)
            return node_data
        except Exception as e:
            logger.error(f"Error expanding node {rich_ctx.node_id} with rich context: {e}")
            # Fallback to basic expansion
            basic_ctx = NodeExpansionContext(
                node_id=rich_ctx.node_id,
                node_name=rich_ctx.node_name,
                placeholder_description=rich_ctx.placeholder_description,
                story_context=story_context,
                adjacent_nodes=rich_ctx.adjacent_nodes,
                characters_here=rich_ctx.characters_here,
                objects_here=rich_ctx.objects_here,
                story_beat=rich_ctx.story_beat,
                is_ending=rich_ctx.is_ending,
                ending_type=rich_ctx.ending_type
            )
            return await self._expand_single_node(basic_ctx, story_context)
    
    def _build_rich_expansion_prompt(self, rich_ctx: 'RichExpansionContext') -> str:
        """Build an enhanced prompt using rich context.
        
        Args:
            rich_ctx: Rich expansion context
            
        Returns:
            Complete prompt string
        """
        # Get the context string from rich context
        context_section = rich_ctx.to_prompt_context()
        
        # Add the task and output format
        prompt = f"""{context_section}

# YOUR TASK
Generate a complete node definition:
- **definition**: Static rules and interaction guidelines for the LLM (immutable)
- **explicit_state**: Current player-visible scene description in second person (100-200 words)
- **implicit_state**: Hidden context/secrets for AI reference (optional)
- **properties**: Flexible dict with status tags, visit_count, etc.

Include:
1. A vivid, atmospheric explicit_state in second person
2. 2-4 node-level actions the player can take, mainly navigation or major scene-level choices
3. Any objects present in this location using the DSPP model; object interactions belong in each object's definition
4. Optional triggers

# OUTPUT FORMAT (JSON)
{{
  "definition": "Static rules: what this location IS, key atmosphere, state conditions, and any scene-level interaction guidance.",
  "explicit_state": "Your vivid scene description here in second person, present tense (100-200 words)...",
  "implicit_state": "Hidden plot secrets or AI context not shown to player",
  "properties": {{"status": [], "visit_count": 0}},
  "actions": [
    {{
      "id": "action_id",
      "text": "What the player sees as the action",
      "intent": "Optional natural-language behavior interpreted by the Architect",
      "effects": [
        {{"type": "effect_type", ...effect_params}}
      ],
      "conditions": []
    }}
  ],
  "objects": [
    {{
      "id": "object_id",
      "name": "Object Name",
      "definition": "What this object IS and its interaction rules. Put interaction rules here using clear sections such as [Description] and [Interaction Rules] with ## headings.",
      "explicit_state": "Current visible state of the object",
      "implicit_state": "Hidden context or function of the object",
      "properties": {{"status": []}}
    }}
  ],
  "triggers": [
    {{
      "id": "trigger_id",
      "type": "pre_enter",
      "intent": "Optional natural-language behavior interpreted by the Architect",
      "effects": [...]
    }}
  ]
}}

# EFFECT TYPES (use "target" for ALL effects that reference an ID)
- display_text: {{"type": "display_text", "text": "..."}}
- goto_node: {{"type": "goto_node", "target": "node_id"}}
- set_variable: {{"type": "set_variable", "target": "var_name", "value": ...}}
- add_to_inventory: {{"type": "add_to_inventory", "target": "object_id"}}
- remove_from_inventory: {{"type": "remove_from_inventory", "target": "object_id"}}
- update_object_status: {{"type": "update_object_status", "target": "object_id", "add_status": ["tag"]}}
- calculate: {{"type": "calculate", "target": "var_name", "operation": "add", "value": 5}}

# IMPORTANT
- Use entity model: definition (rules), explicit_state (visible), properties (state)
- Use "text" for action display text
- Prefer object interaction rules in object definitions instead of stuffing object behavior into node actions
- Actions and triggers may use `intent` when natural-language behavior is clearer than raw effects
- Use "target" (NOT "target_node") for goto_node effects, e.g. {{"type": "goto_node", "target": "node_id"}}
- Include navigation actions to adjacent locations
- Make actions meaningful and tied to the story
- FOLLOW THE CONSTRAINTS listed above

Output ONLY valid JSON, no markdown code blocks or extra text."""

        return prompt
    
    def _parse_rich_response(
        self,
        response: str,
        rich_ctx: 'RichExpansionContext'
    ) -> Dict[str, Any]:
        """Parse LLM response from rich context expansion.
        
        Args:
            response: LLM response text
            rich_ctx: The rich context used for expansion
            
        Returns:
            Parsed node data
        """
        # Reuse the basic parser but with rich context info
        basic_ctx = NodeExpansionContext(
            node_id=rich_ctx.node_id,
            node_name=rich_ctx.node_name,
            placeholder_description=rich_ctx.placeholder_description,
            story_context={},
            adjacent_nodes=rich_ctx.adjacent_nodes,
            characters_here=rich_ctx.characters_here,
            objects_here=rich_ctx.objects_here,
            story_beat=rich_ctx.story_beat,
            is_ending=rich_ctx.is_ending,
            ending_type=rich_ctx.ending_type
        )
        return self._parse_node_response(response, basic_ctx)
    
    def _build_node_expansion_prompt(
        self,
        ctx: NodeExpansionContext,
        story_context: Dict[str, Any]
    ) -> str:
        """Build the prompt for expanding a single node."""
        # Adjacent nodes info
        adjacent_info = ""
        if ctx.adjacent_nodes:
            adjacent_info = "Connected locations:\n"
            for adj in ctx.adjacent_nodes:
                adjacent_info += f"  - {adj['name']} ({adj['direction']} this location)\n"
        
        # Characters present
        chars_info = ""
        if ctx.characters_here:
            chars_info = "Characters present:\n"
            for char in ctx.characters_here:
                chars_info += f"  - {char.get('name', char.get('id'))}: {char.get('one_liner', char.get('description', ''))}\n"
        
        # Objects available
        objects_info = ""
        if ctx.objects_here:
            objects_info = "Key items that could be found here:\n"
            for obj in ctx.objects_here:
                objects_info += f"  - {obj.get('name', obj.get('id'))}: {obj.get('purpose', obj.get('description', ''))}\n"
        
        # Ending info
        ending_info = ""
        if ctx.is_ending:
            ending_info = f"\nThis is an ENDING node ({ctx.ending_type or 'neutral'} ending). The description should provide closure."
        
        prompt = f"""You are expanding a location/scene for an AI native text based game engine.

# STORY CONTEXT
Title: {story_context.get('title', 'Untitled')}
Setting: {story_context.get('setting', '')}
Theme: {story_context.get('theme', '')}
Tone: {story_context.get('tone', '')}

# WRITING STYLE
{story_context.get('writing_style', 'Write in second person, present tense. Be atmospheric and evocative.')}

# STORY BACKGROUND
{story_context.get('lore_outline', '')}

# CURRENT STORY BEAT
{ctx.story_beat or 'This scene continues the story.'}

# LOCATION TO EXPAND
Name: {ctx.node_name}
ID: {ctx.node_id}
{adjacent_info}
{chars_info}
{objects_info}
{ending_info}

# GAME MECHANICS
Key variables: {json.dumps(story_context.get('game_mechanics', {}).get('key_variables', []))}
Core gameplay: {story_context.get('game_mechanics', {}).get('core_loop', 'Explore and make choices')}

# YOUR TASK
Generate a complete node definition:
- **definition**: Static rules and interaction guidelines for the LLM (immutable)
- **explicit_state**: Current player-visible scene description in second person (100-200 words)
- **implicit_state**: Hidden context/secrets for AI reference (optional)
- **properties**: Flexible dict with status tags, visit_count, etc.

Include:
1. A vivid, atmospheric explicit_state in second person
2. 2-4 node-level actions the player can take, mainly navigation or major scene-level choices
3. Any objects present in this location using the DSPP model; object interactions belong in each object's definition
4. Optional triggers

# OUTPUT FORMAT (JSON)
{{
  "definition": "Static rules: what this location IS, key atmosphere, state conditions, and any scene-level interaction guidance.",
  "explicit_state": "Your vivid scene description here in second person, present tense (100-200 words)...",
  "implicit_state": "Hidden plot secrets or AI context not shown to player",
  "properties": {{"status": [], "visit_count": 0}},
  "actions": [
    {{
      "id": "action_id",
      "text": "What the player sees as the action",
      "intent": "Optional natural-language behavior interpreted by the Architect",
      "effects": [
        {{"type": "effect_type", ...effect_params}}
      ],
      "conditions": []
    }}
  ],
  "objects": [
    {{
      "id": "object_id",
      "name": "Object Name",
      "definition": "What this object IS and its interaction rules. Put interaction rules here using clear sections such as [Description] and [Interaction Rules] with ## headings.",
      "explicit_state": "Current visible state of the object",
      "implicit_state": "Hidden context or function of the object",
      "properties": {{"status": []}}
    }}
  ],
  "triggers": [
    {{
      "id": "trigger_id",
      "type": "pre_enter",
      "intent": "Optional natural-language behavior interpreted by the Architect",
      "effects": [...]
    }}
  ]
}}

# EFFECT TYPES (use "target" for ALL effects that reference an ID)
- display_text: {{"type": "display_text", "text": "..."}}
- goto_node: {{"type": "goto_node", "target": "node_id"}}
- set_variable: {{"type": "set_variable", "target": "var_name", "value": ...}}
- add_to_inventory: {{"type": "add_to_inventory", "target": "object_id"}}
- remove_from_inventory: {{"type": "remove_from_inventory", "target": "object_id"}}
- update_object_status: {{"type": "update_object_status", "target": "object_id", "add_status": ["tag"]}}
- calculate: {{"type": "calculate", "target": "var_name", "operation": "add", "value": 5}}

# IMPORTANT
- Use entity model: definition (rules), explicit_state (visible), properties (state)
- Use "text" for action display text
- Prefer object interaction rules in object definitions instead of stuffing object behavior into node actions
- Actions and triggers may use `intent` when natural-language behavior is clearer than raw effects
- Use "target" (NOT "target_node") for goto_node effects, e.g. {{"type": "goto_node", "target": "node_id"}}
- Include navigation actions to adjacent locations
- Make actions meaningful and tied to the story

Output ONLY valid JSON, no markdown code blocks or extra text."""

        return prompt
    
    def _parse_node_response(
        self,
        response: str,
        ctx: NodeExpansionContext
    ) -> Dict[str, Any]:
        """Parse LLM response into node data."""
        # Try to extract JSON
        try:
            # Remove markdown code blocks if present
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_str = response.strip()
            
            # Find JSON boundaries
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            
            data = json.loads(json_str)
            
            # Accept both 'definition'/'explicit_state' and 'description' field names
            definition = data.get("definition", "")
            explicit_state = data.get("explicit_state", data.get("description", ctx.placeholder_description))
            implicit_state = data.get("implicit_state", "")
            properties = data.get("properties", {"status": []})
            
            # Normalize object format
            objects = []
            for obj in data.get("objects", []):
                normalized_obj = {
                    "id": obj.get("id", ""),
                    "name": obj.get("name", obj.get("id", "")),
                    "definition": obj.get("definition", obj.get("description", "")),
                    "explicit_state": obj.get("explicit_state", obj.get("description", "")),
                    "implicit_state": obj.get("implicit_state", ""),
                    "properties": obj.get("properties", {"status": []})
                }
                objects.append(normalized_obj)
            
            # Normalize effects: convert "target_node" to "target" for goto_node effects
            # LLMs may generate "target_node" despite prompt instructions to use "target"
            actions = self._normalize_effects_in_list(data.get("actions", []))
            triggers = self._normalize_effects_in_list(data.get("triggers", []))
            
            # Ensure required fields
            return {
                "id": ctx.node_id,
                "name": ctx.node_name,
                "definition": definition,
                "explicit_state": explicit_state,
                "implicit_state": implicit_state,
                "properties": properties,
                "actions": actions,
                "objects": objects,
                "triggers": triggers,
                "is_ending": ctx.is_ending
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse node response for {ctx.node_id}: {e}")
            # Return basic structure
            return {
                "id": ctx.node_id,
                "name": ctx.node_name,
                "definition": "",
                "explicit_state": response[:500] if len(response) > 50 else ctx.placeholder_description,
                "implicit_state": "",
                "properties": {"status": []},
                "actions": [],
                "objects": [],
                "triggers": [],
                "is_ending": ctx.is_ending
            }
    
    @staticmethod
    def _normalize_effects_in_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize effects in a list of actions/triggers.
        
        Converts 'target_node' to 'target' in goto_node effects, since
        LLMs may generate the wrong field name despite prompt instructions.
        """
        for item in items:
            effects = item.get("effects", [])
            for effect in effects:
                if effect.get("type") == "goto_node" and "target_node" in effect:
                    if "target" not in effect or not effect["target"]:
                        effect["target"] = effect.pop("target_node")
                    else:
                        # "target" already exists, just remove the wrong field
                        effect.pop("target_node", None)
        return items
    
    async def _generate_character_locations(
        self,
        characters: List[Dict[str, Any]],
        expanded_nodes: Dict[str, Dict[str, Any]],
        detailed_outline: Dict[str, Any],
        story_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate starting locations for characters based on expanded nodes."""
        locations = []
        node_ids = list(expanded_nodes.keys())
        
        for char in characters:
            role = char.get("role", "").lower()
            char_id = char.get("id", "")
            
            if not char_id or role == "protagonist":
                continue
            
            # Determine a starting location based on role.
            if role == "antagonist":
                # Place in ending-related or final nodes.
                target_nodes = [nid for nid in node_ids if any(
                    kw in nid for kw in ["final", "end", "boss", "climax", "basement", "core"]
                )]
                if target_nodes:
                    locations.append({
                        "character_id": char_id,
                        "node_id": target_nodes[0],
                    })
            elif role in ["ally", "ally/unknown", "npc"]:
                # Place in middle locations.
                mid_index = len(node_ids) // 2
                if mid_index < len(node_ids):
                    locations.append({
                        "character_id": char_id,
                        "node_id": node_ids[mid_index],
                    })
        
        return locations
    
    async def _generate_connections(
        self,
        expanded_nodes: Dict[str, Dict[str, Any]],
        detailed_outline: Dict[str, Any],
        story_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate additional connections between nodes."""
        connections = []
        
        # For now, we rely on the navigation actions already in nodes
        # Future: Use LLM to generate conditional connections based on story flow
        
        endings = detailed_outline.get("endings", [])
        node_ids = list(expanded_nodes.keys())
        
        # Create connections to ending nodes if they exist
        for ending in endings:
            ending_id = self._normalize_id(ending.get("title", ""))
            if ending_id in node_ids:
                # Add connection from last non-ending node
                non_ending_nodes = [nid for nid in node_ids if not expanded_nodes[nid].get("is_ending")]
                if non_ending_nodes:
                    connections.append({
                        "from_node": non_ending_nodes[-1],
                        "to_node": ending_id,
                        "condition": ending.get("trigger", "")
                    })
        
        return connections
    
    def _compile_final_story(
        self,
        skeleton: Dict[str, Any],
        expanded_nodes: Dict[str, Dict[str, Any]],
        character_locations: List[Dict[str, Any]],
        connections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compile all pieces into a final story structure."""
        # Handle nodes as either list or dict
        raw_nodes = skeleton.get("nodes", {})
        if isinstance(raw_nodes, list):
            skeleton_nodes = {n.get("id", f"node_{i}"): n for i, n in enumerate(raw_nodes)}
        else:
            skeleton_nodes = raw_nodes
        
        # Start with skeleton
        final = {
            "id": skeleton.get("id", "generated_story"),
            "title": skeleton.get("title", "Generated Story"),
            "start_node": skeleton.get("start_node", "start"),
            "initial_variables": skeleton.get("initial_variables", skeleton.get("parameters", {})),
            "characters": skeleton.get("characters", []),
            "objects": skeleton.get("objects", []),
            "nodes": {}
        }
        
        # Merge skeleton nodes with expanded content
        for node_id, node_data in skeleton_nodes.items():
            if node_id in expanded_nodes:
                # Use expanded version
                final["nodes"][node_id] = {
                    **node_data,
                    **expanded_nodes[node_id]
                }
            else:
                # Keep original
                final["nodes"][node_id] = node_data
        
        # Apply character starting locations.
        char_map = {c.get("id"): c for c in final["characters"]}
        for placement in character_locations:
            char_id = placement["character_id"]
            if char_id in char_map:
                properties = char_map[char_id].setdefault("properties", {})
                properties["location"] = placement["node_id"]
        
        # Apply additional connections as actions
        for conn in connections:
            from_node = conn["from_node"]
            to_node = conn["to_node"]
            if from_node in final["nodes"]:
                node = final["nodes"][from_node]
                if "actions" not in node:
                    node["actions"] = []
                # Check if action already exists
                existing = any(
                    a.get("id") == f"go_to_{to_node}" 
                    for a in node["actions"]
                )
                if not existing:
                    node["actions"].append({
                        "id": f"go_to_{to_node}",
                        "text": f"Go to {to_node.replace('_', ' ').title()}",
                        "effects": [{"type": "goto_node", "target": to_node}]
                    })
        
        return final


def get_node_expansion_prompt(
    node_id: str,
    node_name: str,
    story_context: Dict[str, Any],
    story_beat: str = "",
    characters: List[Dict] = None,
    objects: List[Dict] = None,
    adjacent_nodes: List[Dict] = None,
    is_ending: bool = False,
    ending_type: str = None
) -> str:
    """Build a prompt for expanding a single node.
    
    This is a standalone function that can be used outside the conductor class.
    
    Args:
        node_id: The node's ID
        node_name: The node's display name
        story_context: Dict with lore_outline, writing_style, theme, etc.
        story_beat: What happens in the story at this point
        characters: Characters that appear in this node
        objects: Objects available in this node
        adjacent_nodes: Connected nodes
        is_ending: Whether this is an ending node
        ending_type: Type of ending (good/bad/neutral)
        
    Returns:
        Prompt string for LLM
    """
    ctx = NodeExpansionContext(
        node_id=node_id,
        node_name=node_name,
        placeholder_description="",
        story_context=story_context,
        adjacent_nodes=adjacent_nodes or [],
        characters_here=characters or [],
        objects_here=objects or [],
        story_beat=story_beat,
        is_ending=is_ending,
        ending_type=ending_type
    )
    
    conductor = StoryConductor(llm_provider=None)  # We only need the prompt builder
    return conductor._build_node_expansion_prompt(ctx, story_context)
