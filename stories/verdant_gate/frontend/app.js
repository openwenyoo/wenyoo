import * as THREE from "https://unpkg.com/three@0.179.1/build/three.module.js";

const bridge = window.WenyooStorySDK.createBridge();

const HOTSPOTS = {
    gap_bridge: {
        id: "gap_bridge",
        label: "Gap Span",
        accepts: ["bridgeable"],
        solvePath: "bridge_crossing",
        guidance: "Place a stable spanning object here to cross the cracked gap.",
        position: new THREE.Vector3(0, 0.42, 0.65),
        markerScale: new THREE.Vector3(1.15, 0.18, 0.72),
        placement: {
            position: new THREE.Vector3(0, 0.42, 0.65),
            rotationY: 0,
        },
    },
    vine_knot: {
        id: "vine_knot",
        label: "Vine Knot",
        accepts: ["cutting"],
        solvePath: "cut_binding",
        guidance: "A sharp or sawing object could sever the gate's vine binding.",
        position: new THREE.Vector3(-0.55, 1.22, -1.85),
        markerScale: new THREE.Vector3(0.42, 0.42, 0.42),
        placement: {
            position: new THREE.Vector3(-0.9, 0.65, -1.4),
            rotationY: 0.7,
        },
    },
    pressure_plate: {
        id: "pressure_plate",
        label: "Pressure Plate",
        accepts: ["heavy"],
        solvePath: "weight_trigger",
        guidance: "A dense object that stays put could hold this plate down.",
        position: new THREE.Vector3(-2.4, 0.2, -0.72),
        markerScale: new THREE.Vector3(0.72, 0.1, 0.72),
        placement: {
            position: new THREE.Vector3(-2.4, 0.44, -0.72),
            rotationY: 0,
        },
    },
    release_chain: {
        id: "release_chain",
        label: "Release Chain",
        accepts: ["hooking", "climbable"],
        solvePath: "chain_release",
        guidance: "A hook or something climbable could help you reach and pull the chain.",
        position: new THREE.Vector3(1.72, 1.9, -1.08),
        markerScale: new THREE.Vector3(0.34, 0.9, 0.34),
        placement: {
            position: new THREE.Vector3(1.2, 0.44, -1.05),
            rotationY: -0.45,
        },
    },
};

const DOCK_POSITIONS = [
    new THREE.Vector3(-2.8, 0.55, 2.15),
    new THREE.Vector3(-1.7, 0.55, 2.15),
    new THREE.Vector3(-0.6, 0.55, 2.15),
    new THREE.Vector3(0.5, 0.55, 2.15),
    new THREE.Vector3(1.6, 0.55, 2.15),
];

const state = {
    initPayload: null,
    gameState: { variables: {} },
    selectedHotspotId: null,
    selectedItemId: null,
    generating: false,
    pendingRequest: null,
    lastAnalysis: null,
};

const elements = {
    objectiveTitle: document.getElementById("objective-title"),
    objectiveText: document.getElementById("objective-text"),
    sceneStatus: document.getElementById("scene-status"),
    itemCountPill: document.getElementById("item-count-pill"),
    hintPill: document.getElementById("hint-pill"),
    hotspotChip: document.getElementById("hotspot-chip"),
    hotspotDetails: document.getElementById("hotspot-details"),
    itemChip: document.getElementById("item-chip"),
    itemDetails: document.getElementById("item-details"),
    feed: document.getElementById("feed"),
    itemsRow: document.getElementById("items-row"),
    commandInput: document.getElementById("command-input"),
    generateButton: document.getElementById("generate-button"),
    consoleStatus: document.getElementById("console-status"),
    clearSelectionButton: document.getElementById("clear-selection-button"),
    hintButton: document.getElementById("hint-button"),
    returnMenuButton: document.getElementById("return-menu-button"),
    sceneCanvas: document.getElementById("scene-canvas"),
};

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

function slugify(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 40) || "generated_item";
}

function cloneValue(value) {
    return JSON.parse(JSON.stringify(value));
}

function getVariables() {
    return state.gameState && state.gameState.variables ? state.gameState.variables : {};
}

function getGeneratedItems() {
    const items = getVariables().generated_items;
    return Array.isArray(items) ? items : [];
}

function getItemLimit() {
    const limit = Number(getVariables().object_limit || 5);
    return Number.isFinite(limit) && limit > 0 ? limit : 5;
}

function getPuzzleState() {
    return getVariables().puzzle_state || {};
}

function getHintCount() {
    const count = Number(getVariables().hint_tokens_remaining || 0);
    return Number.isFinite(count) && count >= 0 ? count : 0;
}

function getSelectedHotspot() {
    return state.selectedHotspotId ? HOTSPOTS[state.selectedHotspotId] : null;
}

function getSelectedItem() {
    return getGeneratedItems().find((item) => item.id === state.selectedItemId) || null;
}

function extractTextFromMessage(message) {
    if (!message || typeof message !== "object") {
        return "";
    }
    if (typeof message.text === "string") {
        return message.text;
    }
    if (message.client_content && typeof message.client_content.text === "string") {
        return message.client_content.text;
    }
    if (message.response_client && typeof message.response_client.text === "string") {
        return message.response_client.text;
    }
    if (typeof message.raw_text === "string") {
        return message.raw_text;
    }
    if (typeof message.content === "string") {
        return message.content;
    }
    return "";
}

function appendFeed(kind, title, text) {
    if (!text) {
        return;
    }
    const entry = document.createElement("article");
    entry.className = `feed-entry ${kind || "system"}`;

    const heading = document.createElement("strong");
    heading.textContent = title;
    entry.appendChild(heading);

    const body = document.createElement("div");
    body.textContent = text;
    entry.appendChild(body);

    elements.feed.prepend(entry);
}

