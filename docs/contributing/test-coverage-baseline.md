# Test Coverage Baseline

**Captured:** 2026-05-29  •  **Suite:** 74 tests, LLM-free  •  **Command:** `pytest --cov=src --cov-report=term-missing`

> Informational known-debt registry, **not** an enforced gate. There is intentionally **no `--cov-fail-under`** — see [`test-harness-rollout.md`](test-harness-rollout.md) §10. Coverage % is a map of where risk hides, not a target to game.

## Headline

```
TOTAL    11932 stmts    7544 missed    37% covered
```

37% is the expected starting point: the Phase 1-4 harness deliberately targets the Architect's **load-bearing invariants** and core primitives, not breadth. This file lists the highest-risk untested paths so future test work (and the upcoming `architect.py` decomposition) can aim deliberately.

## Top 10 Untested Critical Paths

Ranked by *blast radius if silently broken*, not by line count.

| # | Module | Cover | Why it's critical |
|---|--------|-------|-------------------|
| 1 | [`core/state_context_builder.py`](../../src/core/state_context_builder.py) | **0%** | Builds the world-index/context prompt the Architect reasons over. Broken context → wrong gameplay, no error. Highest-value next target. |
| 2 | [`adapters/base_llm_adapter.py`](../../src/adapters/base_llm_adapter.py) | **0%** | The default OpenAI-compatible provider: tool-call loop, JSON repair, provider-option passthrough. Every non-Claude deployment runs this. |
| 3 | [`core/state_manager.py`](../../src/core/state_manager.py) | 34% | Save/load + versioning. Untested serialization paths = silent save corruption. (Phase 3 covers happy-path round-trip only.) |
| 4 | [`models/game_state.py`](../../src/models/game_state.py) | 37% | The single source of truth — 950 uncovered stmts. `apply_merge_patch` core is covered; perception, derived vars, character/object mutation paths are not. |
| 5 | [`adapters/claude_adapter.py`](../../src/adapters/claude_adapter.py) | **0%** | The OpenAI-shim translation (`tool_use`↔`tool_calls`, streaming, cache breakpoints). Subtle and provider-specific — exactly where bugs hide. |
| 6 | [`core/text_processor.py`](../../src/core/text_processor.py) | 28% | `{action}`, `{{object}}`, `{@char}` hyperlink rendering — directly player-visible. |
| 7 | [`core/variable_resolver.py`](../../src/core/variable_resolver.py) | 29% | Dotted-path resolution + condition evaluation. Gates action availability and trigger firing. |
| 8 | [`core/lua_runtime.py`](../../src/core/lua_runtime.py) | 23% | Scripted-effect sandbox (lupa). Author-supplied logic executes here. |
| 9 | [`core/ticker_service.py`](../../src/core/ticker_service.py) | 28% | Timed/scheduled events — async, stateful, easy to regress invisibly. |
| 10 | [`adapters/routes/plan_routes.py`](../../src/adapters/routes/plan_routes.py) (8%), [`story_routes.py`](../../src/adapters/routes/story_routes.py) (18%) | low | Editor save / version / connection-compile. Data-loss risk for authors. |

## Well-covered already (no action needed)

`core/architect.py` 60%, `core/background_materialization.py` 73%, `adapters/utils/game_state_serializer.py` 72%, `models/story_models.py` 55%, `adapters/web_frontend_adapter.py` 55% — the hot paths the contract + integration tests drive.

## Deliberately near-zero (low priority)

`main.py` (bootstrap), `input_parser.py` (legacy, superseded by Architect), `mock_llm_adapter.py` / `ollama_adapter.py` (test/optional providers), `status_display_resolver.py` (cosmetic HUD). Not worth early test investment.

## Suggested next test targets (post-CI)

1. `state_context_builder` — pure-ish input→prompt-string transform; cheap to unit test, huge value (#1).
2. `base_llm_adapter` tool-loop + `_repair_json` — drive with a stubbed `httpx`/OpenAI client; mirrors the Architect shim work already done.
3. `state_manager` save/load edge cases — partial states, schema-version mismatches, concurrent sessions.

Re-run `pytest --cov=src --cov-report=html` and open `htmlcov/index.html` to drill into specific missed lines before starting.
