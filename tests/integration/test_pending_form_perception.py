"""Regression: a pending form must not trigger a scene re-render.

Bug: clicking the intro action presented the character-creation form, then the
post-command perception refresh re-rendered the intro node via the Architect,
whose "present the form" rule fired present_form a SECOND time — the form showed
twice. Fix: `_build_perception_payload` short-circuits while a form is pending
(GameKernel.has_pending_form), so perception resumes only after submission.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.adapters.web_frontend_adapter import WebFrontendAdapter
from src.core.game_kernel import GameKernel
from src.core.state_manager import StateManager
from src.core.story_manager import StoryManager
from tests.helpers.mock_llm_tool_calling import ToolCallingMockLLM


@pytest.fixture
def adapter_and_kernel(tmp_path):
    stories_dir = Path(__file__).parent.parent / "fixtures" / "stories"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    sm = StoryManager(stories_dir=str(stories_dir))
    gk = GameKernel(sm, StateManager(save_dir=str(tmp_path / "saves")), ToolCallingMockLLM(model="mock"))
    adapter = WebFrontendAdapter(
        host="127.0.0.1", port=0, static_dir=str(static_dir),
        game_kernel=gk, story_manager=sm, editor_secret="",
    )
    gk.frontend_adapter = adapter
    return adapter, gk


async def test_pending_form_suppresses_perception_rerender(adapter_and_kernel):
    adapter, gk = adapter_and_kernel
    gs = await gk.start_new_game_async("role_select", "p1", character_id="shell")
    assert gs is not None
    # Spy on the re-render path (would re-invoke the Architect on the node).
    gk.get_node_perception = AsyncMock(return_value="SCENE")

    # No pending form → perception is built (the node is re-rendered once).
    assert gk.has_pending_form("p1") is False
    payload = await adapter._build_perception_payload(gs, "p1")
    assert payload is not None and payload["content"] == "SCENE"
    assert gk.get_node_perception.await_count == 1

    # A pending form → perception is suppressed; the node is NOT re-rendered,
    # so a present_form node-rule can't fire a second time.
    gk._pending_forms["p1"] = {"form_id": "pick_role", "form_def": None}
    gk.get_node_perception.reset_mock()
    assert gk.has_pending_form("p1") is True
    payload2 = await adapter._build_perception_payload(gs, "p1")
    assert payload2 is None
    assert gk.get_node_perception.await_count == 0


async def test_has_pending_form_accessor(adapter_and_kernel):
    _, gk = adapter_and_kernel
    assert gk.has_pending_form("nobody") is False
    gk._pending_forms["nobody"] = {"form_id": "x"}
    assert gk.has_pending_form("nobody") is True
