# AI-Native Editor for Custom UI Stories

> Design discussion — 2026-04-07

---

## Context

The Wenyoo fiction engine supports two story types:
- **Traditional text stories** — node graph with choices, connections, characters
- **Custom UI stories** — fully custom HTML/CSS/JS frontend (e.g. `arcane_forge`) connected to the backend via a WebSocket SDK bridge

The existing editor (ReactFlow-based) works well for traditional stories but has a fundamental disconnect from custom UI stories: the `main.yaml` is edited in the node graph, while `frontend/` files (HTML/CSS/JS) are edited externally in an IDE. The workflow is: edit YAML → edit frontend in VS Code → restart backend → test in browser.

---

## The Core Shift: AI-Native, Not IDE-Native

The fundamental reframe is to **not build a better IDE**. Instead:

> The user doesn't edit code. The user directs the AI, and the AI builds the UI.

```
Traditional IDE:         AI-Native Editor:

User → Code → UI         User → Intent → AI → UI
                                          ↑    │
                                          └────┘
                                       feedback loop
```

The editor is a **conversation + canvas** where the AI assistant is the primary builder. The user thinks in terms of story intent; the AI translates that into the full technical stack.

---

## Why This Works Especially Well Here

This isn't a generic "AI writes code" tool. There are structural advantages specific to this platform:

1. **Bounded problem space** — The frontend only needs to do a few things: render state, send actions via the SDK, respond to state updates. The SDK is the entire API surface.

2. **AI already understands the story** — The same AI that helps write story nodes, variables, and Architect prompts can also generate the UI that presents them. It has full context of what `forge_energy` means, what `conjured_materials` looks like, what the Architect expects.

3. **Two-way coherence** — When the user adds a new variable in the node graph, the AI can proactively suggest UI changes. When the user asks for a new UI element, the AI knows it needs to add variables and `client_context` entries too. **The AI maintains the contract between YAML and frontend.**

---

## Editor Layout

Three zones, not five panels:

```
┌──────────────────────────────────────────────────┐
│                 AI-Native Editor                  │
│                                                   │
│  ┌─────────────────┐  ┌───────────────────────┐  │
│  │   Node Graph     │  │    Live Canvas         │  │
│  │   (story logic)  │  │                        │  │
│  │                  │  │   ┌────────────────┐   │  │
│  │   [forge_chamber]│  │   │ Generated UI   │   │  │
│  │        │         │  │   │ (live preview) │   │  │
│  │        ▼         │  │   │                │   │  │
│  │   [next_scene]   │  │   └────────────────┘   │  │
│  │                  │  │                        │  │
│  └─────────────────┘  └───────────────────────┘  │
│                                                   │
│  ┌────────────────────────────────────────────┐  │
│  │  💬 AI Assistant                            │  │
│  │                                             │  │
│  │  "Add a particle effect when materials      │  │
│  │   are combined, and show the result in      │  │
│  │   the collection panel"                     │  │
│  │                                             │  │
│  │  > AI: Updated frontend with particle       │  │
│  │    system on forge action. Added             │  │
│  │    collection_view to client_context so      │  │
│  │    the Architect knows about the new panel.  │  │
│  │    [Preview updated ↑]                      │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

- **Node Graph** — story structure (existing, unchanged)
- **Live Canvas** — the actual custom UI, always running in a hot-reloaded iframe
- **AI Chat** — the primary way to build and modify the UI

---

## The AI's Capabilities in This Mode

The AI assistant isn't just answering questions. It's an **agent that operates on the full story package**.

### 1. Generate from Intent

> "Build me a potion brewing interface with a cauldron, ingredient slots, and a recipe book"

The AI generates:
- `frontend/index.html` — layout and structure
- `frontend/app.js` — SDK integration, state management
- `frontend/style.css` — visual design
- Updates `main.yaml` — `initial_variables`, `client_context.views`, `frontend` config

Everything wired together correctly from the start.

### 2. Refine from Visual Feedback

> *User clicks on the energy bar in the canvas*
> "Make this animate smoothly and turn red below 20%"

The AI knows exactly which DOM element, which CSS, which variable binding. It makes a surgical edit.

### 3. Maintain Cross-Layer Coherence

> User adds a new `enchantment_history` variable in the node graph

AI proactively: *"I see you added `enchantment_history`. Want me to add a history panel to the UI that shows past enchantments? I'll also update the Architect's `client_context` so it knows to reference this panel when narrating results."*

### 4. Wire Architect Interactions

> "When the player drags a material onto the anvil, the Architect should evaluate the enchantment"

The AI generates:
- **Frontend**: drag handler → `sdk.sendArchitectTask('evaluate_enchantment', { material, weapon })`
- **YAML**: `client_context` description so the Architect knows what "evaluate enchantment" means
- **YAML**: variable structure the Architect should write results into
- **Frontend**: listener for state update → renders the Architect's response

This is the killer feature — **the AI bridges the gap between "what the player does in the UI" and "what the Architect AI should do in response."** No other tool can do this because no other tool understands both sides.

---

## Interaction Patterns

### Pattern 1: Conversational Building
```
User: "I want a card game interface"
AI:   generates full card game UI + YAML bindings

