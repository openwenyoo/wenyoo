import test from 'node:test';
import assert from 'node:assert/strict';

import { buildPrompt } from './promptBuilder.js';
import { EDITOR_PROMPT_LANGUAGE_SECTION } from './editorPromptLanguage.js';

test('buildPrompt includes the editor language-following rule', () => {
    const prompt = buildPrompt(
        '请把图书馆扩展成一个中文悬疑场景',
        [],
        { metadata: { title: 'Mystery House', genre: 'Mystery' } },
        [{ id: 'library', description: 'Dusty shelves', actions: [], objects: [] }],
        []
    );

    assert.ok(prompt.includes(EDITOR_PROMPT_LANGUAGE_SECTION));
    assert.ok(prompt.includes('# USER REQUEST'));
    assert.ok(prompt.includes('请把图书馆扩展成一个中文悬疑场景'));
});
