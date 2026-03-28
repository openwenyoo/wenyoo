# Editor Reference

## Menus And Status

### File

- create a new story
- save the current story
- open the story list
- open version history

### Edit

- undo
- redo

### View

- simple view
- detailed view

### Graph Status

The graph status button shows whether compiled `connections` are:

- current
- stale
- missing

Use it to trigger recompilation from the editor.

## Panels

### Graph Canvas

- pans and zooms
- displays story nodes and compiled connections

### Node Inspector

- edits the selected node
- exposes node fields and nested story content

### Secondary Editor

- focused editing for nested actions, objects, or triggers

### Floating Tool Panels

- characters
- parameters
- lore
- global objects

### Version History

- view saved versions
- restore previous versions

Version backups are stored by the backend under `saves/story_versions/`.

## Save Semantics

- loading a story creates an original backup if one does not already exist
- saving writes through the backend API
- the backend sanitizes the story ID and writes YAML to the resolved story path

## Shortcuts And Input Notes

The menu labels show `Ctrl+Z` and `Ctrl+Y` for undo and redo.

Treat the menu actions as the reliable workflow. If you depend on keyboard shortcuts, verify them in your environment.

## Current Limitations

- the editor is not the same thing as the player web app
- story playtesting happens in the normal game UI, not in a full embedded preview mode
- round-tripping multi-file stories can flatten them
- older README text may mention features more broadly than the current editor implementation supports

## Related Docs

- [Editor Overview](README.md)
- [Editor Getting Started](getting-started.md)
- [Writing Stories](../writing-stories.md)
- [Troubleshooting](../troubleshooting.md)
