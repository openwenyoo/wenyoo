"""World Blueprint - Comprehensive story structure analysis and planning.

This module provides the WorldBlueprint system that analyzes story outlines
to create a unified plan for narrative structure, numerical design, and
entity management. The blueprint serves as the "source of truth" for
coordinated story generation.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class PlotThreadStatus(str, Enum):
    """Status of a plot thread."""
    NOT_STARTED = "not_started"
    SETUP = "setup"
    DEVELOPMENT = "development"
    CLIMAX = "climax"
    RESOLVED = "resolved"


class CharacterArcStage(str, Enum):
    """Stage of a character's arc."""
    INTRODUCTION = "introduction"
    DEVELOPMENT = "development"
    TRANSFORMATION = "transformation"
    RESOLUTION = "resolution"


@dataclass
class PlotThread:
    """A narrative thread that runs through the story."""
    id: str
    name: str
    description: str
    setup_nodes: List[str] = field(default_factory=list)
    development_nodes: List[str] = field(default_factory=list)
    resolution_nodes: List[str] = field(default_factory=list)
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)
    status: PlotThreadStatus = PlotThreadStatus.NOT_STARTED
    priority: int = 1  # 1 = main plot, 2 = subplot, 3 = minor thread


@dataclass
class CharacterArc:
    """Character development arc."""
    character_id: str
    stages: List[str]  # Description of each stage
    current_stage: int = 0
    trigger_nodes: Dict[str, int] = field(default_factory=dict)  # node_id -> stage
    relationships: Dict[str, str] = field(default_factory=dict)  # char_id -> relationship


@dataclass
class CurrencyConfig:
    """Configuration for a game currency."""
    id: str
    name: str
    initial_value: int
    earn_rate_min: int
    earn_rate_max: int
    spend_rate_min: int
    spend_rate_max: int
    critical_threshold: int = 0
    description: str = ""


@dataclass
class AttributeConfig:
    """Configuration for a player attribute."""
    id: str
    name: str
    min_value: int = 0
    max_value: int = 100
    initial_value: int = 50
    checks: List[str] = field(default_factory=list)  # Actions that use this attribute
    growth_rate: float = 0.0  # Expected growth per action


@dataclass
class DifficultySettings:
    """Difficulty settings for a time period."""
    period: str  # e.g., "week_1", "early_game"
    easy_threshold: int = 30
    normal_threshold: int = 40
    hard_threshold: int = 60


@dataclass 
class EconomyDesign:
    """Economy design configuration."""
    currencies: Dict[str, CurrencyConfig] = field(default_factory=dict)
    balance_rules: List[str] = field(default_factory=list)
    income_sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # action -> {currency, min, max}
    expense_sinks: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # action -> {currency, min, max}


@dataclass
class NarrativeDesign:
    """Narrative structure design."""
    main_plot: List[Dict[str, str]] = field(default_factory=list)  # [{act_1: "..."}, ...]
    plot_threads: Dict[str, PlotThread] = field(default_factory=dict)
    character_arcs: Dict[str, CharacterArc] = field(default_factory=dict)
    themes: List[str] = field(default_factory=list)
    tone: str = ""
    writing_style: str = ""


@dataclass
class EntityRegistry:
    """Registry of all entities in the story."""
    characters: Set[str] = field(default_factory=set)
    locations: Set[str] = field(default_factory=set)
    objects: Set[str] = field(default_factory=set)
    key_items: Set[str] = field(default_factory=set)
    variables: Set[str] = field(default_factory=set)
    
    # Relationships
    character_locations: Dict[str, List[str]] = field(default_factory=dict)  # char -> [locations]
    object_locations: Dict[str, str] = field(default_factory=dict)  # object -> location
    

