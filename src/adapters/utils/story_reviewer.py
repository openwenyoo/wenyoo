"""Story Reviewer - Comprehensive post-generation analysis.

This module provides the StoryReviewAgent which analyzes completed stories
for structural, narrative, and numerical issues. It can be used:
1. After AI-generated stories for quality assurance
2. During manual editing for real-time feedback
3. Before publishing for final validation
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class IssueSeverity(str, Enum):
    """Severity levels for issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IssueCategory(str, Enum):
    """Categories of issues."""
    STRUCTURAL = "structural"
    NARRATIVE = "narrative"
    NUMERICAL = "numerical"
    REFERENCE = "reference"
    QUALITY = "quality"


@dataclass
class ReviewIssue:
    """A single issue found during review."""
    category: IssueCategory
    severity: IssueSeverity
    location: str  # e.g., "node:engine_room", "character:captain_chen"
    message: str
    suggestion: Optional[str] = None
    auto_fixable: bool = False
    fix_action: Optional[Dict[str, Any]] = None


@dataclass
class StructuralReport:
    """Report on story structure."""
    start_node_exists: bool
    reachable_nodes: Set[str]
    unreachable_nodes: Set[str]
    dead_end_nodes: Set[str]  # Nodes with no outgoing actions
    orphan_nodes: Set[str]  # Nodes not connected to anything
    circular_only_paths: List[List[str]]  # Paths that only loop
    
    def get_issues(self) -> List[ReviewIssue]:
        """Convert to list of issues."""
        issues = []
        
        if not self.start_node_exists:
            issues.append(ReviewIssue(
                category=IssueCategory.STRUCTURAL,
                severity=IssueSeverity.CRITICAL,
                location="story",
                message="Start node does not exist",
                suggestion="Define a start node with isStartNode: true"
            ))
        
        for node_id in self.unreachable_nodes:
            issues.append(ReviewIssue(
                category=IssueCategory.STRUCTURAL,
                severity=IssueSeverity.WARNING,
                location=f"node:{node_id}",
                message=f"Node '{node_id}' is not reachable from start",
                suggestion="Add an action from another node that leads here"
            ))
        
        for node_id in self.dead_end_nodes:
            issues.append(ReviewIssue(
                category=IssueCategory.STRUCTURAL,
                severity=IssueSeverity.INFO,
                location=f"node:{node_id}",
                message=f"Node '{node_id}' has no outgoing navigation actions",
                suggestion="This may be intentional for ending nodes"
            ))
        
        return issues


@dataclass
class ReferenceReport:
    """Report on reference integrity."""
    missing_node_references: List[Tuple[str, str, str]]  # (source, action_id, target)
    missing_character_references: List[Tuple[str, str]]  # (location, char_id)
    missing_object_references: List[Tuple[str, str]]  # (location, obj_id)
    orphan_objects: List[str]  # Objects defined but never referenced
    orphan_characters: List[str]  # Characters defined but never placed
    
    def get_issues(self) -> List[ReviewIssue]:
        """Convert to list of issues."""
        issues = []
        
        for source, action_id, target in self.missing_node_references:
            issues.append(ReviewIssue(
                category=IssueCategory.REFERENCE,
                severity=IssueSeverity.ERROR,
                location=f"node:{source}:action:{action_id}",
                message=f"Action '{action_id}' references non-existent node '{target}'",
                suggestion=f"Create node '{target}' or update the action target",
                auto_fixable=False
            ))
        
        for location, char_id in self.missing_character_references:
            issues.append(ReviewIssue(
                category=IssueCategory.REFERENCE,
                severity=IssueSeverity.ERROR,
                location=f"node:{location}",
                message=f"References non-existent character '{char_id}'",
                suggestion=f"Create character '{char_id}' or remove the reference"
            ))
        
        for obj_id in self.orphan_objects:
            issues.append(ReviewIssue(
                category=IssueCategory.REFERENCE,
                severity=IssueSeverity.INFO,
                location=f"object:{obj_id}",
                message=f"Object '{obj_id}' is defined but never used",
                suggestion="Consider placing this object in a node or removing it"
            ))
        
        return issues


