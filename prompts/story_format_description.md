# Wenyoo: Story YAML Format Guide

This document describes the current authored story format for the engine. Use it for story-level structure: metadata, includes, characters, objects, global actions/triggers, status display, and forms.

> **For node/action/effect details, see `node_format_description.md`.**

---

## 1. Canonical Top-Level Structure

The engine loads a story into the `Story` model. The canonical authored shape is:

```yaml
id: unique_story_id                 # Required
name: "Story Name"                  # Required, canonical display name
title: "Optional Alternate Title"   # Optional compatibility/display field
description: "Short summary"        # Optional but strongly recommended
author: "Author Name"               # Optional
version: "1.0"                      # Optional
genre: "Open-world fantasy RPG"     # Optional
start_node_id: intro                # Required

# Optional modular includes
includes:
  - nodes_town.yaml
  - characters.yaml

# Optional story-wide data and behavior
initial_variables: {}
characters: []
objects: []
actions: []
triggers: []
functions: {}
forms: {}
status_display_config: {}
player_character_defaults: {}
metadata: {}

# Required
nodes:
  intro:
    name: "Intro"
    explicit_state: "You arrive at the city gates."
    actions: []
```

### Required fields

- `id`
- `name`
- `start_node_id`
- `nodes`

### Important notes

- `name` is the canonical story name. The loader will fall back from `title` if needed, but new content should provide `name`.
- `nodes` is a mapping from `node_id` to node data, not a list.
- `title` is optional. Keep it in sync with `name` if you use both.
- Unknown extra top-level keys can exist in YAML, but they are not part of the documented authored schema.

---

## 2. Modular Stories With `includes`

YAML stories can be split across multiple files. The main file may declare:

```yaml
includes:
  - nodes_city.yaml
  - nodes_forest.yaml
  - characters_and_objects.yaml
```

Included files are merged into the base story with these rules:

- Dict sections are merged by key: `nodes`, `functions`, `forms`, `initial_variables`, `metadata`
- List sections are appended: `characters`, `objects`, `triggers`, `actions`
- Scalar values from included files do not override values already defined in the main file

Use `includes` when the story is large or when you want to separate nodes, characters, encounter templates, or forms into focused files.

---

## 3. Initial Variables (`initial_variables`)

Use `initial_variables` for persistent story state, counters, flags, lorebook text, and computed values.

```yaml
initial_variables:
  sanity: 100
  gold: 12
  met_guardian: false

  lore_writing_style: |
    Write in second person, present tense.
    Keep descriptions vivid but concise.
```

### Variable substitution

- In text: `{variable_name}`
- In variable-path contexts: `{$variable_name}`

Examples:

```yaml
- type: display_text
  text: "You now have {gold} coins."
```

```yaml
status_display_config:
  stats:
    - label: "Gold"
      format: "{gold}"
      values:
        gold: "{$gold}"
```

### Derived variables with `$lua:`

Derived variables are computed dynamically via Lua expressions:

```yaml
initial_variables:
  base_attack: 10
  weapon_bonus: 3
  strength: 14
  effective_attack: "$lua: base_attack + weapon_bonus + math.floor(strength / 2)"
```

Available in expressions include:

- other variables
- `player_id`
- `player_character`
- `player_stats`
- Lua `math`

Avoid circular dependencies between derived variables.

---

## 4. Characters (`characters`)

Characters use the DSPP-style entity model:

- `definition`: static identity, behavior rules, and lore
- `explicit_state`: mutable visible baseline / compatibility field
- `implicit_state`: hidden runtime context / compatibility field
- `memory`: accumulated interaction history
- `properties`: mechanical state such as `location`, `status`, `inventory`, `stats`, `affinity`

### Playable character example

```yaml
characters:
  - id: player_knight
    name: "Brave Knight"
    is_playable: true
    definition: |
      A disciplined knight from the northern kingdoms.
    explicit_state: "A knight in polished armor stands ready."
    implicit_state: ""
    memory: []
    properties:
      location: town_square
      status: []
      inventory: [iron_sword, bread]
      stats:
        hp: 100
        max_hp: 100
        strength: 15
```

