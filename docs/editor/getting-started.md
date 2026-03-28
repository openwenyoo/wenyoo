# Editor Getting Started

## Open The Editor

1. Start the server with `python -m src.main`.
2. Open `http://localhost:8000/editor`.
3. Wait for the loading panel.

## First Screen

The loading panel is the normal starting point. From there you can:

- create a new story
- load an existing server-side story
- open the import wizard

## Main Areas

- Menu bar: file actions, view mode, undo/redo, language, and connection graph status
- Graph canvas: node layout and connections
- Right-side editors: node details and secondary editors for actions, triggers, and objects
- Floating panels: characters, parameters, lore, and global objects

## Create A New Story

1. Choose the create-new flow.
2. Give the story a title.
3. The editor creates a starting node.
4. Save the story so it becomes a file under `stories/`.

New stories stay local to the editor state until you save them.

## Load An Existing Story

- Use the loading panel or the menu bar story list.
- The editor requests the story from the backend.
- If the story uses `includes`, the backend merges them before returning the editor payload.

## Save A Story

- Save writes the current story to the server through `/api/story/{story_id}`.
- The backend keeps version backups under `saves/story_versions/`.
- After save, the editor reloads the story and resets its unsaved state.

## Import Notes

The import flow is designed for assisted conversion and outline generation rather than as a simple YAML file round-trip tool.

Treat import as a starting point, then review the generated graph carefully before saving.

## First Safe Workflow

1. Create or load a story.
2. Add or revise a small number of nodes.
3. Save once.
4. Compile the connection graph if the graph status shows missing or stale.
5. Open the player UI in a separate tab and playtest.

## Next Docs

- [Editor Workflows](workflows.md)
- [Editor Reference](reference.md)
