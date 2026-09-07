import copy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import yaml

from src.adapters.routes.story_quality_routes import register_story_quality_routes
from src.adapters.routes.story_routes import register_story_routes
from src.core.story_manager import StoryManager
from src.core.story_playtester import playtest_story
from src.core.story_versions import StoryVersions
from tests.helpers.mock_llm_tool_calling import tc


@pytest.fixture
def play_story():
    return {
        'id': 'test', 'title': 'Test', 'name': 'Test', 'start_node_id': 'start',
        'characters': [{'id': 'hero', 'name': 'Hero', 'is_playable': True, 'definition': 'The player.',
                        'properties': {'location': 'start'}}],
        'nodes': {
            'start': {'definition': 'Choose a door.', 'actions': [
                {'id': 'exit', 'text': 'Leave', 'intent': 'Move to the ending.'},
                {'id': 'wait', 'text': 'Wait', 'intent': 'Wait without changing anything.'},
            ]},
            'end': {'definition': 'The ending.', 'is_ending': True},
        },
    }


async def test_playtest_branches_are_isolated_and_find_loop_and_ending(play_story, mock_tool_llm):
    original = copy.deepcopy(play_story)
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'You leave.'}],
                                      state_changes={'character_states': {'hero': {'properties': {'location': 'end'}}}})])
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'You wait.'}])])
    report = await playtest_story(play_story, mock_tool_llm, max_steps=8)
    assert report['status'] == 'completed'
    assert report['ending_nodes'] == ['end']
    assert len(report['steps']) == 2
    assert all(s['from'] == 'start' for s in report['steps'])
    assert any(f['code'] == 'loop' for f in report['findings'])
    assert play_story == original


async def test_playtest_respects_budget_and_reports_provider_fallback(play_story, mock_tool_llm):
    mock_tool_llm.queue_text('')
    report = await playtest_story(play_story, mock_tool_llm, max_steps=1)
    assert len(report['steps']) == 1
    assert report['limited'] is True
    assert any(f['code'] == 'no_response' for f in report['findings'])


async def test_playtest_records_ending_reached_on_last_budgeted_turn(play_story, mock_tool_llm):
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'The end.'}],
                                      state_changes={'character_states': {'hero': {'properties': {'location': 'end'}}}})])
    report = await playtest_story(play_story, mock_tool_llm, max_steps=1)
    assert 'end' in report['ending_nodes']
    assert 'end' in report['visited_nodes']


async def test_form_in_one_branch_does_not_pause_another_branch(play_story, mock_tool_llm):
    play_story['forms'] = {'choice': {'title': 'Choose', 'fields': [{'id': 'name', 'type': 'text', 'label': 'Name'}]}}
    play_story['nodes']['middle'] = {'definition': 'Continue.', 'actions': [{'id': 'finish', 'text': 'Finish'}]}
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'Continue.'}],
                                      state_changes={'character_states': {'hero': {'properties': {'location': 'middle'}}}})])
    mock_tool_llm.queue_tool_calls([tc('present_form', form_id='choice')])
    mock_tool_llm.queue_tool_calls([tc('commit', artifacts=[{'kind': 'narrative', 'payload': 'The end.'}],
                                      state_changes={'character_states': {'hero': {'properties': {'location': 'end'}}}})])
    report = await playtest_story(play_story, mock_tool_llm)
    assert 'end' in report['ending_nodes']
    assert len(report['steps']) == 3
    paused = [f for f in report['findings'] if f['code'] == 'input_required']
    assert len(paused) == 1 and paused[0]['path'] == ['Wait']


def test_quality_endpoints_validate_unsaved_data_and_limit_model_work(game_kernel, play_story):
    app = FastAPI()
    register_story_quality_routes(app, game_kernel)
    client = TestClient(app)
    broken = copy.deepcopy(play_story)
    broken['start_node_id'] = 'missing'
    assert client.post('/api/story-quality/validate', json={'story': broken}).json()['valid'] is False
    response = client.post('/api/story-quality/playtest', json={'story': broken})
    assert response.json()['status'] == 'invalid'
    assert not game_kernel.llm_provider.captured_calls()
    assert client.post('/api/story-quality/playtest', json={'story': play_story, 'max_steps': 1000}).status_code == 422
    diff = client.post('/api/story-quality/diff', json={'before': play_story, 'after': broken}).json()
    assert diff['changes'][0]['path'] == ['start_node_id']


def test_save_restore_and_uuid_lookup_preserve_versions_and_invalidate_cache(tmp_path, play_story):
    story_dir = tmp_path / 'stories'
    story_dir.mkdir()
    path = story_dir / 'test.yaml'
    path.write_text(yaml.safe_dump(play_story))
    manager = StoryManager(str(story_dir))
    manager.saves_dir = str(tmp_path / 'saves')
    app = FastAPI()
    register_story_routes(app, manager)
    client = TestClient(app)
    assert client.post('/api/story/test/backup-original').json()['created'] is True
    original = client.get('/api/story/test/versions').json()['versions'][0]
    changed = {**play_story, 'title': 'Changed title'}
    saved = client.post('/api/story/test', json=changed).json()
    assert saved['success']
    assert client.get('/api/story/test/version/' + saved['uuid']).json()['title'] == 'Changed title'
    manager.discover_stories()
    restored = client.post('/api/story/test/restore/' + original['uuid']).json()
    assert restored['success']
    assert yaml.safe_load(path.read_text())['title'] == 'Test'
    assert manager._stories is None
    assert client.get('/api/story/test/version/' + restored['backup_uuid']).json()['title'] == 'Changed title'
    history = StoryVersions(tmp_path / 'saves/story_versions/test', 'test').list()
    assert len({v['uuid'] for v in history}) == len(history)
    assert client.get('/api/story/test/version/999999').json().get('error')
    assert json.loads((tmp_path / 'saves/story_versions/test/test_0.json').read_text())['uuid'] == original['uuid']


def test_modular_snapshot_is_independent_of_later_include_edits(tmp_path):
    story_dir = tmp_path / 'stories'
    folder = story_dir / 'modular'
    folder.mkdir(parents=True)
    (folder / 'main.yaml').write_text('id: modular\ntitle: Modular\nstart_node_id: start\nincludes: [rooms.yaml]\n')
    rooms = folder / 'rooms.yaml'
    rooms.write_text('nodes:\n  start:\n    definition: Original room\n')
    manager = StoryManager(str(story_dir))
    manager.saves_dir = str(tmp_path / 'saves')
    app = FastAPI()
    register_story_routes(app, manager)
    client = TestClient(app)
    client.post('/api/story/modular/backup-original')
    version = client.get('/api/story/modular/versions').json()['versions'][0]
    rooms.write_text('nodes:\n  start:\n    definition: Changed room\n')
    snapshot = client.get('/api/story/modular/version/' + version['uuid']).json()
    assert 'includes' not in snapshot
    assert snapshot['nodes']['start']['definition'] == 'Original room'
