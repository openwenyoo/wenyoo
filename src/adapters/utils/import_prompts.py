"""Prompt builders and validators for generic import-based story creation."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import json


REQUIRED_IMPORT_DRAFT_FIELDS = (
    "sourceType",
    "sourceFormat",
    "title",
    "summary",
    "rawText",
    "characters",
    "worldInfo",
    "scenario",
    "styleHints",
    "metadata",
    "importWarnings",
    "rawSource",
)


def normalize_import_draft(import_draft: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sanitized import draft with all expected keys present."""
    draft = dict(import_draft or {})
    normalized = {
        "sourceType": str(draft.get("sourceType") or "unknown"),
        "sourceFormat": str(draft.get("sourceFormat") or "unknown"),
        "title": str(draft.get("title") or "Untitled Import"),
        "summary": str(draft.get("summary") or ""),
        "rawText": str(draft.get("rawText") or ""),
        "characters": draft.get("characters") if isinstance(draft.get("characters"), list) else [],
        "worldInfo": draft.get("worldInfo") if isinstance(draft.get("worldInfo"), list) else [],
        "scenario": str(draft.get("scenario") or ""),
        "styleHints": draft.get("styleHints") if isinstance(draft.get("styleHints"), dict) else {},
        "metadata": draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {},
        "importWarnings": draft.get("importWarnings") if isinstance(draft.get("importWarnings"), list) else [],
        "rawSource": draft.get("rawSource"),
    }
    return normalized


