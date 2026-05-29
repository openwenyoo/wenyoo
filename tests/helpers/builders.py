"""Quick factories for tests (see test-harness-rollout.md §5.1).

These wrap the verbose ``ArchitectTask`` construction so tests can drive the
Architect through a specific task profile in one line.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.architect import ArchitectTask


def make_task(
    task_type: str = "player_input",
    *,
    player_input: Optional[str] = "do something",
    task_profile: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> ArchitectTask:
    """Build an ``ArchitectTask`` with sensible test defaults.

    ``task_profile`` is left as ``None`` by default so the Architect infers it
    from ``task_type`` (matching production); pass it explicitly to test a
    specific profile's branching.
    """
    return ArchitectTask(
        task_type=task_type,
        player_input=player_input,
        task_profile=task_profile,
        extra_context=extra_context or {},
        **kwargs,
    )
