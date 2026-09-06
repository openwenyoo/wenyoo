import copy
import json

from src.models.game_state import GameState
from tests.helpers.mock_llm_tool_calling import tc


async def test_clarification_preserves_world_and_resolves_numbered_answer(game_kernel, mock_tool_llm, started_game):
    state, story = started_game
    before = copy.deepcopy(state.variables)
    version = state.version
    mock_tool_llm.queue_tool_calls([tc('request_clarification', question='Which door?', options=['Red door', 'Blue door'])])
    result = await game_kernel.process_input('open it', state, story, 'player1')
    assert 'Which door?' in result['narrative_response']
    assert state.variables == before
    assert state.version == version
    assert len(mock_tool_llm.captured_calls()) == 1
    restored = GameState.from_dict(state.to_dict(), story)
    assert restored.save_metadata['pending_clarifications']['player1']['original_input'] == 'open it'
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'The blue door opens.', 'audience': 'self'}], state_changes={'variables': {'door_open': True}})])
    await game_kernel.process_input('2', restored, story, 'player1')
    prompt = json.dumps(mock_tool_llm.captured_calls()[-1].messages)
    assert 'CLARIFICATION RESPONSE' in prompt and 'Blue door' in prompt and 'open it' in prompt
    assert restored.variables['door_open'] is True
    assert 'player1' not in restored.save_metadata['pending_clarifications']


async def test_clarification_is_player_scoped_and_can_be_cancelled(game_kernel, mock_tool_llm, started_game):
    state, story = started_game
    state.add_player('player2')
    mock_tool_llm.queue_tool_calls([tc('request_clarification', question='Which item?')])
    await game_kernel.process_input('take it', state, story, 'player1')
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'You look around.'}])])
    await game_kernel.process_input('look', state, story, 'player2')
    assert 'player1' in state.save_metadata['pending_clarifications']
    calls = len(mock_tool_llm.captured_calls())
    await game_kernel.process_input('/cancel', state, story, 'player1')
    assert 'player1' not in state.save_metadata['pending_clarifications']
    assert len(mock_tool_llm.captured_calls()) == calls


async def test_mixed_clarification_and_mutation_batch_cannot_change_state(game_kernel, mock_tool_llm, started_game):
    state, story = started_game
    mock_tool_llm.queue_tool_calls([
        tc('commit', state_changes={'variables': {'wrong_target': True}}),
        tc('request_clarification', question='Which one?'),
    ])
    mock_tool_llm.queue_tool_calls([tc('request_clarification', question='Which one?')])
    await game_kernel.process_input('steal it', state, story, 'player1')
    assert 'wrong_target' not in state.variables
    assert 'player1' in state.save_metadata['pending_clarifications']
