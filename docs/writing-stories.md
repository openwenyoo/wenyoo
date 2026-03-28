# Writing Stories

This guide explains the recommended authoring workflow. Use it together with the canonical schema references:

- [`prompts/story_format_description.md`](../prompts/story_format_description.md)
- [`prompts/node_format_description.md`](../prompts/node_format_description.md)

## Choose a Story Layout

Use a single file when the story is small:

- `stories/my_story.yaml`

Use a folder with `main.yaml` and `includes` when the story is larger:

- `stories/my_story/main.yaml`
- `stories/my_story/nodes_forest.yaml`
- `stories/my_story/characters.yaml`

See `stories/age_of_fable/main.yaml` for a multi-file example.

## Minimum Working Story

At minimum, a full story should define:

- `id`
- `name`
- `start_node_id`
- `nodes`

Example:

```yaml
id: cabin_demo
name: "Cabin Demo"
start_node_id: start

nodes:
  start:
    name: "Outside the Cabin"
    explicit_state: "A small cabin stands in the pines."
    actions:
      - id: enter_cabin
        text: "Enter the cabin"
        effects:
          - type: goto_node
            target: inside

  inside:
    name: "Inside"
    explicit_state: "Dust hangs in the still air."
    is_ending: true
```

New content should use canonical field names such as `explicit_state`, `type`, and `target`.

## Recommended Workflow

1. Sketch the premise, scope, and major locations.
2. Decide whether the story should stay in one file or use `includes`.
3. Create the minimal story shell.
4. Add nodes, actions, objects, triggers, and characters.
5. Validate the YAML.
6. Compile the connection graph if your story uses generated or cross-node relationships.
7. Playtest in the browser.

## Key Authoring Concepts

### Nodes

Nodes represent places, scenes, or states in the story. They usually contain:

- `name`
- `definition`
- `explicit_state`
- `objects`
- `actions`
- `triggers`

### Actions

Actions are what the player can do. New content should prefer:

- `text` for player-facing labels
- `effects` for deterministic changes
- `intent` when the Architect should interpret the action in a less rigid way

### Variables and State

Use `initial_variables` for story state, counters, flags, and lorebook-style context. For example:

- counters like `gold`
- flags like `met_guardian`
- style and lore variables such as `lore_writing_style`

### Characters and Objects

Characters and objects both use the same general layered model:

- `definition`: authored identity and rules
- `explicit_state`: visible baseline
- `implicit_state`: hidden context or compatibility state
- `properties`: mechanical data

## Validation

Run the validator before you ship or commit a story:

```bash
python scripts/validate_story_yaml.py stories/example.yaml
```

Useful cases:

- validate one story file
- validate a whole story folder with `main.yaml`
- validate all YAML files under a tree with `--all-yaml`

The validator also warns when the compiled `connections` graph is stale.

## Connection Graph Compilation

The editor graph and some runtime relationship features depend on `connections`.

Compile them with:

```bash
python tools/compile_connections.py stories/example.yaml --write
```

Optional:

- add `--with-llm` to let the tool infer more relationships
- rerun after structural changes to nodes, objects, character locations, or navigation

Do not hand-edit the generated `connections` block.

## Editor vs Hand-Written YAML

Use the editor when you want:

- visual graph authoring
- easier browsing of nodes and connections
- save-to-server version history
- AI-assisted editing flows

Use direct YAML editing when you want:

- exact schema control
- comfortable multi-file editing with `includes`
- bulk refactors in your code editor
- review-friendly diffs

Important editor behavior:

- the editor loads multi-file stories by merging `includes`
- the editor saves a flattened story payload back to the story entry path
- saving from the editor creates version backups under `saves/story_versions/`

## Helpful References and Examples

- `stories/example.yaml`: large single-file example
- `stories/form_demo.yaml`: forms example
- `stories/multiplayer_coop_demo.yaml`: multiplayer example
- `skills/create-story/validation-checklist.md`: author checklist
- `skills/create-story/story-patterns.md`: narrative structure patterns

## Next Docs

- [Editor Overview](editor/README.md)
- [Editor Workflows](editor/workflows.md)
- [Troubleshooting](troubleshooting.md)
