"""Expansion Coordinator - Intelligent context management for story generation.

This module provides the ExpansionCoordinator which manages context across
node expansions, ensuring consistency and providing rich context to each
LLM call. It integrates with WorldBlueprint, NumericalDesign, and NarrativeTracker.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple

from .world_blueprint import WorldBlueprint, BlueprintGenerator, PlotThread
from .numerical_design import NumericalDesign, DifficultyLevel
from .narrative_tracker import NarrativeTracker, FactType

logger = logging.getLogger(__name__)


@dataclass
class ExpansionConstraints:
    """Constraints for node expansion."""
    # Narrative constraints
    must_advance_plots: List[str] = field(default_factory=list)  # Plot thread IDs
    must_include_characters: List[str] = field(default_factory=list)  # Character IDs
    must_not_contradict: List[str] = field(default_factory=list)  # Established facts
    
    # Numerical constraints
    reward_range: Dict[str, Tuple[int, int]] = field(default_factory=dict)  # currency -> (min, max)
    stat_threshold_range: Tuple[int, int] = (35, 55)  # Default range for stat checks
    
    # Story requirements
    story_beat: Optional[str] = None
    required_actions: List[str] = field(default_factory=list)
    forbidden_elements: List[str] = field(default_factory=list)


@dataclass
class RichExpansionContext:
    """Rich context for node expansion with global awareness."""
    # Basic node info
    node_id: str
    node_name: str
    placeholder_description: str
    
    # Story context
    title: str
    setting: str
    theme: str
    tone: str
    writing_style: str
    lore_outline: str
    
    # From blueprint
    plot_threads_here: List[PlotThread]
    characters_here: List[Dict[str, Any]]
    objects_here: List[Dict[str, Any]]
    adjacent_nodes: List[Dict[str, str]]
    
    # From narrative tracker
    narrative_so_far: str  # Summary of established facts
    mentioned_entities: Dict[str, Set[str]]  # entity -> nodes
    
    # From numerical design
    economy_context: str  # Summary of economy state
    suggested_rewards: Dict[str, Tuple[int, int]]  # currency -> (min, max)
    suggested_thresholds: Dict[str, int]  # attribute -> threshold
    
    # Constraints
    constraints: ExpansionConstraints = field(default_factory=ExpansionConstraints)
    
    # Node-specific
    is_ending: bool = False
    ending_type: Optional[str] = None
    story_beat: Optional[str] = None
    
    def to_prompt_context(self) -> str:
        """Convert to a string suitable for LLM prompts."""
        sections = []
        
        # Basic story context
        sections.append(f"""# STORY CONTEXT
Title: {self.title}
Setting: {self.setting}
Theme: {self.theme}
Tone: {self.tone}

# WRITING STYLE
{self.writing_style}

# STORY BACKGROUND
{self.lore_outline}""")
        
        # Current story beat
        if self.story_beat:
            sections.append(f"""
# CURRENT STORY BEAT
{self.story_beat}""")
        
        # Node info
        sections.append(f"""
# LOCATION TO EXPAND
Name: {self.node_name}
ID: {self.node_id}""")
        
        # Adjacent nodes
        if self.adjacent_nodes:
            adj_lines = ["Connected locations:"]
            for adj in self.adjacent_nodes:
                adj_lines.append(f"  - {adj.get('name', adj.get('id'))} ({adj.get('direction', 'nearby')})")
            sections.append("\n".join(adj_lines))
        
        # Characters
        if self.characters_here:
            char_lines = ["Characters present:"]
            for char in self.characters_here:
                char_lines.append(f"  - {char.get('name', char.get('id'))}: {char.get('description', '')[:100]}")
            sections.append("\n".join(char_lines))
        
        # Objects
        if self.objects_here:
            obj_lines = ["Key items that could be found here:"]
            for obj in self.objects_here:
                obj_lines.append(f"  - {obj.get('name', obj.get('id'))}: {obj.get('purpose', obj.get('description', ''))[:80]}")
            sections.append("\n".join(obj_lines))
        
        # Narrative state
        if self.narrative_so_far:
            sections.append(f"""
# NARRATIVE STATE (What's already established)
{self.narrative_so_far}""")
        
        # Economy context
        if self.economy_context:
            sections.append(f"""