User: "The cards should fan out in an arc"
AI:   updates CSS/JS, preview updates live

User: "When I play a card, the Architect should narrate the effect"
AI:   wires up SDK action + client_context + Architect prompt
```

### Pattern 2: Point-and-Modify
```
User: *selects element in canvas*
User: "Change this to a circular progress indicator"
AI:   replaces the element, preserves data binding
```

### Pattern 3: Cross-Layer Refactoring
```
User: "Rename forge_energy to mana"
AI:   updates main.yaml variables, all frontend references,
      client_context descriptions, Architect prompts — everything
```

### Pattern 4: Template Kickstart
```
User: "Start from a shop interface template"
AI:   generates a complete shop UI package

User: "But make it a magical apothecary"
AI:   re-themes everything while keeping the interaction structure
```

---

## Comparison: Generic AI IDE vs AI-Native Story Editor

| Generic AI IDE | AI-Native Story Editor |
|---|---|
| AI writes code, user reviews | AI builds the full story package — YAML + frontend + Architect prompts — as one coherent unit |
| User needs to understand the code | User only needs to understand the story intent |
| AI doesn't know the runtime | AI knows the SDK, the WebSocket bridge, the Architect's capabilities, the variable system |
| Feedback is "does it compile" | Feedback is "does it play right" — live in the canvas |
| One-shot generation | Continuous refinement in a live environment |

---

## Implementation Direction

The key pieces to build:

### 1. AI Agent with Story-Package Tools
The assistant needs tools to:
- Read/write `frontend/` files
- Modify specific YAML sections (`initial_variables`, `client_context`, `frontend` config)
- Trigger preview iframe refresh
- Inspect current canvas element state (for point-and-modify)

The AI gets the same file access the editor has, exposed through tool calls.

### 2. Live Canvas with Hot Reload
The preview iframe needs instant refresh when files change. Likely a dev-mode file watcher on the `frontend/` directory with a lightweight dev server or WebSocket-based reload signal.

### 3. Canvas ↔ AI Bridge
When the user clicks/selects an element in the canvas, that context (element type, current variable bindings, position, rendered state) flows into the AI conversation as context. This is what makes "point and modify" work without the user having to describe what they're looking at.

### 4. Coherence Validation
After the AI makes changes, run a quick check:
- Are all variables used in frontend defined in `initial_variables`?
- Are all `sdk.sendArchitectTask` calls covered by a `client_context.views` entry?
- Are all `sdk.dispatchAction` IDs handled by the backend router?

Surface mismatches as inline warnings in the chat, not blocking errors.

---

## Phased Approach

### Phase 1 — AI Chat + Live Canvas (highest value, foundational)
- Embed the custom UI in a live iframe canvas next to the node graph
- Add AI chat panel with access to story-package tools (read/write files + YAML)
- Hot-reload on file changes
- This makes the edit-test cycle immediate and unlocks conversational building

### Phase 2 — Point-and-Modify
- Canvas selection sends element context to AI
- AI can target specific elements for surgical edits
- Variable inspector shows `initial_variables` with live values during play

### Phase 3 — Coherence & Proactive Suggestions
- AI proactively suggests UI updates when YAML changes (new variables, new nodes)
- Validation layer surfaces YAML ↔ frontend mismatches
- AI-generated `client_context` descriptions from actual UI structure

---

## Open Questions

1. **Scope of AI file access** — Should the AI be able to create arbitrary files, or only within the story package directory?
2. **Canvas security** — The iframe sandbox needs to be loosened for dev mode (hot reload, element selection bridge). How do we keep this safe?
3. **Variable ↔ UI connection** — Convention-based (frontend just reads variables by name) vs. explicit manifest? Convention is simpler but harder to validate.
4. **Template library** — What common custom UI patterns (shop, card game, forge, lab) should ship as templates to kickstart new stories?