function setConsoleStatus(text) {
    elements.consoleStatus.textContent = text;
}

function getCompatibility(item, hotspot) {
    if (!item || !hotspot) {
        return {
            compatible: false,
            reason: "Select an item and a hotspot to compare them.",
        };
    }
    const affordances = Array.isArray(item.affordances) ? item.affordances : [];
    const match = affordances.find((affordance) => hotspot.accepts.includes(affordance));
    if (match) {
        return {
            compatible: true,
            matchingAffordance: match,
            reason: `${item.label || "This item"} can satisfy ${hotspot.label.toLowerCase()} via ${match}.`,
        };
    }
    return {
        compatible: false,
        reason: `${item.label || "This item"} does not expose the affordance ${hotspot.accepts.join(" or ")} required here.`,
    };
}

function makeTagRow(values) {
    if (!Array.isArray(values) || values.length === 0) {
        return "";
    }
    return `
        <div class="tag-row">
            ${values.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
        </div>
    `;
}

function renderHotspotDetails() {
    const hotspot = getSelectedHotspot();
    if (!hotspot) {
        elements.hotspotChip.className = "chip neutral";
        elements.hotspotChip.textContent = "No hotspot selected";
        elements.hotspotDetails.className = "detail-card empty-state";
        elements.hotspotDetails.textContent =
            "Select a mechanism in the scene to see what kind of object can solve it.";
        return;
    }

    const item = getSelectedItem();
    const compatibility = item ? getCompatibility(item, hotspot) : null;

    elements.hotspotChip.className = compatibility
        ? compatibility.compatible
            ? "chip good"
            : "chip bad"
        : "chip warn";
    elements.hotspotChip.textContent = hotspot.label;

    elements.hotspotDetails.className = "detail-card";
    elements.hotspotDetails.innerHTML = `
        <div class="subtle-label">Mechanism</div>
        <p>${escapeHtml(hotspot.guidance)}</p>
        <div class="detail-list">
            <div><strong>Needs:</strong> ${escapeHtml(hotspot.accepts.join(" or "))}</div>
            <div><strong>Solves as:</strong> ${escapeHtml(hotspot.solvePath)}</div>
            ${compatibility ? `<div><strong>Current fit:</strong> ${escapeHtml(compatibility.reason)}</div>` : ""}
        </div>
        ${makeTagRow(hotspot.accepts)}
    `;
}

function renderItemDetails() {
    const item = getSelectedItem();
    if (!item) {
        elements.itemChip.className = "chip neutral";
        elements.itemChip.textContent = "No item selected";
        elements.itemDetails.className = "detail-card empty-state";
        elements.itemDetails.textContent =
            "Generate an item to inspect its affordances and predicted fit.";
        return;
    }

    const hotspot = getSelectedHotspot();
    const compatibility = hotspot ? getCompatibility(item, hotspot) : null;
    const statusClass = item.status === "rejected"
        ? "bad"
        : compatibility
            ? compatibility.compatible ? "good" : "bad"
            : "warn";

    elements.itemChip.className = `chip ${statusClass}`;
    elements.itemChip.textContent = item.label || item.id;

    elements.itemDetails.className = "detail-card";
    elements.itemDetails.innerHTML = `
        <div class="subtle-label">Generated object</div>
        <p>${escapeHtml(item.summary || "No summary available.")}</p>
        <div class="detail-list">
            <div><strong>Type:</strong> ${escapeHtml(item.canonical_type || "unknown")}</div>
            <div><strong>Size:</strong> ${escapeHtml(item.size_class || "unknown")}</div>
            <div><strong>Preferred anchors:</strong> ${escapeHtml((item.preferred_anchor_ids || []).join(", ") || "none")}</div>
            <div><strong>Placement:</strong> ${escapeHtml(item.placement_rules?.notes || "No placement notes provided.")}</div>
            <div><strong>Prediction:</strong> ${escapeHtml(
                compatibility
                    ? compatibility.reason
                    : (item.rejection_reason || "Select a hotspot to see a concrete fit prediction.")
            )}</div>
        </div>
        ${makeTagRow(item.affordances)}
        ${makeTagRow(item.material_tags)}
    `;
}

function renderItems() {
    const items = getGeneratedItems();
    const limit = getItemLimit();

    elements.itemCountPill.textContent = `${items.length} / ${limit} items`;
    elements.itemsRow.innerHTML = "";
    elements.itemsRow.classList.toggle("empty", items.length === 0);

    if (items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "No generated items yet.";
        elements.itemsRow.appendChild(empty);
        return;
    }

    items.forEach((item) => {
        const card = document.createElement("article");
        card.className = "item-card";
        if (item.id === state.selectedItemId) {
            card.classList.add("selected");
        }
        if (item.used_to_solve) {
            card.classList.add("used");
        }

        card.innerHTML = `
            <div class="item-header">
                <div>
                    <div class="item-title">${escapeHtml(item.label || item.id)}</div>
                    <div class="item-meta">${escapeHtml(item.canonical_type || "unknown")} · ${escapeHtml(item.size_class || "unknown")}</div>
                </div>
                <span class="chip ${item.used_to_solve ? "good" : "neutral"}">${item.used_to_solve ? "Placed" : "Ready"}</span>
            </div>
            <div class="item-summary">${escapeHtml(item.summary || "")}</div>
            ${makeTagRow(item.affordances)}
            <div class="item-actions">
                <button class="ghost-button select-button">Select</button>
                <button class="ghost-button delete-button"${item.used_to_solve ? " disabled" : ""}>Delete</button>
            </div>
        `;

        card.querySelector(".select-button").addEventListener("click", () => {
            state.selectedItemId = item.id;
            renderAll();
        });

        card.querySelector(".delete-button").addEventListener("click", () => {
            deleteItem(item.id);
        });

        elements.itemsRow.appendChild(card);
    });
}

