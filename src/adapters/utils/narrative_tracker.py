"""Narrative Tracker - Plot threads, character arcs, and story consistency.

This module tracks narrative elements across the story to ensure consistency:
- Plot thread progression
- Character arc stages
- Established facts (what has been "said" in the story)
- Contradiction detection
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class FactType(str, Enum):
    """Types of established facts."""
    WORLD = "world"  # World-building facts
    CHARACTER = "character"  # Character-related facts
    OBJECT = "object"  # Object descriptions/states
    EVENT = "event"  # Things that happened
    RELATIONSHIP = "relationship"  # Character relationships


@dataclass
class EstablishedFact:
    """A fact established in the narrative."""
    id: str
    fact_type: FactType
    content: str
    source_node: str
    entities_involved: Set[str] = field(default_factory=set)
    keywords: Set[str] = field(default_factory=set)
    contradicts: Set[str] = field(default_factory=set)  # IDs of contradicting facts


@dataclass
class PlotThreadState:
    """State of a plot thread."""
    thread_id: str
    name: str
    status: str = "not_started"  # not_started, setup, development, climax, resolved
    current_stage: int = 0
    nodes_visited: List[str] = field(default_factory=list)
    key_events: List[str] = field(default_factory=list)


@dataclass
class CharacterState:
    """State of a character in the narrative."""
    character_id: str
    name: str
    arc_stage: int = 0
    arc_stages: List[str] = field(default_factory=list)
    appearances: List[str] = field(default_factory=list)  # Node IDs
    established_traits: Set[str] = field(default_factory=set)
    relationships: Dict[str, str] = field(default_factory=dict)  # char_id -> relationship


@dataclass
class ContradictionReport:
    """Report of a potential contradiction."""
    severity: str  # "warning", "error"
    existing_fact: EstablishedFact
    new_content: str
    node_id: str
    detail: str
    suggestion: Optional[str] = None


class NarrativeTracker:
    """Tracks narrative consistency across the story.
    
    Maintains a memory of established facts, plot thread states,
    and character arcs to detect contradictions and ensure consistency.
    """
    
    def __init__(self):
        """Initialize the narrative tracker."""
        self.established_facts: Dict[str, EstablishedFact] = {}
        self.plot_threads: Dict[str, PlotThreadState] = {}
        self.character_states: Dict[str, CharacterState] = {}
        self.entity_mentions: Dict[str, Set[str]] = {}  # entity -> {node_ids}
        
        # Keywords that indicate specific types of content
        self.contradiction_patterns = [
            # Physical descriptions
            (r"has no (windows?|door|exit)", r"(window|door|exit) (is|are|opens)"),
            (r"is empty", r"contains|filled with|has"),
            (r"is (dark|pitch black)", r"(bright|lit|illuminated)"),
            (r"is (cold|freezing)", r"(warm|hot|heated)"),
            # Character states
            (r"is dead", r"(speaks|walks|moves|alive)"),
            (r"is alone", r"(accompanied|with|together)"),
            # Temporal
            (r"never", r"always|often|sometimes"),
        ]
    
    def establish_fact(
        self,
        fact_id: str,
        fact_type: FactType,
        content: str,
        source_node: str,
        entities: Optional[Set[str]] = None
    ) -> Optional[ContradictionReport]:
        """Establish a new fact and check for contradictions.
        
        Args:
            fact_id: Unique identifier for the fact
            fact_type: Type of fact
            content: The fact content
            source_node: Node where the fact was established
            entities: Entities involved in the fact
            
        Returns:
            ContradictionReport if contradiction found, None otherwise
        """
        # Extract keywords
        keywords = self._extract_keywords(content)
        
        # Check for contradictions
        contradiction = self._check_contradictions(content, source_node, entities or set())
        
        # Create and store the fact
        fact = EstablishedFact(
            id=fact_id,
            fact_type=fact_type,
            content=content,
            source_node=source_node,
            entities_involved=entities or set(),
            keywords=keywords
        )
        
        if contradiction:
            fact.contradicts.add(contradiction.existing_fact.id)
        
        self.established_facts[fact_id] = fact
        
        # Track entity mentions
        for entity in (entities or set()):
            if entity not in self.entity_mentions:
                self.entity_mentions[entity] = set()
            self.entity_mentions[entity].add(source_node)
        
        return contradiction
    
    def update_plot_thread(
        self,
        thread_id: str,
        name: str = "",
        status: Optional[str] = None,
        node_visited: Optional[str] = None,
        key_event: Optional[str] = None
    ):
        """Update a plot thread's state.
        
        Args:
            thread_id: The thread ID
            name: Thread name (set on first call)
            status: New status if changed
            node_visited: Node that advanced this thread
            key_event: Key event that occurred
        """
        if thread_id not in self.plot_threads:
            self.plot_threads[thread_id] = PlotThreadState(
                thread_id=thread_id,
                name=name or thread_id
            )
        
        thread = self.plot_threads[thread_id]
        
        if status:
            thread.status = status
            # Update stage based on status
            status_stages = {
                "not_started": 0,
                "setup": 1,
                "development": 2,
                "climax": 3,
                "resolved": 4
            }
            thread.current_stage = status_stages.get(status, thread.current_stage)
        
        if node_visited and node_visited not in thread.nodes_visited:
            thread.nodes_visited.append(node_visited)
        
        if key_event:
            thread.key_events.append(key_event)
    
    def update_character_state(
        self,
        character_id: str,
        name: str = "",
        arc_stage: Optional[int] = None,
        appearance_node: Optional[str] = None,
        trait: Optional[str] = None,
        relationship: Optional[Tuple[str, str]] = None  # (other_char, relationship)
    ):
        """Update a character's narrative state.
        
        Args:
            character_id: The character ID
            name: Character name
            arc_stage: New arc stage
            appearance_node: Node where character appeared
            trait: New trait to add
            relationship: Relationship update (other_char_id, relationship_type)
        """
        if character_id not in self.character_states:
            self.character_states[character_id] = CharacterState(
                character_id=character_id,
                name=name or character_id
            )
        
        char = self.character_states[character_id]
        
        if arc_stage is not None:
            char.arc_stage = arc_stage
        
        if appearance_node and appearance_node not in char.appearances:
            char.appearances.append(appearance_node)
        
        if trait:
            char.established_traits.add(trait)
        
        if relationship:
            other_char, rel_type = relationship
            char.relationships[other_char] = rel_type
    
    def get_established_facts(self, filter_type: Optional[FactType] = None) -> List[EstablishedFact]:
        """Get all established facts, optionally filtered by type.
        
        Args:
            filter_type: Optional type to filter by
            
        Returns:
            List of established facts
        """
        if filter_type:
            return [f for f in self.established_facts.values() if f.fact_type == filter_type]
        return list(self.established_facts.values())
    
    def get_facts_for_entity(self, entity_id: str) -> List[EstablishedFact]:
        """Get all facts involving a specific entity.
        
        Args:
            entity_id: The entity ID
            
        Returns:
            List of facts involving this entity
        """
        return [
            f for f in self.established_facts.values()
            if entity_id in f.entities_involved
        ]
    
    def get_facts_for_node(self, node_id: str) -> List[EstablishedFact]:
        """Get all facts established in a specific node.
        
        Args:
            node_id: The node ID
            
        Returns:
            List of facts from this node
        """
        return [
            f for f in self.established_facts.values()
            if f.source_node == node_id
        ]
    
    def find_contradictions(
        self,
        node_id: str,
        new_content: str,
        entities: Optional[Set[str]] = None
    ) -> List[ContradictionReport]:
        """Find all contradictions with existing facts.
        
        Args:
            node_id: Node where new content appears
            new_content: The new content to check
            entities: Entities involved
            
        Returns:
            List of contradiction reports
        """
        contradictions = []
        
        # Check against all relevant facts
        for fact in self.established_facts.values():
            # Only check facts involving overlapping entities
            if entities and not entities.intersection(fact.entities_involved):
                continue
            
            report = self._check_specific_contradiction(fact, new_content, node_id)
            if report:
                contradictions.append(report)
        
        return contradictions
    
    def get_mentioned_entities(self) -> Dict[str, Set[str]]:
        """Get all mentioned entities and their locations.
        
        Returns:
            Dict mapping entity IDs to sets of node IDs
        """
        return self.entity_mentions.copy()
    
    def get_narrative_context(self) -> Dict[str, Any]:
        """Get a summary of narrative state for LLM context.
        
        Returns:
            Dictionary with narrative context
        """
        return {
            "plot_threads": {
                tid: {
                    "name": t.name,
                    "status": t.status,
                    "stage": t.current_stage,
                    "nodes_visited": t.nodes_visited[-3:] if t.nodes_visited else []
                }
                for tid, t in self.plot_threads.items()
            },
            "character_states": {
                cid: {
                    "name": c.name,
                    "arc_stage": c.arc_stage,
                    "traits": list(c.established_traits)[:5],
                    "last_appearance": c.appearances[-1] if c.appearances else None
                }
                for cid, c in self.character_states.items()
            },
            "key_facts": [
                {"type": f.fact_type.value, "content": f.content[:100]}
                for f in list(self.established_facts.values())[-10:]
            ],
            "entities_mentioned": {
                eid: list(nodes)[:3]
                for eid, nodes in self.entity_mentions.items()
            }
        }
    
    def to_context_string(self) -> str:
        """Generate a context string for LLM prompts.
        
        Returns a summary of narrative state for inclusion in prompts.
        """
        lines = ["# NARRATIVE STATE"]
        
        # Plot threads
        if self.plot_threads:
            lines.append("\n## Plot Threads")
            for tid, thread in self.plot_threads.items():
                lines.append(f"- {thread.name}: {thread.status} (stage {thread.current_stage})")
        
        # Character states
        if self.character_states:
            lines.append("\n## Character States")
            for cid, char in self.character_states.items():
                traits = ", ".join(list(char.established_traits)[:3]) if char.established_traits else "no traits established"
                lines.append(f"- {char.name}: arc stage {char.arc_stage}, {traits}")
        
        # Key established facts
        if self.established_facts:
            lines.append("\n## Established Facts (Do Not Contradict)")
            for fact in list(self.established_facts.values())[-5:]:
                lines.append(f"- [{fact.source_node}] {fact.content[:80]}...")
        
        return "\n".join(lines)
    
    def extract_from_story(self, story: Dict[str, Any]):
        """Extract narrative state from an existing story.
        
        Args:
            story: The story data
        """
        # Extract character info
        characters = story.get("characters", [])
        for char in characters:
            if isinstance(char, dict):
                char_id = char.get("id", "")
                self.update_character_state(
                    character_id=char_id,
                    name=char.get("name", char_id)
                )
                
                # Extract authored starting location as an appearance.
                location = (char.get("properties", {}) or {}).get("location")
                if location:
                    self.update_character_state(char_id, appearance_node=location)
        
        # Extract facts from node descriptions
        nodes = story.get("nodes", {})
        if isinstance(nodes, dict):
            for node_id, node_data in nodes.items():
                description = node_data.get("description", node_data.get("explicit_state", ""))
                if description:
                    # Extract entities mentioned
                    entities = self._extract_entities_from_text(description, story)
                    
                    self.establish_fact(
                        fact_id=f"{node_id}_description",
                        fact_type=FactType.WORLD,
                        content=description,
                        source_node=node_id,
                        entities=entities
                    )
    
    def _check_contradictions(
        self,
        content: str,
        source_node: str,
        entities: Set[str]
    ) -> Optional[ContradictionReport]:
        """Check if content contradicts existing facts.
        
        Args:
            content: New content to check
            source_node: Source node
            entities: Entities involved
            
        Returns:
            ContradictionReport if found
        """
        content_lower = content.lower()
        
        for fact in self.established_facts.values():
            # Check for same entities
            if not entities.intersection(fact.entities_involved):
                continue
            
            report = self._check_specific_contradiction(fact, content, source_node)
            if report:
                return report
        
        return None
    
    def _check_specific_contradiction(
        self,
        fact: EstablishedFact,
        new_content: str,
        node_id: str
    ) -> Optional[ContradictionReport]:
        """Check if new content contradicts a specific fact.
        
        Args:
            fact: The existing fact
            new_content: New content to check
            node_id: Node of new content
            
        Returns:
            ContradictionReport if contradiction found
        """
        fact_lower = fact.content.lower()
        new_lower = new_content.lower()
        
        for pattern1, pattern2 in self.contradiction_patterns:
            match1_in_fact = re.search(pattern1, fact_lower)
            match2_in_new = re.search(pattern2, new_lower)
            
            if match1_in_fact and match2_in_new:
                return ContradictionReport(
                    severity="warning",
                    existing_fact=fact,
                    new_content=new_content,
                    node_id=node_id,
                    detail=f"'{match1_in_fact.group()}' in {fact.source_node} vs '{match2_in_new.group()}' in {node_id}",
                    suggestion=f"Consider aligning with established fact from {fact.source_node}"
                )
            
            # Check reverse
            match1_in_new = re.search(pattern1, new_lower)
            match2_in_fact = re.search(pattern2, fact_lower)
            
            if match1_in_new and match2_in_fact:
                return ContradictionReport(
                    severity="warning",
                    existing_fact=fact,
                    new_content=new_content,
                    node_id=node_id,
                    detail=f"'{match2_in_fact.group()}' in {fact.source_node} vs '{match1_in_new.group()}' in {node_id}",
                    suggestion=f"Consider aligning with established fact from {fact.source_node}"
                )
        
        return None
    
    def _extract_keywords(self, content: str) -> Set[str]:
        """Extract keywords from content.
        
        Args:
            content: The text content
            
        Returns:
            Set of keywords
        """
        # Simple keyword extraction - could be enhanced with NLP
        words = re.findall(r'\b\w{4,}\b', content.lower())
        
        # Filter common words
        stopwords = {
            "this", "that", "with", "from", "have", "been", "were", "what",
            "when", "where", "which", "there", "their", "would", "could",
            "should", "about", "after", "before", "between", "through"
        }
        
        return set(w for w in words if w not in stopwords)
    
    def _extract_entities_from_text(
        self,
        text: str,
        story: Dict[str, Any]
    ) -> Set[str]:
        """Extract entity references from text.
        
        Args:
            text: The text to analyze
            story: The story for entity lookup
            
        Returns:
            Set of entity IDs mentioned
        """
        entities = set()
        text_lower = text.lower()
        
        # Check characters
        for char in story.get("characters", []):
            if isinstance(char, dict):
                char_id = char.get("id", "")
                char_name = char.get("name", "").lower()
                if char_id.lower() in text_lower or char_name in text_lower:
                    entities.add(char_id)
        
        # Check node IDs
        nodes = story.get("nodes", {})
        if isinstance(nodes, dict):
            for node_id in nodes.keys():
                if node_id.lower() in text_lower:
                    entities.add(node_id)
        
        return entities
