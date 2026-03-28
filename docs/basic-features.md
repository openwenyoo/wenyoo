# Basic Features

Wenyoo is both a playable web game and a story-authoring platform.

## Player-Facing Features

- Free-text play through the browser
- Real-time WebSocket updates
- Multiplayer sessions with shared world state
- Session codes for joining existing runs
- Save and load support
- Reconnect support after refresh or short disconnects
- Message history export from the web client
- English and Chinese UI strings in the player client

## Author-Facing Features

- YAML-authored stories
- Single-file and multi-file stories with `includes`
- Nodes, actions, triggers, objects, characters, forms, and variables
- Connection graph compilation through `tools/compile_connections.py`
- Story validation through `scripts/validate_story_yaml.py`
- Visual story editor served at `/editor`
- Version backups when saving from the editor

## Engine Features

- LLM-driven Architect runtime
- OpenAI-compatible providers, Ollama, and mock mode
- Lua-backed derived variables and scripting hooks
- Status display configuration for game HUD output
- Per-player state alongside shared session state for multiplayer stories

## What To Read Next

- [Playing Stories](playing-stories.md) if you want to use the game
- [Writing Stories](writing-stories.md) if you want to author content
- [Editor Overview](editor/README.md) if you want to work visually
