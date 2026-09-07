# Validate, playtest, and review stories

Open **File → Story quality · Validate / Auto-test / Changes** in the editor.
These tools inspect the current unsaved story. Close and reopen the panel after
making a fix to check the new state.

## Validation

Validation checks model fields, duplicate IDs, missing references, character
locations, conflicting inventory ownership, contradictory equality conditions,
missing definitions, and nodes without a static path from the start. Use **Open**
to jump to the related node, character, object, or connection.

Errors identify invalid structure or references. Warnings need author judgment:
natural-language intent, Lua, and generated content can legitimately reach a node
that has no static graph path. Validation cannot prove narrative logic correct.

The same checks are available without an LLM:

```bash
python scripts/validate_story_yaml.py stories/example.yaml
python scripts/validate_story_yaml.py stories/example.yaml --json
```

The command resolves `includes`, rejects duplicate YAML mapping keys, and exits
with status 1 for errors. Warnings alone do not fail the command.

## Auto-test

Fix validation errors, choose a player-turn budget (1–30, default 8), optionally
provide up to ten sample commands, and click **Run auto-test**. This uses the
configured LLM and consumes model tokens. Each player turn can contain several
Architect tool calls.

The bot explores available authored actions and sample commands breadth-first,
forking state for each choice. It uses the first playable character when one is
defined. Runs use a temporary story and temporary saves; they do not join live
rooms. Deferred generation and tickers are disabled. The UI uses a depth limit of
four; each startup/turn has a 45-second timeout and the request has a three-minute
limit.

Reports show attempted commands, paths, narrative results, visited nodes, endings,
unvisited nodes, repeated world states, runtime errors, and non-ending nodes with
no available actions. A repeated state may be an intentional inspection action.
Paths that ask for forms or clarification are reported for manual testing.
**Download report** exports JSON. Coverage is sampled, not exhaustive; the bot does
not certify free-text choices, multiplayer coordination, timing, or narrative quality.

## Changes and version history

**Changes** compares the current story with the version loaded into the editor.
After AI edits, the panel opens with a comparison against the story immediately
before that edit, including partial changes if the AI request failed. Nodes,
actions, entities, connections, and parameters are compared by ID where possible;
expand an entry to see before and after values.

**File → Version history** lists immutable snapshots with UUIDs, timestamps, and
summaries. Select **Review changes** and compare against the current editor story
or another snapshot. Restore backs up the full current editor story, including
unsaved changes, before replacing it. Saving also keeps a snapshot of the newly
saved story. Legacy numbered versions remain readable and get stable UUIDs.

Snapshots live under `saves/story_versions/<story_id>/`, with YAML content and a
JSON metadata file. New snapshots of modular stories resolve their includes, so
later edits to included files cannot change the snapshot. Existing legacy backups
that contain includes still depend on those included files.
