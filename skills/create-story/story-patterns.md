# Story Architecture Patterns

## 1. Linear Narrative (Escape Room / Sequential)

Best for: short puzzle games, escape rooms, tutorials.

Nodes form a chain. The player progresses through scenes in order, gated by puzzles or item collection.

```yaml
id: escape_room
name: "The Locked Lab"
start_node_id: cell
initial_variables:
  sanity: 100

objects:
  - id: rusty_key
    name: "Rusty Key"
    definition: "A corroded key found behind the painting."
    explicit_state: "A rusty key."
    properties: { status: [] }

nodes:
  cell:
    name: "Locked Cell"
    explicit_state: "A cold cell. A {examine_painting: painting} hangs on the wall. The {door: door} is locked."
    objects:
      - id: rusty_key
    actions:
      - id: examine_painting
        text: "Examine the painting"
        effects:
          - type: display_text
            text: "Behind the painting you find a rusty key!"
          - type: add_to_inventory
            target: rusty_key
      - id: unlock_door
        text: "Unlock the door"
        conditions:
          - type: inventory
            operator: has
            value: rusty_key
        effects:
          - type: goto_node
            target: hallway

  hallway:
    name: "Hallway"
    explicit_state: "A dim corridor stretches ahead..."
    actions:
      - id: go_forward
        text: "Continue down the hallway"
        effects:
          - type: goto_node
            target: exit
      - id: go_back
        text: "Go back to the cell"
        effects:
          - type: goto_node
            target: cell

  exit:
    name: "Freedom"
    explicit_state: "Daylight floods in. You've escaped!"
    is_ending: true
```

**Key traits**: Few nodes, item-gated progression, clear win state with `is_ending: true`.

---

## 2. Hub-and-Spoke / Open World

Best for: RPGs, exploration games, quest-based adventures.

A central hub connects to multiple areas. The player can explore freely. Quests span across areas.

```yaml
id: fantasy_city
name: "Karrakara"
start_node_id: city_square
genre: "Open-world fantasy RPG"

initial_variables:
  gold: 50
  reputation: 0
  lore_economy: |
    Currency: gold coins.
    Drink prices: 1-3 gold. Weapons: 20-100 gold.
    Merchants haggle based on player Charisma.

characters:
  - id: tavern_keeper
    name: "Greta"
    is_playable: false
    definition: |
      [Identity]
      A stout woman who runs The Golden Mug tavern. Former adventurer.
      [Personality]
      Warm but shrewd. Calls everyone "dear". Speaks bluntly.
      [Behavior Rules]
      ## Greeting
      When greeted:
      - Welcome the player, mention drinks and rumors
      - Effect: {"type": "set_variable", "target": "met_greta", "value": true}
      ## Buy drink
      When player orders a drink:
      - Serve it, charge 2 gold
      - Effect: {"type": "modify_variable", "target": "gold", "operation": "add", "value": -2}
      ## Ask about rumors
      When player asks for rumors:
      - Share a hint about the dungeon to the north
    explicit_state: "A stout woman polishes mugs behind the bar."
    implicit_state: "Knows the dungeon entrance is through the old well"
    memory: []
    properties:
      location: tavern
      status: []
      inventory: []
      affinity: 50

nodes:
  city_square:
    name: "City Square"
    explicit_state: |
      The bustling heart of Karrakara. Streets branch in every direction.
      {go_tavern: The Golden Mug tavern} sits to the west.
      {go_market: The market} sprawls to the east.
      {go_north_gate: The north gate} leads to the wilds.
    actions:
      - id: go_tavern
        text: "Enter the tavern"
        effects:
          - type: goto_node
            target: tavern
      - id: go_market
        text: "Visit the market"
        effects:
          - type: goto_node
            target: market
      - id: go_north_gate
        text: "Head to the north gate"
        effects:
          - type: goto_node
            target: north_gate

  tavern:
    name: "The Golden Mug"
    definition: |
      A warm tavern with crackling fireplace. Serves food and drinks.
      The barkeep Greta knows everything happening in the city.
    explicit_state: null  # auto-generated from definition on first visit
    actions:
      - id: go_square
        text: "Return to the city square"
        effects:
          - type: goto_node
            target: city_square

  # market, north_gate, etc. follow the same pattern...
```

