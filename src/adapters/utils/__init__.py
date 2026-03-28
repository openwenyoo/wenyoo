"""Utility modules for web frontend adapter."""

from .game_state_serializer import build_game_state_dict, build_object_definitions
from .llm_prompts import create_intent_prompt, create_add_prompt, create_update_prompt
from .editor_tools import EDITOR_TOOLS, get_format_documentation, get_tool_names
from .editor_function_executor import (
    EditorFunctionExecutor,
    SSEEvent,
    EventType,
    EditorState,
    ChangeRecord
)
from .plan_executor import (
    PlanExecutor,
    ExecutionPlan,
    PlanStep,
    PlanType,
    PlanScope,
    PlanExecutionResult,
    build_plan_generation_prompt,
    get_outline_generation_prompt,
    get_outline_expansion_prompt,
    get_outline_refinement_prompt,
    get_outline_set_refinement_prompt,
    get_detailed_outline_refinement_prompt
)
from .story_conductor import (
    StoryConductor,
    ConductorEvent,
    ConductorEventType,
    NodeExpansionContext,
    get_node_expansion_prompt
)

# Intelligent Conductor System
from .world_blueprint import (
    WorldBlueprint,
    BlueprintGenerator,
    PlotThread,
    CharacterArc,
    NarrativeDesign,
    EconomyDesign,
    EntityRegistry
)
from .numerical_design import (
    NumericalDesign,
    BalanceReport,
    DifficultyReport,
    IncomeSource,
    ExpenseSink,
    StatCheck,
    DifficultyLevel
)
from .narrative_tracker import (
    NarrativeTracker,
    EstablishedFact,
    PlotThreadState,
    CharacterState,
    ContradictionReport,
    FactType
)
from .expansion_coordinator import (
    ExpansionCoordinator,
    RichExpansionContext,
    ExpansionConstraints
)
from .story_reviewer import (
    StoryReviewAgent,
    ReviewReport,
    ReviewIssue,
    IssueSeverity,
    IssueCategory
)
from .import_prompts import (
    normalize_import_draft,
    validate_import_draft,
    get_import_outline_generation_prompt,
    get_import_outline_expansion_prompt,
)

__all__ = [
    # Game state serialization
    'build_game_state_dict',
    'build_object_definitions',
    # LLM prompts
    'create_intent_prompt',
    'create_add_prompt', 
    'create_update_prompt',
    # Editor tools for AI function calling
    'EDITOR_TOOLS',
    'get_format_documentation',
    'get_tool_names',
    # Editor function executor
    'EditorFunctionExecutor',
    'SSEEvent',
    'EventType',
    'EditorState',
    'ChangeRecord',
    # Plan-based executor
    'PlanExecutor',
    'ExecutionPlan',
    'PlanStep',
    'PlanType',
    'PlanScope',
    'PlanExecutionResult',
    'build_plan_generation_prompt',
    'get_outline_generation_prompt',
    'get_outline_expansion_prompt',
    'get_outline_refinement_prompt',
    'get_outline_set_refinement_prompt',
    'get_detailed_outline_refinement_prompt',
    # Story conductor
    'StoryConductor',
    'ConductorEvent',
    'ConductorEventType',
    'NodeExpansionContext',
    'get_node_expansion_prompt',
    # Intelligent Conductor - World Blueprint
    'WorldBlueprint',
    'BlueprintGenerator',
    'PlotThread',
    'CharacterArc',
    'NarrativeDesign',
    'EconomyDesign',
    'EntityRegistry',
    # Intelligent Conductor - Numerical Design
    'NumericalDesign',
    'BalanceReport',
    'DifficultyReport',
    'IncomeSource',
    'ExpenseSink',
    'StatCheck',
    'DifficultyLevel',
    # Intelligent Conductor - Narrative Tracker
    'NarrativeTracker',
    'EstablishedFact',
    'PlotThreadState',
    'CharacterState',
    'ContradictionReport',
    'FactType',
    # Intelligent Conductor - Expansion Coordinator
    'ExpansionCoordinator',
    'RichExpansionContext',
    'ExpansionConstraints',
    # Intelligent Conductor - Story Reviewer
    'StoryReviewAgent',
    'ReviewReport',
    'ReviewIssue',
    'IssueSeverity',
    'IssueCategory',
    # Import prompt helpers
    'normalize_import_draft',
    'validate_import_draft',
    'get_import_outline_generation_prompt',
    'get_import_outline_expansion_prompt',
]

