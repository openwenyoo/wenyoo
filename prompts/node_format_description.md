# Wenyoo: Node, Action, Trigger, and Effect Guide

This document describes the current authored format for nodes and node-level behavior. For top-level story structure, forms, includes, and status display, see `story_format_description.md`.

---

## 1. Canonical Authoring Rules

Use these shapes in new authored YAML:

### Effects

Always use `type`:

```yaml
effects:
  - type: display_text
    text: "Hello"
```

### Variable mutation

Use `target` for the variable path:

```yaml
- type: set_variable
  target: has_key
  value: true
```

### Navigation

Use `target`, not `target_node`:

```yaml
- type: goto_node
  target: temple_hall
```

### Node object references

Use object refs as objects, not bare strings:

```yaml
objects:
  - id: notice_board
  - id: fountain
```

### Actions

Use `text`, not `name`, for the player-facing action text:

```yaml
actions:
  - id: examine_board
    text: "Read the notice board"
    effects:
      - type: display_text
        text: "Most of the notices are old, but one is fresh."
```

### Node depiction

Prefer `explicit_state` in authored nodes. `description` is legacy compatibility, not the canonical field for new content.

---

## 2. Nodes (`nodes`)

Nodes represent places, scenes, or states in the story graph.

Canonical node structure:

```yaml
nodes:
  node_id_here:
    name: "Human-Readable Node Name"
    definition: |
      【Description】
      A rain-swept stone courtyard lit by paper lanterns.

      【Interaction Rules】
      ## Examine the gate
      When the player examines the gate:
      - Display: The wood is swollen from the rain, but not rotten.
    explicit_state: "Rain beads on the lantern frames as the courtyard lies silent."
    implicit_state: "A guard is watching from the upper balcony"
    hints: |
      Keep social interactions tense and formal here.
    properties:
      status: []
      visit_count: 0
    objects:
      - id: front_gate
    actions:
      - id: knock_on_gate
        text: "Knock on the gate"
        effects:
          - type: display_text
            text: "Your knuckles echo against wet wood."
    triggers: []
    is_ending: false
```

### Node fields

| Field | Purpose |
|-------|---------|
| `name` | human-readable node name |
| `definition` | static lore, rules, and authored interaction guidance |
| `explicit_state` | mutable visible baseline / compatibility field |
| `implicit_state` | hidden runtime context / compatibility field |
| `hints` | free-form Architect guidance that belongs with the node |
| `properties` | mechanical state such as `status`, `visit_count`, and custom data |
| `objects` | object refs or inline object definitions present in the node |
| `actions` | player actions available in the node |
| `triggers` | automatic behavior |
| `is_ending` | whether the node concludes the story |

### Notes on authored content

- `definition` is the best place for scene rules, catalogs, pricing tables, and structured interaction guidance.
- `explicit_state` can be blank or omitted, but new authored content should still treat it as the canonical node depiction field.
- Prefer changing underlying state first; use depiction-mutation effects only when you specifically need them.

---

## 3. Hyperlink Syntax

Narrative text can include clickable references:

- Action link: `{action_id: display text}`
- Object link: `{{object_id: display text}}`
- Character mention: `{@character_id: display text}`

Example:

```yaml
explicit_state: |
  The tavern is loud and warm. You could {order_drink: order a drink},
  {speak_to_barkeep: speak with the barkeep}, or inspect
  {{old_poster: the torn poster}} by the hearth.
```

Rules:

- Action IDs must exist in the node's `actions`
- Use hyperlinks when you want narrative text to double as affordance text
- Double braces are only for objects

---

## 4. Triggers (`triggers`)

Triggers are automatic behaviors. They can be:

- lifecycle triggers: use `type`
- condition-based triggers: omit `type`, rely on `conditions`

Canonical trigger:

```yaml
triggers:
  - id: temple_entry_blessing
    type: post_enter
    conditions:
      - type: variable
        variable: blessed
        operator: eq
        value: true
    effects:
      - type: display_text
        text: "A warmth moves through your chest as you cross the threshold."
```

### Lifecycle trigger types

| Type | Meaning |
|------|---------|
| `pre_enter` | before entering the node |
| `post_enter` | after entering the node |
| `pre_leave` | before leaving the current node |
| `post_leave` | after leaving the node |

### Intent-based triggers

Triggers can also use `intent` for Architect-driven behavior:

```yaml
triggers:
  - id: first_market_impression
    type: post_enter
    intent: "Briefly narrate the market's mood the first time the player arrives."
```

If `intent` is present, keep `effects` minimal or omit them when the behavior is meant to be Architect-authored rather than fully scripted.

---

## 5. Objects in Nodes (`objects`)

Node `objects` may contain either references or inline definitions.

### Reference form

```yaml
objects:
  - id: fountain
  - id: notice_board
```

### Inline definition form

