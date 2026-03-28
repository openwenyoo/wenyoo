# Developer Guide

This guide complements the repository-wide contribution rules in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Main Surfaces

- `src/`: Python backend and game engine
- `static/`: player-facing web client
- `editor/`: React-based story editor source
- `stories/`: authored content
- `prompts/`: canonical prompt and schema references
- `docs/`: user and contributor documentation

## Architecture At A Glance

- `src/main.py`: runtime entry point
- `src/core/`: game kernel, Architect, and engine services
- `src/models/`: story and runtime data models
- `src/adapters/`: FastAPI routes, WebSocket handlers, and external adapters
- `static/`: browser game client
- `editor/src/`: visual editor client

For the design intent behind the Architect itself, see [`architect-design.md`](architect-design.md).

## Development Workflow

### Backend

```bash
python -m venv venv
pip install -r requirements.txt
pip install -r requirements-test.txt
python -m src.main --llm-provider mock
```

### Editor

```bash
cd editor
npm install
npm run dev
```

Build production assets when needed:

```bash
npm run build
```

## Docs Placement

Use these rules when adding or updating docs:

- `README.md` and `README_CN.md`: concise landing pages
- `docs/`: task-oriented product and contributor docs
- `prompts/`: canonical authored schema and prompt reference
- `skills/`: agent-specific workflows, not general public docs

Avoid copying the same schema explanations into multiple places. Link to `prompts/story_format_description.md` and `prompts/node_format_description.md` when possible.

## Story Development Workflow

1. author or edit YAML in `stories/` or through the editor
2. validate with `scripts/validate_story_yaml.py`
3. compile `connections` when needed
4. playtest in the browser
5. update docs if behavior or workflow changed

## Editor Development Notes

- the editor loads stories through `/api/story/*`
- saving writes YAML through the backend
- version history lives under `saves/story_versions/`
- editor docs live in `docs/editor/`

If you change editor capabilities, update:

- `editor/README.md`
- `docs/editor/`
- any affected top-level docs under `docs/`

## Testing

Common commands:

```bash
pytest
pytest --cov=src
python scripts/validate_story_yaml.py stories/example.yaml
python tools/compile_connections.py stories/example.yaml --write
```

## Cross-Language Docs

When changing user-facing documentation:

- update the English page
- update the matching page under `docs/zh-CN/`
- update `README.md` and `README_CN.md` if navigation changed
