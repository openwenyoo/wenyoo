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
pip install -r requirements-test.txt
pytest                         # full suite, LLM-free, < 30s
pytest tests/contracts         # Architect invariant contracts
pytest --cov=src
python scripts/validate_story_yaml.py stories/example.yaml
python tools/compile_connections.py stories/example.yaml --write
```

### Test harness layout

The suite is deterministic and LLM-free — no network, no real provider calls.

| Path | What it covers |
|------|----------------|
| `tests/helpers/mock_llm_tool_calling.py` | `ToolCallingMockLLM` — scripts the Architect's `async_client.chat.completions.create(...)` surface in **both** non-streaming and streaming (`stream=True`) modes. The single most important piece: `MockLLMAdapter` alone cannot drive the Architect. |
| `tests/conftest.py` | Shared fixtures: `mock_tool_llm`, `game_kernel` (no frontend adapter → non-streaming path), `started_game` → `(game_state, story)`. All disk I/O is pinned to `tmp_path`. |
| `tests/fixtures/stories/` | `tiny.yaml` (3-node workhorse) and `with_form.yaml` (1 form). Treat these as part of the schema contract. |
| `tests/contracts/` | Architect load-bearing invariants (commit atomicity, merge-patch, profile branching, loop cap). |
| `tests/unit/` | Primitives: `apply_merge_patch`, story-model validators, config precedence, text/variable resolution. |
| `tests/integration/` | `process_input`, form submission, multiplayer audience targeting, save/load. |
| `tests/e2e/` | One real FastAPI WebSocket round-trip — the only test that exercises the **streaming** Architect path. |

### Writing a new Architect test

Copy an existing contract test. Queue the tool calls the Architect should make
with the `tc(...)` helper, drive it through `architect.handle(task, gs, pid, story)`
(or `game_kernel.process_input`), and assert the invariant:

```python
from tests.helpers.mock_llm_tool_calling import tc

async def test_my_invariant(game_kernel, mock_tool_llm, started_game):
    gs, story = started_game
    mock_tool_llm.queue_tool_calls([
        tc("commit", artifacts=[{"kind": "narrative", "payload": "..."}],
           state_changes={"variables": {"x": 1}}),
    ])
    await game_kernel.architect.handle(make_task(), gs, "player1", story)
    assert gs.variables["x"] == 1
```

The full conventions and rationale live in
[`test-harness-rollout.md`](test-harness-rollout.md) (the one-time rollout plan).

## Continuous Integration

`.github/workflows/ci.yml` runs on every push to `main` and every PR.

| Job | Blocking? | What it runs |
|-----|-----------|--------------|
| `backend-tests` | **Yes** | `pytest` on Python 3.10 + 3.11 (installs `liblua5.4-dev` for `lupa`). Must pass to merge. |
| `frontend` | **Yes** | `npm run lint` (0 errors; warnings allowed) + `node --test` in `editor/`. |
| `ruff` | No (ratchet) | `ruff check src/ --select F`. Surfaces unused imports; needs a `TYPE_CHECKING`-aware config before it can block. |

The non-blocking jobs exist to make pre-existing debt visible. To promote one to
blocking: clear its findings, then delete its `continue-on-error: true`. Coverage
debt is tracked in [`test-coverage-baseline.md`](test-coverage-baseline.md).

## Cross-Language Docs

When changing user-facing documentation:

- update the English page
- update the matching page under `docs/zh-CN/`
- update `README.md` and `README_CN.md` if navigation changed