```yaml
objects:
  - id: large_desk
    name: "Large Desk"
    definition: |
      【Description】
      A heavy oak desk covered in papers and candle wax.

      【Interaction Rules】
      ## Search the desk
      When player searches the desk:
      - Display: You find a tarnished key in the bottom drawer.
      - Effect: {"type": "add_to_inventory", "target": "tarnished_key"}
      - Effect: {"type": "update_object_status", "target": "large_desk", "add_status": ["searched"]}
    explicit_state: "A large oak desk sits beneath the shuttered window."
    implicit_state: "Contains a tarnished key in the bottom drawer"
    properties:
      status: []
```

Object fields match the story-level object model:

- `id`
- `name`
- `definition`
- `explicit_state`
- `implicit_state`
- `properties`

---

## 6. Actions (`actions`)

Actions are the authored affordances the player can invoke from a node.

Canonical action:

```yaml
actions:
  - id: open_gate
    text: "Push the gate open"
    conditions:
      - type: object_status
        target: front_gate
        value: unlocked
    effects:
      - type: goto_node
        target: inner_courtyard
```

### Action fields

| Field | Purpose |
|-------|---------|
| `id` | unique action identifier |
| `text` | player-facing action phrasing used for matching |
| `description` | legacy alias; new content should use `text` |
| `intent` | natural-language behavior handled by the Architect |
| `conditions` | availability rules |
| `effects` | structured deterministic outcomes |
| `feedback` | optional categorized responses |

### Intent-based actions

When authored behavior is too open-ended for a small effect list, use `intent`:

```yaml
actions:
  - id: haggle_with_merchant
    text: "Try to haggle with the merchant"
    intent: "Resolve bargaining with tone, consequences, and price movement based on the player's approach."
```

If `intent` is present, `effects` may be omitted.

---

## 7. Effects (`effects`)

Effects are the structured way to change state, display text, or branch the story.

### General rules

- Every effect must have `type`
- Use `target` for the main thing being affected
- Use `value` for the main value being written or applied
- An individual effect may also have its own `conditions`

---

### 7.1 Text and presentation

#### `display_text`

```yaml
- type: display_text
  text: "The room falls silent."
  speaker: "Narrator"
```

#### `present_choice`

```yaml
- type: present_choice
  text: "What do you do?"
  choices:
    - text: "Step inside"
      effects:
        - type: goto_node
          target: foyer
    - text: "Back away"
      effects:
        - type: display_text
          text: "You decide caution is the wiser path."
```

#### `present_form`

```yaml
- type: present_form
  form_id: character_creation
  prefill:
    player_name: "{$suggested_name}"
```

Forms are defined at story root. See `story_format_description.md`.

---

### 7.2 Variables and math

#### `set_variable`

```yaml
- type: set_variable
  target: quest_started
  value: true
```

Do not use arithmetic expressions inside `set_variable`. It stores literals.

#### `modify_variable`

```yaml
- type: modify_variable
  target: gold
  operation: subtract
  value: 3
```

Supported operations:

- `add`
- `subtract`
- `multiply`
- `divide`
- `set`

#### `calculate`

Legacy variable math shape:

```yaml
- type: calculate
  target: sanity
  operation: subtract
  value: 10
```

#### `random_number`

```yaml
- type: random_number
  target: dice_result
  min_value: 1
  max_value: 6
```

---

### 7.3 Navigation and flow

#### `goto_node`

Moves directly to a node.

```yaml
- type: goto_node
  target: alleyway
```

#### `move_to_node`

Movement path that preserves transition semantics and trigger execution.

```yaml
- type: move_to_node
  target: alleyway
```

#### `random_branch`

```yaml
- type: random_branch
  branches:
    - weight: 1
      effects:
        - type: display_text
          text: "You find a silver ring."
    - weight: 3
      effects:
        - type: display_text
          text: "Your search turns up nothing."
```

#### `conditional`

```yaml
- type: conditional
  condition:
    type: variable
    variable: has_key
    operator: eq
    value: true
  if_effects:
    - type: goto_node
      target: vault
  else_effects:
    - type: display_text
      text: "The vault remains locked."
```

#### `for_each`

```yaml
- type: for_each
  array_variable: inventory_items
  item_variable: current_item
  index_variable: item_index
  effects:
    - type: display_text
      text: "Item {item_index}: {current_item}"
```

---

### 7.4 Inventory and ownership

#### `add_to_inventory`

```yaml
- type: add_to_inventory
  target: rusty_key
```

#### `remove_from_inventory`

```yaml
- type: remove_from_inventory
  target: rusty_key
```

#### `drop_items`

```yaml
- type: drop_items
  items: [gold_coin, potion]
```

---

### 7.5 Object, node, and character state

#### `update_object_status`

```yaml
- type: update_object_status
  target: front_gate
  add_status: [open]
  remove_status: [closed, locked]
  regenerate_explicit_state: true
```

