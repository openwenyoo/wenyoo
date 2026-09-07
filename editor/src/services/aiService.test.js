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

const { buildBatchConvertPrompt, buildGenericAIPrompt, streamAIEdit } = await import('./aiService.js');
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

test('AI review lifecycle brackets streamed changes and completes on failure', async (t) => {
    const events = [];
    global.window.dispatchEvent = event => events.push(event.type);
    const originalFetch = global.fetch;
    t.after(() => { global.fetch = originalFetch; delete global.window.dispatchEvent; });
    t.mock.method(console, 'log', () => {});
    t.mock.method(console, 'error', () => {});
    global.fetch = async () => new Response(
        'event: node_updated\ndata: {"node":{"id":"room","name":"Revised"}}\n\nevent: complete\ndata: {"message":"Done"}\n\n',
        { headers: { 'content-type': 'text/event-stream' } },
    );
    await streamAIEdit({ prompt: 'Revise the room', onNodeUpdated: () => events.push('node_updated') });
    assert.deepEqual(events, ['wenyoo-ai-edit-start', 'node_updated', 'wenyoo-ai-edit-end']);
    events.length = 0;
    global.fetch = async () => { throw new Error('offline'); };
    await streamAIEdit({ prompt: 'Revise the room', onError: () => events.push('error') });
    assert.deepEqual(events, ['wenyoo-ai-edit-start', 'error', 'wenyoo-ai-edit-end']);
});