### NPC example

```yaml
characters:
  - id: forest_hermit
    name: "Forest Hermit"
    definition: |
      【Identity】
      An old hermit who knows the forest's hidden paths.

      【Behavior Rules】
      ## Greeting
      When the player greets you:
      - Respond warmly
      - Effect: {"type": "set_variable", "target": "met_hermit", "value": true}
    explicit_state: "An old hermit sits beside a mossy stump."
    implicit_state: "Knows where the silver key is hidden"
    memory: []
    properties:
      location: hidden_grove
      status: []
      inventory: [ancient_map]
      affinity: 50
```

Authored starting location belongs in `properties.location`.

---

## 5. Objects (`objects`)

Global objects live at the story root. Node-local object references and inline object definitions are described in `node_format_description.md`.

Object fields:

- `id`
- `name`
- `definition`
- `explicit_state`
- `implicit_state`
- `properties`

Example:

```yaml
objects:
  - id: rusty_key
    name: "Rusty Key"
    definition: |
      An old iron key with deep rust along the teeth.
    explicit_state: "A rusty key lies half-buried in the dust."
    implicit_state: ""
    properties:
      status: []
```

Interactive object definitions can embed behavior rules for the Architect:

```yaml
objects:
  - id: stone_well
    name: "Stone Well"
    definition: |
      【Description】
      An ancient stone well covered in moss and creeping vines.

      【Interaction Rules】
      ## Examine the well
      When player examines the well:
      - Display: You peer down and spot {{silver_key: a silver key}} at the bottom.
      - Effect: {"type": "set_variable", "target": "well_examined", "value": true}
    explicit_state: "An old stone well stands in the clearing."
    implicit_state: "Contains the silver key needed for the cave door"
    properties:
      status: []
      contains: [silver_key]
```

Timed behavior should be authored in `definition`, not in a separate object
schema field. If an object automatically changes after a delay, describe that
rule clearly in prose so the Architect can reason about it and schedule a
future `timed_event`.

Concrete example: auto-return lever in Relay Gallery

```yaml
objects:
  - id: relay_lever
    name: "Relay Lever"
    definition: |
      【Description】
      A heavy brass lever wired into the relay gate controls.

      【Behavior Rules】
      Pulling the lever energizes the relay path.

      【Timed Rules】
      If the lever is left on, it automatically snaps back to off after 15 seconds.
      Anyone in Relay Gallery should notice the reset.
    explicit_state: "The lever rests in the off position."
    implicit_state: ""
    properties:
      status: []
      switch_state: off
```

Authoring tip:

- Put the full timed rule in `definition`. The Architect should handle the
  reasoning, while the engine only stores and fires the scheduled event later.

---

## 6. Nodes (`nodes`)

Nodes are the required backbone of every story.

> **See `node_format_description.md` for the full node/action/trigger/effect reference.**

Minimal node example:

```yaml
nodes:
  town_square:
    name: "Town Square"
    definition: |
      The busy commercial heart of the city.
    explicit_state: "Merchants shout over one another in the crowded square."
    implicit_state: ""
    properties:
      status: []
      visit_count: 0
    objects:
      - id: notice_board
    actions:
      - id: go_to_inn
        text: "Head to the inn"
        effects:
          - type: goto_node
            target: crooked_inn
    triggers: []
```

Use `explicit_state`, not legacy node `description`, in new authored content.

---

## 7. Story-Level Actions, Triggers, and Functions

### Global actions (`actions`)

Stories may define root-level actions that can be resolved outside a specific node:

```yaml
actions:
  - id: check_journal
    text: "Review your journal"
    intent: "Summarize the player's active quests and recent discoveries."
```

### Global triggers (`triggers`)

Story-level triggers are checked regardless of the current node:

```yaml
triggers:
  - id: sanity_break
    conditions:
      - type: variable
        variable: sanity
        operator: lte
        value: 0
    effects:
      - type: goto_node
        target: game_over_insanity
```

