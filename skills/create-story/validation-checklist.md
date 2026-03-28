# Story Validation Checklist

Use this checklist after creating or editing a story. Work through each section systematically.

## 1. YAML Syntax

- [ ] File parses without YAML syntax errors (consistent 2-space indentation, proper quoting)
- [ ] Multi-line strings use `|` (literal block) or `>` (folded) correctly
- [ ] Special characters in strings are properly quoted (colons, `#`, `{`, `}`)

## 2. Required Top-Level Fields

- [ ] `id` -- unique snake_case identifier
- [ ] `name` -- human-readable display name (or `title`, which the loader uses as fallback)
- [ ] `start_node_id` -- references an existing node key in `nodes:`
- [ ] `nodes` -- at least one node defined

## 2a. Connection Graph

- [ ] If `connections` is present, every connection has a unique `id`
- [ ] Every connection has `source` and `targets`
- [ ] Every `source` and `target` references an existing node, character, or object ID
- [ ] Connection `targets` arrays are non-empty
- [ ] Prefer generating connections with `python tools/compile_connections.py` rather than hand-authoring

## 3. Node Integrity

- [ ] Every `goto_node` / `move_to_node` target references a node that exists in `nodes:`
- [ ] `start_node_id` matches a key in `nodes:`
- [ ] No orphaned nodes (every non-start node is reachable from at least one other node)
- [ ] Nodes with `is_ending: true` have no outgoing navigation actions (or only optional ones)
- [ ] Nodes use `explicit_state` (not `description`) for player-visible text -- except in legacy stories

## 4. Actions

- [ ] Every action has both `id` and `text` fields
- [ ] No action uses `name` instead of `text` for the display label
- [ ] No action uses `description` instead of `text`
- [ ] No `keywords` field (deprecated -- LLM handles intent matching)
- [ ] Action IDs are unique within each node
- [ ] Actions with conditions have valid condition structures

## 5. Effects

- [ ] All effects use `type:` as the type field, never `effect:`
- [ ] `set_variable` uses `target:` for the variable name, never `variable:`
- [ ] `goto_node` uses `target:`, never `target_node:`
- [ ] `add_to_inventory` / `remove_from_inventory` use `target:` for item ID
- [ ] Arithmetic uses `modify_variable` (with `operation: add/subtract/multiply/divide/set`), never `set_variable` with expression strings
- [ ] `llm_generate` for narrative prose has `output_format: text`
- [ ] `llm_generate` for repeatable actions has `regenerate: true`
- [ ] `present_form` references a `form_id` that exists in the `forms:` section
- [ ] `dice_roll` has `dice` field (e.g., `"2d6"`) and `output_variable`
- [ ] `call_function` references a `function` ID that exists in `functions:`
- [ ] `execute_script` has a `script` field with valid Lua code

## 6. Objects

- [ ] Object references in nodes use `- id: object_id` format, never bare strings
- [ ] Objects have at minimum: `id`, `name`
- [ ] Interactive objects have a `definition` field with interaction rules
- [ ] Objects referenced by `add_to_inventory` / `remove_from_inventory` effects are defined somewhere

## 7. Characters

- [ ] Characters have: `id`, `name`, `definition`
- [ ] `is_playable` is set (true for player characters, false for NPCs)
- [ ] NPC `definition` includes behavior rules with `##` section headers
- [ ] Effects in definitions use JSON format: `{"type": "...", ...}`
- [ ] `properties.location`, if present, points to a valid node ID
- [ ] Playable characters have appropriate `properties.stats` and `properties.inventory`

## 8. Triggers

- [ ] Every trigger has a unique `id`
- [ ] Lifecycle triggers have a valid `type`: `pre_enter`, `post_enter`, `pre_leave`, `post_leave`, `game_start`
- [ ] Condition-based triggers (no `type`) have at least one condition
- [ ] All triggers have an `effects` list
- [ ] Global triggers (at story root) don't accidentally duplicate node-level triggers

## 9. Conditions

- [ ] `variable` conditions have: `variable`, `operator` (eq/neq/gt/lt/gte/lte/contains/not_contains/exists/not_exists), `value`
- [ ] `compare` conditions have: `left`, `operator` (>=, <=, >, <, ==, !=), `right`
- [ ] `inventory` conditions have: `operator` (has/not_has), `value`
- [ ] `object_status` conditions have: `target`, `value` (or legacy `state`)
- [ ] `stat` conditions have: `variable` (stat name), `operator`, `value`
- [ ] `and` / `or` compound conditions have a `conditions` list of sub-conditions
- [ ] Variable names in conditions match variables defined in `initial_variables` or set by effects

## 10. Forms

- [ ] Each form has a unique key in `forms:`
- [ ] Form fields have unique `id` within the form
- [ ] Required field types are valid: text, textarea, number, select, multiselect, radio, checkbox, checkboxgroup, slider, rating, file, date, time, hidden
- [ ] Select/radio/multiselect fields have `options` defined
- [ ] `on_submit.store_variables` uses `field:` (field ID or `"*"`) and `to:` (variable path)
- [ ] File fields have valid `accept` MIME types
- [ ] `show_if` references valid field IDs within the same form

## 11. Variables

- [ ] `initial_variables` defines all variables used in conditions and effects
- [ ] Variable substitution in text uses `{variable_name}` or `{$variable_name}` syntax
- [ ] Derived variables (computed) use `$lua:` prefix and don't have circular dependencies
- [ ] Lorebook variables follow `lore_*` naming convention for LLM context
- [ ] Variables can also be initialized via `llm_generate:` prefix for LLM-filled values at startup

## 11a. Functions

- [ ] Each function has a unique `id`
- [ ] Function `parameters` list matches what callers pass in `call_function` effects
- [ ] Functions defined as a list have `id` on each entry; dict format uses the key as the ID
- [ ] Lua scripts in `execute_script` effects are syntactically valid

## 12. Multi-File Stories

- [ ] `includes` lists files relative to the main YAML file
- [ ] All included files exist and parse correctly
- [ ] No duplicate node/character/object IDs across included files
- [ ] The main file has `start_node_id` pointing to a node in any of the files

## 13. Language & Content

- [ ] All player-facing text is in a single consistent language
- [ ] `definition` fields, `explicit_state` fields, action `text`, and `display_text` effects all use the same language
- [ ] No mixed-language content (unless intentionally bilingual)

## 14. Status Display Config (if used)

- [ ] `stats` entries have: `label`, `format`, `values`
- [ ] `values` dict maps local names to valid game state paths
- [ ] `{player_id}` placeholder used correctly in paths like `{$players.{player_id}.character.stats.hp}`
- [ ] If using `template`, the template name matches a file in `stories/status_display_templates/`

## Quick Smoke Test

After validation, mentally walk through the story:

1. Start at `start_node_id` -- does the first node have a explicit_state or definition for generation?
2. Follow each action chain -- can the player reach every node?
3. Check ending paths -- do all `is_ending: true` nodes feel like proper conclusions?
4. Test puzzle gates -- are conditions satisfiable? Can the player obtain required items?
5. Verify NPC interactions -- do character definitions have rules covering likely player interactions?