function renderObjective() {
    const variables = getVariables();
    elements.objectiveTitle.textContent = variables.objective_title || "Objective";

    const puzzleState = getPuzzleState();
    if (puzzleState.gate_open) {
        const hotspot = HOTSPOTS[puzzleState.solved_anchor_id];
        const item = getGeneratedItems().find((entry) => entry.id === puzzleState.solved_with_item_id);
        elements.objectiveText.textContent = `Solved via ${hotspot ? hotspot.label : "a valid mechanism"} using ${item ? item.label : "a generated item"}.`;
        elements.sceneStatus.textContent = "The Verdant Gate is opening. Your object solved the ruin.";
    } else {
        elements.objectiveText.textContent = variables.objective_text || "";
        elements.sceneStatus.textContent = "Inspect the ruin, then create something plausible.";
    }
}

function renderHintStatus() {
    const count = getHintCount();
    elements.hintPill.textContent = `${count} hint${count === 1 ? "" : "s"}`;
    elements.hintButton.disabled = count <= 0;
}

function renderAll() {
    renderObjective();
    renderHintStatus();
    renderItems();
    renderHotspotDetails();
    renderItemDetails();
    sceneController.setState({
        items: getGeneratedItems(),
        puzzleState: getPuzzleState(),
        selectedItemId: state.selectedItemId,
        selectedHotspotId: state.selectedHotspotId,
    });
}

function syncGameState(nextState) {
    if (!nextState || typeof nextState !== "object") {
        return;
    }
    state.gameState = nextState;

    const selectedExists = getGeneratedItems().some((item) => item.id === state.selectedItemId);
    if (!selectedExists) {
        state.selectedItemId = null;
    }
    renderAll();
}

function mergePatchVariables(patchVariables, displayText) {
    bridge.sendDeterministicAction("merge_patch", {
        patch: {
            variables: patchVariables,
        },
    }, {
        display_text: displayText,
    });
}

function normalizeGeneratedItem(rawResult, requestText) {
    const now = new Date().toISOString();
    const fallbackLabel = rawResult.label || requestText || "Generated Item";
    const itemId = rawResult.id || slugify(fallbackLabel);

    return {
        id: itemId,
        request_text: rawResult.request_text || requestText,
        label: fallbackLabel,
        summary: rawResult.summary || "A plausible low-poly approximation.",
        canonical_type: rawResult.canonical_type || "unknown",
        size_class: rawResult.size_class || "medium",
        material_tags: Array.isArray(rawResult.material_tags) ? rawResult.material_tags : [],
        affordances: Array.isArray(rawResult.affordances) ? rawResult.affordances : [],
        preferred_anchor_ids: Array.isArray(rawResult.preferred_anchor_ids) ? rawResult.preferred_anchor_ids : [],
        placement_rules: rawResult.placement_rules || {
            mode: "place_on_ground",
            stable: true,
            notes: "No placement notes provided.",
        },
        interaction_rules: rawResult.interaction_rules || {
            success_if: "",
            failure_if: "",
        },
        visual_spec: rawResult.visual_spec || {
            proxy_kind: "unknown",
            primary_color: "#d7dbc4",
            secondary_color: "#6b6f56",
            accent_color: "#f0d97a",
            silhouette: "simple low-poly block",
            scale_hint: 1,
            approximation: true,
        },
        rejection_reason: rawResult.rejection_reason || "",
        status: "inventory",
        generated_at: now,
        placed_at: null,
        used_to_solve: false,
    };
}

function persistAcceptedItem(rawResult, requestText) {
    const currentItems = getGeneratedItems();
    const nextItem = normalizeGeneratedItem(rawResult, requestText);
    const deduped = currentItems.filter((item) => item.id !== nextItem.id);
    mergePatchVariables({
        generated_items: [...deduped, nextItem],
        last_generation: nextItem,
    }, `Generate ${nextItem.label}`);
    appendFeed("system", "Object generated", `${nextItem.label}: ${nextItem.summary}`);
    setConsoleStatus(`Generated ${nextItem.label}. Select it, then click a hotspot.`);
}

function deleteItem(itemId) {
    const item = getGeneratedItems().find((entry) => entry.id === itemId);
    if (!item || item.used_to_solve) {
        return;
    }
    const nextItems = getGeneratedItems().filter((entry) => entry.id !== itemId);
    if (state.selectedItemId === itemId) {
        state.selectedItemId = null;
    }
    mergePatchVariables({
        generated_items: nextItems,
    }, `Delete ${item.label || item.id}`);
    appendFeed("system", "Object deleted", `${item.label || item.id} was removed from the scene inventory.`);
}

function solveWithItem(item, hotspot, compatibility) {
    if (!item || !hotspot || !compatibility.compatible) {
        return;
    }

    const nextItems = getGeneratedItems().map((entry) => {
        if (entry.id !== item.id) {
            return entry;
        }
        return {
            ...entry,
            placed_at: hotspot.id,
            used_to_solve: true,
        };
    });

    mergePatchVariables({
        generated_items: nextItems,
        puzzle_state: {
            gate_open: true,
            solved: true,
            solution_path: hotspot.solvePath,
            solved_anchor_id: hotspot.id,
            solved_with_item_id: item.id,
        },
    }, `Apply ${item.label} to ${hotspot.label}`);

    appendFeed("system", "Mechanism resolved", `${item.label} solved ${hotspot.label.toLowerCase()} via ${compatibility.matchingAffordance}.`);
    setConsoleStatus(`Solved with ${item.label}. The Verdant Gate is opening.`);
}