def validate_import_draft(import_draft: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Validate an import draft payload."""
    normalized = normalize_import_draft(import_draft)
    errors: List[str] = []

    for field in REQUIRED_IMPORT_DRAFT_FIELDS:
        if field not in normalized:
            errors.append(f"Missing import draft field: {field}")

    if not normalized["title"].strip():
        errors.append("Import draft title is required")

    if not normalized["summary"].strip() and not normalized["rawText"].strip() and not normalized["characters"]:
        errors.append("Import draft must include some extracted source material")

    return len(errors) == 0, errors, normalized


def _compact_import_context(import_draft: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce the import draft to prompt-friendly, high-value fields."""
    style_hints = import_draft.get("styleHints") or {}
    metadata = import_draft.get("metadata") or {}
    characters = import_draft.get("characters") or []
    world_info = import_draft.get("worldInfo") or []
    raw_text = import_draft.get("rawText") or ""

    return {
        "source_type": import_draft.get("sourceType"),
        "source_format": import_draft.get("sourceFormat"),
        "title": import_draft.get("title"),
        "summary": import_draft.get("summary"),
        "scenario": import_draft.get("scenario"),
        "characters": characters[:5],
        "world_info": world_info[:12],
        "style_hints": style_hints,
        "import_warnings": import_draft.get("importWarnings") or [],
        "metadata": {
            "filename": metadata.get("filename"),
            "parser": metadata.get("parser"),
            "card_spec": metadata.get("cardSpec"),
            "tags": metadata.get("tags"),
            "creator": metadata.get("creator"),
        },
        "raw_text_preview": raw_text[:4000],
    }


def get_import_outline_generation_prompt(
    import_draft: Dict[str, Any],
    writer_intent: str,
    num_options: int = 3,
) -> str:
    """Build prompt for generating story outline options from imported material."""
    compact_context = _compact_import_context(import_draft)
    return f"""You are a creative story designer for interactive AI native text based games.

The writer has imported external source material and wants to turn it into a playable story.
Use the imported material as inspiration and grounding, but design an original interactive story
that fits the engine rather than copying the source mechanically.

# ENGINE CAPABILITIES - IMPORTANT
You are designing for a specific AI native text based game engine. Your story MUST be achievable with these features:

## What the engine CAN do:
- Nodes/Locations: Scenes the player can visit with descriptions and actions
- Actions: Player choices with conditions and effects
- Branching: Multiple paths based on player choices (goto_node)
- Variables: Track story state (booleans, numbers, strings) for flags and stats
- Conditions: Show/hide actions or trigger events based on variables
- Inventory: Add/remove items, check item possession
- Characters/NPCs: Place characters in locations with dialogue and character-specific actions
- Objects: Interactive objects in locations using DSPP fields (`definition`, `explicit_state`, `implicit_state`, `properties`)
- Triggers: Automatic events on entering/leaving nodes or when conditions are met
- LLM Text Generation: Generate dynamic text descriptions using prompts (stored in variables)
- Dice Rolls: Random skill checks with success/failure outcomes
- Lorebook/Parameters: Store world lore, writing style, and background info for LLM prompts

## What the engine CANNOT do:
- Real-time mechanics or timers tied to actual wall-clock time
- Dynamic UI changes beyond text and action buttons
- Audio, images, or visual effects
- Complex minigames outside text-driven choices and variables

# IMPORTED SOURCE MATERIAL
{json.dumps(compact_context, indent=2, ensure_ascii=False)}

# WRITER'S GOAL
{writer_intent}

# YOUR TASK
Generate {num_options} distinct outline options that transform the imported material into different playable story directions.
Preserve the most useful parts of the source, but adapt them into a format that works well for branching interactive fiction.

# OUTPUT FORMAT
Return a JSON object with {num_options} outline options:
{{
  "outlines": [
    {{
      "id": "option_1",
      "title": "Catchy title for this version",
      "theme": "The specific theme/subgenre",
      "setting": {{
        "time_period": "When does it take place",
        "location": "Where does it happen",
        "atmosphere": "The mood/vibe"
      }},
      "protagonist": {{
        "archetype": "Type of main character",
        "motivation": "What drives them"
      }},
      "core_conflict": "The main tension/problem",
      "estimated_length": "short" | "medium" | "long",
      "key_features": ["Feature 1", "Feature 2", "Feature 3"],
      "sample_beats": [
        "Opening scene/hook",
        "First major choice",
        "Midpoint twist",
        "Climax setup",
        "Possible endings"
      ]
    }}
  ]
}}

IMPORTANT JSON RULES:
- Return STRICT valid JSON only.
- Escape any double quote characters that appear inside string values as \\\".
- Do not include raw dialogue quotes or quoted phrases inside JSON strings unless they are escaped.
- Do not add markdown commentary before or after the JSON.

Make the options meaningfully different from each other.
Focus on branching narrative, atmosphere, and achievable story mechanics."""


def get_import_conversion_prompt(
    import_draft: Dict[str, Any],
    writer_intent: str,
) -> str:
    """Build prompt for directly converting imported material into one detailed outline."""
    compact_context = _compact_import_context(import_draft)
    return f"""You are a story designer converting imported source material into an interactive AI native text based game engine.

# IMPORTANT
- The imported source already establishes the direction.
- Do NOT generate multiple options.
- Your job is to convert the source into a strong, playable structure for this engine.
- Keep the output high-level and structured so the writer can review and confirm it before full generation.

# ENGINE CAPABILITIES
- Nodes/locations with descriptions and actions
- Branching narrative via goto_node actions
- Variables, conditions, inventory, characters, objects, triggers
- Lorebook/parameters for world context and style

# IMPORTED SOURCE MATERIAL
{json.dumps(compact_context, indent=2, ensure_ascii=False)}

# WRITER'S CONVERSION GOAL
{writer_intent}

# YOUR TASK
Produce one conversion draft that:
1. Preserves the source's core direction
2. Identifies the best interactive structure for it
3. Extracts the most important characters, locations, items, and mechanics
4. Turns the imported material into a detailed outline and execution plan seed

# OUTPUT FORMAT
{{
  "detailed_outline": {{
    "title": "Story title",
    "theme": "Core theme in one sentence",
    "setting": "Where and when, brief",
    "tone": "Narrative tone/atmosphere",
    "writing_style": "How to write descriptions (2-3 sentences)",
    "game_mechanics": {{
      "key_variables": [
        {{"name": "variable_name", "type": "number/boolean/string", "purpose": "What it tracks"}}
      ],
      "core_loop": "What the player repeatedly does",
      "win_condition": "How to win/complete",
      "fail_conditions": ["How the player can lose"]
    }},
    "characters": [
      {{
        "id": "char_id",
        "name": "Name",
        "role": "protagonist/antagonist/ally/npc",
        "one_liner": "Character in one sentence"
      }}
    ],
    "key_items": [
      {{"id": "item_id", "name": "Name", "purpose": "Why it matters"}}
    ],
    "story_structure": {{
      "act_1": "Setup - what happens at the start",
      "act_2": "Confrontation - main challenges",
      "act_3": "Resolution - how it can end"
    }},
    "major_locations": ["Location 1", "Location 2", "Location 3"],
    "endings": [
      {{"type": "good/bad/neutral", "title": "Ending name", "trigger": "How to reach it"}}
    ]
  }},
  "lore_outline": "A 3-5 paragraph text summary of the converted story for LLM context"
}}

Output only one conversion draft. Do not return multiple alternatives."""


def get_import_outline_expansion_prompt(
    import_draft: Dict[str, Any],
    selected_outline: Dict[str, Any],
    user_modifications: str | None = None,
) -> str:
    """Build prompt for expanding a selected import-derived outline."""
    modifications_text = ""
    if user_modifications:
        modifications_text = f"""
# USER MODIFICATIONS
The writer requested these changes to the selected direction:
{user_modifications}
"""

    compact_context = _compact_import_context(import_draft)

    return f"""You are a story designer creating a high-level story bible for an interactive AI native text based game engine.

# IMPORTANT
- The story is based on imported source material.
- Use the imported material as grounding, but adapt it into a clean interactive structure.
- Keep the output concise and high-level.
- Do NOT list every final node; actual node creation happens separately.

# IMPORTED SOURCE MATERIAL
{json.dumps(compact_context, indent=2, ensure_ascii=False)}

# SELECTED OUTLINE
{json.dumps(selected_outline, indent=2, ensure_ascii=False)}
{modifications_text}

# YOUR TASK
Create a compact story bible with:
1. Core narrative elements (theme, setting, tone)
2. Key game mechanics and variables
3. Main characters (3-5 max)
4. Critical objects/items
5. Major story beats
6. Possible endings

# OUTPUT FORMAT
{{
  "detailed_outline": {{
    "title": "Story title",
    "theme": "Core theme in one sentence",
    "setting": "Where and when, brief",
    "tone": "Narrative tone/atmosphere",
    "writing_style": "How to write descriptions (2-3 sentences)",
    "game_mechanics": {{
      "key_variables": [
        {{"name": "variable_name", "type": "number/boolean/string", "purpose": "What it tracks"}}
      ],
      "core_loop": "What the player repeatedly does",
      "win_condition": "How to win/complete",
      "fail_conditions": ["How the player can lose"]
    }},
    "characters": [
      {{
        "id": "char_id",
        "name": "Name",
        "role": "protagonist/antagonist/ally/npc",
        "one_liner": "Character in one sentence"
      }}
    ],
    "key_items": [
      {{"id": "item_id", "name": "Name", "purpose": "Why it matters"}}
    ],
    "story_structure": {{
      "act_1": "Setup - what happens at the start",
      "act_2": "Confrontation - main challenges",
      "act_3": "Resolution - how it can end"
    }},
    "major_locations": ["Location 1", "Location 2", "Location 3"],
    "endings": [
      {{"type": "good/bad/neutral", "title": "Ending name", "trigger": "How to reach it"}}
    ]
  }},
  "lore_outline": "A 3-5 paragraph text summary of the story for LLM context"
}}

Keep the output compact.
When useful, preserve names, relationships, lore, or style from the imported source."""
