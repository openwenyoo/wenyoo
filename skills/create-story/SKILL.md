---
name: create-story
description: Create, edit, and validate story YAML files for Wenyoo. Use when the user wants to write a new story, adventure, quest, or game scenario, modify an existing story, add nodes/characters/objects, or check a story for errors.
---

# Wenyoo Story Authoring

## Workflow

### Phase 1: Design

Gather requirements before writing any YAML:

1. **Genre & tone** -- horror, fantasy RPG, puzzle, sandbox simulation, etc.
2. **Language** -- all story content must be in a single consistent language
3. **Scope** -- how many nodes/scenes? Linear path or open world?
4. **Mechanics** -- dice checks? inventory puzzles? sanity meter? combat?
5. **AI latitude** -- tightly scripted (detailed definitions + effects) or AI-native (minimal nodes + rich world rules)?

If the user provides an outline or concept doc, extract these from it. If unclear, ask.

### Phase 2: Scaffold

Create the story file at `stories/<story_id>.yaml` (or `stories/<story_id>/main.yaml` for multi-file stories).

Required top-level fields:

```yaml
id: story_id                  # snake_case unique identifier
name: "Story Name"            # required display name
start_node_id: first_node     # must match a node key in nodes:
initial_variables: {}         # game state tracking
nodes: {}                     # at least one node
```

Optional top-level fields: `title`, `description`, `author`, `version`, `genre`, `characters`, `objects`, `triggers`, `forms`, `status_display_config`, `includes`, `functions`, `connections`, `player_character_defaults`, `frontend`.

If `name` is omitted in YAML, the loader derives it from `title`. Both are accepted, but `name` is the canonical required field.

For world rules and lorebook entries, put them in `initial_variables` as `lore_*` variables (e.g. `lore_world_rules`, `lore_economy`) so the Architect LLM can reference them at runtime.

### Phase 3: Build

Flesh out entities using the DSPP entity model. Build in this order:

1. **initial_variables** -- player stats, flags, lorebook entries (`lore_*`)
2. **Global objects** -- items the player can pick up across multiple scenes
3. **Characters** -- NPCs with behavior rules
4. **Nodes** -- scenes/locations with actions, triggers, and object refs
5. **Global triggers** -- cross-node reactive events
6. **Functions** -- reusable effect sequences (Lua scripts, effect chains)
7. **Forms** -- structured player input (character creation, etc.)

`connections` are optional compiled graph edges that help the Architect propagate consequences consistently across related entities. Each connection has `id`, `source`, and `targets` (list of entity IDs). Generate them with:

```bash
python tools/compile_connections.py <story.yaml> --write
```

Use `--with-llm` to add semantic edges via LLM analysis. Review the generated connections before committing. The compiler also writes a `connection_graph_source_md5` hash to detect when the story has changed and connections need recompiling.

At runtime the engine may add separate `runtime_connections`, but those are emergent state and should not be hand-authored into the story file.

### Phase 4: Validate

Run through the validation checklist in [validation-checklist.md](validation-checklist.md).

---

## Quick Reference

### The Entity Model (DSPP)

Every entity (node, object, character) has these key fields:

| Field | Purpose | Mutability |
|-------|---------|------------|
| `definition` | What it IS -- static rules for the LLM | Immutable |
| `state` | What the player SEES -- current state description | Dynamic |
| `properties` | Mechanical state (status, inventory, stats) | Dynamic |

The `definition` field is where interaction rules live. Use `##` headers for different interactions. Effects inside definitions use JSON format: `{"type": "set_variable", "target": "var", "value": true}`.

### Node Anatomy

```yaml
nodes:
  node_id:
    name: "Location Name"
    definition: |
      [Description]
      Physical description of the place.
      [State Conditions]
      - If "lit" in status: The room is bright.
      - Default: Darkness surrounds you.
      [Interaction Rules]
      ## Examine the altar
      When player examines the altar:
      - Display: Ancient runes glow faintly...
      - Effect: {"type": "set_variable", "target": "altar_examined", "value": true}
    state: "Player-visible scene text. Use {action_id: link text} for clickable actions."
    state: "Hidden plot info the AI knows but player doesn't see"
    properties:
      status: []
    triggers: []    # lifecycle (pre_enter, post_enter, etc.) or condition-based
    objects:
      - id: object_ref  # references a global or inline object
    actions:
      - id: action_id
        text: "What the player can do"  # LLM matches player intent against this
        effects:
          - type: goto_node
            target: next_node
    is_ending: false  # true if this node concludes the game
```