# ECONOMY/BALANCE CONTEXT
{self.economy_context}""")
        
        # Constraints
        constraint_lines = []
        if self.constraints.must_advance_plots:
            constraint_lines.append(f"- MUST advance plot threads: {', '.join(self.constraints.must_advance_plots)}")
        if self.constraints.must_include_characters:
            constraint_lines.append(f"- MUST include characters: {', '.join(self.constraints.must_include_characters)}")
        if self.constraints.reward_range:
            for currency, (min_v, max_v) in self.constraints.reward_range.items():
                constraint_lines.append(f"- Reward constraint: {currency} should be {min_v}-{max_v}")
        if self.constraints.stat_threshold_range:
            min_t, max_t = self.constraints.stat_threshold_range
            constraint_lines.append(f"- Difficulty constraint: stat checks should use threshold {min_t}-{max_t}")
        
        if constraint_lines:
            sections.append("# CONSTRAINTS\n" + "\n".join(constraint_lines))
        
        # Do not contradict
        if self.constraints.must_not_contradict:
            sections.append("# DO NOT CONTRADICT\n" + "\n".join(f"- {fact}" for fact in self.constraints.must_not_contradict[:5]))
        
        # Ending info
        if self.is_ending:
            sections.append(f"""
# ENDING NODE
This is an ENDING node ({self.ending_type or 'neutral'} ending). The description should provide closure.""")
        
        return "\n".join(sections)


class ExpansionCoordinator:
    """Coordinates node expansion with global awareness.
    
    This class manages the state across multiple node expansions, providing
    each expansion with rich context from the blueprint, numerical design,
    and narrative tracker.
    """
    
    def __init__(
        self,
        blueprint: Optional[WorldBlueprint] = None,
        numerical_design: Optional[NumericalDesign] = None,
        narrative_tracker: Optional[NarrativeTracker] = None
    ):
        """Initialize the coordinator.
        
        Args:
            blueprint: The world blueprint
            numerical_design: The numerical design tracker
            narrative_tracker: The narrative tracker
        """
        self.blueprint = blueprint or WorldBlueprint()
        self.numerical_design = numerical_design or NumericalDesign()
        self.narrative_tracker = narrative_tracker or NarrativeTracker()
        
        # Track expanded nodes
        self.expanded_nodes: Dict[str, Dict[str, Any]] = {}
        
        # Track expansion order
        self.expansion_order: List[str] = []
    
    @classmethod
    def from_outline(
        cls,
        detailed_outline: Dict[str, Any],
        existing_story: Optional[Dict[str, Any]] = None
    ) -> 'ExpansionCoordinator':
        """Create a coordinator from a detailed outline.
        
        Args:
            detailed_outline: The detailed story outline
            existing_story: Optional existing story for context
            
        Returns:
            Configured ExpansionCoordinator
        """
        # Generate blueprint
        generator = BlueprintGenerator()
        blueprint = generator.generate_from_outline(detailed_outline, existing_story)
        
        # Create numerical design
        numerical_design = NumericalDesign()
        if existing_story:
            numerical_design.extract_from_story(existing_story)
        
        # Configure from outline
        game_mechanics = detailed_outline.get("game_mechanics", {})
        for var in game_mechanics.get("key_variables", []):
            if isinstance(var, dict):
                var_id = var.get("name", var.get("id", ""))
                var_type = var.get("type", "").lower()
                
                if var_type in ["currency", "resource"]:
                    numerical_design.configure_currency(
                        var_id,
                        var.get("initial", 0),
                        var.get("critical", 0)
                    )
                elif var_type in ["attribute", "stat"]:
                    numerical_design.configure_attribute(
                        var_id,
                        var.get("initial", 50)
                    )
        
        # Create narrative tracker
        narrative_tracker = NarrativeTracker()
        if existing_story:
            narrative_tracker.extract_from_story(existing_story)
        
        return cls(blueprint, numerical_design, narrative_tracker)
    
    def get_expansion_context(
        self,
        node_id: str,
        node_name: str,
        placeholder_description: str,
        story_context: Dict[str, Any],
        adjacent_nodes: List[Dict[str, str]],
        characters_here: List[Dict[str, Any]],
        objects_here: List[Dict[str, Any]],
        is_ending: bool = False,
        ending_type: Optional[str] = None
    ) -> RichExpansionContext:
        """Build rich context for node expansion.
        
        Args:
            node_id: The node ID
            node_name: The node name
            placeholder_description: Initial description
            story_context: Basic story context
            adjacent_nodes: Adjacent node info
            characters_here: Characters in this node
            objects_here: Objects in this node
            is_ending: Whether this is an ending node
            ending_type: Type of ending
            
        Returns:
            RichExpansionContext with all context
        """
        # Get plot threads for this node
        plot_threads = self.blueprint.get_plot_threads_for_node(node_id)
        
        # Get node requirements from blueprint
        requirements = self.blueprint.get_node_requirements(node_id)
        story_beat = requirements.get("story_beat", story_context.get("story_beat"))
        
        # Build constraints
        constraints = self._build_constraints(node_id, plot_threads, requirements)
        
        # Get narrative context
        narrative_context = self.narrative_tracker.to_context_string()
        mentioned = self.narrative_tracker.get_mentioned_entities()
        
        # Get economy context
        economy_context = self.numerical_design.to_context_string()
        
        # Get suggested rewards and thresholds
        suggested_rewards = {}
        for currency_id in self.numerical_design.currency_configs.keys():
            suggested_rewards[currency_id] = self.numerical_design.suggest_reward(
                "work",  # Default action type
                DifficultyLevel.NORMAL,
                currency_id
            )
        
        suggested_thresholds = {}
        for attr_id in self.numerical_design.attribute_configs.keys():
            suggested_thresholds[attr_id] = self.numerical_design.suggest_threshold(
                attr_id,
                DifficultyLevel.NORMAL,
                self._get_period_for_node(node_id)
            )
        
        return RichExpansionContext(
            node_id=node_id,
            node_name=node_name,
            placeholder_description=placeholder_description,
            title=story_context.get("title", ""),
            setting=story_context.get("setting", ""),
            theme=story_context.get("theme", ""),
            tone=story_context.get("tone", ""),
            writing_style=story_context.get("writing_style", ""),
            lore_outline=story_context.get("lore_outline", ""),
            plot_threads_here=plot_threads,
            characters_here=characters_here,
            objects_here=objects_here,
            adjacent_nodes=adjacent_nodes,
            narrative_so_far=narrative_context,
            mentioned_entities=mentioned,
            economy_context=economy_context,
            suggested_rewards=suggested_rewards,
            suggested_thresholds=suggested_thresholds,
            constraints=constraints,
            is_ending=is_ending,
            ending_type=ending_type,
            story_beat=story_beat
        )
    
    def record_expansion(
        self,
        node_id: str,
        expanded_data: Dict[str, Any]
    ):
        """Record a completed node expansion.
        
        This updates the narrative tracker and numerical design with
        information from the expanded node.
        
        Args:
            node_id: The node ID
            expanded_data: The expanded node data
        """
        self.expanded_nodes[node_id] = expanded_data
        self.expansion_order.append(node_id)
        
        # Update narrative tracker with description
        description = expanded_data.get("description", expanded_data.get("explicit_state", ""))
        if description:
            # Extract entities
            entities = set()
            for char in expanded_data.get("characters", []):
                if isinstance(char, dict):
                    entities.add(char.get("id", ""))
                elif isinstance(char, str):
                    entities.add(char)
            
            self.narrative_tracker.establish_fact(
                fact_id=f"{node_id}_description",
                fact_type=FactType.WORLD,
                content=description,
                source_node=node_id,
                entities=entities
            )
        
        # Update numerical design with actions
        for action in expanded_data.get("actions", []):
            if isinstance(action, dict):
                action_id = action.get("id", "")
                self.numerical_design._extract_from_node(node_id, {"actions": [action]})
        
        # Update plot thread states
        for thread_id, thread in self.blueprint.narrative.plot_threads.items():
            if node_id in thread.setup_nodes:
                self.narrative_tracker.update_plot_thread(thread_id, status="setup", node_visited=node_id)
            elif node_id in thread.development_nodes:
                self.narrative_tracker.update_plot_thread(thread_id, status="development", node_visited=node_id)
            elif node_id in thread.resolution_nodes:
                self.narrative_tracker.update_plot_thread(thread_id, status="resolved", node_visited=node_id)
    
    def validate_expansion(
        self,
        node_id: str,
        expanded_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate an expanded node against constraints.
        
        Args:
            node_id: The node ID
            expanded_data: The expanded node data
            
        Returns:
            List of validation issues (empty if valid)
        """
        issues = []
        
        # Check narrative consistency
        description = expanded_data.get("description", "")
        contradictions = self.narrative_tracker.find_contradictions(
            node_id, description
        )
        for c in contradictions:
            issues.append({
                "type": "narrative_contradiction",
                "severity": c.severity,
                "detail": c.detail,
                "suggestion": c.suggestion
            })
        
        # Check numerical constraints
        for action in expanded_data.get("actions", []):
            for effect in action.get("effects", []):
                if effect.get("type") == "calculate":
                    target = effect.get("target", "")
                    value = effect.get("value", 0)
                    
                    # Check if reward is in reasonable range
                    if target in self.numerical_design.currency_configs:
                        suggested = self.numerical_design.suggest_reward(
                            "work", DifficultyLevel.NORMAL, target
                        )
                        if value < suggested[0] * 0.5 or value > suggested[1] * 2:
                            issues.append({
                                "type": "economy_imbalance",
                                "severity": "warning",
                                "detail": f"Reward {value} for {target} outside suggested range {suggested}",
                                "suggestion": f"Consider using a value between {suggested[0]} and {suggested[1]}"
                            })
        
        # Check required characters are mentioned
        requirements = self.blueprint.get_node_requirements(node_id)
        required_chars = requirements.get("must_include_characters", [])
        for char_id in required_chars:
            if char_id.lower() not in description.lower():
                issues.append({
                    "type": "missing_character",
                    "severity": "warning",
                    "detail": f"Required character {char_id} not mentioned in description",
                    "suggestion": f"Consider including {char_id} in the scene"
                })
        
        return issues
    
    def _build_constraints(
        self,
        node_id: str,
        plot_threads: List[PlotThread],
        requirements: Dict[str, Any]
    ) -> ExpansionConstraints:
        """Build constraints for a node expansion.
        
        Args:
            node_id: The node ID
            plot_threads: Plot threads involving this node
            requirements: Node requirements from blueprint
            
        Returns:
            ExpansionConstraints
        """
        constraints = ExpansionConstraints()
        
        # Plot thread constraints
        for thread in plot_threads:
            if node_id in thread.setup_nodes:
                constraints.must_advance_plots.append(f"{thread.id} (setup)")
            elif node_id in thread.development_nodes:
                constraints.must_advance_plots.append(f"{thread.id} (develop)")
            elif node_id in thread.resolution_nodes:
                constraints.must_advance_plots.append(f"{thread.id} (resolve)")
        
        # Character constraints
        characters_for_node = self.blueprint.get_characters_for_node(node_id)
        constraints.must_include_characters = characters_for_node
        
        # Reward constraints
        for currency_id in self.numerical_design.currency_configs.keys():
            suggested = self.numerical_design.suggest_reward(
                "work", DifficultyLevel.NORMAL, currency_id
            )
            constraints.reward_range[currency_id] = suggested
        
        # Difficulty constraints based on period
        period = self._get_period_for_node(node_id)
        settings = self.numerical_design.difficulty_settings.get(period, {})
        if settings:
            constraints.stat_threshold_range = (
                settings.get("easy", 30),
                settings.get("hard", 60)
            )
        
        # Story beat
        constraints.story_beat = requirements.get("story_beat")
        
        # Established facts to not contradict
        recent_facts = self.narrative_tracker.get_established_facts()[-10:]
        constraints.must_not_contradict = [f"{f.source_node}: {f.content[:80]}" for f in recent_facts]
        
        return constraints
    
    def _get_period_for_node(self, node_id: str) -> str:
        """Determine the game period for a node.
        
        Args:
            node_id: The node ID
            
        Returns:
            Period string ("early", "mid", "late")
        """
        # Use expansion order to determine period
        if node_id in self.expansion_order:
            idx = self.expansion_order.index(node_id)
        else:
            idx = len(self.expansion_order)
        
        total_nodes = len(self.blueprint.entities.locations) or 10
        
        if idx < total_nodes * 0.3:
            return "early"
        elif idx < total_nodes * 0.7:
            return "mid"
        else:
            return "late"
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the coordinator state.
        
        Returns:
            Dictionary with state summary
        """
        return {
            "nodes_expanded": len(self.expanded_nodes),
            "expansion_order": self.expansion_order,
            "plot_thread_states": {
                tid: {
                    "status": t.status,
                    "nodes_visited": t.nodes_visited
                }
                for tid, t in self.narrative_tracker.plot_threads.items()
            },
            "economy_status": {
                cid: self.numerical_design.analyze_balance(cid).status.value
                for cid in self.numerical_design.currency_configs.keys()
            },
            "facts_established": len(self.narrative_tracker.established_facts)
        }
