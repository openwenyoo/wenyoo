# Editor Workflows

## Build The Story Graph

Use the graph canvas to shape the story visually, but remember that the final graph comes from the story's `connections`.

Recommended loop:

1. Create or load a story.
2. Add or revise nodes.
3. Edit actions, triggers, objects, and characters.
4. Save.
5. Compile the connection graph when needed.
6. Playtest in the game UI.

## Work With Nodes

Use nodes for places, scenes, or state transitions.

For each node, review:

- `name`
- `definition`
- `explicit_state`
- `implicit_state`
- `objects`
- `actions`
- `triggers`

The editor surfaces node details visually, but the saved data still maps back to canonical YAML fields.

## Edit Actions, Objects, And Triggers

The editor provides secondary editing flows for nested content:

- actions
- objects
- triggers

Use these to keep the graph readable while still editing structured data.

When writing new content, prefer canonical authored fields:

- `text`, not `name`, for action labels
- `type`, not legacy effect aliases
- `target` for navigation and variable paths where the schema expects it

## Work With Characters, Parameters, Lore, And Global Objects

Use the floating tool panel to open higher-level story data:

- characters
- parameters and variables
- lore
- global objects

This is helpful when the node graph alone is not enough to understand world state.

## Compile The Connection Graph

The graph status control tells you whether the story connection graph is current, stale, or missing.

Recompile when:

- navigation changed
- object relationships changed
- character locations changed
- the graph no longer matches the logical structure of the story

The editor can trigger the same compile step as `tools/compile_connections.py`.

## Save Strategy

The editor is best for rapid iteration, but save behavior matters:

- saving writes a flattened story representation
- stories that started as multi-file `includes` stories may need extra care after round-tripping through the editor
- if your workflow depends on keeping files split, use the editor carefully and review the saved output before committing

## When To Switch Back To YAML

Switch to direct YAML editing when:

- the story is heavily modular
- you need bulk edits
- you need schema-level precision
- you are reviewing generated `connections` or advanced forms/functions

The editor and YAML are complementary, not exclusive.