If `state` is null and `definition` exists, the engine auto-generates an state via LLM on first visit.

**Hyperlink syntax** in state text:
- Action links: `{action_id: display text}`
- Object links: `{{object_id: display text}}`
- Character mentions: `{@character_id: display text}`

### Action Format

```yaml
actions:
  - id: unique_action_id        # REQUIRED
    text: "Description of action" # REQUIRED -- used for LLM intent matching
    intent: "Optional natural-language behavior"  # Preferred for Architect-driven behavior
    conditions: []               # optional
    effects:                     # optional structured mechanical hints / deterministic outcomes
      - type: goto_node
        target: destination
```

No `keywords` field needed -- the LLM handles intent matching from the `text` field.

Runtime note:
- Player input is resolved by the Architect, not by a generic action-effect runner in `GameKernel`.
- The Architect must express consequential state changes through `commit(state_changes=...)`.
- Use `intent` for open-ended authored behavior.
- Keep `effects` for authored mechanical intent that the Architect can translate into the correct state changes, especially for clear flows like navigation or form opening.

### Character Anatomy

```yaml
characters:
  - id: character_id
    name: "Character Name"
    is_playable: false
    definition: |
      [Identity]
      Role, appearance, background (2-3 sentences).
      [Personality & Speaking Style]
      Speech patterns, mannerisms (1-2 sentences).
      [Behavior Rules]
      ## Greeting
      When player greets:
      - Respond warmly, mention services
      - Effect: {"type": "set_variable", "target": "met_npc", "value": true}
      ## Ask about [topic]
      When player asks about topic:
      - Provide information in character voice
    state: "Current visible appearance"
    state: "Hidden knowledge"
    memory: []
    properties:
      location: location_id
      status: []
      inventory: []
      affinity: 50
```

### Effect Types (Common Authoring Vocabulary)

These effect types are still valid authoring shapes and still matter for validation, tooling, and existing stories. However, in the current runtime they are not a guarantee of direct execution by a generic effect engine.

Treat them as:
- structured mechanical intent for authors
- schema that stories and validators understand
- hints the Architect may map into `commit(state_changes=...)`

Special cases:
- `present_form` is still a direct runtime action the Architect can call
- form `on_submit.effects` are summarized for the Architect and then converted into one authoritative `commit`
- trigger `effects` are legacy in the current kernel; prefer `intent` on triggers

| Effect | Key Fields |
|--------|-----------|
| `display_text` | `text`, optional `speaker` |
| `goto_node` / `move_to_node` | `target` (node ID) |
| `set_variable` | `target` (var name), `value` |
| `modify_variable` / `calculate` | `target`, `operation` (add/subtract/multiply/divide/set), `value` |
| `random_number` | `target` (var name), `min_value`, `max_value` |
| `add_to_inventory` | `target` (item ID) |
| `remove_from_inventory` | `target` (item ID) |
| `drop_items` | `items` (list of item IDs) |
| `present_choice` | `text`, `choices` (array of `{text, effects}`) |
| `conditional` | `condition`, `if_effects`, `else_effects` |
| `for_each` | `array_variable`, `item_variable`, optional `index_variable`, `effects` |
| `dice_roll` | `dice` ("2d6"), `output_variable`, optional `target_number`, `bonus`, `success_effects`/`failure_effects` |
| `llm_generate` | `prompt`, `output_variable`, use `output_format: text` for narrative |
| `update_object_status` | `target`, `add_status`, `remove_status`, optional `regenerate_state: true` |
| `set_object_state` | `target`, `state` (or `value`) |
| `update_node_status` | `target`, `add_status`, `remove_status`, optional `regenerate_state: true` |
| `set_node_state` | `target`, `state` |
| `regenerate_node_state` | `target` |
| `present_form` | `form_id`, optional `prefill`, `on_submit_override` |
| `random_branch` | `branches` (array of `{weight, effects}`) |
| `generate_character` | `id`, `brief`, optional `hints`, `location` |
| `generate_object` | `id`, `brief`, optional `hints` |
| `set_controlled_character` | `target` (character ID) |
| `call_function` | `function` (function ID), `parameters` (dict) |
| `execute_script` | `script` (Lua code string) |
| `trigger_character_prompt` | `character_id`, `situation`, optional `context_vars` |
| `start_timed_event` | `id`, `duration`, `effects`, optional `response`/`message` |

