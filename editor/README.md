# Wenyoo Story Editor

A React and ReactFlow-based visual editor for Wenyoo stories.

## Current Capabilities

- Visual node graph editing
- Story load and save through backend APIs
- Node, action, trigger, object, character, parameter, lore, and global object editing
- Story version history
- Connection graph compilation from the UI
- AI-assisted editing flows

## Notes About Scope

- The editor is served by the main game server at `/editor`.
- Story saves go through the backend and write YAML to the resolved story path.
- The player game UI is separate from the editor. Use the normal game client for playtesting.

## Development

### Prerequisites

- Node.js 18 or higher
- npm or yarn

### Setup

```bash
npm install
npm run dev
```

The development server runs at `http://localhost:5173`.

### Build

```bash
npm run build
```

The build output goes to `dist/`. Copy it into `../static/editor/` for integration with the backend-served UI.

You can also use:

```bash
node ../scripts/copy-build-files.js
```

## Project Structure

```text
src/
├── components/   # Editor UI components
├── hooks/        # Custom hooks
├── i18n/         # Localization support
├── services/     # API clients and orchestration
├── styles/       # Editor-specific styles
├── utils/        # Graph layout and helpers
└── App.jsx       # Main editor entry
```

## Documentation

- [Editor Overview](../docs/editor/README.md)
- [Editor Getting Started](../docs/editor/getting-started.md)
- [Editor Workflows](../docs/editor/workflows.md)
- [Editor Reference](../docs/editor/reference.md)
- [Story Format Guide](../prompts/story_format_description.md)
- [Node and Effects Guide](../prompts/node_format_description.md)

## Tech Stack

- React 19
- Vite 7
- ReactFlow
- Axios