### Reusable functions (`functions`)

Reusable effect sequences can be defined at story level. Dict form is preferred:

```yaml
functions:
  heal_player:
    parameters: [amount]
    effects:
      - type: modify_variable
        target: player.properties.stats.hp
        operation: add
        value: "{parameters.amount}"
```

List form is also accepted by the loader:

```yaml
functions:
  - id: heal_player
    parameters: [amount]
    effects: []
```

---

## 8. Player Defaults (`player_character_defaults`)

`player_character_defaults` lets you seed newly created player-character data. It can be a dict or a Lua snippet, depending on your story's needs.

Example dict:

```yaml
player_character_defaults:
  stats:
    hp: 100
    max_hp: 100
  inventory: []
```

Example Lua:

```yaml
player_character_defaults: |
  return {
    position = { x = 0, y = 0, z = 0 },
    facing = { axis = "X", sign = 1 }
  }
```

---

## 9. Status Display Configuration (`status_display_config`)

Use `status_display_config` to populate the player's status/details panel.

### Template only

```yaml
status_display_config:
  template: rpg_basic
```

### Custom stats

```yaml
status_display_config:
  stats:
    - label: "HP"
      format: "{hp}/{max_hp}"
      values:
        hp: "{$players.{player_id}.character.stats.hp}"
        max_hp: "{$players.{player_id}.character.stats.max_hp}"
    - label: "Gold"
      format: "{gold}"
      values:
        gold: "{$gold}"
```

### Template plus overrides

```yaml
status_display_config:
  template: rpg_basic
  stats_override:
    - label: "HP"
      format: "{hp} HP"
      values:
        hp: "{$players.{player_id}.character.stats.hp}"
  stats:
    - label: "Sanity"
      format: "{sanity}/100"
      values:
        sanity: "{$sanity}"
```

Each item uses:

- `label`
- `format`
- `values`

`{player_id}` inside value paths is replaced automatically at runtime.

---

## 10. Forms (`forms`)

Forms collect structured player input. They are defined at the story root and presented via the `present_form` effect or Architect tool flow.

### Basic form

```yaml
forms:
  character_creation:
    title: "Create Your Character"
    description: "Tell us who you are."
    submit_text: "Create Character"
    fields:
      - id: player_name
        type: text
        label: "Character Name"
        required: true
        placeholder: "Enter your name"
      - id: player_class
        type: select
        label: "Class"
        required: true
        options:
          - { value: warrior, text: "Warrior" }
          - { value: mage, text: "Mage" }
    on_submit:
      store_variables:
        - field: player_name
          to: "players.{player_id}.character.name"
        - field: player_class
          to: "players.{player_id}.character.class"
      effects:
        - type: display_text
          text: "Welcome, {$form.player_name}!"
        - type: goto_node
          target: game_start
```

### Supported field types

| Type | Notes |
|------|-------|
| `text` | single-line text |
| `textarea` | multiline text |
| `number` | numeric input |
| `select` | dropdown |
| `multiselect` | multi-select dropdown |
| `radio` | radio buttons |
| `checkbox` | single boolean |
| `checkboxgroup` | multiple checkboxes, returns array |
| `slider` | range input |
| `rating` | star/rating input |
| `file` | file upload with optional text extraction |
| `date` | date input |
| `time` | time input |
| `hidden` | hidden value |

### Validation

```yaml
fields:
  - id: username
    type: text
    label: "Username"
    required: true
    validation:
      min_length: 3
      max_length: 20
      pattern: "^[a-zA-Z0-9_]+$"
      pattern_error: "Only letters, numbers, and underscores allowed"

  - id: age
    type: number
    label: "Age"
    validation:
      min: 18
      max: 120
      integer_only: true
```

### Conditional fields with `show_if`

Client-side field dependency:

```yaml
show_if:
  field: has_magic
  operator: eq
  value: true
```

Server-side game-state dependency:

```yaml
show_if:
  variable: player.properties.background
  operator: exists
```