**Key traits**: Central hub node, multiple branch areas, NPCs with services, lorebook variables for world rules, `explicit_state: null` for AI-generated scene text.

---

## 3. Puzzle-Driven

Best for: mystery games, point-and-click style adventures.

Heavily uses object status, variables, and conditional triggers. Progress depends on finding and combining items.

```yaml
nodes:
  ritual_room:
    name: "Ritual Chamber"
    explicit_state: "Three empty pedestals surround a sealed door."
    objects:
      - id: pedestal_left
      - id: pedestal_center
      - id: pedestal_right
    triggers:
      - id: all_gems_placed
        conditions:
          - type: variable
            variable: gems_placed
            operator: gte
            value: 3
        effects:
          - type: display_text
            text: "The door rumbles open as all three gems glow!"
          - type: update_node_status
            target: ritual_room
            add_status: ["door_open"]
            regenerate_explicit_state: true
    actions:
      - id: place_red_gem
        text: "Place the red gem on the left pedestal"
        conditions:
          - type: inventory
            operator: has
            value: red_gem
        effects:
          - type: remove_from_inventory
            target: red_gem
          - type: modify_variable
            target: gems_placed
            operation: add
            value: 1
          - type: display_text
            text: "The red gem glows as it settles into the pedestal."
      - id: enter_door
        text: "Enter through the opened door"
        conditions:
          - type: variable
            variable: gems_placed
            operator: gte
            value: 3
        effects:
          - type: goto_node
            target: treasure_vault
```

**Key traits**: Heavy use of conditions, object status tracking, variable counters for multi-step puzzles, conditional triggers for milestone events. See [stories/cthulhu_escape_zh.yaml](stories/cthulhu_escape_zh.yaml) for a full example.

---

## 4. AI-Native / Sandbox

Best for: simulation games, open-ended RPGs, emergent narrative.

Minimal predefined nodes. Rich lorebook variables (`lore_*` in `initial_variables`) define the world's systems. The Architect LLM dynamically generates content, materializes NPCs and locations on the fly.

```yaml
id: snow_train_sim
name: "Snowpiercer Simulator"
start_node_id: awakening
genre: "Post-apocalyptic survival simulation"

initial_variables:
  lore_world_rules: |
    [World Laws]
    Trains must maintain >200km/h for survival heat.
    Economy uses heat-coins earned through labor.
    Each week: 3 action points (work, socialize, explore, learn, rest).
    [Attribute System]
    Constitution, Intelligence, Agility, Charisma (0-100 each).
    [Crisis Types]
    Equipment failure, resource shortage, social conflict, external threat.
  lore_economy: |
    Heat-coins are the base currency. Workers earn 5-15 per shift.
    Black market prices are 2x normal. Bribes cost 10-50 heat-coins.
  lore_social_rules: |
    Train hierarchy: Captain > Engineers > Workers > Stowaways.
    Moving between car classes requires a pass or bribery.
  action_points: 3
  heat_coins: 20
  week: 1

nodes:
  awakening:
    name: "Your Bunk"
    definition: |
      The player's small bunk in the worker car of train "North Wind".
      Cramped but warm. A small window shows the frozen wasteland outside.
      This is the player's home base -- they return here to rest and plan.
      
      Nearby: the worker canteen, the maintenance shaft, the car connector.
    explicit_state: null  # LLM generates based on definition
    actions:
      - id: go_canteen
        text: "Head to the canteen"
        effects:
          - type: goto_node
            target: canteen
      - id: rest
        text: "Rest for the day"
        effects:
          - type: display_text
            text: "You rest and recover your strength."
```

**Key traits**: `lore_*` variables in `initial_variables` define world systems and constraints for LLM context. Nodes have rich `definition` but null `explicit_state` (AI generates). Very few predefined actions -- the Architect handles most player input creatively within the rules. See [stories/snow_train.yaml](stories/snow_train.yaml) for a full example.
