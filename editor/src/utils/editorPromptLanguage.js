export const EDITOR_PROMPT_LANGUAGE_SECTION = `# LANGUAGE
Respond in the same language as the user's request unless the user explicitly asks for a different language.
Keep explanations, summaries, and generated story content in that same language.
Do not default to English just because the format instructions or schema examples are written in English.`;

export function appendEditorLanguageSection(prompt) {
    const trimmedPrompt = String(prompt || '').trim();

    if (!trimmedPrompt) {
        return EDITOR_PROMPT_LANGUAGE_SECTION;
    }

    if (trimmedPrompt.includes(EDITOR_PROMPT_LANGUAGE_SECTION)) {
        return trimmedPrompt;
    }

    return `${trimmedPrompt}\n\n${EDITOR_PROMPT_LANGUAGE_SECTION}`;
}
