# Custom Frontend Purpose

This document captures the core purpose behind supporting story-specific custom frontends in Wenyoo.

It is not an implementation plan. It describes why this capability should exist and what role it should play in the architecture.

## In One Sentence

Custom frontends exist so that each story can define the most appropriate way for players to experience and interact with that world, while Wenyoo remains the authoritative backend for state, rules, multiplayer coordination, and intelligent world evolution.

## Core Purpose

The purpose of custom frontends is to separate:

- the way a story is presented and interacted with
- the authoritative simulation and state management behind that story

Wenyoo should not assume that every story is best represented as the current default chat-style web interface.

Some stories may work well as:

- a text-first conversation interface
- a visual novel layout
- a detective board
- a card-based interface
- a tactical panel
- a phone or desktop simulation
- a map-driven exploration UI
- a highly story-specific interactive surface

The engine should support these different modes of representation without requiring the core backend to become story-specific.

## Why This Matters

The current web frontend is a good default story/world representation, but it is still only one representation.

The deeper goal is that Wenyoo should be an engine whose backend capabilities are strong enough to support many different frontends for many different kinds of story experiences.

That means:

- the frontend should not define what the game fundamentally is
- the backend should not assume one fixed presentation style
- the story author should be able to choose or build a frontend that matches the story's interaction model

This is important because different stories do not only differ in art or theme. They often differ in how the player should think, decide, observe, and act.

## What The Default Frontend Should Be

The existing web frontend should remain:

- the default renderer
- the reference implementation
- the fallback experience for stories without a custom frontend

It is still valuable because it provides:

- a usable baseline experience
- a stable testing surface
- a simple authoring target
- a built-in way to experience the world even before a custom frontend exists

But it should be understood as a default client, not as the permanent definition of the engine's UI model.

## What A Custom Frontend Is

A custom frontend is a story-specific representation layer that decides:

- what the player sees
- what kinds of interactions are available
- which interactions are local UI behavior
- which interactions call backend deterministic logic
- which interactions invoke the Architect or other intelligent backend behavior

The custom frontend is responsible for presentation and interaction design.

Wenyoo remains responsible for:

- authoritative game state
- persistent world evolution
- multiplayer/session coordination
- deterministic backend capabilities
- Architect-driven interpretation and intelligent state changes

## Desired Relationship Between Frontend And Backend

The frontend should be expressive, but the backend should remain authoritative.

That means the custom frontend may decide:

- how to present a scene
- how to group actions
- what widgets or workflows to use
- how the player expresses intent

But the backend still decides:

- what is true in the world
- what changed
- what other players should receive
- what state should persist
- how intelligent interpretation affects the world

This preserves the engine's coherence while allowing much more freedom in presentation.

## Why The Architect Still Matters

A custom frontend does not reduce the importance of the Architect. It changes how the Architect is reached.

The Architect should function as a powerful backend capability that can be called from many kinds of UI, not just from a text box.

In this model:

- the default frontend may call the Architect through free-text input
- a custom frontend may call the Architect through richer, purpose-driven tasks and explicit task profiles
- the Architect remains part of the backend world-handling layer rather than part of a specific frontend design

So the point of custom frontends is not to move intelligence into the UI. The point is to let different UIs access backend intelligence in the way that best fits their interaction model.

## Long-Term Product Direction

Supporting custom frontends means Wenyoo is not just a single web app for one interaction style. It becomes a backend-first story engine that can power multiple kinds of clients.

This opens a path for:

- story-authored frontend experiences
- genre-specific interfaces
- workflows that mix deterministic UI with intelligent backend interpretation
- future generated or adaptive UI layers
- a cleaner separation between engine capability and presentation choice

## What Should Stay True

Even with custom frontends, several principles should remain stable:

- world state is the source of truth
- engine code stays story-agnostic
- frontend freedom should not break backend coherence
- player-facing interactions should still map cleanly to meaningful backend operations
- the Architect and other backend systems should remain reusable across many stories and many frontend styles

## Summary

The base purpose of custom frontend support is to let each story choose the right interaction form for its world, instead of forcing all stories through one default presentation.

The current web frontend should remain the default representation, but Wenyoo itself should evolve into a strong backend that can power many different story-specific clients while keeping state, rules, and intelligent world evolution consistent.