Supported operators include:

- `eq`
- `ne`
- `gt`
- `lt`
- `gte`
- `lte`
- `contains`
- `in`
- `exists`
- `not_exists`

### `on_submit`

`on_submit` may contain:

- `store_variables`
- `llm_process`
- `script`
- `effects`

Example:

```yaml
on_submit:
  store_variables:
    - field: background
      to: "players.{player_id}.character.background"
    - field: "*"
      to: "last_form_data"
  llm_process:
    prompt: |
      Analyze this background: {$form.background}
    parse_as: text
    store_to: "players.{player_id}.analysis"
  script: |
    local name = game:get_variable("form.player_name")
    game:display_text("Processing " .. name .. "...")
  effects:
    - type: goto_node
      target: next_scene
```

### File fields

The backend validates `accept` against MIME types, so prefer MIME strings:

```yaml
fields:
  - id: notes_file
    type: file
    label: "Upload notes"
    accept: ["text/plain", "text/markdown", "application/pdf", "application/json", "text/csv"]
    max_size_mb: 5
    extract_text: true
    max_text_length: 10000
```

Uploaded file fields store extracted text, not raw file bytes, when `extract_text` is enabled.

### Presenting a form

```yaml
actions:
  - id: create_character
    text: "Create your character"
    effects:
      - type: present_form
        form_id: character_creation
        prefill:
          player_name: "{$suggested_name}"
```

Submitted values are available as `{$form.field_id}` during post-submit processing.

---

## 11. Compact Story Example

```yaml
id: haunted_mansion
name: "Haunted Mansion"
title: "Haunted Mansion"
description: "Explore a decaying estate and uncover what still walks its halls."
author: "Game Author"
version: "1.0"
genre: "gothic horror mystery"
start_node_id: mansion_gate

initial_variables:
  sanity: 100
  has_flashlight: false
  lore_writing_style: |
    Gothic horror. Second person. Focus on atmosphere and dread.

characters:
  - id: investigator
    name: "Investigator"
    is_playable: true
    definition: "A determined investigator of the occult."
    explicit_state: "A wary figure clutching a notebook."
    implicit_state: ""
    memory: []
    properties:
      location: mansion_gate
      status: []
      inventory: []
      stats:
        hp: 100
        max_hp: 100

objects:
  - id: flashlight
    name: "Flashlight"
    definition: "A sturdy metal flashlight."
    explicit_state: "A flashlight lies in the weeds."
    implicit_state: ""
    properties:
      status: []

nodes:
  mansion_gate:
    name: "Mansion Gate"
    definition: |
      Rusted iron gates stand before a looming Victorian manor.
    explicit_state: "The iron gate hangs crooked as fog curls through the garden."
    implicit_state: ""
    properties:
      status: []
      visit_count: 0
    objects:
      - id: flashlight
    actions:
      - id: enter_mansion
        text: "Push through the gate"
        effects:
          - type: goto_node
            target: main_hall
    triggers: []

  main_hall:
    name: "Main Hall"
    definition: "A vast entrance hall lined with portraits."
    explicit_state: "Dusty portraits stare down from the walls of the hall."
    implicit_state: ""
    properties:
      status: []
      visit_count: 0
    actions: []
    triggers: []
```

---

## 12. Validation Checklist

- [ ] Story has `id`, `name`, `start_node_id`, and `nodes`
- [ ] `start_node_id` points to an existing node
- [ ] Node IDs are unique and snake_case
- [ ] New authored nodes use `explicit_state`, not legacy `description`
- [ ] Effects use `type`
- [ ] `set_variable` uses `target`, not `variable`
- [ ] `goto_node` uses `target`, not `target_node`
- [ ] Forms use `store_variables.field`, not `from`
- [ ] Form regex errors use `pattern_error`, not `pattern_message`
- [ ] File field `accept` values are MIME types
- [ ] All referenced nodes, objects, forms, and variables exist

---

## 13. Related Docs

- `node_format_description.md` for nodes, actions, triggers, conditions, and effects
