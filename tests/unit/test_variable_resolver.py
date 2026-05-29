"""Phase 2 — VariableResolver dotted-path resolution (test-harness-rollout.md §7).

``resolve_path_in_context`` is a pure function over a dict/object graph.
"""
from __future__ import annotations

import pytest

from src.core.variable_resolver import VariableResolver


@pytest.fixture
def resolver():
    return VariableResolver()


def test_resolves_nested_dict_path(resolver):
    ctx = {"player": {"stats": {"hp": 7}}}
    assert resolver.resolve_path_in_context("player.stats.hp", ctx) == 7


def test_resolves_list_index(resolver):
    ctx = {"things": ["sword", "shield"]}
    assert resolver.resolve_path_in_context("things.1", ctx) == "shield"


def test_known_quirk_dict_method_names_shadow_keys(resolver):
    """resolve_path_in_context checks hasattr() BEFORE dict-key lookup, so a key
    that collides with a dict method name ('items', 'keys', 'get', ...) resolves
    to the *method*, not the value. Documented here so a future refactor that
    fixes it knows this behavior was intentional-by-omission, not by design."""
    got = resolver.resolve_path_in_context("items", {"items": ["a", "b"]})
    assert got != ["a", "b"]          # surprising: returns the bound dict.items method
    assert callable(got)


def test_missing_key_returns_none(resolver):
    ctx = {"a": {"b": 1}}
    assert resolver.resolve_path_in_context("a.missing", ctx) is None
    assert resolver.resolve_path_in_context("nope.deep.path", ctx) is None


def test_top_level_key(resolver):
    assert resolver.resolve_path_in_context("flag", {"flag": True}) is True


def test_index_out_of_range_returns_none(resolver):
    assert resolver.resolve_path_in_context("items.9", {"items": [1]}) is None


def test_falsey_value_is_returned_not_treated_as_missing(resolver):
    ctx = {"count": 0, "name": ""}
    assert resolver.resolve_path_in_context("count", ctx) == 0
    assert resolver.resolve_path_in_context("name", ctx) == ""
