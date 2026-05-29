"""Phase 2 — config precedence (test-harness-rollout.md §7).

Precedence (low -> high): defaults < config.yaml top-level < config_groups.<name>
< env vars. We exercise the pure precedence helpers directly (rather than
``load_config`` end-to-end) so the repo's real .env / config.yaml can't leak in.
"""
from __future__ import annotations

import pytest

from src.config import (
    _apply_env_overrides,
    _dict_to_config,
    _resolve_config_group,
)


# ── defaults ───────────────────────────────────────────────────────────────────

def test_dict_to_config_applies_defaults():
    cfg = _dict_to_config({})
    assert cfg.llm.provider == "mock"
    assert cfg.llm.model == "llama3"
    assert cfg.llm.base_url == "http://localhost:11434/v1"


# ── config_groups overlay shared/top-level ──────────────────────────────────────

def test_group_overrides_shared_top_level():
    data = {
        "llm": {"provider": "mock", "base_url": "http://shared/v1"},
        "config_groups": {
            "default": {"llm": {"model": "default-model"}},
            "claude": {"llm": {"provider": "anthropic", "model": "claude"}},
        },
    }
    merged = _resolve_config_group(data, "claude")
    # group value wins over shared
    assert merged["llm"]["provider"] == "anthropic"
    assert merged["llm"]["model"] == "claude"
    # shared value is preserved where the group doesn't override
    assert merged["llm"]["base_url"] == "http://shared/v1"
    # the config_groups key itself is stripped from the resolved config
    assert "config_groups" not in merged


def test_group_defaults_to_default_when_unspecified():
    data = {"config_groups": {"default": {"llm": {"model": "D"}}}}
    assert _resolve_config_group(data, None)["llm"]["model"] == "D"


def test_unknown_group_raises():
    data = {"config_groups": {"default": {}}}
    with pytest.raises(ValueError, match="Unknown config group"):
        _resolve_config_group(data, "ghost")


def test_missing_default_group_raises():
    data = {"config_groups": {"only": {}}}
    with pytest.raises(ValueError, match="default.*required"):
        _resolve_config_group(data, "only")


def test_no_groups_passthrough():
    data = {"llm": {"provider": "mock"}}
    assert _resolve_config_group(data, "anything") == data


# ── env vars win over everything ────────────────────────────────────────────────

def test_env_overrides_win(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("SERVER_PORT", "9999")
    data = {"llm": {"provider": "anthropic"}, "server": {"port": 8000}}
    out = _apply_env_overrides(data)
    assert out["llm"]["provider"] == "openai"
    assert out["server"]["port"] == 9999            # coerced to int


def test_env_creates_missing_section(monkeypatch):
    monkeypatch.setenv("STORIES_DIR", "/tmp/custom-stories")
    out = _apply_env_overrides({})
    assert out["paths"]["stories_dir"] == "/tmp/custom-stories"


def test_invalid_port_is_ignored(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "not-a-number")
    out = _apply_env_overrides({"server": {"port": 8000}})
    assert out["server"]["port"] == 8000            # bad value ignored, default kept
