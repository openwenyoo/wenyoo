"""Architect package — unified LLM agent for the AI Native game engine.

Public surface is re-exported here so existing imports
(`from src.core.architect import Architect, ArchitectTask, ...`) keep working
unchanged after the module was split into a package.
"""
from src.core.architect.agent import Architect
from src.core.architect.task import (
    ArchitectTask,
    infer_task_profile,
    TASK_PROFILE_WORLD_ACTION,
    TASK_PROFILE_PERCEPTION_RENDER,
    TASK_PROFILE_WORKFLOW,
    TASK_PROFILE_BACKGROUND_SIMULATION,
    DEFAULT_TASK_PROFILE_BY_TYPE,
    ARTIFACT_KIND_NARRATIVE,
    ARTIFACT_KIND_STRUCTURED,
)

__all__ = [
    "Architect",
    "ArchitectTask",
    "infer_task_profile",
    "TASK_PROFILE_WORLD_ACTION",
    "TASK_PROFILE_PERCEPTION_RENDER",
    "TASK_PROFILE_WORKFLOW",
    "TASK_PROFILE_BACKGROUND_SIMULATION",
    "DEFAULT_TASK_PROFILE_BY_TYPE",
    "ARTIFACT_KIND_NARRATIVE",
    "ARTIFACT_KIND_STRUCTURED",
]