#### `set_object_explicit_state`

Use when you explicitly want to overwrite an object's visible depiction:

```yaml
- type: set_object_explicit_state
  target: front_gate
  explicit_state: "The gate stands open, rainwater dripping from its iron bars."
```

#### `set_node_description`

Legacy/compatibility effect for directly updating a node's depiction:

```yaml
- type: set_node_description
  target: temple_hall
  value: "The hall is now lit by a pale green flame."
```

#### `set_node_explicit_state`

Canonical explicit-state mutation shape when supported by your authored flow:

```yaml
- type: set_node_explicit_state
  target: temple_hall
  explicit_state: "The hall is now lit by a pale green flame."
```

#### `update_node_status`

```yaml
- type: update_node_status
  target: temple_hall
  add_status: [ritual_active]
  remove_status: [silent]
  regenerate_explicit_state: true
```

#### `regenerate_node_explicit_state`

```yaml
- type: regenerate_node_explicit_state
  target: temple_hall
```

#### `set_controlled_character`

```yaml
- type: set_controlled_character
  target: "{player_class}"
```

---

### 7.6 Dice, generation, and scripts

#### `dice_roll`

```yaml
- type: dice_roll
  dice: "2d6"
  output_variable: _roll
  target_number: 12
  bonus: 2
  success_effects:
    - type: display_text
      text: "Success!"
  failure_effects:
    - type: display_text
      text: "Failure."
```

#### `llm_generate`

```yaml
- type: llm_generate
  prompt: |
    Describe the eerie mood of the chapel in 2-3 sentences.
  output_variable: chapel_mood
  output_format: text
  regenerate: true
```

Use `output_format: text` for narrative prose.

#### `generate_character`

```yaml
- type: generate_character
  id: mysterious_stranger
  brief: "A hooded traveler who knows the ruins better than they admit."
  hints:
    - "Speaks in riddles"
    - "Avoids giving direct answers"
  location: village_square
```

#### `execute_script`

```yaml
- type: execute_script
  script: |
    local hp = game:get_variable("player.properties.stats.hp")
    game:set_variable("player.properties.stats.hp", hp + 10)
```

#### `execute_script_async`

```yaml
- type: execute_script_async
  script: |
    game:display_text("The background ritual completes.")
```

---

## 8. Conditions

Conditions control action availability, trigger activation, and per-effect execution.

### Variable condition

```yaml
- type: variable
  variable: has_key
  operator: eq
  value: true
```

Supported variable operators include:

- `eq`
- `neq`
- `gt`
- `lt`
- `gte`
- `lte`
- `contains`
- `not_contains`
- `exists`
- `not_exists`

### Compare condition

```yaml
- type: compare
  left: "{gold}"
  operator: ">="
  right: 12
```

Also supports `==`, `!=`, `<`, `>`, `<=`, `>=` and word-form equivalents.

### Inventory condition

```yaml
- type: inventory
  operator: has
  value: rusty_key
```

Operators:

- `has`
- `not_has`

### Object status condition

```yaml
- type: object_status
  target: front_gate
  value: open
```

`state` may also appear in compatibility content; new authored content should prefer `value`.

### Stat condition

```yaml
- type: stat
  variable: strength
  operator: gte
  value: 12
```

### Character condition

```yaml
- type: character
  value: player_knight
```

### Compound conditions

```yaml
- type: and
  conditions:
    - type: variable
      variable: has_key
      operator: eq
      value: true
    - type: inventory
      operator: has
      value: torch
```

Use `type: or` for alternatives.

### Effect-level conditions

Any effect can include its own `conditions`:

```yaml
effects:
  - type: display_text
    text: "The lock clicks open."
    conditions:
      - type: inventory
        operator: has
        value: bronze_key
```

---

## 9. Quick Reference

### Preferred field naming

- `type`: effect/condition type
- `target`: main thing being affected
- `value`: main literal value being compared or written
- `text`: player-facing text

### Common compatibility aliases you may still see

- action `description` -> treated as `text`
- node `description` -> legacy depiction alias
- `target_node` -> legacy `goto_node` target
- `variable` on `set_variable` -> legacy alias for `target`

New authored content should not introduce those aliases.

---

## 10. Validation Checklist

- [ ] Nodes use `explicit_state` instead of authored `description`
- [ ] Actions have `id` and `text`
- [ ] Open-ended authored behavior uses `intent` where appropriate
- [ ] Object references use `- id: object_id`
- [ ] Effects use `type`
- [ ] `set_variable` uses `target`
- [ ] `goto_node` uses `target`
- [ ] Arithmetic uses `modify_variable` or `calculate`, not string math in `set_variable`
- [ ] Narrative `llm_generate` uses `output_format: text`
- [ ] `present_form` references a form defined at story root
- [ ] All node, object, and character IDs referenced by effects actually exist
