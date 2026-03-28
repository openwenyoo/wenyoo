import test from 'node:test';
import assert from 'node:assert/strict';

global.window = {
    location: { search: '' },
    localStorage: {
        getItem() {
            return '';
        },
        setItem() {},
    },
    navigator: { language: 'en-US' },
};

global.localStorage = global.window.localStorage;

const { buildBatchConvertPrompt, buildGenericAIPrompt } = await import('./aiService.js');
const { EDITOR_PROMPT_LANGUAGE_SECTION } = await import('../utils/editorPromptLanguage.js');

test('buildGenericAIPrompt includes the shared language-following rule', () => {
    const prompt = buildGenericAIPrompt({
        prompt: '请把这个物体改成中文描述',
        systemPrompt: 'You are editing an object.',
        contextData: { id: 'artifact', name: 'Ancient Artifact' },
    });

    assert.ok(prompt.includes(EDITOR_PROMPT_LANGUAGE_SECTION));
    assert.ok(prompt.includes('请把这个物体改成中文描述'));
});

test('buildBatchConvertPrompt includes the shared language-following rule', () => {
    const prompt = buildBatchConvertPrompt({
        pseudoContext: 'Pseudo-Node ID: attic\nPrompt: 用中文扩写这个场景',
        edgeContext: 'start (Real) -> attic (Pseudo)',
        realNodeContext: 'Existing Node ID: start\nName: Entrance',
    });

    assert.ok(prompt.includes(EDITOR_PROMPT_LANGUAGE_SECTION));
    assert.ok(prompt.includes('用中文扩写这个场景'));
});
