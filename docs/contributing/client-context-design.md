# Client Context: Representation-Aware Architect

## Problem

The Architect core produces typed artifacts (narrative, structured) via `commit()`, but it has no principled model of **who is consuming those artifacts and what the player's experience looks like**. Today, each frontend compensates by stuffing delivery instructions into the `purpose` field:

```js
purpose: "Respond ONLY as Sophie in 1-3 short texting-style sentences. "
       + "Use commit() with a narrative artifact containing ONLY the character's reply text..."
```

This works but has problems:
- The frontend is doing the Architect's job of deciding output format
- Every `sendArchitectTask` call must re-explain how to format output
- The Architect can't make contextual decisions about content style (chat-style text vs prose narration vs scene description) because it doesn't know what the player sees
- Adding a new frontend type (Godot, VR, board game) means every call site needs new prompt engineering

## Design Principle

The *content* of what the Architect produces should differ based on representation. "The door creaks open and you step into a dimly lit tavern..." is right for text chat but wrong for a phone messenger (where it should be a character's text message) and wrong for a 3D scene (where the player can already see the tavern).

The Architect needs to know the representation context to produce the right **content**, not just the right **artifact shape**.

## Options Evaluated

### Option 1: Architect reads frontend code on-the-fly

The Architect reads `app.js` / `index.html` at runtime and infers what the player sees.

**Verdict: Not viable.** The Architect is a world reasoning agent, not a code interpreter. Feeding it JS/HTML would bloat context, produce unreliable inferences, and slow everything down. Godot scene trees are even worse.

### Option 2: Compiled at build time

A tool scans the frontend code and extracts a client context descriptor automatically.

**Verdict: Not viable as primary.** Inferring "the player sees message bubbles" from JS source is itself an LLM-hard problem. The mapping from code to player experience is semantic, not syntactic. Could be useful as a helper that generates a draft for authors to edit.

### Option 3: Author-described (static) ← Recommended

The author writes the client context in YAML alongside the frontend config. They know what their UI does — they built it. This follows the same pattern as writing character definitions and node descriptions.

### Option 4: Author provides a runtime service/endpoint

The frontend exposes an endpoint describing what the player currently sees, like an accessibility API.

**Verdict: Overkill for the general case.** Most UIs have a small number of views that don't change structurally at runtime. Reserve for truly dynamic UIs (maybe Godot procedural scenes).

## Recommended Design

**Author-described client context in YAML, with a runtime `active_view` signal from the frontend.**

### YAML Schema

```yaml
frontend:
  app:
    mode: sandboxed_app
    entry: index.html
    client_type: story_app
    # ... existing fields ...

  client_context:
    representation: phone_app
    description: "A simulated smartphone with messaging and shopping apps"

    # Default guidance when no specific view matches
    default_guidance: >
      This is a phone UI, not a text adventure. Do not write scene descriptions
      or narration prose. All player interaction happens through app interfaces.

    views:
      heartchat:
        description: "A messaging app with contact list and chat bubbles"
        player_sees: "Message bubbles in a 1-on-1 chat conversation"
        player_can: "Type text messages to NPCs"
        artifact_guidance: >
          Narrative artifacts appear as chat bubbles from the NPC. Write as the
          character would text — short, casual, no scene description, no stage
          directions, no attribution like 'Sophie says:'.
      giftbox:
        description: "An e-commerce app with product cards"
        player_sees: "Grid of gift items with emoji, name, price, description, tags"
        player_can: "Buy gifts for characters, refresh shop inventory"
        artifact_guidance: >
          No narrative artifacts needed for shop interactions. State changes
          handle inventory and currency. Generation tasks should write structured
          data to variables.giftbox_inventory.
      home:
        description: "Phone home screen with app icons"
        player_sees: "Grid of app icons on a dark phone screen"
        player_can: "Tap app icons to open apps"
        artifact_guidance: "No Architect interaction expected from this view."
```

### Frontend Signal

The frontend sends its current `active_view` as part of each bridge message:

```js
bridge.sendArchitectTask("character_interaction", {
  active_view: "heartchat",    // which view the player is currently in
  player_input: "Hello!",
  purpose: "Role-play Sophie's reply to the player's message.",
  // ...
});
```

The `purpose` field now only describes **what** to do, not **how** to format the output. Formatting guidance comes from the client context.

### Upper Layer Injection

The upper layer (game_loop_handler or web_frontend_adapter) assembles the client context and injects it into the Architect's task prompt:

```
## CLIENT CONTEXT
Representation: phone_app — A simulated smartphone with messaging and shopping apps
Active view: heartchat — A messaging app with chat bubbles
Player sees: Message bubbles in a 1-on-1 chat conversation
Player can: Type text messages to NPCs
Guidance: Narrative artifacts appear as chat bubbles from the NPC. Write as the
character would text — short, casual, no scene description.
```

This section is injected after the TASK CONTRACT and before the task-specific content.

### Fallback Behavior

- If no `frontend.client_context` exists (default text chat), no CLIENT CONTEXT section is injected. The Architect defaults to its existing text narration behavior.
- If `active_view` is missing or doesn't match a declared view, the `default_guidance` is used.
- If `client_context` exists but a specific view has no `artifact_guidance`, only the view description and player affordances are injected.

## Examples by Frontend Type

### Phone Dating Sim

```yaml
client_context:
  representation: phone_app
  description: "A simulated smartphone with messaging and shopping apps"
  default_guidance: "Phone UI. No prose narration. All interaction through app interfaces."
  views:
    heartchat:
      player_sees: "Message bubbles in a 1-on-1 chat conversation"
      player_can: "Type text messages to NPCs"
      artifact_guidance: "Write as the NPC would text. Short, casual, in-character."
    giftbox:
      player_sees: "Grid of gift items with prices and tags"
      player_can: "Buy gifts, refresh shop"
      artifact_guidance: "State changes only. No narrative."
```

### Godot Isometric RPG

```yaml
client_context:
  representation: godot_3d
  description: "Isometric 3D RPG with character models, environments, and UI overlays"
  default_guidance: "Players can see the environment. Describe what happens, not what things look like."
  views:
    overworld:
      player_sees: "Isometric 3D scene with character sprites, terrain, objects"
      player_can: "Click to move, interact with objects and NPCs, open inventory"
      artifact_guidance: "Narrate actions and consequences. Do not describe visual appearance of things the player can already see in 3D."
    dialogue:
      player_sees: "Dialogue box overlay with NPC portrait and text"
      player_can: "Read NPC speech, choose dialogue options"
      artifact_guidance: "Write dialogue lines only. No action descriptions — the 3D scene shows those."
    combat:
      player_sees: "Turn-based combat UI with health bars, action menu"
      player_can: "Select attack, defend, use item, flee"
      artifact_guidance: "Narrate combat outcomes briefly. State changes handle mechanical results."
```

### Interactive Map

```yaml
client_context:
  representation: map_app
  description: "An interactive map with clickable regions and info panels"
  default_guidance: "Players see a visual map. Describe events and discoveries, not geography they can see."
  views:
    map:
      player_sees: "Overhead map with clickable regions, markers, fog of war"
      player_can: "Click regions to explore, zoom, toggle layers"
      artifact_guidance: "Structured artifacts for map data updates. Narrative for discovery announcements."
    region_detail:
      player_sees: "Side panel with region description, resources, events"
      player_can: "Read details, assign workers, start expeditions"
      artifact_guidance: "Narrative for event outcomes. Structured for resource changes."
```

## Responsibilities Summary

| Layer | Responsibility |
|---|---|
| **Author** | Declares `client_context` in YAML: representation, views, what the player sees/can do, artifact guidance |
| **Frontend JS** | Sends `active_view` string with each bridge message |
| **Upper layer** | Looks up the active view in `client_context`, assembles the CLIENT CONTEXT prompt section |
| **Architect** | Reads CLIENT CONTEXT, adapts content style and artifact choices accordingly |

The key insight: authors already describe the world for the Architect (characters, nodes, rules). The client context is the same pattern — describing the **player's window into the world** so the Architect knows how to present through it.

## Implementation Steps

1. Add `client_context` to `StoryFrontendConfig` model in `story_models.py`
2. Add `active_view` field to the bridge message schema (SDK + router)
3. Build prompt section assembly in the upper layer (resolve view from `active_view` + fallback to `default_guidance`)
4. Inject CLIENT CONTEXT section into `_build_task_prompt` for story_app tasks
5. Update the phone dating sim to use `client_context` instead of verbose `purpose` strings
6. Update the `create-story` skill documentation