@dataclass
class NumericalReport:
    """Report on numerical design."""
    economy_status: Dict[str, str]  # currency -> status
    income_sources: int
    expense_sinks: int
    stat_checks: int
    average_difficulty: float
    estimated_pass_rate: float
    balance_warnings: List[str]
    
    def get_issues(self) -> List[ReviewIssue]:
        """Convert to list of issues."""
        issues = []
        
        for currency, status in self.economy_status.items():
            if status == "critical":
                issues.append(ReviewIssue(
                    category=IssueCategory.NUMERICAL,
                    severity=IssueSeverity.WARNING,
                    location=f"economy:{currency}",
                    message=f"Currency '{currency}' has critical imbalance",
                    suggestion="Add more income sources or reduce expenses"
                ))
        
        if self.estimated_pass_rate < 0.4:
            issues.append(ReviewIssue(
                category=IssueCategory.NUMERICAL,
                severity=IssueSeverity.WARNING,
                location="difficulty",
                message=f"Estimated pass rate ({self.estimated_pass_rate:.0%}) is low",
                suggestion="Consider lowering some stat check thresholds"
            ))
        elif self.estimated_pass_rate > 0.95:
            issues.append(ReviewIssue(
                category=IssueCategory.NUMERICAL,
                severity=IssueSeverity.INFO,
                location="difficulty",
                message=f"Estimated pass rate ({self.estimated_pass_rate:.0%}) is very high",
                suggestion="Consider adding harder challenges for variety"
            ))
        
        for warning in self.balance_warnings:
            issues.append(ReviewIssue(
                category=IssueCategory.NUMERICAL,
                severity=IssueSeverity.WARNING,
                location="economy",
                message=warning
            ))
        
        return issues


@dataclass
class QualityReport:
    """Report on content quality."""
    empty_descriptions: List[str]  # Nodes with no description
    short_descriptions: List[Tuple[str, int]]  # (node_id, word_count)
    missing_actions: List[str]  # Nodes with no actions
    duplicate_action_ids: List[Tuple[str, str]]  # (node_id, action_id)
    
    def get_issues(self) -> List[ReviewIssue]:
        """Convert to list of issues."""
        issues = []
        
        for node_id in self.empty_descriptions:
            issues.append(ReviewIssue(
                category=IssueCategory.QUALITY,
                severity=IssueSeverity.WARNING,
                location=f"node:{node_id}",
                message="Node has no description",
                suggestion="Add a explicit_state or description for this location"
            ))
        
        for node_id, word_count in self.short_descriptions:
            issues.append(ReviewIssue(
                category=IssueCategory.QUALITY,
                severity=IssueSeverity.INFO,
                location=f"node:{node_id}",
                message=f"Node description is short ({word_count} words)",
                suggestion="Consider adding more atmospheric detail"
            ))
        
        for node_id in self.missing_actions:
            issues.append(ReviewIssue(
                category=IssueCategory.QUALITY,
                severity=IssueSeverity.WARNING,
                location=f"node:{node_id}",
                message="Node has no actions defined",
                suggestion="Add at least one action for player interaction"
            ))
        
        for node_id, action_id in self.duplicate_action_ids:
            issues.append(ReviewIssue(
                category=IssueCategory.QUALITY,
                severity=IssueSeverity.ERROR,
                location=f"node:{node_id}",
                message=f"Duplicate action ID '{action_id}'",
                suggestion="Use unique action IDs within each node"
            ))
        
        return issues