Any individual effect can have an inline `conditions:` field for conditional execution.

For the full effects reference, read [prompts/node_format_description.md](prompts/node_format_description.md) Section 7.

### Triggers

Two categories:
- **Lifecycle triggers** (have `type` field): `pre_enter`, `post_enter`, `pre_leave`, `post_leave`, `game_start`
- **Condition-based triggers** (no `type`): fire when conditions become true after any state change

```yaml
triggers:
  - id: trigger_id
    type: post_enter          # omit for condition-based
    intent: "Optional natural-language behavior"
    conditions:
      - type: variable
        variable: has_key
        operator: eq           # eq, neq, gt, lt, gte, lte
        value: true
    effects:
      - type: display_text
        text: "The door swings open!"
```

Current runtime guidance:
- Prefer `intent` for authored trigger behavior.
- In the current kernel, trigger `effects` are treated as legacy and skipped rather than executed directly.
- If a trigger must cause player-visible or mechanical consequences, author it so the Architect can resolve it and record the result through `commit`.

Node-level triggers only fire while the player is in that node. Story-level triggers (at the root `triggers:` key) fire globally.

### Conditions

| Type | Fields | Purpose |
|------|--------|---------|
| `variable` | `variable`, `operator`, `value` | Check game variable (supports dot paths) |
| `compare` | `left`, `operator` (>=, <=, ==, !=), `right` | Compare with variable references |
| `inventory` | `operator` (has/not_has), `value` | Check player inventory |
| `object_status` | `target`, `value` (or legacy `state`) | Check if status tag exists |
| `stat` | `variable`, `operator`, `value` | Check character stat |
| `character` | `value` (character ID) | Check controlled character |
| `and` | `conditions` (nested list) | All sub-conditions must be true |
| `or` | `conditions` (nested list) | Any sub-condition must be true |

Variable condition operators: `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `contains`, `not_contains`, `exists`, `not_exists`.

Conditions can reference other variables in the `value` field: `"{$variable_name}"`.

---

## Critical Rules

These are the most common mistakes. **Always verify before saving:**

1. **Effect type field**: Use `type:`, never `effect:`
2. **Variable setting**: `set_variable` uses `target:` for the variable name, never `variable:`
3. **Arithmetic**: Use `modify_variable` with `operation: add`. Never use `set_variable` with expressions like `"{a} + {b}"` -- that stores the literal string
4. **Object references**: Use `- id: object_name`, never bare strings like `- object_name`
5. **Action fields**: Use `id` + `text`, never `name` or `description` for the display text
6. **Navigation**: `goto_node` uses `target:`, never `target_node:`
7. **LLM generation**: Use `output_format: text` for narrative prose. Omitting it uses JSON mode which produces garbage for prose
8. **Repeatable LLM actions**: Set `regenerate: true` on `llm_generate` for actions that should produce fresh content each time (gambling, shopping, etc.)
9. **Variable substitution**: Use `{variable_name}` in text, `{$variable_name}` for derived/computed variables
10. **YAML indentation**: Always use 2-space indentation consistently

---

## Editing Existing Stories

### Adding a Node

1. Add the node under `nodes:` with a unique key
2. Add navigation actions in neighboring nodes that `goto_node` to the new node
3. Add a return action in the new node pointing back
4. Reference any objects/characters by `id`

### Adding a Character

1. Add to the `characters:` list with all entity fields
2. Set `properties.location` to specify their authored starting node when needed
3. The Architect LLM will handle dialogue based on the character's `definition`

### Multi-File Stories

For large stories, use `includes:` to split into multiple files:

```yaml
# stories/my_story/main.yaml
id: my_story
name: "My Story"
start_node_id: intro
includes:
  - characters.yaml      # relative to main.yaml
  - nodes_area_one.yaml
  - nodes_area_two.yaml