@dataclass
class WorldBlueprint:
    """Complete blueprint for story generation.
    
    This serves as the central "source of truth" for the intelligent conductor,
    containing all structural, narrative, and numerical design information.
    """
    # Metadata
    title: str = ""
    genre: str = ""
    setting: str = ""
    
    # Core designs
    narrative: NarrativeDesign = field(default_factory=NarrativeDesign)
    economy: EconomyDesign = field(default_factory=EconomyDesign)
    entities: EntityRegistry = field(default_factory=EntityRegistry)
    
    # Attributes and difficulty
    attributes: Dict[str, AttributeConfig] = field(default_factory=dict)
    difficulty_curve: Dict[str, DifficultySettings] = field(default_factory=dict)
    
    # Node-specific requirements
    node_requirements: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def get_plot_threads_for_node(self, node_id: str) -> List[PlotThread]:
        """Get plot threads that involve this node."""
        threads = []
        for thread in self.narrative.plot_threads.values():
            if (node_id in thread.setup_nodes or 
                node_id in thread.development_nodes or
                node_id in thread.resolution_nodes):
                threads.append(thread)
        return threads
    
    def get_characters_for_node(self, node_id: str) -> List[str]:
        """Get characters that should appear in this node."""
        characters = []
        for char_id, locations in self.entities.character_locations.items():
            if node_id in locations:
                characters.append(char_id)
        return characters
    
    def get_thresholds_for_period(self, period: str) -> DifficultySettings:
        """Get difficulty thresholds for a time period."""
        if period in self.difficulty_curve:
            return self.difficulty_curve[period]
        # Return default
        return DifficultySettings(period=period)
    
    def get_node_requirements(self, node_id: str) -> Dict[str, Any]:
        """Get specific requirements for a node."""
        return self.node_requirements.get(node_id, {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "genre": self.genre,
            "setting": self.setting,
            "narrative": {
                "main_plot": self.narrative.main_plot,
                "themes": self.narrative.themes,
                "tone": self.narrative.tone,
                "writing_style": self.narrative.writing_style,
                "plot_threads": {
                    tid: {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description,
                        "setup_nodes": t.setup_nodes,
                        "development_nodes": t.development_nodes,
                        "resolution_nodes": t.resolution_nodes,
                        "status": t.status.value,
                        "priority": t.priority
                    }
                    for tid, t in self.narrative.plot_threads.items()
                },
                "character_arcs": {
                    cid: {
                        "character_id": arc.character_id,
                        "stages": arc.stages,
                        "current_stage": arc.current_stage,
                        "trigger_nodes": arc.trigger_nodes
                    }
                    for cid, arc in self.narrative.character_arcs.items()
                }
            },
            "economy": {
                "currencies": {
                    cid: {
                        "id": c.id,
                        "name": c.name,
                        "initial_value": c.initial_value,
                        "earn_rate": f"{c.earn_rate_min}-{c.earn_rate_max}",
                        "spend_rate": f"{c.spend_rate_min}-{c.spend_rate_max}",
                        "critical_threshold": c.critical_threshold
                    }
                    for cid, c in self.economy.currencies.items()
                },
                "balance_rules": self.economy.balance_rules,
                "income_sources": self.economy.income_sources,
                "expense_sinks": self.economy.expense_sinks
            },
            "entities": {
                "characters": list(self.entities.characters),
                "locations": list(self.entities.locations),
                "objects": list(self.entities.objects),
                "key_items": list(self.entities.key_items),
                "character_locations": self.entities.character_locations
            },
            "attributes": {
                aid: {
                    "id": a.id,
                    "name": a.name,
                    "initial_value": a.initial_value,
                    "checks": a.checks
                }
                for aid, a in self.attributes.items()
            },
            "difficulty_curve": {
                did: {
                    "period": d.period,
                    "easy_threshold": d.easy_threshold,
                    "normal_threshold": d.normal_threshold,
                    "hard_threshold": d.hard_threshold
                }
                for did, d in self.difficulty_curve.items()
            },
            "node_requirements": self.node_requirements
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorldBlueprint':
        """Create from dictionary."""
        blueprint = cls()
        blueprint.title = data.get("title", "")
        blueprint.genre = data.get("genre", "")
        blueprint.setting = data.get("setting", "")
        
        # Parse narrative
        narrative_data = data.get("narrative", {})
        blueprint.narrative.main_plot = narrative_data.get("main_plot", [])
        blueprint.narrative.themes = narrative_data.get("themes", [])
        blueprint.narrative.tone = narrative_data.get("tone", "")
        blueprint.narrative.writing_style = narrative_data.get("writing_style", "")
        
        for tid, tdata in narrative_data.get("plot_threads", {}).items():
            blueprint.narrative.plot_threads[tid] = PlotThread(
                id=tdata.get("id", tid),
                name=tdata.get("name", ""),
                description=tdata.get("description", ""),
                setup_nodes=tdata.get("setup_nodes", []),
                development_nodes=tdata.get("development_nodes", []),
                resolution_nodes=tdata.get("resolution_nodes", []),
                status=PlotThreadStatus(tdata.get("status", "not_started")),
                priority=tdata.get("priority", 1)
            )
        
        for cid, cdata in narrative_data.get("character_arcs", {}).items():
            blueprint.narrative.character_arcs[cid] = CharacterArc(
                character_id=cdata.get("character_id", cid),
                stages=cdata.get("stages", []),
                current_stage=cdata.get("current_stage", 0),
                trigger_nodes=cdata.get("trigger_nodes", {})
            )
        
        # Parse economy
        economy_data = data.get("economy", {})
        for cid, cdata in economy_data.get("currencies", {}).items():
            earn_rate = cdata.get("earn_rate", "0-0")
            spend_rate = cdata.get("spend_rate", "0-0")
            
            earn_parts = earn_rate.split("-") if isinstance(earn_rate, str) else [earn_rate, earn_rate]
            spend_parts = spend_rate.split("-") if isinstance(spend_rate, str) else [spend_rate, spend_rate]
            
            blueprint.economy.currencies[cid] = CurrencyConfig(
                id=cid,
                name=cdata.get("name", cid),
                initial_value=cdata.get("initial_value", 0),
                earn_rate_min=int(earn_parts[0]) if earn_parts else 0,
                earn_rate_max=int(earn_parts[-1]) if earn_parts else 0,
                spend_rate_min=int(spend_parts[0]) if spend_parts else 0,
                spend_rate_max=int(spend_parts[-1]) if spend_parts else 0,
                critical_threshold=cdata.get("critical_threshold", 0)
            )
        
        blueprint.economy.balance_rules = economy_data.get("balance_rules", [])
        blueprint.economy.income_sources = economy_data.get("income_sources", {})
        blueprint.economy.expense_sinks = economy_data.get("expense_sinks", {})
        
        # Parse entities
        entities_data = data.get("entities", {})
        blueprint.entities.characters = set(entities_data.get("characters", []))
        blueprint.entities.locations = set(entities_data.get("locations", []))
        blueprint.entities.objects = set(entities_data.get("objects", []))
        blueprint.entities.key_items = set(entities_data.get("key_items", []))
        blueprint.entities.character_locations = entities_data.get("character_locations", {})
        
        # Parse attributes
        for aid, adata in data.get("attributes", {}).items():
            blueprint.attributes[aid] = AttributeConfig(
                id=aid,
                name=adata.get("name", aid),
                initial_value=adata.get("initial_value", 50),
                checks=adata.get("checks", [])
            )
        
        # Parse difficulty curve
        for did, ddata in data.get("difficulty_curve", {}).items():
            blueprint.difficulty_curve[did] = DifficultySettings(
                period=ddata.get("period", did),
                easy_threshold=ddata.get("easy_threshold", 30),
                normal_threshold=ddata.get("normal_threshold", 40),
                hard_threshold=ddata.get("hard_threshold", 60)
            )
        
        blueprint.node_requirements = data.get("node_requirements", {})
        
        return blueprint


class BlueprintGenerator:
    """Generates WorldBlueprint from story outlines and existing content."""
    
    def __init__(self, llm_provider: Any = None):
        """Initialize the generator.
        
        Args:
            llm_provider: Optional LLM provider for enhanced analysis
        """
        self.llm_provider = llm_provider
    
    def generate_from_outline(
        self,
        detailed_outline: Dict[str, Any],
        existing_story: Optional[Dict[str, Any]] = None
    ) -> WorldBlueprint:
        """Generate a blueprint from a detailed outline.
        
        Args:
            detailed_outline: The detailed story outline
            existing_story: Optional existing story to incorporate
            
        Returns:
            WorldBlueprint with all design information
        """
        blueprint = WorldBlueprint()
        
        # Extract metadata
        blueprint.title = detailed_outline.get("title", "")
        blueprint.genre = detailed_outline.get("genre", "")
        blueprint.setting = detailed_outline.get("setting", "")
        
        # Build narrative design
        self._build_narrative_design(blueprint, detailed_outline)
        
        # Build economy design
        self._build_economy_design(blueprint, detailed_outline)
        
        # Build entity registry
        self._build_entity_registry(blueprint, detailed_outline, existing_story)
        
        # Build attributes and difficulty
        self._build_attributes(blueprint, detailed_outline)
        self._build_difficulty_curve(blueprint, detailed_outline)
        
        # Build node requirements
        self._build_node_requirements(blueprint, detailed_outline)
        
        return blueprint
    
    def generate_from_existing_story(
        self,
        story: Dict[str, Any]
    ) -> WorldBlueprint:
        """Analyze an existing story and generate its blueprint.
        
        This is useful for understanding the current state of a story
        and providing context for edits.
        
        Args:
            story: The existing story data
            
        Returns:
            WorldBlueprint extracted from the story
        """
        blueprint = WorldBlueprint()
        
        # Extract metadata
        blueprint.title = story.get("title", story.get("name", ""))
        blueprint.genre = story.get("metadata", {}).get("genre", "")
        
        # Extract entities from story
        self._extract_entities_from_story(blueprint, story)
        
        # Extract economy from initial_variables
        self._extract_economy_from_story(blueprint, story)
        
        # Infer narrative structure
        self._infer_narrative_from_story(blueprint, story)
        
        return blueprint
    
    def _build_narrative_design(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any]
    ):
        """Build narrative design from outline."""
        # Extract story beats as main plot
        story_beats = outline.get("story_beats", [])
        for i, beat in enumerate(story_beats):
            if isinstance(beat, dict):
                blueprint.narrative.main_plot.append(beat)
            else:
                blueprint.narrative.main_plot.append({f"beat_{i+1}": str(beat)})
        
        # Extract themes
        blueprint.narrative.themes = outline.get("themes", [])
        if isinstance(blueprint.narrative.themes, str):
            blueprint.narrative.themes = [blueprint.narrative.themes]
        
        # Extract tone and style
        blueprint.narrative.tone = outline.get("tone", "")
        blueprint.narrative.writing_style = outline.get("writing_style", "")
        
        # Build plot threads from story structure
        story_structure = outline.get("story_structure", {})
        
        # Main conflict as primary thread
        core_conflict = outline.get("core_conflict", "")
        if core_conflict:
            blueprint.narrative.plot_threads["main_conflict"] = PlotThread(
                id="main_conflict",
                name="Main Conflict",
                description=core_conflict,
                priority=1
            )
        
        # Character arcs
        characters = outline.get("characters", [])
        for char in characters:
            if isinstance(char, dict):
                char_id = char.get("id", char.get("name", "").lower().replace(" ", "_"))
                arc_description = char.get("arc", char.get("role", ""))
                if arc_description:
                    blueprint.narrative.character_arcs[char_id] = CharacterArc(
                        character_id=char_id,
                        stages=[arc_description] if isinstance(arc_description, str) else arc_description
                    )
    
    def _build_economy_design(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any]
    ):
        """Build economy design from outline."""
        game_mechanics = outline.get("game_mechanics", {})
        
        # Extract currencies from key_variables
        key_variables = game_mechanics.get("key_variables", [])
        for var in key_variables:
            if isinstance(var, dict):
                var_id = var.get("name", var.get("id", ""))
                var_type = var.get("type", "").lower()
                
                # Identify currency-like variables
                if var_type in ["currency", "resource"] or any(
                    term in var_id.lower() 
                    for term in ["coin", "gold", "money", "voucher", "credit", "point"]
                ):
                    blueprint.economy.currencies[var_id] = CurrencyConfig(
                        id=var_id,
                        name=var.get("display_name", var_id),
                        initial_value=var.get("initial", var.get("default", 0)),
                        earn_rate_min=var.get("earn_min", 1),
                        earn_rate_max=var.get("earn_max", 10),
                        spend_rate_min=var.get("spend_min", 1),
                        spend_rate_max=var.get("spend_max", 5),
                        description=var.get("description", "")
                    )
        
        # Default balance rules
        blueprint.economy.balance_rules = [
            "Early game should be net positive (tutorial phase)",
            "Mid game introduces resource tension",
            "Late game requires strategic resource management"
        ]
    
    def _build_entity_registry(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any],
        existing_story: Optional[Dict[str, Any]]
    ):
        """Build entity registry from outline and existing story."""
        # Extract characters
        characters = outline.get("characters", [])
        for char in characters:
            if isinstance(char, dict):
                char_id = char.get("id", char.get("name", "").lower().replace(" ", "_"))
                blueprint.entities.characters.add(char_id)
                
                # Track character locations
                location = (char.get("properties", {}) or {}).get("location")
                if location:
                    blueprint.entities.character_locations[char_id] = [location]
            elif isinstance(char, str):
                blueprint.entities.characters.add(char.lower().replace(" ", "_"))
        
        # Extract locations from major_locations
        locations = outline.get("major_locations", outline.get("locations", []))
        for loc in locations:
            if isinstance(loc, dict):
                loc_id = loc.get("id", loc.get("name", "").lower().replace(" ", "_"))
                blueprint.entities.locations.add(loc_id)
            elif isinstance(loc, str):
                blueprint.entities.locations.add(loc.lower().replace(" ", "_"))
        
        # Extract objects/items
        items = outline.get("key_items", outline.get("items", []))
        for item in items:
            if isinstance(item, dict):
                item_id = item.get("id", item.get("name", "").lower().replace(" ", "_"))
                blueprint.entities.key_items.add(item_id)
            elif isinstance(item, str):
                blueprint.entities.key_items.add(item.lower().replace(" ", "_"))
        
        # Incorporate existing story entities
        if existing_story:
            # Add nodes as locations
            nodes = existing_story.get("nodes", {})
            if isinstance(nodes, dict):
                for node_id in nodes.keys():
                    blueprint.entities.locations.add(node_id)
            elif isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict):
                        blueprint.entities.locations.add(node.get("id", ""))
            
            # Add characters
            chars = existing_story.get("characters", [])
            for char in chars:
                if isinstance(char, dict):
                    blueprint.entities.characters.add(char.get("id", ""))
    
    def _build_attributes(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any]
    ):
        """Build attribute configuration from outline."""
        game_mechanics = outline.get("game_mechanics", {})
        key_variables = game_mechanics.get("key_variables", [])
        
        for var in key_variables:
            if isinstance(var, dict):
                var_id = var.get("name", var.get("id", ""))
                var_type = var.get("type", "").lower()
                
                # Identify attribute-like variables
                if var_type in ["attribute", "stat"] or any(
                    term in var_id.lower()
                    for term in ["strength", "intelligence", "agility", "constitution", 
                                 "charisma", "wisdom", "dexterity", "health", "stamina"]
                ):
                    blueprint.attributes[var_id] = AttributeConfig(
                        id=var_id,
                        name=var.get("display_name", var_id),
                        initial_value=var.get("initial", var.get("default", 50)),
                        min_value=var.get("min", 0),
                        max_value=var.get("max", 100),
                        checks=var.get("checks", [])
                    )
        
        # Default attributes if none found
        if not blueprint.attributes:
            blueprint.attributes = {
                "player_constitution": AttributeConfig(
                    id="player_constitution", name="Constitution", initial_value=50
                ),
                "player_intelligence": AttributeConfig(
                    id="player_intelligence", name="Intelligence", initial_value=50
                ),
                "player_agility": AttributeConfig(
                    id="player_agility", name="Agility", initial_value=50
                )
            }
    
    def _build_difficulty_curve(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any]
    ):
        """Build difficulty curve from outline."""
        # Default difficulty progression
        blueprint.difficulty_curve = {
            "early": DifficultySettings(
                period="early",
                easy_threshold=30,
                normal_threshold=40,
                hard_threshold=55
            ),
            "mid": DifficultySettings(
                period="mid",
                easy_threshold=35,
                normal_threshold=45,
                hard_threshold=60
            ),
            "late": DifficultySettings(
                period="late",
                easy_threshold=40,
                normal_threshold=50,
                hard_threshold=65
            )
        }
    
    def _build_node_requirements(
        self,
        blueprint: WorldBlueprint,
        outline: Dict[str, Any]
    ):
        """Build node-specific requirements."""
        story_beats = outline.get("story_beats", [])
        major_locations = outline.get("major_locations", [])
        
        # Map story beats to locations
        for i, beat in enumerate(story_beats):
            beat_text = beat if isinstance(beat, str) else list(beat.values())[0] if beat else ""
            
            if i < len(major_locations):
                loc = major_locations[i]
                loc_id = loc.get("id") if isinstance(loc, dict) else loc.lower().replace(" ", "_")
                
                blueprint.node_requirements[loc_id] = {
                    "story_beat": beat_text,
                    "must_advance_plot": True,
                    "beat_index": i
                }
    
    def _extract_entities_from_story(
        self,
        blueprint: WorldBlueprint,
        story: Dict[str, Any]
    ):
        """Extract entities from an existing story."""
        # Extract nodes as locations
        nodes = story.get("nodes", {})
        if isinstance(nodes, dict):
            for node_id, node_data in nodes.items():
                blueprint.entities.locations.add(node_id)
                
                # Extract objects from nodes
                node_objects = node_data.get("objects", [])
                for obj in node_objects:
                    obj_id = obj.get("id", "") if isinstance(obj, dict) else obj
                    blueprint.entities.objects.add(obj_id)
        
        # Extract characters
        characters = story.get("characters", [])
        for char in characters:
            if isinstance(char, dict):
                char_id = char.get("id", "")
                blueprint.entities.characters.add(char_id)
                
                # Track locations
                location = (char.get("properties", {}) or {}).get("location")
                if location:
                    blueprint.entities.character_locations[char_id] = [location]
        
        # Extract global objects
        global_objects = story.get("objects", [])
        for obj in global_objects:
            obj_id = obj.get("id", "") if isinstance(obj, dict) else obj
            blueprint.entities.objects.add(obj_id)
    
    def _extract_economy_from_story(
        self,
        blueprint: WorldBlueprint,
        story: Dict[str, Any]
    ):
        """Extract economy design from existing story."""
        initial_vars = story.get("initial_variables", {})
        
        # Identify currency-like variables
        currency_patterns = ["coin", "gold", "money", "voucher", "credit", "point", "currency"]
        
        for var_id, value in initial_vars.items():
            if isinstance(value, (int, float)) and any(p in var_id.lower() for p in currency_patterns):
                blueprint.economy.currencies[var_id] = CurrencyConfig(
                    id=var_id,
                    name=var_id.replace("_", " ").title(),
                    initial_value=int(value),
                    earn_rate_min=1,
                    earn_rate_max=10,
                    spend_rate_min=1,
                    spend_rate_max=5
                )
    
    def _infer_narrative_from_story(
        self,
        blueprint: WorldBlueprint,
        story: Dict[str, Any]
    ):
        """Infer narrative structure from existing story."""
        # Extract lore content as narrative info
        initial_vars = story.get("initial_variables", {})
        
        lore_outline = initial_vars.get("lore_outline", "")
        if lore_outline:
            blueprint.narrative.main_plot.append({"lore": lore_outline})
        
        writing_style = initial_vars.get("lore_writing_style", "")
        if writing_style:
            blueprint.narrative.writing_style = writing_style
        
        # Extract themes from lore
        theme = initial_vars.get("lore_theme", "")
        if theme:
            blueprint.narrative.themes.append(theme)
