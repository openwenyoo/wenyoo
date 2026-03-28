# Playing Stories

The player web app lives at `http://localhost:8000`.

## Session Flow

1. Open the game in a browser.
2. Enter a player name.
3. Select a story from the story list.
4. Create a new session, join an existing session with a code, or load a saved game when available.
5. Play by typing free-form commands into the input box.

## Multiplayer

- One player can create a session and share the game code.
- Other players can join with that code from the session screen.
- The game keeps shared world state while still tracking player-specific data.
- Reconnecting to an active session is supported when the browser still has the saved session token.

## Common Commands

- `look` or `l`: inspect the current location
- `inventory` or `i`: inspect inventory
- `help`, `h`, or `?`: show help
- `save [name]`: save the game
- `quit`, `exit`, or `q`: leave the current game

## UI Overview

- Main message area: the story narrative, dialogue, forms, and choices
- Input area: free-text commands and action entry
- Info panel: current stats, node information, and inventory
- Settings panel: game code, typewriter toggle, save, export history, return to menu, and reload

## Reconnect Behavior

- The client stores a persistent player ID in browser storage.
- The server can reattach you to the active session after a refresh or short disconnect.
- If the old session is still live, you usually return directly to the current game state instead of starting over.

## Save and Load

- Use `save` from the command input or the save action in the settings panel.
- Saved games are listed during the story/session selection flow.
- Loading is handled from the session selection UI rather than through a free-form in-game `load` command.

## Exporting History

The player client can export the visible message history as PNG images. This happens entirely in the browser.

## Language

The player UI supports English and Chinese and remembers the selected locale in browser storage.

## Related Docs

- [Getting Started](getting-started.md)
- [Basic Features](basic-features.md)
- [Troubleshooting](troubleshooting.md)
