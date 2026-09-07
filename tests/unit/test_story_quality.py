import copy
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from src.core.story_validation import validate_story_data
from src.core.story_versions import StoryVersions, story_diff
from src.models.game_state import GameState
from src.models.story_models import load_story_from_data, load_story_from_file


@pytest.fixture
def authored_story(stories_dir):
    return yaml.safe_load((stories_dir / 'tiny.yaml').read_text())


def test_validation_reports_actionable_references_and_dynamic_targets(authored_story):
    authored_story['nodes']['start_node']['actions'][0]['effects'] = [
        {'type': 'goto_node', 'target': 'missing'},
        {'type': 'goto_node', 'target': '{destination}'},
        {'type': 'present_form', 'form_id': 'unknown'},
    ]
    issues = validate_story_data(authored_story)
    errors = [i for i in issues if i['severity'] == 'error']
    assert len(errors) == 2
    assert errors[0]['entity_id'] == 'start_node'
    assert errors[0]['path'][-2:] == [0, 'target']
    assert any(i['code'] == 'unreachable' and i['entity_id'] == 'end_node' for i in issues)


def test_validation_checks_duplicate_inventory_ids_schema_and_definitions(authored_story):
    char = authored_story['characters'][0]
    char['properties']['inventory'] = ['entity_a']
    second = copy.deepcopy(char)
    second['id'] = 'character_y'
    authored_story['characters'].append(second)
    authored_story['nodes']['start_node']['definition'] = ''
    authored_story['forms'] = {'broken': {'fields': [{'id': 'x'}]}}
    issues = validate_story_data(authored_story)
    assert {'inventory_ownership', 'schema', 'missing_definition'} <= {i['code'] for i in issues}
    assert any(i['entity_id'] == 'character_y' and i['code'] == 'inventory_ownership' for i in issues)


def test_validation_does_not_mutate_authored_data(authored_story):
    original = copy.deepcopy(authored_story)
    validate_story_data(authored_story)
    assert authored_story == original


def test_duplicate_yaml_keys_are_reported_instead_of_losing_a_node(tmp_path):
    path = tmp_path / 'duplicate.yaml'
    path.write_text('id: duplicate\nnodes:\n  start: {state: first}\n  start: {state: second}\n')
    with pytest.raises(yaml.constructor.ConstructorError, match='duplicate key'):
        load_story_from_file(str(path))


def test_validation_handles_malformed_collections_and_conflicting_conditions(authored_story):
    authored_story['actions'] = 7
    authored_story['nodes']['start_node']['actions'][0]['conditions'] = [
        {'type': 'variable', 'variable': 'x', 'operator': 'eq', 'value': 1},
        {'type': 'variable', 'variable': 'x', 'operator': 'eq', 'value': 2},
    ]
    issues = validate_story_data(authored_story)
    assert {'structure', 'contradictory_conditions'} <= {i['code'] for i in issues}


def test_demo_phones_have_independent_identity_and_survive_transfer_and_save():
    story = load_story_from_file('stories/multiplayer_coop_demo.yaml')
    state = GameState(story)
    for player, char in [('a', 'operator_alpha'), ('b', 'operator_beta')]:
        state.add_player(player)
        state.set_player_character(player, story.get_character(char))
    alpha, = state.get_player_inventory('a')
    beta, = state.get_player_inventory('b')
    assert alpha != beta
    state.apply_merge_patch({'object_states': {alpha: {'properties': {'broken': True}}}}, 'a')
    assert not state.object_states[beta]['properties'].get('broken')
    assert state.transfer_item(alpha, 'a', 'b')
    restored = GameState.from_dict(state.to_dict(), story.model_copy(deep=True))
    assert restored.get_player_inventory('a') == []
    assert set(restored.get_player_inventory('b')) == {alpha, beta}
    assert restored.object_states[alpha]['properties']['broken'] is True


def test_inventory_collision_rejects_entire_patch_and_allows_atomic_transfer(authored_story):
    char = authored_story['characters'][0]
    char['properties']['inventory'] = ['entity_a']
    second = copy.deepcopy(char)
    second['id'] = 'character_y'
    second['properties']['inventory'] = []
    authored_story['characters'].append(second)
    state = GameState(load_story_from_data(authored_story))
    version = state.version
    with pytest.raises(ValueError, match='separate object ID'):
        state.apply_merge_patch({'variables': {'changed': True}, 'character_states': {
            'character_y': {'properties': {'inventory': ['entity_a']}},
        }}, 'player')
    assert 'changed' not in state.variables
    assert state.version == version
    state.apply_merge_patch({'character_states': {
        'character_x': {'properties': {'inventory': []}},
        'character_y': {'properties': {'inventory': ['entity_a']}},
    }}, 'player')
    assert state.character_states['character_y']['properties']['inventory'] == ['entity_a']


def test_runtime_nested_inventory_does_not_mutate_the_story(authored_story):
    authored_story['characters'][0]['properties']['inventory'] = ['entity_a']
    story = load_story_from_data(authored_story)
    first, second = GameState(story), GameState(story)
    first.character_states['character_x']['properties']['inventory'].clear()
    assert second.character_states['character_x']['properties']['inventory'] == ['entity_a']
    assert story.characters[0].properties['inventory'] == ['entity_a']


def test_snapshot_uuids_survive_reload_and_numbering_gaps(tmp_path):
    (tmp_path / 'story_0.yaml').write_text('name: Original\n')
    (tmp_path / 'story_5.yaml').write_text('name: Later\n')
    store = StoryVersions(tmp_path, 'story')
    old = store.list()
    assert UUID(old[0]['uuid'])
    created = store.snapshot('name: New\n', 'AI review checkpoint')
    assert created['version'] == 6
    reloaded = StoryVersions(tmp_path, 'story')
    assert reloaded.list()[:2] == old
    assert reloaded.resolve(created['uuid']).read_text() == 'name: New\n'
    assert reloaded.resolve('5') == Path(tmp_path, 'story_5.yaml')
    with pytest.raises(FileNotFoundError):
        reloaded.resolve('../../story')


def test_semantic_diff_matches_ids_and_records_removal_and_null():
    before = {'nodes': {'room': {'actions': [{'id': 'a', 'text': 'Old'}, {'id': 'b', 'text': 'B'}]}}, 'initial_variables': {'x': None}}
    after = {'nodes': {'room': {'actions': [{'id': 'b', 'text': 'B'}, {'id': 'a', 'text': 'New'}]}}, 'initial_variables': {}}
    diff = story_diff(before, after)
    assert diff['counts'] == {'added': 0, 'removed': 1, 'modified': 1}
    assert diff['changes'][1]['path'] == ['nodes', 'room', 'actions', 'a', 'text']
    assert diff['changes'][0]['kind'] == 'removed'


def test_diff_ignores_editor_node_defaults():
    before = {'nodes': {'room': {'definition': 'Old'}}}
    after = {'objects': [], 'nodes': {'room': {'id': 'room', 'objects': [], 'actions': [],
                                            'properties': {}, 'definition': 'New'}}}
    diff = story_diff(before, after)
    assert diff['counts'] == {'added': 0, 'removed': 0, 'modified': 1}
    assert diff['changes'][0]['path'] == ['nodes', 'room', 'definition']