function tryApplySelectedItemToHotspot(hotspotId) {
    state.selectedHotspotId = hotspotId;
    const hotspot = HOTSPOTS[hotspotId];
    const item = getSelectedItem();

    if (!item) {
        renderAll();
        return;
    }

    if (getPuzzleState().gate_open) {
        setConsoleStatus("The puzzle is already solved. You can still inspect the scene.");
        renderAll();
        return;
    }

    const compatibility = getCompatibility(item, hotspot);
    if (!compatibility.compatible) {
        appendFeed("error", "Invalid fit", compatibility.reason);
        setConsoleStatus(compatibility.reason);
        renderAll();
        return;
    }

    solveWithItem(item, hotspot, compatibility);
    renderAll();
}

function requestGeneration() {
    const requestText = elements.commandInput.value.trim();
    if (!requestText || state.generating) {
        return;
    }

    const currentItems = getGeneratedItems();
    if (currentItems.length >= getItemLimit()) {
        const message = `Item limit reached. Delete an item before generating another one.`;
        appendFeed("error", "Generation blocked", message);
        setConsoleStatus(message);
        return;
    }

    state.generating = true;
    state.pendingRequest = {
        kind: "generation",
        requestText,
    };
    elements.generateButton.disabled = true;
    elements.commandInput.value = "";
    setConsoleStatus(`Interpreting "${requestText}"...`);

    bridge.sendArchitectTask("ui_requested_generation", {
        action_id: "generate_object",
        active_view: "console",
        player_input: requestText,
        purpose: "Interpret the player's object request for the Verdant Gate diorama. Return only a structured result grounded in the story's generation contract. Do not narrate. Do not mutate world state in this step.",
        structured_input: {
            request_text: requestText,
            current_item_count: currentItems.length,
            object_limit: getItemLimit(),
            hotspot_contracts: getVariables().hotspot_contracts || [],
            puzzle_state: getPuzzleState(),
        },
        expected_output: "Return a structured verdict object describing whether the requested item is acceptable, what affordances it has, and which hotspot it best matches.",
        extra_context: {
            active_view: "console",
            ui_mode: "threejs_diorama",
        },
        input_type: "story_app",
    });
}

function requestHint() {
    if (state.pendingRequest) {
        return;
    }
    const count = getHintCount();
    if (count <= 0) {
        setConsoleStatus("No free hints remain in this slice.");
        return;
    }

    state.pendingRequest = { kind: "hint" };
    elements.hintButton.disabled = true;
    setConsoleStatus("Analyzing the scene for a grounded hint...");

    bridge.sendArchitectTask("tool_assisted_decision", {
        action_id: "request_hint",
        active_view: "analysis",
        task_profile: "uiDecision",
        purpose: "Provide one concise grounded hint for the Verdant Gate puzzle. Return only a structured result with hint_text, suggested_affordances, suggested_anchor_ids, and reason. Do not narrate. Do not mutate world state in this step.",
        structured_input: {
            puzzle_state: getPuzzleState(),
            generated_items: getGeneratedItems(),
            hotspot_contracts: getVariables().hotspot_contracts || [],
            hints_remaining: count,
        },
        expected_output: "Return a compact hint object for the sidebar.",
        extra_context: {
            active_view: "analysis",
            ui_mode: "threejs_diorama",
        },
        input_type: "story_app",
    });
}

function handleUiDecisionResult(content, response) {
    const structured = content.structured_result && content.structured_result.result
        ? content.structured_result.result
        : null;
    if (!structured || !state.pendingRequest) {
        return;
    }

    if (state.pendingRequest.kind === "generation") {
        const requestText = state.pendingRequest.requestText;
        state.lastAnalysis = structured;
        state.generating = false;
        elements.generateButton.disabled = false;
        state.pendingRequest = null;

        if (structured.status === "accepted") {
            persistAcceptedItem(structured, requestText);
            state.selectedItemId = structured.id || slugify(structured.label || requestText);
        } else {
            const title = structured.status === "needs_clarification" ? "Needs clarification" : "Rejected";
            const detail = structured.rejection_reason || structured.summary || "The request did not produce a usable object.";
            appendFeed("error", title, detail);
            setConsoleStatus(detail);
        }
        renderAll();
        return;
    }

    if (state.pendingRequest.kind === "hint") {
        state.pendingRequest = null;
        const hintText = structured.hint_text || structured.summary || "Try an object with a more grounded affordance.";
        const suggested = Array.isArray(structured.suggested_affordances) ? structured.suggested_affordances : [];
        const anchors = Array.isArray(structured.suggested_anchor_ids) ? structured.suggested_anchor_ids : [];
        appendFeed("system", "Hint", hintText);
        setConsoleStatus(hintText);

        const remaining = Math.max(0, getHintCount() - 1);
        mergePatchVariables({
            hint_tokens_remaining: remaining,
            last_hint: {
                hint_text: hintText,
                suggested_affordances: suggested,
                suggested_anchor_ids: anchors,
                reason: structured.reason || "",
            },
        }, "Consume hint");
        renderAll();
    }
}

function handleCommandResult(message) {
    const content = message && message.content ? message.content : {};
    if (content.game_state) {
        syncGameState(content.game_state);
    }

    const response = content.response || {};
    const taskType = response.task_type || content.structured_result?.task_type || "";
    const profile = response.task_profile || content.structured_result?.task_profile || "";

    if (profile === "uiDecision" || taskType === "ui_requested_generation" || state.pendingRequest) {
        handleUiDecisionResult(content, response);
    }

    if (response.deterministic_result && response.deterministic_result.display_text) {
        appendFeed("system", "State update", response.deterministic_result.display_text);
    }

    const responseText = extractTextFromMessage(content.response_client);
    if (responseText) {
        appendFeed("system", "Console", responseText);
        setConsoleStatus(responseText);
    }

    elements.generateButton.disabled = state.generating;
    renderAll();
}