@dataclass
class ReviewReport:
    """Complete review report."""
    structural: StructuralReport
    references: ReferenceReport
    numerical: NumericalReport
    quality: QualityReport
    
    # Summary statistics
    total_nodes: int = 0
    total_characters: int = 0
    total_objects: int = 0
    total_actions: int = 0
    
    def get_all_issues(self) -> List[ReviewIssue]:
        """Get all issues from all reports."""
        issues = []
        issues.extend(self.structural.get_issues())
        issues.extend(self.references.get_issues())
        issues.extend(self.numerical.get_issues())
        issues.extend(self.quality.get_issues())
        return issues
    
    def get_issues_by_severity(self, severity: IssueSeverity) -> List[ReviewIssue]:
        """Get issues filtered by severity."""
        return [i for i in self.get_all_issues() if i.severity == severity]
    
    def get_issues_by_category(self, category: IssueCategory) -> List[ReviewIssue]:
        """Get issues filtered by category."""
        return [i for i in self.get_all_issues() if i.category == category]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        all_issues = self.get_all_issues()
        
        return {
            "summary": {
                "total_nodes": self.total_nodes,
                "total_characters": self.total_characters,
                "total_objects": self.total_objects,
                "total_actions": self.total_actions,
                "issue_counts": {
                    "critical": len([i for i in all_issues if i.severity == IssueSeverity.CRITICAL]),
                    "error": len([i for i in all_issues if i.severity == IssueSeverity.ERROR]),
                    "warning": len([i for i in all_issues if i.severity == IssueSeverity.WARNING]),
                    "info": len([i for i in all_issues if i.severity == IssueSeverity.INFO])
                }
            },
            "structural": {
                "start_node_exists": self.structural.start_node_exists,
                "reachable_nodes": len(self.structural.reachable_nodes),
                "unreachable_nodes": list(self.structural.unreachable_nodes),
                "dead_end_nodes": list(self.structural.dead_end_nodes)
            },
            "references": {
                "missing_node_refs": len(self.references.missing_node_references),
                "missing_char_refs": len(self.references.missing_character_references),
                "orphan_objects": self.references.orphan_objects,
                "orphan_characters": self.references.orphan_characters
            },
            "numerical": {
                "economy_status": self.numerical.economy_status,
                "income_sources": self.numerical.income_sources,
                "expense_sinks": self.numerical.expense_sinks,
                "average_difficulty": self.numerical.average_difficulty,
                "pass_rate": self.numerical.estimated_pass_rate
            },
            "quality": {
                "empty_descriptions": len(self.quality.empty_descriptions),
                "short_descriptions": len(self.quality.short_descriptions),
                "missing_actions": len(self.quality.missing_actions)
            },
            "issues": [
                {
                    "category": i.category.value,
                    "severity": i.severity.value,
                    "location": i.location,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "auto_fixable": i.auto_fixable
                }
                for i in all_issues
            ]
        }


