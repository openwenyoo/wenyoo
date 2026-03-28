# Editor Overview

The visual editor is served at `http://localhost:8000/editor`.

## Who It Is For

Use the editor if you want:

- a visual node graph
- a story list and load flow in the browser
- built-in save-to-server behavior
- version history for editor saves
- AI-assisted editing and import flows

Use direct YAML editing if you want:

- exact control over multi-file story layouts
- bulk refactors in your code editor
- tighter review diffs
- schema work directly against the canonical prompt docs

## What The Editor Does Well

- load stories from the server
- visualize nodes and compiled connections
- edit nodes, actions, triggers, objects, characters, parameters, lore, and global objects
- create new stories
- save stories back to the repo
- keep backup versions under `saves/story_versions/`
- compile the connection graph from the UI

## Important Behavior

- the editor loads stories through the backend and merges `includes`
- saving writes a flattened story payload back to the story entry path
- the graph is driven by the story `connections` data, so compile the connection graph when structural changes are not reflected visually

## Known Scope Limits

- it is not a full in-editor game player
- browser-side export-as-YAML is not the main save path; saving happens through server APIs
- some older docs referred to a single `editor-guide.md`; this docs section replaces that deleted page

## Editor Docs

- [Editor Getting Started](getting-started.md)
- [Editor Workflows](workflows.md)
- [Editor Reference](reference.md)
- [Writing Stories](../writing-stories.md)