function handleInit(payload) {
    state.initPayload = payload || {};
    elements.feed.innerHTML = "";
    syncGameState(payload.gameState || { variables: {} });

    if (payload.transcript && Array.isArray(payload.transcript)) {
        payload.transcript.slice().reverse().forEach((entry) => {
            const text = extractTextFromMessage(entry);
            if (text) {
                appendFeed("system", entry.type || "Transcript", text);
            }
        });
    }

    if (payload.perception && payload.perception.client_content?.text) {
        appendFeed("system", "Scene brief", payload.perception.client_content.text);
    }

    appendFeed("system", "Story app ready", "Inspect a mechanism, then generate a grounded object to solve it.");
    renderAll();
}

function handleEvent(message) {
    if (!message || typeof message !== "object") {
        return;
    }

    switch (message.type) {
        case "game_start":
            handleInit({
                gameState: message.content?.game_state,
                perception: message.content?.perception,
                transcript: message.content?.transcript || [],
            });
            return;
        case "game_state":
            syncGameState(message.content);
            return;
        case "command_result":
            handleCommandResult(message);
            return;
        case "perception": {
            const text = extractTextFromMessage(message);
            if (text) {
                appendFeed("system", "Perception", text);
            }
            return;
        }
        case "error": {
            const text = extractTextFromMessage(message) || "The story app received an unknown error.";
            appendFeed("error", "Error", text);
            setConsoleStatus(text);
            state.generating = false;
            state.pendingRequest = null;
            elements.generateButton.disabled = false;
            renderAll();
            return;
        }
        default: {
            const text = extractTextFromMessage(message);
            if (text) {
                appendFeed("system", message.type || "Message", text);
            }
        }
    }
}

class VerdantGateScene {
    constructor(container, handlers) {
        this.container = container;
        this.handlers = handlers;
        this.scene = new THREE.Scene();
        this.scene.fog = new THREE.Fog(0x1b2a2d, 9, 21);

        this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.shadowMap.enabled = false;
        container.appendChild(this.renderer.domElement);

        this.root = new THREE.Group();
        this.scene.add(this.root);

        this.hotspotGroup = new THREE.Group();
        this.root.add(this.hotspotGroup);

        this.itemGroup = new THREE.Group();
        this.root.add(this.itemGroup);

        this.previewGroup = new THREE.Group();
        this.root.add(this.previewGroup);

        this.hotspotMeshes = new Map();
        this.itemMeshes = new Map();
        this.itemBases = new Map();
        this.currentState = {
            items: [],
            puzzleState: {},
            selectedItemId: null,
            selectedHotspotId: null,
        };
        this.pointer = new THREE.Vector2();
        this.raycaster = new THREE.Raycaster();
        this.hovered = null;
        this.gateOpenValue = 0;

        this.controls = {
            radius: 9.1,
            azimuth: 0.2,
            elevation: 0.78,
            dragging: false,
            lastX: 0,
            lastY: 0,
        };

        this.buildScene();
        this.attachEvents();
        this.resize();
        this.animate();
    }

    material(color, options = {}) {
        return new THREE.MeshStandardMaterial({
            color,
            flatShading: true,
            roughness: options.roughness ?? 0.92,
            metalness: options.metalness ?? 0.06,
            emissive: options.emissive ?? 0x000000,
            emissiveIntensity: options.emissiveIntensity ?? 0,
            transparent: options.transparent ?? false,
            opacity: options.opacity ?? 1,
        });
    }

