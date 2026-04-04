# Architect Task Purpose

This document captures the product and design purpose behind treating the Architect as a general task engine rather than as something tied only to the default input box.

## In One Sentence

The Architect should accept purpose-driven tasks from many kinds of story UI, not just free-text player input, so that custom frontends can ask for intelligent world handling with richer, author-defined context.

## Core Purpose

The purpose of the Architect task abstraction is to separate:

- what the player or UI is trying to do
- what context the author wants the Architect to understand
- what kind of handling is being requested
- how that request reached the backend

This means the important thing is not whether an interaction came from a text box, a map, a card game panel, a detective board, a dialogue wheel, or some other custom story UI. The important thing is what the interaction means in the story and what the Architect should accomplish.

## Why This Matters

The current default web frontend naturally centers around a text input box. In that flow, the backend receives text and turns it into a `player_input` task. That is a useful default, but it should not define the Architect's long-term role.

If Wenyoo supports story-specific custom frontend apps, then some Architect calls will come from richer UI flows where the author already knows much more than a plain input string can express.

Examples:

- a negotiation screen may know the selected tone, stance, and target character
- an investigation UI may know which clues are selected and what comparison the player is attempting
- a tactical interface may know the chosen action mode, target area, and relevant battlefield state
- a custom story workflow may want the Architect to judge, interpret, or narrate something after deterministic UI steps have already happened

In these cases, the Architect should be able to receive a task that reflects the actual purpose of the interaction, instead of forcing everything to be flattened into fake text commands.

## What A Task Should Express

A task should express:

- what is happening in the current story or UI workflow
- what the caller wants the Architect to do
- what context is important for this invocation
- what kind of result is expected

That result may be:

- player-facing narrative
- world-state interpretation and evolution
- a judgment or recommendation
- event handling
- perception rendering
- structured UI-relevant output

## Task Profiles, Not Frontend Assumptions

Tasks should carry an explicit profile so behavior is driven by intent and delivery contract rather than by whether the caller is the default web client.

- `worldAction` for real in-world action and intent resolution
- `perceptionRender` for viewer-scoped scene rendering
- `workflowTask` for forms, events, and guided backend workflows
- `uiDecision` for strictly non-player-facing structured UI reasoning
- `backgroundSimulation` for deferred world evolution

## Relationship To `process_input()`

`process_input()` should be understood as one adapter, not the defining model of Architect usage.

Its job is to take a generic text-box interaction and package it into an Architect task. That is useful for the default frontend, but it should not remain the conceptual center of the system.

The deeper abstraction is:

- the UI or backend creates a task with a clear purpose
- the Architect handles that task against authoritative game state
- the Architect uses its tools to read, reason, and commit world-relevant outcomes

So the real boundary is the task contract, not the input box.

## Desired Direction

The Architect should become flexible enough to support many kinds of purpose-driven invocations, including:

- free-form player input
- guided intent execution from custom UI
- scene or object interaction from structured interfaces
- character-focused interaction with rich social context
- interpretation of form or workflow completion
- event-driven backend tasks
- background world-evolution tasks
- future UI-related generation requests

The caller should be able to provide comprehensive context when needed, especially in custom story apps where the author knows more about the UI flow than a plain input line can convey.

## What Should Stay True

Even with richer task types, the Architect should still preserve the core Wenyoo design:

- the backend remains authoritative over game state
- the Architect operates on meaningful world context, not isolated UI fragments
- authored story intent should guide the request framing
- custom UI can shape the request, but should not replace engine truth
- the Architect remains a general world-handling backend capability, not a frontend-specific trick

## Summary

The purpose of this abstraction is to let Wenyoo treat the Architect as a general intelligent backend for story interaction and world evolution.

The default input box should remain supported, but it should become just one possible source of Architect tasks. Custom story frontends should be able to invoke the same Architect with clearer purpose, richer context, and interaction-specific intent.
