"""Shared fixtures for the Wenyoo test suite (see test-harness-rollout.md §5.5).

All fixtures are LLM-free and disk-isolated:
- ``ToolCallingMockLLM`` never touches the network.
- ``StateManager`` is always pointed at ``tmp_path`` so tests never write ``saves/``.
- ``game_kernel`` has NO frontend adapter, so the Architect uses its
  non-streaming LLM path (intended for Phase 1-3). The e2e phase attaches a
  real adapter to exercise streaming.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.core.game_kernel import GameKernel
from src.core.story_manager import StoryManager
from src.core.state_manager import StateManager
from src.models.story_models import Story, load_story_from_file

from tests.helpers.mock_llm_tool_calling import ToolCallingMockLLM


@pytest.fixture
def mock_tool_llm() -> ToolCallingMockLLM:
    return ToolCallingMockLLM(model="mock")


@pytest.fixture
def stories_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "stories"


@pytest.fixture
def tiny_story(stories_dir) -> Story:
    return load_story_from_file(str(stories_dir / "tiny.yaml"))


@pytest.fixture
def game_kernel(mock_tool_llm, stories_dir, tmp_path) -> GameKernel:
    sm = StoryManager(stories_dir=str(stories_dir))
    state_mgr = StateManager(save_dir=str(tmp_path / "saves"))  # NB: kwarg is save_dir
    return GameKernel(sm, state_mgr, mock_tool_llm)


@pytest.fixture
async def started_game(game_kernel):
    """Start ``tiny`` for ``player1``; yield ``(game_state, story)``.

    ``process_input`` and ``architect.handle`` both require the ``story``, so we
    return the manifest the kernel just loaded alongside the state.
    """
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    assert gs is not None, "tiny.yaml failed to start"
    await asyncio.sleep(0)  # let the fire-and-forget proactive-gen task settle
    yield gs, game_kernel.story_manifest