    buildScene() {
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.95));
        const sun = new THREE.DirectionalLight(0xfff4dd, 1.4);
        sun.position.set(5, 8, 4);
        this.scene.add(sun);

        const fill = new THREE.DirectionalLight(0x8fd8ff, 0.35);
        fill.position.set(-5, 4, 3);
        this.scene.add(fill);

        const base = new THREE.Mesh(
            new THREE.CylinderGeometry(5.4, 5.9, 1.2, 8),
            this.material(0x567b58)
        );
        base.position.y = -0.6;
        this.root.add(base);

        const soil = new THREE.Mesh(
            new THREE.CylinderGeometry(5.15, 5.45, 0.45, 8),
            this.material(0x31533b)
        );
        soil.position.y = -0.05;
        this.root.add(soil);

        const path = new THREE.Mesh(
            new THREE.BoxGeometry(2.6, 0.06, 4.5),
            this.material(0xb8b38f)
        );
        path.position.set(0, 0.03, 0.3);
        this.root.add(path);

        const gap = new THREE.Mesh(
            new THREE.BoxGeometry(2.2, 0.62, 1.1),
            this.material(0x16333a, { roughness: 0.6 })
        );
        gap.position.set(0, -0.16, 0.7);
        this.root.add(gap);

        this.buildTrees();
        this.buildRuins();
        this.buildDock();
        this.buildHotspots();
        this.updateCamera();
    }

    buildTrees() {
        const treePositions = [
            [-3.6, 0, -2.6],
            [3.2, 0, -2.7],
            [-4.0, 0, 1.4],
            [3.6, 0, 1.0],
        ];
        treePositions.forEach(([x, y, z], index) => {
            const trunk = new THREE.Mesh(
                new THREE.CylinderGeometry(0.16, 0.22, 1.3, 6),
                this.material(0x6b4b34)
            );
            trunk.position.set(x, y + 0.65, z);
            this.root.add(trunk);

            const crown = new THREE.Mesh(
                new THREE.ConeGeometry(0.85 + (index % 2) * 0.12, 1.6, 7),
                this.material(index % 2 === 0 ? 0x7cab57 : 0x8ec66a)
            );
            crown.position.set(x, y + 1.8, z);
            this.root.add(crown);
        });
    }

    buildRuins() {
        const stone = this.material(0x9ca590);
        const mossStone = this.material(0x70806b);

        const archLeft = new THREE.Mesh(new THREE.BoxGeometry(0.72, 2.8, 0.84), stone);
        archLeft.position.set(-1.05, 1.4, -2.0);
        this.root.add(archLeft);

        const archRight = new THREE.Mesh(new THREE.BoxGeometry(0.72, 2.8, 0.84), stone);
        archRight.position.set(1.05, 1.4, -2.0);
        this.root.add(archRight);

        const lintel = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.52, 0.96), mossStone);
        lintel.position.set(0, 2.72, -2.0);
        this.root.add(lintel);

        const steps = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.25, 1.15), stone);
        steps.position.set(0, 0.12, -1.1);
        this.root.add(steps);

        this.leftGatePivot = new THREE.Group();
        this.leftGatePivot.position.set(-0.38, 0, -1.66);
        this.root.add(this.leftGatePivot);

        const leftGate = new THREE.Mesh(new THREE.BoxGeometry(0.7, 2.05, 0.16), this.material(0x62705d));
        leftGate.position.set(-0.35, 1.03, 0);
        this.leftGatePivot.add(leftGate);

        this.rightGatePivot = new THREE.Group();
        this.rightGatePivot.position.set(0.38, 0, -1.66);
        this.root.add(this.rightGatePivot);

        const rightGate = new THREE.Mesh(new THREE.BoxGeometry(0.7, 2.05, 0.16), this.material(0x62705d));
        rightGate.position.set(0.35, 1.03, 0);
        this.rightGatePivot.add(rightGate);

        this.vineGroup = new THREE.Group();
        this.root.add(this.vineGroup);
        const vineMaterial = this.material(0x4c7f45);
        for (let i = 0; i < 5; i += 1) {
            const vine = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 1.25, 5), vineMaterial);
            vine.position.set(-0.42 + i * 0.2, 1.22 + (i % 2) * 0.06, -1.86);
            vine.rotation.z = 0.7 + i * 0.14;
            this.vineGroup.add(vine);
        }

        const chainMaterial = this.material(0x8d8f87, { metalness: 0.2, roughness: 0.6 });
        for (let i = 0; i < 6; i += 1) {
            const link = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.02, 4, 8), chainMaterial);
            link.position.set(1.7, 2.45 - i * 0.2, -1.08);
            link.rotation.x = Math.PI / 2;
            link.rotation.y = i * 0.3;
            this.root.add(link);
        }

        const plate = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.14, 0.9), mossStone);
        plate.position.set(-2.4, 0.12, -0.72);
        this.root.add(plate);

        const farWinch = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.82, 6), this.material(0x856e48));
        farWinch.rotation.z = Math.PI / 2;
        farWinch.position.set(0, 1.0, -2.85);
        this.root.add(farWinch);
    }

    buildDock() {
        const table = new THREE.Mesh(
            new THREE.BoxGeometry(4.8, 0.2, 1.15),
            this.material(0x8a9274)
        );
        table.position.set(-0.6, 0.26, 2.16);
        this.root.add(table);

        const legs = [
            [-2.5, 0.08, 1.7],
            [1.3, 0.08, 1.7],
            [-2.5, 0.08, 2.6],
            [1.3, 0.08, 2.6],
        ];
        legs.forEach(([x, y, z]) => {
            const leg = new THREE.Mesh(
                new THREE.BoxGeometry(0.2, 0.36, 0.2),
                this.material(0x6d6b57)
            );
            leg.position.set(x, y, z);
            this.root.add(leg);
        });
    }

    buildHotspots() {
        Object.values(HOTSPOTS).forEach((hotspot) => {
            const marker = new THREE.Mesh(
                new THREE.CylinderGeometry(0.5, 0.6, 0.12, 12),
                this.material(0x8de36c, {
                    transparent: true,
                    opacity: 0.24,
                    emissive: 0x285c23,
                    emissiveIntensity: 0.9,
                })
            );
            marker.position.copy(hotspot.position);
            marker.scale.copy(hotspot.markerScale);
            marker.userData = {
                type: "hotspot",
                hotspotId: hotspot.id,
                baseY: hotspot.position.y,
            };
            this.hotspotGroup.add(marker);
            this.hotspotMeshes.set(hotspot.id, marker);
        });
    }

    attachEvents() {
        this.renderer.domElement.addEventListener("pointerdown", (event) => {
            this.controls.dragging = true;
            this.controls.lastX = event.clientX;
            this.controls.lastY = event.clientY;
        });

        window.addEventListener("pointerup", () => {
            this.controls.dragging = false;
        });

        window.addEventListener("pointermove", (event) => {
            if (!this.container.contains(event.target) && !this.controls.dragging) {
                return;
            }
            if (this.controls.dragging) {
                const dx = event.clientX - this.controls.lastX;
                const dy = event.clientY - this.controls.lastY;
                this.controls.lastX = event.clientX;
                this.controls.lastY = event.clientY;
                this.controls.azimuth -= dx * 0.008;
                this.controls.elevation = THREE.MathUtils.clamp(
                    this.controls.elevation - dy * 0.006,
                    0.28,
                    1.22
                );
                this.updateCamera();
            } else {
                this.updateHover(event);
            }
        });

        this.renderer.domElement.addEventListener("wheel", (event) => {
            event.preventDefault();
            this.controls.radius = THREE.MathUtils.clamp(this.controls.radius + event.deltaY * 0.01, 6.5, 12);
            this.updateCamera();
        }, { passive: false });

        this.renderer.domElement.addEventListener("click", (event) => {
            const hit = this.pick(event);
            if (!hit) {
                return;
            }
            if (hit.userData.type === "item") {
                this.handlers.onSelectItem(hit.userData.itemId);
                return;
            }
            if (hit.userData.type === "hotspot") {
                this.handlers.onSelectHotspot(hit.userData.hotspotId);
            }
        });

        window.addEventListener("resize", () => this.resize());
    }

    resize() {
        const width = this.container.clientWidth || 1;
        const height = this.container.clientHeight || 1;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    updateCamera() {
        const target = new THREE.Vector3(0, 1.2, -0.6);
        const x = Math.sin(this.controls.azimuth) * Math.cos(this.controls.elevation) * this.controls.radius;
        const y = Math.sin(this.controls.elevation) * this.controls.radius + 0.8;
        const z = Math.cos(this.controls.azimuth) * Math.cos(this.controls.elevation) * this.controls.radius;
        this.camera.position.set(x, y, z);
        this.camera.lookAt(target);
    }

    pick(event) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.pointer, this.camera);
        const meshes = [
            ...this.hotspotMeshes.values(),
            ...this.itemMeshes.values(),
        ];
        const hits = this.raycaster.intersectObjects(meshes, true);
        return hits.length > 0 ? hits[0].object : null;
    }

    updateHover(event) {
        const hit = this.pick(event);
        this.hovered = hit ? hit.userData : null;
        this.renderer.domElement.style.cursor = hit ? "pointer" : "grab";
    }

    setState(nextState) {
        this.currentState = nextState;
        this.renderItems(nextState.items, nextState.puzzleState);
        this.updateSelection();
        this.updatePreview();
    }

    updateSelection() {
        this.hotspotMeshes.forEach((mesh, hotspotId) => {
            const isSelected = hotspotId === this.currentState.selectedHotspotId;
            const isSolved = this.currentState.puzzleState?.solved_anchor_id === hotspotId;
            mesh.material.opacity = isSolved ? 0.16 : isSelected ? 0.34 : 0.22;
            mesh.material.emissive.setHex(isSolved ? 0x84d86a : isSelected ? 0x6fd96a : 0x285c23);
            mesh.scale.set(
                HOTSPOTS[hotspotId].markerScale.x * (isSelected ? 1.06 : 1),
                HOTSPOTS[hotspotId].markerScale.y,
                HOTSPOTS[hotspotId].markerScale.z * (isSelected ? 1.06 : 1)
            );
        });

        this.itemMeshes.forEach((mesh, itemId) => {
            const base = this.itemBases.get(itemId);
            mesh.scale.setScalar(base * (itemId === this.currentState.selectedItemId ? 1.08 : 1));
        });
    }

    updatePreview() {
        this.previewGroup.clear();
        const item = this.currentState.items.find((entry) => entry.id === this.currentState.selectedItemId);
        const hotspot = HOTSPOTS[this.currentState.selectedHotspotId];
        if (!item || !hotspot || this.currentState.puzzleState?.gate_open) {
            return;
        }

        const compatibility = getCompatibility(item, hotspot);
        const preview = this.buildItemGroup(item);
        preview.position.copy(hotspot.placement.position);
        preview.rotation.y = hotspot.placement.rotationY || 0;
        preview.scale.multiplyScalar(compatibility.compatible ? 0.92 : 0.86);
        preview.traverse((node) => {
            if (node.isMesh) {
                node.material = node.material.clone();
                node.material.transparent = true;
                node.material.opacity = compatibility.compatible ? 0.42 : 0.25;
                node.material.emissive.setHex(compatibility.compatible ? 0x74cc62 : 0x823d2f);
                node.material.emissiveIntensity = 0.7;
            }
        });
        this.previewGroup.add(preview);
    }

    renderItems(items, puzzleState) {
        this.itemGroup.clear();
        this.itemMeshes.clear();
        this.itemBases.clear();

        items.forEach((item, index) => {
            const group = this.buildItemGroup(item);
            const placement = item.placed_at && HOTSPOTS[item.placed_at]
                ? HOTSPOTS[item.placed_at].placement
                : null;

            if (placement) {
                group.position.copy(placement.position);
                group.rotation.y = placement.rotationY || 0;
            } else {
                const dockSpot = DOCK_POSITIONS[index] || DOCK_POSITIONS[DOCK_POSITIONS.length - 1];
                group.position.copy(dockSpot);
                group.rotation.y = -0.25 + index * 0.18;
            }

            const baseScale = item.placed_at ? 0.95 : 0.82;
            group.scale.multiplyScalar(baseScale);
            group.userData = {
                type: "item",
                itemId: item.id,
                placed: Boolean(item.placed_at),
                floatPhase: index * 0.7,
                baseY: group.position.y,
            };
            group.traverse((node) => {
                if (node.isMesh) {
                    node.userData = {
                        type: "item",
                        itemId: item.id,
                    };
                }
            });
            this.itemGroup.add(group);
            this.itemMeshes.set(item.id, group);
            this.itemBases.set(item.id, baseScale);
        });

        const solved = Boolean(puzzleState && puzzleState.gate_open);
        this.vineGroup.visible = !solved || puzzleState?.solution_path !== "cut_binding";
    }

    buildItemGroup(item) {
        const visual = item.visual_spec || {};
        const primary = new THREE.Color(visual.primary_color || "#c8cfb0");
        const secondary = new THREE.Color(visual.secondary_color || "#7b725c");
        const accent = new THREE.Color(visual.accent_color || "#f0d97a");
        const group = new THREE.Group();

        const woodMat = this.material(primary);
        const altMat = this.material(secondary);
        const accentMat = this.material(accent, { emissive: accent.getHex(), emissiveIntensity: 0.18 });
        const proxyKind = visual.proxy_kind || item.canonical_type || "unknown";

        if (proxyKind === "ladder") {
            const left = new THREE.Mesh(new THREE.BoxGeometry(0.12, 1.5, 0.12), woodMat);
            left.position.set(-0.22, 0.75, 0);
            const right = new THREE.Mesh(new THREE.BoxGeometry(0.12, 1.5, 0.12), woodMat);
            right.position.set(0.22, 0.75, 0);
            group.add(left, right);
            for (let i = 0; i < 5; i += 1) {
                const rung = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.08, 0.08), altMat);
                rung.position.set(0, 0.28 + i * 0.24, 0);
                group.add(rung);
            }
        } else if (proxyKind === "plank" || proxyKind === "rope_bridge") {
            const board = new THREE.Mesh(new THREE.BoxGeometry(1.35, 0.12, 0.32), woodMat);
            board.position.set(0, 0.1, 0);
            group.add(board);
            if (proxyKind === "rope_bridge") {
                const ropeLeft = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.42, 5), accentMat);
                ropeLeft.rotation.z = Math.PI / 2;
                ropeLeft.position.set(0, 0.32, -0.18);
                const ropeRight = ropeLeft.clone();
                ropeRight.position.z = 0.18;
                group.add(ropeLeft, ropeRight);
            }
        } else if (proxyKind === "axe") {
            const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.1, 6), woodMat);
            handle.position.set(0, 0.55, 0);
            const blade = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.28, 0.12), accentMat);
            blade.position.set(0.18, 1.0, 0);
            group.add(handle, blade);
        } else if (proxyKind === "saw") {
            const handle = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.14, 0.1), woodMat);
            handle.position.set(-0.15, 0.18, 0);
            const blade = new THREE.Mesh(new THREE.BoxGeometry(0.95, 0.1, 0.08), accentMat);
            blade.position.set(0.28, 0.18, 0);
            group.add(handle, blade);
        } else if (proxyKind === "hook") {
            const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.25, 6), woodMat);
            pole.position.set(0, 0.62, 0);
            const tip = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.035, 5, 8, Math.PI), accentMat);
            tip.position.set(0.14, 1.18, 0);
            tip.rotation.z = Math.PI / 2;
            group.add(pole, tip);
        } else if (proxyKind === "pole") {
            const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 1.5, 6), woodMat);
            pole.position.set(0, 0.75, 0);
            group.add(pole);
        } else if (proxyKind === "block" || proxyKind === "crate") {
            const block = new THREE.Mesh(new THREE.BoxGeometry(0.76, 0.76, 0.76), proxyKind === "crate" ? woodMat : altMat);
            block.position.set(0, 0.38, 0);
            group.add(block);
            if (proxyKind === "crate") {
                const strap = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.78, 0.82), accentMat);
                strap.position.set(0, 0.38, 0);
                group.add(strap);
            }
        } else {
            const tool = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.32, 0.32), woodMat);
            tool.position.set(0, 0.2, 0);
            const cap = new THREE.Mesh(new THREE.ConeGeometry(0.18, 0.3, 6), accentMat);
            cap.position.set(0.18, 0.52, 0);
            group.add(tool, cap);
        }

        const scaleHint = Number(visual.scale_hint || 1);
        group.scale.multiplyScalar(Number.isFinite(scaleHint) ? THREE.MathUtils.clamp(scaleHint, 0.78, 1.4) : 1);
        return group;
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        const time = performance.now() * 0.001;

        this.hotspotMeshes.forEach((mesh, hotspotId) => {
            const data = mesh.userData;
            const solved = this.currentState.puzzleState?.solved_anchor_id === hotspotId;
            mesh.position.y = data.baseY + Math.sin(time * 1.7 + hotspotId.length) * (solved ? 0.01 : 0.03);
            mesh.rotation.y += 0.003;
        });

        this.itemMeshes.forEach((group, itemId) => {
            if (group.userData.placed) {
                return;
            }
            group.position.y = group.userData.baseY + Math.sin(time * 1.9 + group.userData.floatPhase) * 0.04;
            group.rotation.y += 0.004;
            if (itemId === this.currentState.selectedItemId) {
                group.rotation.y += 0.01;
            }
        });

        const target = this.currentState.puzzleState?.gate_open ? 1 : 0;
        this.gateOpenValue += (target - this.gateOpenValue) * 0.08;
        this.leftGatePivot.rotation.y = this.gateOpenValue * 1.15;
        this.rightGatePivot.rotation.y = -this.gateOpenValue * 1.15;

        this.renderer.render(this.scene, this.camera);
    }
}

const sceneController = new VerdantGateScene(elements.sceneCanvas, {
    onSelectHotspot(hotspotId) {
        tryApplySelectedItemToHotspot(hotspotId);
    },
    onSelectItem(itemId) {
        state.selectedItemId = itemId;
        renderAll();
    },
});

elements.generateButton.addEventListener("click", requestGeneration);
elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        requestGeneration();
    }
});

elements.clearSelectionButton.addEventListener("click", () => {
    state.selectedItemId = null;
    state.selectedHotspotId = null;
    setConsoleStatus("Selection cleared.");
    renderAll();
});

elements.hintButton.addEventListener("click", requestHint);
elements.returnMenuButton.addEventListener("click", () => {
    bridge.requestReturnToMenu();
});

bridge.on("init", handleInit);
bridge.on("event", handleEvent);
bridge.requestInitialState();
