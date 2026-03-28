"""Shared editor-only language guidance for LLM prompts."""

EDITOR_PROMPT_LANGUAGE_SECTION = """# LANGUAGE
Respond in the same language as the user's request unless the user explicitly asks for a different language.
Keep explanations, summaries, and generated story content in that same language.
Do not default to English just because the format instructions or schema examples are written in English."""
