(function () {
    const bridge = window.WenyooStorySDK.createBridge();

    const chargeValue = document.getElementById("charge-value");
    const scanValue = document.getElementById("scan-value");
    const stageValue = document.getElementById("stage-value");
    const localNotes = document.getElementById("local-notes");
    const feed = document.getElementById("feed");
    const objectActionsList = document.getElementById("object-actions-list");
    const profileSelect = document.getElementById("profile-select");
    const analysisGoal = document.getElementById("analysis-goal");

    const chargeBtn = document.getElementById("charge-btn");
    const resetBtn = document.getElementById("reset-btn");
    const refreshStateBtn = document.getElementById("refresh-state-btn");
    const queryActionsBtn = document.getElementById("query-actions-btn");
    const architectBtn = document.getElementById("architect-btn");
    const saveNotesBtn = document.getElementById("save-notes-btn");
    const clearNotesBtn = document.getElementById("clear-notes-btn");
    const returnMenuBtn = document.getElementById("return-menu-btn");

    let initPayload = null;
    let currentState = { variables: {} };
    let currentStreamNode = null;

    function getNotesStorageKey() {
        const storyId = initPayload && initPayload.storyId ? initPayload.storyId : "custom-ui-story";
        return `wenyoo:${storyId}:local-notes`;
    }

    function loadLocalNotes() {
        localNotes.value = window.localStorage.getItem(getNotesStorageKey()) || "";
    }

    function saveLocalNotes() {
        window.localStorage.setItem(getNotesStorageKey(), localNotes.value);
        appendFeed("local", "Local notebook", "Saved private notes inside the sandboxed story app.");
    }

    function clearLocalNotes() {
        window.localStorage.removeItem(getNotesStorageKey());
        localNotes.value = "";
        appendFeed("local", "Local notebook", "Cleared private notes without touching backend state.");
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

        feed.prepend(entry);
    }

    function startStream(title) {
        const entry = document.createElement("article");
        entry.className = "feed-entry system";

        const heading = document.createElement("strong");
        heading.textContent = title;
        entry.appendChild(heading);

        const body = document.createElement("div");
        body.textContent = "";
        entry.appendChild(body);

        feed.prepend(entry);
        currentStreamNode = body;
    }

    function endStream(finalText) {
        if (currentStreamNode && finalText) {
            currentStreamNode.textContent = finalText;
        }
        currentStreamNode = null;
    }

    function getVariables() {
        return currentState && currentState.variables ? currentState.variables : {};
    }

    function renderSummary() {
        const variables = getVariables();
        chargeValue.textContent = String(variables.lab_charge || 0);
        scanValue.textContent = String(variables.scan_count || 0);
        stageValue.textContent = String(variables.anomaly_stage || "dormant");
    }

    function syncGameState(nextState) {
        if (!nextState || typeof nextState !== "object") {
            return;
        }
        currentState = nextState;
        renderSummary();
    }

    function extractTextFromMessage(message) {
        if (!message || typeof message !== "object") {
            return "";
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

    function renderTranscript(transcript) {
        if (!Array.isArray(transcript)) {
            return;
        }
        transcript.slice().reverse().forEach((entry) => {
            const text = extractTextFromMessage(entry);
            if (text) {
                appendFeed("system", entry.type || "Transcript", text);
            }
        });
    }

    function renderObjectActions(actions) {
        objectActionsList.innerHTML = "";
        if (!Array.isArray(actions) || actions.length === 0) {
            const item = document.createElement("li");
            item.textContent = "No object actions available right now.";
            objectActionsList.appendChild(item);
            return;
        }

        actions.forEach((action) => {
            const item = document.createElement("li");
            item.textContent = `${action.text} (${action.id})`;
            objectActionsList.appendChild(item);
        });
    }

    function handleInit(payload) {
        initPayload = payload || {};
        feed.innerHTML = "";
        syncGameState(initPayload.gameState || { variables: {} });
        renderTranscript(initPayload.transcript);

        if (initPayload.perception && initPayload.perception.client_content?.text) {
            appendFeed("system", "Opening scene", initPayload.perception.client_content.text);
        }

        loadLocalNotes();
        appendFeed(
            "local",
            "Story app ready",
            "Local notebook, deterministic backend controls, and Architect analysis are all available."
        );
    }

    function handleGameStartMessage(message) {
        const content = message && message.content ? message.content : {};
        syncGameState(content.game_state || { variables: {} });
        if (content.perception && content.perception.client_content?.text) {
            appendFeed("system", "Scene update", content.perception.client_content.text);
        }
    }

    function handleCommandResult(message) {
        const content = message && message.content ? message.content : {};
        syncGameState(content.game_state);

        if (content.response_client && content.response_client.text) {
            appendFeed("system", "Command result", content.response_client.text);
        } else if (
            content.response &&
            content.response.deterministic_result &&
            Array.isArray(content.response.deterministic_result.applied)
        ) {
            appendFeed(
                "system",
                "Direct backend update",
                `Applied: ${content.response.deterministic_result.applied.join(", ")}`
            );
        }
    }

    function handleEvent(message) {
        if (!message || typeof message !== "object") {
            return;
        }

        const type = message.type || "event";
        if (type === "game_start") {
            handleGameStartMessage(message);
            return;
        }
        if (type === "game_state") {
            syncGameState(message.content);
            return;
        }
        if (type === "command_result") {
            handleCommandResult(message);
            return;
        }
        if (type === "perception") {
            const text = extractTextFromMessage(message);
            if (text) {
                appendFeed("system", "Perception", text);
            }
            return;
        }
        if (type === "object_actions") {
            renderObjectActions(message.actions);
            appendFeed("system", "Backend query", "Fetched the current action list for the signal core.");
            return;
        }
        if (type === "stream_start") {
            startStream("Architect stream");
            return;
        }
        if (type === "stream_token") {
            if (currentStreamNode) {
                currentStreamNode.textContent += message.content || "";
            }
            return;
        }
        if (type === "stream_end") {
            const finalText = extractTextFromMessage(message) || message.content || "";
            endStream(finalText);
            return;
        }

        const text = extractTextFromMessage(message);
        if (text) {
            appendFeed(type === "error" ? "local" : "system", type, text);
        }
    }

    function sendChargeUpdate(nextCharge) {
        const nextStage = nextCharge >= 3 ? "primed" : "dormant";
        const recommendedAction = nextCharge >= 3 ? "initiate_contact" : "run_scan";
        bridge.sendDeterministicAction(
            "merge_patch",
            {
                patch: {
                    variables: {
                        lab_charge: nextCharge,
                        anomaly_stage: nextStage,
                        recommended_action: recommendedAction,
                    },
                },
            },
            {
                display_text: `Set lab charge to ${nextCharge}`,
            }
        );
    }

    function runArchitectScan() {
        const variables = getVariables();
        bridge.sendArchitectTask("guided_intent", {
            action_id: "intelligent_scan",
            display_text: "Run intelligent signal scan",
            player_input: "Run a careful signal analysis through the lab interface.",
            purpose:
                "Interpret the anomaly using the custom signal-lab UI context. If the scan produces a meaningful new fact, increment scan_count and update anomaly_stage or recommended_action so the world remembers it.",
            structured_input: {
                interface: "signal_lab_console",
                selected_waveform_profile: profileSelect.value,
                operator_goal: analysisGoal.value,
                current_charge: variables.lab_charge || 0,
                existing_scan_count: variables.scan_count || 0,
                current_stage: variables.anomaly_stage || "dormant",
            },
            expected_output:
                "Return a concise player-facing analysis and record any meaningful discoveries in world state.",
            extra_context: {
                ui_mode: "custom_story_app",
            },
            input_type: "story_app",
        });
    }

    chargeBtn.addEventListener("click", () => {
        const nextCharge = Number(getVariables().lab_charge || 0) + 1;
        sendChargeUpdate(nextCharge);
    });

    resetBtn.addEventListener("click", () => {
        bridge.sendDeterministicAction(
            "merge_patch",
            {
                patch: {
                    variables: {
                        lab_charge: 0,
                        anomaly_stage: "dormant",
                        recommended_action: "observe",
                    },
                },
            },
            {
                display_text: "Reset lab charge",
            }
        );
    });

    refreshStateBtn.addEventListener("click", () => {
        bridge.requestInitialState();
    });

    queryActionsBtn.addEventListener("click", () => {
        bridge.query("object_actions", { object_id: "signal_core" });
    });

    architectBtn.addEventListener("click", () => {
        runArchitectScan();
    });

    saveNotesBtn.addEventListener("click", () => {
        saveLocalNotes();
    });

    clearNotesBtn.addEventListener("click", () => {
        clearLocalNotes();
    });

    returnMenuBtn.addEventListener("click", () => {
        bridge.requestReturnToMenu();
    });

    bridge.on("init", handleInit);
    bridge.on("event", handleEvent);
})();
