# Backend Test Harness Rollout Plan

**Owner:** TBD  •  **Target window:** ~2-3 weeks of focused work  •  **Status:** Proposed (rev. 2026-05-29)

> Companion to [`developer-guide.md`](developer-guide.md) and [`architect-design.md`](architect-design.md). This is a **one-time rollout plan**, not a long-term test policy. Once Phase 4 completes, ongoing test conventions belong in `developer-guide.md`.

> **Rev. 2026-05-29 (post-code-review).** Five corrections applied after verifying the plan against the codebase: (1) the **streaming** LLM path is the default in any frontend-attached run (`use_streaming_api = self.game_kernel.frontend_adapter is not None`, [architect.py:528](../../src/core/architect.py#L528)), so the streaming shim is **pulled into Phase 0** — Phase 4's e2e WebSocket test cannot run without it; (2) sample fixtures fixed (`StateManager(save_dir=...)` not `saves_dir=`, and the missing `story` argument to `process_input`); (3) the `saves/` cross-test-pollution check is **promoted to Phase 0**; (4) `filterwarnings` starts permissive and is escalated to `error` only once green; (5) line references re-synced to current `architect.py`.

---

## 1. Motivation

The engine is 30k LOC at v0.7.0. The Architect agent ([`src/core/architect.py`](../../src/core/architect.py), 3071 lines) governs every player-visible event through a 12-iteration tool-calling loop with JSON repair, four task profiles, two atomic-commit shims, streaming extractors, and a "synthetic-narrative-on-bare-text" fallback. **None of it is covered by automated tests.**

Three pieces of evidence that this is urgent:

1. `MockLLMAdapter` ([`src/adapters/mock_llm_adapter.py`](../../src/adapters/mock_llm_adapter.py)) was built explicitly to enable LLM-free testing — and is unused.
2. [`CLAUDE.md`](../../CLAUDE.md), [`CONTRIBUTING.md`](../../CONTRIBUTING.md), and [`developer-guide.md`](developer-guide.md) all reference `requirements-test.txt` and `pytest tests/test_e2e_game.py` — **none of which exist**.
3. [`architect.py:555-558`](../../src/core/architect.py#L555) carries a TODO: *"This fallback exists because some LLMs fail to call commit_world_event… remove this when models are reliable enough."* That's load-bearing trust without a verification net.

The goal of this rollout is **not coverage percentage**. It is to lock the engine's load-bearing invariants behind cheap, deterministic, fast tests so that future Architect refactors (and the `architect.py` decomposition planned as the next initiative) can ship without leaps of faith.

---

## 2. Success Criteria

When this rollout is done, all of the following must be true:

- `pip install -r requirements-test.txt && pytest` succeeds on a clean checkout in **< 30 seconds**.
- **At least 10 Architect contract tests** pass and assert the invariants listed in §5.
- All tests are deterministic — **zero network, zero real LLM calls**, no flaky failures over 100 sequential runs.
- A new contributor can write a new Architect test in **under 15 minutes** by copying an existing one.
- The rollout deliverables feed directly into the upcoming **CI pipeline initiative** (separate plan) — pytest invocation, requirements pin, and exit-code semantics are all CI-ready.

**Non-goals (explicit):**

- Line/branch coverage targets. They incentivize garbage tests.
- Prompt-quality testing for `architect_system.txt`. That's an *eval suite*, not unit tests. Separate work.
- Real provider integration tests (OpenAI / Claude / Ollama). Flaky, slow, expensive. Out of scope.
- Editor (JavaScript) tests. The editor has its own `node:test` files; that's a separate initiative.
- Load / performance / soak testing. Premature.

---

## 3. The Critical Phase-0 Blocker

`MockLLMAdapter` implements only `generate_response` / `generate_text_response`. **Architect does not use these methods.** Architect uses [`llm_provider.async_client.chat.completions.create(...)`](../../src/core/architect.py#L540) with an OpenAI-shaped response (`.choices[0].message.tool_calls`, `.finish_reason`, etc.).

This means: **today, `MockLLMAdapter` cannot drive a single Architect tool-calling test.** The plan starts here.

The reference implementation already exists — [`ClaudeAdapter`](../../src/adapters/claude_adapter.py#L253) builds an OpenAI-shim (`_OpenAIShim`, `_AsyncOpenAIShim`, `_Completions`, `_ToolCall`, `_Message`) to translate Anthropic's native API into Architect-compatible shape. Phase 0 builds the same surface — but driven by a scripted queue instead of an LLM API.

---

## 4. Phased Rollout

| Phase | Window | Outcome |
|-------|--------|---------|
| **0** | Days 1-3 | Test infra + MockLLM that Architect can drive **in both modes** (non-streaming `.create()` **and** streaming `.create(stream=True)`); `saves/` isolation verified |
| **1** | Days 4-8 | 10 Architect contract tests — the load-bearing invariants (non-streaming path) |
| **2** | Days 9-11 | Unit tests for atomic-commit primitives (`apply_merge_patch`, Pydantic validators, config) |
| **3** | Days 12-14 | Integration tests — `GameKernel.process_input`, form submission, multiplayer targeting |
| **4** | Days 15-16 | One e2e WebSocket roundtrip via FastAPI `TestClient` (**exercises the streaming path** — depends on the Phase 0 streaming shim) |
| **5** | Optional | Coverage baseline report (informational only — no enforcement) |

Phases are **strictly sequential** for Phase 0→1→2. Phases 3 and 4 can overlap once Phase 2 ships.

> **Why streaming is in Phase 0, not deferred.** The Architect picks its LLM call path at [architect.py:528](../../src/core/architect.py#L528): `use_streaming_api = self.game_kernel.frontend_adapter is not None`. Phase 1–3 tests build a kernel with **no** frontend adapter, so they hit the non-streaming `chat.completions.create(...)` branch — that's fine and intentional. But Phase 4 constructs a real `WebFrontendAdapter`, which sets `frontend_adapter`, which **forces** the streaming branch (`_streaming_llm_call`, [architect.py:2970](../../src/core/architect.py#L2970)). That path consumes an **async iterator of chunks**, not a `_Completion`. If the shim only supports non-streaming, Phase 4 silently falls into the streaming→non-streaming `except` fallback ([architect.py:536](../../src/core/architect.py#L536)) and never tests the path real players use. So the streaming shim is a Phase 0 deliverable.

---

## 5. Phase 0 — Test Infrastructure (Days 1-3)

### 5.1 Deliverables

```
requirements-test.txt
pyproject.toml                # add [tool.pytest.ini_options] block
tests/
  __init__.py
  conftest.py                 # shared fixtures
  fixtures/
    stories/
      tiny.yaml               # 3-node minimal story (see §5.3)
      with_form.yaml          # 1-form story (see §5.3)
  helpers/
    __init__.py
    mock_llm_tool_calling.py  # OpenAI-shim for MockLLMAdapter — non-streaming AND streaming (THE blocker)
    builders.py               # quick GameKernel + GameState factories
```

### 5.2 `requirements-test.txt`

Pin minimally — these are dev-only:

```
pytest>=8.0,<9.0
pytest-asyncio>=0.23,<1.0
pytest-cov>=5.0
```

`httpx` and `starlette.testclient` are already transitive via FastAPI 0.111 — no new pin needed.

### 5.3 `pyproject.toml` addition

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"           # @pytest.mark.asyncio not required on every test
testpaths = ["tests"]
addopts = [
    "-ra",                       # short summary for skip/xfail/fail
    "--strict-markers",
    "--strict-config",
    "-p", "no:cacheprovider",   # keep CI workspace clean
]
filterwarnings = [
    "default",   # Phase 0-4: report deprecations without failing. Third-party
                 # combos (FastAPI 0.115 / Pydantic 2 / pytest-asyncio) emit
                 # deprecations we don't control; failing on them stalls Day 1.
    # Escalate to "error::DeprecationWarning" ONLY once the suite is green and
    # the remaining warnings all originate from src/ (CI-pipeline initiative).
]
```

`asyncio_mode = "auto"` is **non-negotiable** — without it every `async def test_*` needs a decorator and that friction will discourage writing tests.

### 5.4 The tool-calling shim — the actual blocker

Create `tests/helpers/mock_llm_tool_calling.py`. It must expose a `ToolCallingMockLLM` class whose `.async_client.chat.completions.create(...)` returns an OpenAI-shaped object that Architect can consume.

Required surface (mirrors what the Architect actually touches in [architect.py:540-595](../../src/core/architect.py#L540)):

```python
class ToolCallingMockLLM(ILLMProvider):
    model: str

    # legacy ILLMProvider surface (unused by Architect but required by interface)
    async def generate_response(self, prompt, **kw) -> str: ...
    async def generate_text_response(self, prompt, system_prompt=None, **kw) -> str: ...

    # what Architect actually uses
    async_client: _AsyncClient   # exposes .chat.completions.create(...)

    # test-author surface
    def queue_tool_calls(self, calls: list[dict]) -> None:
        """Next .create() returns a response with these tool_calls."""
    def queue_text(self, content: str) -> None:
        """Next .create() returns plain content, no tool_calls."""
    def queue_finish(self, *, content: str = "", reason: str = "stop") -> None:
        """Next .create() returns content with a custom finish_reason."""
    def captured_calls(self) -> list[CapturedCall]:
        """All .create() invocations: messages, tools, tool_choice, model."""
```

**Streaming support is required, not optional (Phase 0).** The same queued script must drive both call shapes. When `.create(stream=True)` is passed, the shim must return an **async iterator** yielding OpenAI-shaped chunk objects that `_streaming_llm_call` ([architect.py:2992](../../src/core/architect.py#L2992)) consumes:

```python
# chunk.choices[0].delta — what _streaming_llm_call reads each iteration
chunk.choices[0].delta.role            # str | None (first chunk only)
chunk.choices[0].delta.content         # str | None (narrative tokens)
chunk.choices[0].delta.tool_calls      # list | None of:
    tc.index                           # int  — groups fragments per call
    tc.id                              # str | None
    tc.function.name                   # str | None (sent once)
    tc.function.arguments              # str | None (concatenated across chunks)
chunk.choices[0].finish_reason         # str | None (last chunk)
```

A queued `commit` tool call should be emitted as: one chunk with `delta.role="assistant"`, one chunk carrying `tc.index=0, tc.id, tc.function.name="commit"`, then one-or-more chunks streaming `tc.function.arguments` fragments, then a final chunk with `finish_reason="tool_calls"`. Reference the chunk dataclasses in [`claude_adapter.py:273-342`](../../src/adapters/claude_adapter.py#L273) (`_StreamChunk`, `_StreamChoice`, `_StreamDelta`, `_StreamToolCallDelta`). Splitting `arguments` across ≥2 chunks is what actually exercises the Architect's `_NarrativeStreamExtractor`/`_ArtifactStreamExtractor` token forwarding — emit at least two argument fragments in the e2e test.

> Note: the **async** path is what Architect uses (`llm_provider.async_client...`). The sync `_OpenAIShim`/`_Completions` in `claude_adapter.py` is a reference for object *shape* only; the shim's live surface is `async_client` (`_AsyncOpenAIShim` → `_AsyncCompletions`, [claude_adapter.py:363-468](../../src/adapters/claude_adapter.py#L363)). `finish_reason` is not read on the non-streaming branch but the acceptance test asserts it, so set it.

Helper to build OpenAI-shaped tool calls cleanly:

```python
def tc(name: str, **args) -> dict:
    """Build one tool_call dict in OpenAI format."""
    return {
        "id": f"call_{uuid4().hex[:8]}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }
```

Reference: copy the response-object shape from [`claude_adapter.py:84-115`](../../src/adapters/claude_adapter.py#L84) (`_ToolCallFunction`, `_ToolCall`, `_Message`, `_Choice`, `_Completion`). Those classes are the contract.

**Acceptance test for the shim itself** (one of the first tests written):

```python
async def test_shim_returns_openai_shaped_response(mock_tool_llm):
    mock_tool_llm.queue_tool_calls([tc("roll_dice", dice="1d20", reason="test")])
    resp = await mock_tool_llm.async_client.chat.completions.create(
        model="mock", messages=[], tools=[]
    )
    assert resp.choices[0].message.tool_calls[0].function.name == "roll_dice"
    assert json.loads(resp.choices[0].message.tool_calls[0].function.arguments)["dice"] == "1d20"
    assert resp.choices[0].finish_reason == "tool_calls"
```

### 5.5 `conftest.py` fixtures

```python
@pytest.fixture
def mock_tool_llm() -> ToolCallingMockLLM:
    return ToolCallingMockLLM(model="mock")

@pytest.fixture
def stories_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "stories"

@pytest.fixture
def tiny_story(stories_dir) -> Story:
    # StoryManager resolves by the story's `id:` field, not filename.
    return load_story_from_file(str(stories_dir / "tiny.yaml"))

@pytest.fixture
def game_kernel(mock_tool_llm, stories_dir, tmp_path):
    sm = StoryManager(stories_dir=str(stories_dir))
    state_mgr = StateManager(save_dir=str(tmp_path / "saves"))   # NB: kwarg is save_dir, not saves_dir
    # No frontend_adapter -> Architect uses the NON-streaming path (intended for Phase 1-3).
    return GameKernel(sm, state_mgr, mock_tool_llm)

@pytest.fixture
async def started_game(game_kernel):
    # start_new_game_async loads + sets game_kernel.story_manifest; return both
    # because process_input(user_input, game_state, story, player_id, ...) needs `story`.
    gs = await game_kernel.start_new_game_async("tiny", "player1")
    yield gs, game_kernel.story_manifest
```

`tmp_path` is critical — `StateManager` writes JSON to disk; tests must never touch `saves/`.

### 5.6 `tiny.yaml` — the workhorse fixture

A 3-node story that exercises every surface a contract test needs:

- 3 nodes (start, branch, end) with `definition` + `state`
- 1 character at the start node, with `properties.location`
- 1 object at the start node, with `state` + `properties`
- 1 named action on the start node
- 1 trigger on the branch node (variable condition)
- 3 variables: a counter (`turns`), a flag (`door_open`), a `lore_*` (`lore_world`)
- 1 connection (start → branch) so connection_graph surfaces are exercised

Keep it under 80 lines of YAML. **No story-specific narrative content** — names like `start_node`, `entity_a`, `character_x`. This fixture must remain illustrative, never a real story.

### 5.7 Phase 0 Done When

- `pytest` runs (even with zero tests) without import errors.
- The shim acceptance test (§5.4 end) passes.
- `tiny.yaml` loads via `StoryManager` and `start_new_game_async("tiny", ...)` produces a `GameState`. **Correction:** a minimal story with no state-mutating start triggers is at `version == 0` after start (the original "version=1" was wrong); `version` only advances through `apply_merge_patch`, which contract #3 verifies.

---

## 6. Phase 1 — Architect Contract Tests (Days 4-8)

The ten invariants below are derived directly from [`architect_system.txt`](../../prompts/architect_system.txt) and the Architect's profile-branching logic. Each test should be **< 50 lines**, run in **< 100ms**, and depend only on Phase 0 fixtures.

Each test must follow this pattern:

```python
async def test_<invariant>(game_kernel, mock_tool_llm, started_game):
    gs, story = started_game
    # Arrange: queue tool calls the Architect should make
    mock_tool_llm.queue_tool_calls([tc("commit", artifacts=[...], state_changes={...})])

    # Act: drive the Architect. Two valid entrypoints:
    #   (a) through the kernel (note the required `story` positional arg):
    await game_kernel.process_input("anything", gs, story, "player1")
    #   (b) directly, when you need to control task_profile/task_type:
    #   from src.core.architect import ArchitectTask
    #   await game_kernel.architect.handle(
    #       ArchitectTask(task_type="player_input", player_input="anything",
    #                     task_profile="perceptionRender"),
    #       gs, "player1", story)

    # Assert: invariant property (see file below)
    assert ...
```

> Most contract tests below use entrypoint **(b)** (`architect.handle`) because they assert profile-specific behavior (`perceptionRender`, `backgroundSimulation`) that `process_input` always sets to `worldAction`.

### The 10 contract tests (file: `tests/contracts/test_architect_contracts.py`)

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_world_action_must_produce_narrative_or_form` | `worldAction` task ending without a `commit`/`present_form` produces a synthetic narrative artifact ([architect.py:430-440](../../src/core/architect.py#L430)) |
| 2 | `test_bare_text_response_becomes_synthetic_artifact` | When mock returns content + no tool_calls, ctx gets exactly one narrative artifact with that content ([architect.py:554-576](../../src/core/architect.py#L554)) |
| 3 | `test_commit_applies_state_and_artifacts_atomically` | One `commit` with both `state_changes` and `artifacts` → `game_state.version` bumps **exactly once**, artifact delivered exactly once ([architect.py:1703](../../src/core/architect.py#L1703)) |
| 4 | `test_merge_patch_replaces_arrays_not_append` | `state_changes={"variables.list": [1,2]}` over current `[3,4,5]` → final value is `[1,2]` |
| 5 | `test_merge_patch_null_deletes_key` | `state_changes={"variables.flag": None}` → key removed from `game_state.variables` |
| 6 | `test_perception_render_strips_node_state_writes` | `task_profile=perceptionRender` (`capture_only=True`) + `commit` with `state_changes` touching `nodes.<id>.state` → node.state unchanged ([architect.py:1738-1762](../../src/core/architect.py#L1738)) |
| 7 | `test_background_simulation_suppresses_narrative_delivery` | `backgroundSimulation` + narrative artifact + default flags → artifact recorded but NOT in `displayed_messages` ([architect.py:1881](../../src/core/architect.py#L1881)) |
| 8 | `test_loop_terminates_at_max_iterations` | Queue 20 `read_game_state` tool calls → loop breaks at `max_iterations = 12`, no exception, fallback message produced ([architect.py:527](../../src/core/architect.py#L527), warning at [:689](../../src/core/architect.py#L689)) |
| 9 | `test_commit_world_event_legacy_shim_delegates_to_commit` | Calling `_tool_commit_world_event` with old-format args produces identical `game_state.version` bump and artifact delivery as `_tool_commit` ([architect.py:1992](../../src/core/architect.py#L1992)) |
| 10 | `test_form_pending_blocks_subsequent_input` | With `player1` in `_pending_forms`, `process_input(...)` returns `{"script_paused": True}` early without entering the Architect loop ([game_kernel.py:719](../../src/core/game_kernel.py#L719)) |

### Suggested additional tests (write if time permits in Phase 1)

- `test_json_repair_recovers_from_trailing_comma`: malformed tool args get repaired by `_repair_json` ([architect.py:717](../../src/core/architect.py#L717)) in `_dispatch_tool` ([:783-793](../../src/core/architect.py#L783)) and tool still executes
- `test_tool_error_creates_error_artifact_and_breaks`: tool handler raising returns `{"error": "..."}` and loop terminates gracefully
- `test_early_exit_after_commit_and_terminal_tools`: `commit` + `roll_dice` only → loop breaks at next iteration even with capacity for more

### Phase 1 Done When

- `tests/contracts/test_architect_contracts.py` exists with all 10 tests.
- All 10 pass.
- Each test takes < 100ms (`pytest --durations=0` shows them at the bottom).
- Running 100 sequential invocations produces zero flakes: `for i in {1..100}; do pytest tests/contracts/ -q || break; done`.

---

## 7. Phase 2 — Atomic-Commit Primitives (Days 9-11)

Tests for the layer beneath Architect. **No LLM involvement** in this phase.

### Files

```
tests/unit/
  test_game_state_patch.py      # apply_merge_patch semantics
  test_story_models.py          # Pydantic validators that gate authored input
  test_config.py                # config_groups precedence
  test_text_processor.py        # {a:b}, {{o:b}}, {@c:b} hyperlink syntax
  test_variable_resolver.py     # dotted-path resolution
```

### Highest-priority cases (must-have)

- `GameState.apply_merge_patch`:
  - replaces arrays (mirrors contract #4 but isolated)
  - deep-merges nested dicts
  - `None` deletes
  - rejects invalid dotted paths cleanly (raises typed error, doesn't corrupt state)
  - version bumps exactly once per call
- `StoryCondition.evaluate`: each of the ~12 condition types — happy path + negative path
- `FormDefinition.to_frontend_format`: variable substitution + `show_if` evaluation
- `Story` loading: `_load_yaml_with_includes` handles `includes:` list correctly
- `load_config` precedence: defaults < `config.yaml` top-level < `config_groups.<name>` < env vars (use `monkeypatch.setenv`)
- `TextProcessor`: all three hyperlink kinds round-trip; raw `{` not consumed

### Phase 2 Done When

- Each file has ≥ 5 tests.
- `pytest tests/unit/` runs in < 5 seconds total.
- No test touches disk outside `tmp_path`.

---

## 8. Phase 3 — Integration Tests (Days 12-14)

Wire several real components together; still no real LLM.

### Files

```
tests/integration/
  test_kernel_process_input.py     # full path: input → Architect → state mutation → observer fire
  test_form_submission.py          # present_form → submit → on_submit effects
  test_multiplayer_targeting.py    # commit audience: self / players_here / location_players / session / specific_players
  test_session_lifecycle.py        # start_new_game → save → load → resume → state matches
```

### Highest-value scenarios

- **Observer fan-out**: register a fake observer, `process_input`, assert observer received exactly one notification with the post-commit version.
- **Form happy-path**: `present_form` queued → simulated submit → `on_submit.store_variables` writes propagate into `game_state.variables`.
- **Audience resolution**: queue a `commit` with `audience="location_players"` and 3 players at 2 locations; assert only the 2 at the named location received the artifact.
- **Save / load fidelity**: serialize → deserialize → `state == state_before` (modulo `version` and timestamps).

### Phase 3 Done When

- 4 files, ~3-5 tests each.
- `pytest tests/integration/` runs in < 10 seconds.

---

## 9. Phase 4 — One e2e WebSocket Test (Days 15-16)

One realistic round-trip through the actual FastAPI app. Use `httpx.AsyncClient` + `starlette.testclient.WebSocketTestSession`. **This is the only phase that runs the streaming LLM path** — it relies on the streaming half of the Phase 0 shim (`.create(stream=True)` → async chunk iterator). Queue the `commit` with its `arguments` split across ≥2 chunks so the narrative stream extractor fires.

### File

```
tests/e2e/
  test_websocket_full_turn.py
```

### What it covers

1. Build a `WebFrontendAdapter` with `ToolCallingMockLLM`, point it at `tests/fixtures/stories`.
2. `with TestClient(app).websocket_connect("/ws") as ws:`
3. Send `register_or_rejoin` with `player_id="test_player"`.
4. Walk pregame flow → start `tiny.yaml`.
5. Queue the mock to return `commit` with a narrative artifact + state change.
6. Send `input` message.
7. Assert: WS receives a `narrative` message with the queued text; `game_state.version` advanced; `saves/` (in `tmp_path`) contains the session JSON.

This single test exercises: WS handshake, session handler, pregame handler, game-loop handler, GameKernel, Architect, observer, WebSocketManager, serializer. If it stays green, the wiring is intact.

### Phase 4 Done When

- One test, passes, runs in < 3 seconds.
- Documented in [`developer-guide.md`](developer-guide.md) as the e2e smoke test.

---

## 10. Phase 5 (Optional) — Coverage Baseline

Run once, save the report, **do not enforce a threshold**.

```bash
pytest --cov=src --cov-report=html --cov-report=term-missing
```

Use the report to identify untested critical paths for future test work. **Do NOT add `--cov-fail-under` to CI** — that incentivizes garbage tests written for line coverage.

Acceptable outcome: a one-page summary under `docs/contributing/test-coverage-baseline.md` listing the top 10 untested critical paths as a known-debt registry.

---

## 11. Risks & Open Questions

| Risk | Mitigation |
|------|------------|
| Architect's tool-call dispatch depends on subtle response shape from `chat.completions.create`. Shim might miss a field. | Copy class structure directly from [`claude_adapter.py:84-289`](../../src/adapters/claude_adapter.py#L84) — that's a working reference. Diff any added fields against current calls in `architect.py`. |
| `pytest-asyncio` event-loop scoping conflicts with GameKernel's internal asyncio usage (`_run_coroutine_sync`, [`game_kernel.py:157`](../../src/core/game_kernel.py#L157)). | Use `asyncio_mode="auto"` + `loop_scope="function"`. If issues persist, mark integration tests `@pytest.mark.asyncio(loop_scope="module")` only where needed. |
| `tiny.yaml` may need updates as `story_models.py` evolves; tests become brittle. | Keep `tiny.yaml` minimal. When schema changes, fixture update is part of the same PR as the schema change. Treat the fixture as part of the schema contract. |
| `StateManager` may write shared state (save-code maps, session store) under `save_dir`; if anything is written to a *global* path instead, `tmp_path` isolation breaks and tests get cross-run pollution. | **Phase 0 verification step** (not Phase 3): construct `StateManager(save_dir=tmp_path)`, run a save, and assert nothing was written outside `tmp_path`. If a global path is found, fix it before Phase 1. |
| Streaming path (`_streaming_llm_call`, [`architect.py:2970`](../../src/core/architect.py#L2970)) consumes an async iterator of chunks, **not** `chat.completions.create`'s `_Completion`. It is the **default** whenever a frontend adapter is attached ([:528](../../src/core/architect.py#L528)), so Phase 4 inherently runs it. | **Build the streaming shim in Phase 0** (moved up from a "Phase 2.5 follow-up"). Phase 1–3 still run non-streaming (no frontend adapter) by design; Phase 4 attaches a real adapter and exercises streaming end-to-end. Emit `arguments` across ≥2 chunks so the narrative extractors actually run. |
| Test suite grows fast, becomes slow, CI times out. | Budget: total `pytest` runtime stays < 30s through Phase 4. If breached, profile with `--durations=20` and fix the slowest culprits before adding tests. |
| Contributor unaware test infra exists and writes ad-hoc tests. | After Phase 4, [`developer-guide.md`](developer-guide.md) gains a "Writing tests" section pointing at `tests/conftest.py`, `tests/contracts/`, and the `tc(...)` helper. |

---

## 12. PR Checklist for New Architect Tests

Any test added after this rollout should answer **yes** to all of these:

- [ ] Asserts a documented invariant (cite the line or doc the invariant comes from).
- [ ] Uses `mock_tool_llm`, never real network.
- [ ] Runs in under 200ms on a developer laptop.
- [ ] Names match: `test_<verb>_<object>_<expected_outcome>` (e.g. `test_commit_replaces_array_value`).
- [ ] Uses `tmp_path` for any filesystem effect.
- [ ] Doesn't reference a real story ID (`example`, `form_demo`) — fixtures only.
- [ ] If it tests a new Architect behavior, the behavior is also documented in either [`architect_system.txt`](../../prompts/architect_system.txt) or [`architect-design.md`](architect-design.md).

---

## 13. Day-1 Starter Commands

For whoever picks this up:

```bash
# 1. Make the requirements file
cat > requirements-test.txt <<'EOF'
pytest>=8.0,<9.0
pytest-asyncio>=0.23,<1.0
pytest-cov>=5.0
EOF

# 2. Install
pip install -r requirements-test.txt

# 3. Skeleton
mkdir -p tests/{contracts,unit,integration,e2e,fixtures/stories,helpers}
touch tests/__init__.py tests/helpers/__init__.py
touch tests/conftest.py tests/helpers/mock_llm_tool_calling.py

# 4. Add [tool.pytest.ini_options] block to pyproject.toml (see §5.3)

# 5. Verify pytest finds nothing yet but doesn't error
pytest -q
# Expected output: "no tests ran in 0.XXs"

# 6. Write the shim (§5.4), then its acceptance test, then iterate.
```

---

## 14. After This Rollout

The natural next initiatives, in order:

1. **CI pipeline** (separate plan) — wire `pytest`, ESLint, ruff, and a `story-agnostic` grep guard into GitHub Actions on every PR. Trivial once this rollout lands.
2. **`architect.py` decomposition** (separate plan) — with contract tests as the safety net, split the 3071-line file into the package layout proposed in the project-level PM brief.
3. **Schema-sync verification** — parse `prompts/story_format_description.md` headings, diff against `src/models/story_models.py` field names, fail PR on drift. Builds on the test harness's Pydantic loading.

None of these are blocked on each other after Phase 4 of this plan completes.
