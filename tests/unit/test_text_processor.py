"""Phase 2 — TextProcessor hyperlink syntax (rollout plan §7).

Correction to the plan: the actual link kinds (text_processor.py:138-201) are
  * {@character_id: display}  -> [[character:...]]
  * {object_id: display}      -> [[object:...]]   (when object_id is known)
  * {display: hint} / {display} -> [[input:...]]
There is no `{{o:b}}` double-brace form — the plan's "{a:b}, {{o:b}}, {@c:b}"
shorthand was inaccurate.
"""
from __future__ import annotations

from src.core.text_processor import TextProcessor


def _tp():
    return TextProcessor()


async def test_character_link(started_game):
    gs, _ = started_game
    out = _tp().process_text_for_hyperlinks("Greet {@character_x: the figure}.", gs, "player1")
    assert out == "Greet [[character:character_x|the figure]]."


async def test_object_link(started_game):
    gs, _ = started_game
    out = _tp().process_text_for_hyperlinks("Inspect {entity_a: the object}.", gs, "player1")
    assert out == "Inspect [[object:entity_a|the object]]."


async def test_input_link_with_hint(started_game):
    gs, _ = started_game
    out = _tp().process_text_for_hyperlinks("You could {flee: run away}.", gs, "player1")
    assert out == "You could [[input:flee|run away]]."


async def test_bare_ascii_token_left_untouched(started_game):
    """A bare ascii token with no colon is likely a failed variable
    substitution and must be left unchanged (text_processor.py:194)."""
    gs, _ = started_game
    out = _tp().process_text_for_hyperlinks("Go {north} now.", gs, "player1")
    assert out == "Go {north} now."


async def test_unknown_object_id_becomes_input_link_not_object(started_game):
    gs, _ = started_game
    # 'mystery' is not a known object -> falls through to input link (has a hint).
    out = _tp().process_text_for_hyperlinks("Touch {mystery: do it}.", gs, "player1")
    assert out == "Touch [[input:mystery|do it]]."


async def test_raw_braces_without_pattern_preserved(started_game):
    gs, _ = started_game
    text = "Code uses { } and {123 abc} freely."
    assert _tp().process_text_for_hyperlinks(text, gs, "player1") == text