initial_variables: {}
nodes:
  intro: ...             # nodes in main.yaml
```

Included files contribute their `nodes`, `characters`, `objects`, etc. into the main story. See [stories/age_of_fable/main.yaml](stories/age_of_fable/main.yaml) for a working example.

**Merge rules**: dict-keyed collections (`nodes`, `functions`, `forms`, `initial_variables`, `metadata`) merge by key. List collections (`characters`, `objects`, `triggers`, `actions`, `connections`) are appended. Scalar values from included files do not override the base file.

### Functions

Reusable authored effect sequences defined at the story root:

```yaml
functions:
  apply_damage:
    id: apply_damage
    parameters: [amount]
    effects:
      - type: modify_variable
        target: "players.{player_id}.character.stats.hp"
        operation: subtract
        value: "{$parameters.amount}"
```

Invoke via: `{ type: call_function, function: apply_damage, parameters: { amount: 10 } }`

Use this as story schema / authoring structure, especially when working with existing content. For new content, prefer patterns the current Architect runtime can faithfully translate into `commit(state_changes=...)`. See [stories/rubiks_nightmare.yaml](stories/rubiks_nightmare.yaml) for examples using `execute_script` with Lua.

### Player Character Defaults

Use `player_character_defaults` (Lua script or dict) to initialize per-player data when a new player joins:

```yaml
player_character_defaults: |
  return {
    position = { x = 0, y = 0 },
    stats = { hp = 100, mp = 50 }
  }
```

### Forms

Define forms at the story root and trigger them with `present_form`:

```yaml
forms:
  character_creation:
    title: "Create Your Character"
    fields:
      - id: player_name
        type: text
        label: "Name"
        required: true
      - id: player_class
        type: select
        label: "Class"
        options:
          - { value: warrior, text: "Warrior" }
          - { value: mage, text: "Mage" }
    on_submit:
      store_variables:
        - field: "player_name"
          to: "players.{player_id}.character.name"
      effects:
        - type: goto_node
          target: game_start
```

Trigger with: `- type: present_form` / `form_id: character_creation`

Runtime note:
- `present_form` remains a first-class runtime operation.
- On submission, `store_variables`, optional LLM processing, and optional Lua script run first.
- `on_submit.effects` are then treated as authoritative writer intent and summarized for the Architect.
- The Architect should convert the resulting mechanical changes into one `commit(state_changes=...)` rather than relying on a generic direct effect runner.

For full form docs, read [prompts/story_format_description.md](prompts/story_format_description.md) Section 9.

---

### Custom Frontend (Story App)

Stories can replace the default text-based chat UI with a sandboxed custom frontend. The story ships its own HTML/CSS/JS in a `frontend/` directory, and the engine loads it in an iframe.

**Directory structure:**

```
stories/my_story/
  main.yaml
  frontend/
    index.html    # entry point
    app.js        # application logic
    style.css     # styling
    images/       # static assets (images, fonts, etc.)
```

**YAML frontend config:**

```yaml
frontend:
  app:
    mode: sandboxed_app
    app_root: frontend        # directory relative to main.yaml
    entry: index.html         # entry file within app_root
    sandbox:
      - allow-scripts
      - allow-same-origin
    client_type: story_app    # tells the engine this is a custom UI client
    capabilities:             # what interaction types the frontend uses
      - local_state           # purely client-side state (no backend)
      - ui_query              # read-only queries to backend
      - deterministic_action  # direct state patches (merge_patch)
      - architect_action      # LLM-powered Architect tasks
