# Architect Design

This document explains what the Architect is for, why it exists, and how to think about it when developing stories or engine features.

## In One Sentence

The Architect is a general-purpose world-building and world-expressing agent for the game engine: it reads the authored world, follows the rules and entities defined by the story author, and uses a small toolset to turn player intent into coherent world events, state changes, and player-facing narration.

## Design Purpose

The Architect exists to solve a specific problem:

- players interact with the world in free text
- authors want to define the world declaratively in YAML
- the engine needs one consistent place where authored rules, generated narrative, and runtime state all meet

Instead of scattering LLM behavior across many subsystems, Wenyoo uses one central agent that is responsible for interpreting intent, consulting the current world state, and committing changes in a controlled way.

## What The Architect Is

The Architect is:

- a unified LLM agent
- a runtime world interpreter
- a narrator that only speaks through engine-approved write tools
- a bridge between authored data and moment-to-moment player interaction

The Architect is not:

- a replacement for authored story structure
- a free-writing assistant that ignores game state
- a separate game design layer that invents rules on its own

The author's YAML remains the source of truth for the world model. The Architect's job is to apply that model at runtime.

## Mental Model

You can think of the system like this:

1. The author defines the world: nodes, characters, objects, variables, triggers, forms, and rules.
2. The player expresses intent in natural language or through UI actions.
3. The Architect reads the relevant context.
4. The Architect decides what actually happens in the world.
5. The Architect records the change and presents it to the player through engine tools.

This means the Architect is not just "writing text." It is deciding world events, then expressing those events.

## Core Design Idea: World Events First

The most important design choice is that the Architect is event-first, not prose-first.

Before it describes anything to the player, it should determine:

- what happened
- who was affected
- what state changed
- what each player can perceive

Only then should it narrate the event.

That is why the architecture revolves around `commit_world_event`: narrative and state are committed together, instead of letting prose drift away from the underlying world model.

## Why A General World Agent

The Architect is intentionally general-purpose so the engine can support many genres and interaction styles without hardcoding story-specific logic into Python.

That gives authors a powerful contract:

- define the world in data
- define rules in entity and node descriptions
- let the Architect apply those rules in moment-to-moment interaction

This makes the engine more reusable. A mystery game, fantasy RPG, survival scenario, or multiplayer social story can all use the same runtime pattern.

## How It Follows Author Intent

The Architect is designed to follow authored content rather than improvise blindly.

At runtime it is expected to resolve behavior through a hierarchy such as:

1. entity-level rules
2. node-local rules
3. story-wide lore and variables
4. genre and world logic
5. only then broader language-model reasoning

In practice, that means the author decides what is mechanically important, what entities exist, and what behavior is allowed. The Architect applies those rules to the current situation instead of replacing them.

## Tools, Not Raw Text

The Architect works through tools rather than directly writing arbitrary responses.

The current design centers on a small set of runtime tools such as:

- `read_game_state`
- `read_node`
- `commit_world_event`
- `roll_dice`
- `queue_materialization`
- `present_form`

This matters because tools provide boundaries:

- read tools help it inspect the world
- write tools ensure actions happen through the engine
- UI tools like `present_form` let it request structured input when free text is not enough

That is how the Architect interacts with both the world model and the player interface in a controlled way.

## Dynamic UI As Part Of The Agent Design

The Architect is not limited to plain narration. It can also drive dynamic user interaction.

Examples:

- presenting a form when the player needs to choose a class or answer a questionnaire
- targeting different messages to different players in multiplayer
- materializing new interactive entities so they appear in the UI and game state

This is an important part of the design: the Architect is a world interaction agent, not just a storyteller.

## The Relationship Between Narrative And State

The Architect is built on a strict principle:

- if something consequential happens in the fiction, the game state should record it
- if the game state changes in a player-relevant way, the player-facing output should reflect it

This protects the game from a common LLM failure mode where the model says something happened, but the engine has no durable record of it.

In Wenyoo, the goal is not "beautiful prose at any cost." The goal is coherent world simulation that can also speak naturally.

## The DSPP Runtime Model

The Architect operates over a layered entity model:

- `definition`: what an entity is, and the rules that define it
- `explicit_state`: what is visibly true now
- `implicit_state`: hidden context
- `memory`: accumulated interaction history for characters
- `properties`: mechanical state such as stats, inventory, status, and location

This gives the Architect a clear separation between authored identity, visible condition, hidden condition, and gameplay mechanics.

## Why This Design Helps The Engine

This design gives the project several benefits:

- one place to manage LLM behavior
- fewer scattered prompt and inference paths
- stronger consistency between authored rules and runtime behavior
- easier extension through tools instead of story-specific hacks
- better support for multiplayer, forms, and dynamic world changes

## Guidance For Developers

When you add or change features, try to preserve the Architect's role:

- keep the core engine story-agnostic
- prefer giving the Architect better tools or clearer state
- avoid adding new ad hoc LLM call sites
- make sure new player-visible behavior has a state representation when it needs one

If a feature changes how the Architect reasons, reads state, writes events, or interacts with the UI, update this document and `prompts/architect_system.txt` together.

## Related Files

- `src/core/architect.py`
- `prompts/architect_system.txt`
- `docs/contributing/developer-guide.md`