class StoryReviewAgent:
    """Agent for reviewing stories and providing feedback.
    
    Performs comprehensive analysis of story structure, references,
    numerical design, and content quality.
    """
    
    def __init__(self, llm_provider: Any = None):
        """Initialize the review agent.
        
        Args:
            llm_provider: Optional LLM for advanced analysis
        """
        self.llm_provider = llm_provider
    
    def review(self, story: Dict[str, Any]) -> ReviewReport:
        """Perform a comprehensive review of a story.
        
        Args:
            story: The story data to review
            
        Returns:
            ReviewReport with all findings
        """
        # Extract story components
        nodes = story.get("nodes", {})
        if isinstance(nodes, list):
            nodes = {n.get("id", f"node_{i}"): n for i, n in enumerate(nodes)}
        
        characters = story.get("characters", [])
        objects = story.get("objects", [])
        initial_variables = story.get("initial_variables", {})
        start_node_id = story.get("start_node_id")
        
        # Find start node
        if not start_node_id:
            for node_id, node_data in nodes.items():
                if node_data.get("isStartNode"):
                    start_node_id = node_id
                    break
        
        # Perform reviews
        structural = self._review_structure(nodes, start_node_id)
        references = self._review_references(nodes, characters, objects)
        numerical = self._review_numerical(nodes, initial_variables)
        quality = self._review_quality(nodes)
        
        # Count totals
        total_actions = sum(
            len(n.get("actions", [])) for n in nodes.values()
        )
        
        return ReviewReport(
            structural=structural,
            references=references,
            numerical=numerical,
            quality=quality,
            total_nodes=len(nodes),
            total_characters=len(characters),
            total_objects=len(objects),
            total_actions=total_actions
        )
    
    def _review_structure(
        self,
        nodes: Dict[str, Any],
        start_node_id: Optional[str]
    ) -> StructuralReport:
        """Review story structure for reachability issues."""
        node_ids = set(nodes.keys())
        
        # Check start node exists
        start_exists = start_node_id is not None and start_node_id in node_ids
        
        # Build adjacency graph
        adjacency = defaultdict(set)
        for node_id, node_data in nodes.items():
            for action in node_data.get("actions", []):
                for effect in action.get("effects", []):
                    if effect.get("type") == "goto_node":
                        target = effect.get("target", effect.get("target_node", ""))
                        if target:
                            adjacency[node_id].add(target)
        
        # BFS to find reachable nodes
        reachable = set()
        if start_exists:
            queue = [start_node_id]
            while queue:
                current = queue.pop(0)
                if current in reachable:
                    continue
                reachable.add(current)
                for neighbor in adjacency.get(current, []):
                    if neighbor in node_ids and neighbor not in reachable:
                        queue.append(neighbor)
        
        unreachable = node_ids - reachable
        
        # Find dead ends (nodes with no outgoing goto_node actions)
        dead_ends = set()
        for node_id, node_data in nodes.items():
            has_navigation = False
            for action in node_data.get("actions", []):
                for effect in action.get("effects", []):
                    if effect.get("type") == "goto_node":
                        has_navigation = True
                        break
                if has_navigation:
                    break
            if not has_navigation:
                dead_ends.add(node_id)
        
        # Find orphan nodes (no incoming or outgoing connections)
        has_incoming = set()
        for neighbors in adjacency.values():
            has_incoming.update(neighbors)
        
        orphans = set()
        for node_id in node_ids:
            if node_id not in has_incoming and not adjacency.get(node_id):
                if node_id != start_node_id:
                    orphans.add(node_id)
        
        return StructuralReport(
            start_node_exists=start_exists,
            reachable_nodes=reachable,
            unreachable_nodes=unreachable,
            dead_end_nodes=dead_ends,
            orphan_nodes=orphans,
            circular_only_paths=[]  # TODO: Implement cycle detection
        )
    
    def _review_references(
        self,
        nodes: Dict[str, Any],
        characters: List[Dict[str, Any]],
        objects: List[Dict[str, Any]]
    ) -> ReferenceReport:
        """Review reference integrity."""
        node_ids = set(nodes.keys())
        char_ids = {c.get("id", "") for c in characters if isinstance(c, dict)}
        obj_ids = {o.get("id", "") for o in objects if isinstance(o, dict)}
        
        # Also collect objects defined in nodes
        for node_data in nodes.values():
            for obj in node_data.get("objects", []):
                if isinstance(obj, dict):
                    obj_ids.add(obj.get("id", ""))
        
        missing_nodes = []
        missing_chars = []
        missing_objs = []
        referenced_objs = set()
        referenced_chars = set()
        
        # Check all node references
        for node_id, node_data in nodes.items():
            for action in node_data.get("actions", []):
                action_id = action.get("id", "")
                for effect in action.get("effects", []):
                    effect_type = effect.get("type", "")
                    
                    if effect_type == "goto_node":
                        target = effect.get("target", effect.get("target_node", ""))
                        if target and target not in node_ids:
                            missing_nodes.append((node_id, action_id, target))
                    
                    elif effect_type == "trigger_character_prompt":
                        char_id = effect.get("character_id", "")
                        if char_id:
                            referenced_chars.add(char_id)
                            if char_id not in char_ids:
                                missing_chars.append((node_id, char_id))
                    
                    elif effect_type in ["add_to_inventory", "remove_from_inventory"]:
                        item_id = effect.get("target", effect.get("item_id", ""))
                        if item_id:
                            referenced_objs.add(item_id)
        
        # Find orphan objects and characters
        orphan_objs = list(obj_ids - referenced_objs)
        
        # Characters should have an explicit starting location if they are meant to appear.
        placed_chars = set()
        for char in characters:
            if isinstance(char, dict):
                location = (char.get("properties", {}) or {}).get("location")
                if location:
                    placed_chars.add(char.get("id", ""))
        orphan_chars = list(char_ids - placed_chars - {"player"})
        
        return ReferenceReport(
            missing_node_references=missing_nodes,
            missing_character_references=missing_chars,
            missing_object_references=missing_objs,
            orphan_objects=orphan_objs,
            orphan_characters=orphan_chars
        )
    
    def _review_numerical(
        self,
        nodes: Dict[str, Any],
        initial_variables: Dict[str, Any]
    ) -> NumericalReport:
        """Review numerical design and balance."""
        # Import numerical design for analysis
        try:
            from .numerical_design import NumericalDesign
            numerical = NumericalDesign()
            
            # Configure currencies from initial_variables
            for var_id, value in initial_variables.items():
                if isinstance(value, (int, float)):
                    if any(p in var_id.lower() for p in ["coin", "voucher", "credit", "point"]):
                        numerical.configure_currency(var_id, int(value))
                    elif any(p in var_id.lower() for p in ["constitution", "intelligence", "agility"]):
                        numerical.configure_attribute(var_id, int(value))
            
            # Extract from nodes
            for node_id, node_data in nodes.items():
                numerical._extract_from_node(node_id, node_data)
            
            # Get analysis
            economy_status = {}
            balance_warnings = []
            for currency_id in numerical.currency_configs.keys():
                report = numerical.analyze_balance(currency_id)
                economy_status[currency_id] = report.status.value
                balance_warnings.extend(report.recommendations)
            
            diff_report = numerical.analyze_difficulty()
            
            return NumericalReport(
                economy_status=economy_status,
                income_sources=len(numerical.income_sources),
                expense_sinks=len(numerical.expense_sinks),
                stat_checks=len(numerical.stat_checks),
                average_difficulty=diff_report.average_threshold,
                estimated_pass_rate=diff_report.pass_rate_estimate,
                balance_warnings=balance_warnings
            )
        except Exception as e:
            logger.warning(f"Failed to analyze numerical design: {e}")
            return NumericalReport(
                economy_status={},
                income_sources=0,
                expense_sinks=0,
                stat_checks=0,
                average_difficulty=0,
                estimated_pass_rate=0,
                balance_warnings=[]
            )
    
    def _review_quality(self, nodes: Dict[str, Any]) -> QualityReport:
        """Review content quality."""
        empty_descriptions = []
        short_descriptions = []
        missing_actions = []
        duplicate_actions = []
        
        for node_id, node_data in nodes.items():
            # Check description
            description = node_data.get("description", node_data.get("explicit_state", ""))
            if not description or not description.strip():
                empty_descriptions.append(node_id)
            elif len(description.split()) < 20:
                short_descriptions.append((node_id, len(description.split())))
            
            # Check actions
            actions = node_data.get("actions", [])
            if not actions:
                missing_actions.append(node_id)
            else:
                # Check for duplicates
                action_ids = set()
                for action in actions:
                    action_id = action.get("id", "")
                    if action_id in action_ids:
                        duplicate_actions.append((node_id, action_id))
                    action_ids.add(action_id)
        
        return QualityReport(
            empty_descriptions=empty_descriptions,
            short_descriptions=short_descriptions,
            missing_actions=missing_actions,
            duplicate_action_ids=duplicate_actions
        )
    
    async def review_with_llm(
        self,
        story: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform enhanced review using LLM for narrative analysis.
        
        Args:
            story: The story data to review
            
        Returns:
            Enhanced review with narrative insights
        """
        # Get basic review
        basic_report = self.review(story)
        
        if not self.llm_provider:
            return basic_report.to_dict()
        
        # TODO: Add LLM-based narrative analysis
        # - Plot hole detection
        # - Character consistency
        # - Writing style consistency
        # - Engagement estimation
        
        return basic_report.to_dict()
