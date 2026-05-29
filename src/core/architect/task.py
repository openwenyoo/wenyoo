"""Architect task contract: profiles, artifact kinds, and the task dataclass.

Pure data + one resolver function. No engine logic, no ``self`` — safe to import
from anywhere without pulling in the Architect class.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

TASK_PROFILE_WORLD_ACTION = "worldAction"
TASK_PROFILE_PERCEPTION_RENDER = "perceptionRender"
TASK_PROFILE_WORKFLOW = "workflowTask"
TASK_PROFILE_BACKGROUND_SIMULATION = "backgroundSimulation"


# Artifact kinds (extensible)
ARTIFACT_KIND_NARRATIVE = "narrative"
ARTIFACT_KIND_STRUCTURED = "structured"

DEFAULT_TASK_PROFILE_BY_TYPE = {
    "player_input": TASK_PROFILE_WORLD_ACTION,
    "execute_intent": TASK_PROFILE_WORLD_ACTION,
    "guided_intent": TASK_PROFILE_WORLD_ACTION,
    "scene_interaction": TASK_PROFILE_WORLD_ACTION,
    "character_interaction": TASK_PROFILE_WORLD_ACTION,
    "tool_assisted_decision": TASK_PROFILE_WORLD_ACTION,
    "render_perception": TASK_PROFILE_PERCEPTION_RENDER,
    "process_form_result": TASK_PROFILE_WORKFLOW,
    "process_event": TASK_PROFILE_WORKFLOW,
    "background_materialization": TASK_PROFILE_BACKGROUND_SIMULATION,
}


def infer_task_profile(task_type: str, explicit_profile: Optional[str] = None) -> str:
    """Resolve the task profile that should govern Architect behavior."""
    if explicit_profile:
        return explicit_profile
    return DEFAULT_TASK_PROFILE_BY_TYPE.get(task_type, TASK_PROFILE_WORLD_ACTION)


# ═══════════════════════════════════════════════════════════════════════════════
# Task Dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ArchitectTask:
    """Describes what the Architect should do in a single invocation."""
    task_type: str                  # e.g. "player_input", "render_perception", "process_form_result", "process_event"
    player_input: Optional[str] = None      # For player_input tasks
    node_id: Optional[str] = None           # For render_perception tasks
    event_context: Optional[str] = None     # For trigger/event tasks
    form_data: Optional[Dict[str, Any]] = None  # For process_form_result tasks
    task_profile: Optional[str] = None
    purpose: Optional[str] = None
    structured_input: Optional[Dict[str, Any]] = None
    extra_context: Dict[str, Any] = field(default_factory=dict)