```

**Frontend SDK:**

The story app communicates with the engine via `WenyooStorySDK`:

```html
<script src="/static/js/wenyoo-story-sdk.js"></script>
<script>
  const bridge = WenyooStorySDK.createBridge();

  // Listen for events
  bridge.on("game_start", (msg) => { /* initialize UI */ });
  bridge.on("game_state", (msg) => { /* update from state changes */ });
  bridge.on("command_result", (msg) => { /* handle Architect responses */ });

  // Request initial state
  bridge.requestInitialState();

  // Send an Architect task (LLM-powered)
  bridge.sendArchitectTask("character_interaction", {
    action_id: "chat_sophie",
    player_input: "Hello!",
    purpose: "Role-play Sophie's reply to the player's message.",
    structured_input: { target_character: "sophie", message_text: "Hello!" },
    extra_context: { input_type: "story_app" },
  });

  // Direct state mutation (no LLM)
  bridge.sendDeterministicAction("merge_patch", {
    patch: {
      variables: { player_coins: 100 },
      timed_events: [{
        id: "delivery_123",
        event_type: "gift_delivery",
        delay_seconds: 120,
        player_id: playerId,
        event_context: "A gift has arrived. Update affection and react.",
      }],
    },
  }, { display_text: "Bought a gift" });

  // Read-only query
  bridge.query("object_actions", { object_id: "signal_core" });

  // Return to story selection
  bridge.requestReturnToMenu();
</script>
```

**Three interaction tiers:**

| Tier | Method | Touches Architect? | Use case |
|------|--------|-------------------|----------|
| Local-only | Client JS, no bridge call | No | UI navigation, animations, local notes |
| Direct mutation | `bridge.sendDeterministicAction("merge_patch", ...)` | No | Currency deduction, scheduling timed events |
| Reasoned interaction | `bridge.sendArchitectTask(taskType, options)` | Yes | NPC chat, world queries, story progression |

**Timed events from frontend:**

Story apps can schedule timed events via merge_patch. Include `delay_seconds` and a detailed `event_context` that tells the Architect what to do when the event fires:

```js
bridge.sendDeterministicAction("merge_patch", {
  patch: {
    timed_events: [{
      id: "gift_delivery_sophie_" + Date.now(),
      event_type: "gift_delivery",
      delay_seconds: 120,
      player_id: playerId,     // capture from game_state.player_state.player_id
      object_id: "tea_set",
      scope: "player",
      audience: "self",
      event_context:
        "A Tea Set has been delivered to Sophie. " +
        "Check Sophie's gift_preferences. If the gift is in 'likes', " +
        "increase affection by 8-12. Update state_changes accordingly " +
        "and send an in-character reaction as a narrative artifact.",
    }],
  },
});
```

**Static assets:**

All files under `frontend/` are served at `/story-apps/{story_id}/{path}`. Use relative paths in HTML (`./images/bg.png`, `./lib/three.min.js`). The engine prevents path traversal outside the `frontend/` directory.

**Game state access:**

The `game_state` dict sent to clients includes `character_states` with all properties (affection, chat_history, inventory, etc.), `variables`, and `nodes`. The frontend reads these to render its UI.

**Design guidelines for story app stories:**

- Keep one node (the "virtual space") since the UI handles all navigation
- Put world rules in `lore_*` variables so the Architect has context
- Use `character.definition` with detailed behavior rules and `##` sections
- Store per-character dynamic data in `character.properties` (affection, chat_history, gift_preferences, etc.)
- Use `event_context` on timed events to give the Architect clear instructions
- The Architect uses `commit(artifacts=[...], state_changes={...})` to respond — narrative artifacts for player-facing text, structured artifacts for data, and state_changes for world mutations

**Reference example:** See [stories/phone_dating_sim/](stories/phone_dating_sim/) for a complete story app with chat, e-commerce, timed gift delivery, and affection system.

---

## Story Patterns

For examples of different story architectures (linear, hub-and-spoke, puzzle-driven, AI-native sandbox), see [story-patterns.md](story-patterns.md).

---

## Deep References

Read these files for comprehensive documentation when needed:

- **Full story YAML format** -- [prompts/story_format_description.md](prompts/story_format_description.md)
- **All effects, triggers, conditions** -- [prompts/node_format_description.md](prompts/node_format_description.md)
- **Architect runtime behavior** -- [prompts/architect_system.txt](prompts/architect_system.txt) (this is the source of truth for how authored rules become `commit(...)` and `present_form(...)` calls at runtime)
- **Example stories** -- browse `stories/` for working references
- **Validation checklist** -- [validation-checklist.md](validation-checklist.md)
