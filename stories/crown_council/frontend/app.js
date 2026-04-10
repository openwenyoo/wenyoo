(function () {
    const bridge = window.WenyooStorySDK.createBridge();

    const elements = {
        subtitle: document.getElementById("subtitle"),
        dynastyPill: document.getElementById("dynasty-pill"),
        turnPill: document.getElementById("turn-pill"),
        bufferPill: document.getElementById("buffer-pill"),
        metricsGrid: document.getElementById("metrics-grid"),
        speakerName: document.getElementById("speaker-name"),
        speakerRole: document.getElementById("speaker-role"),
        generationStatus: document.getElementById("generation-status"),
        portraitFrame: document.getElementById("portrait-frame"),
        promptText: document.getElementById("prompt-text"),
        leftChoiceButton: document.getElementById("left-choice-button"),
        rightChoiceButton: document.getElementById("right-choice-button"),
        leftChoiceLabel: document.getElementById("left-choice-label"),
        rightChoiceLabel: document.getElementById("right-choice-label"),
        stageStatus: document.getElementById("stage-status"),
        endBanner: document.getElementById("end-banner"),
        decisionCard: document.getElementById("decision-card"),
        swipeLeftIndicator: document.getElementById("swipe-left-indicator"),
        swipeRightIndicator: document.getElementById("swipe-right-indicator"),
        returnMenuButton: document.getElementById("return-menu-button"),
    };

    const state = {
        initPayload: null,
        gameState: { variables: {} },
        pendingChoice: false,
        pendingGeneration: false,
        pendingPromotion: false,
        lastGenerationKey: "",
        lastStructured: null,
        swipeStart: null,
        swipeCurrentDx: 0,
        exitAnimationToken: 0,
    };

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function numberOrDefault(value, fallback) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : fallback;
    }

    function hexToRgba(hex, alpha) {
        const normalized = String(hex || "").trim();
        const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(normalized);
        if (!match) {
            return `rgba(34, 26, 24, ${alpha})`;
        }
        return `rgba(${parseInt(match[1], 16)}, ${parseInt(match[2], 16)}, ${parseInt(match[3], 16)}, ${alpha})`;
    }

    function buildPortraitBackground(spec) {
        const safeSpec = spec || {};
        const primary = safeSpec.primary_color || "#5b4a3f";
        const secondary = safeSpec.secondary_color || "#d8d6cf";
        const accent = safeSpec.accent_color || "#ddb45f";
        return [
            `radial-gradient(circle at 50% 16%, ${hexToRgba(accent, 0.32)}, transparent 34%)`,
            `radial-gradient(circle at 18% 78%, ${hexToRgba(secondary, 0.18)}, transparent 38%)`,
            `linear-gradient(160deg, ${hexToRgba(primary, 0.92)} 0%, ${hexToRgba(accent, 0.24)} 56%, ${hexToRgba(secondary, 0.34)} 100%)`,
        ].join(", ");
    }

    function hashString(value) {
        const text = String(value || "");
        let hash = 0;
        for (let index = 0; index < text.length; index += 1) {
            hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
        }
        return hash;
    }

    function getVariables() {
        return state.gameState && state.gameState.variables ? state.gameState.variables : {};
    }

    function getRunState() {
        return getVariables().run_state || {};
    }

    function getMetrics() {
        return getVariables().kingdom_metrics || {};
    }

    function getMetricConfig() {
        return getVariables().metric_config || {};
    }

    function getCardLibrary() {
        return getVariables().card_library || {};
    }

    function getDrawPile() {
        const drawPile = getVariables().draw_pile;
        return Array.isArray(drawPile) ? drawPile : [];
    }

    function getChoiceHistory() {
        const history = getVariables().choice_history;
        return Array.isArray(history) ? history : [];
    }

    function getOpenThreads() {
        const threads = getVariables().open_threads;
        return Array.isArray(threads) ? threads : [];
    }

    function getRecentGeneratedIds() {
        const ids = getVariables().recent_generated_card_ids;
        return Array.isArray(ids) ? ids : [];
    }

    function getGenerationQueue() {
        const queue = getVariables().generation_queue;
        return Array.isArray(queue) ? queue : [];
    }

    function getActiveCardId() {
        return getVariables().active_card_id || null;
    }

    function getActiveCard() {
        const activeCardId = getActiveCardId();
        return activeCardId ? getCardLibrary()[activeCardId] || null : null;
    }

    function summarizeCard(card, includeChoices) {
        if (!card || typeof card !== "object") {
            return null;
        }
        const summary = {
            id: card.id,
            source: card.source,
            status: card.status,
            speaker_name: card.speaker_name,
            speaker_role: card.speaker_role,
            prompt_text: card.prompt_text,
            followup_hooks: Array.isArray(card.followup_hooks) ? card.followup_hooks : [],
            resolution_tags: Array.isArray(card.resolution_tags) ? card.resolution_tags : [],
            reuse_rules: card.reuse_rules || {},
            times_used: Number(card.times_used || 0),
            portrait_spec: card.portrait_spec || {},
        };
        if (includeChoices) {
            summary.left_choice = card.left_choice || null;
            summary.right_choice = card.right_choice || null;
        }
        return summary;
    }

    function summarizeVisibleCards() {
        const library = getCardLibrary();
        const ids = [];
        const activeId = getActiveCardId();
        if (activeId) {
            ids.push(activeId);
        }
        getDrawPile().forEach((cardId) => {
            if (!ids.includes(cardId)) {
                ids.push(cardId);
            }
        });
        return ids
            .map((cardId) => summarizeCard(library[cardId], false))
            .filter(Boolean);
    }

    function cloneValue(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function setStageStatus(text) {
        elements.stageStatus.textContent = text;
    }

    function renderGenerationTone() {
        const label = elements.generationStatus;
        label.className = "pill";
        if (getRunState().status === "ended") {
            label.textContent = "Ended";
            return;
        }
        if (state.pendingChoice) {
            label.textContent = "Resolving";
            return;
        }
        if (state.pendingGeneration) {
            label.textContent = "Generating";
            return;
        }
            label.textContent = getDrawPile().length <= 1 ? "Thin queue" : "Ready";
    }

    function makeAuthoredPortraitSvg(card, spec) {
        const primary = spec.primary_color || "#6d2431";
        const secondary = spec.secondary_color || "#f0e0ca";
        const accent = spec.accent_color || "#ddb45f";
        const shell = spec.skin_tone || "#cfd6df";
        const dark = "#181311";
        const soft = "rgba(255,255,255,0.08)";
        const label = card?.speaker_name || card?.speaker_role || "Machine figure";

        if (card?.id === "starter_protocol_bishop") {
            return `
                <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
                    <rect width="360" height="360" fill="transparent"/>
                    <circle cx="180" cy="126" r="102" fill="${accent}" opacity="0.14"/>
                    <path d="M102 320 L140 244 L180 218 L220 244 L258 320 L220 320 L180 286 L140 320 Z" fill="${secondary}"/>
                    <rect x="166" y="220" width="28" height="88" rx="10" fill="${accent}" opacity="0.9"/>
                    <path d="M150 54 L180 18 L210 54 L210 160 L150 160 Z" fill="${primary}"/>
                    <rect x="170" y="54" width="20" height="118" rx="10" fill="${accent}"/>
                    <ellipse cx="180" cy="178" rx="70" ry="84" fill="${shell}"/>
                    <rect x="120" y="226" width="120" height="20" rx="10" fill="${primary}" opacity="0.78"/>
                    <rect x="136" y="162" width="36" height="10" rx="5" fill="${secondary}"/>
                    <rect x="188" y="162" width="36" height="10" rx="5" fill="${secondary}"/>
                    <circle cx="154" cy="167" r="5" fill="${dark}"/>
                    <circle cx="206" cy="167" r="5" fill="${dark}"/>
                    <rect x="165" y="194" width="30" height="12" rx="6" fill="${secondary}" opacity="0.22"/>
                    <rect x="150" y="228" width="60" height="8" rx="4" fill="${accent}"/>
                    <rect x="92" y="252" width="30" height="60" rx="12" fill="${primary}"/>
                    <rect x="100" y="238" width="22" height="70" rx="10" fill="${secondary}"/>
                    <circle cx="111" cy="270" r="10" fill="${accent}"/>
                    <path d="M242 104 L278 124 L262 156 L226 138 Z" fill="${soft}"/>
                </svg>
            `;
        }

        if (card?.id === "starter_frontier_warframe") {
            return `
                <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
                    <rect width="360" height="360" fill="transparent"/>
                    <circle cx="182" cy="120" r="96" fill="${accent}" opacity="0.12"/>
                    <path d="M72 312 L122 232 L180 210 L238 232 L288 312 L228 312 L180 286 L132 312 Z" fill="${primary}"/>
                    <path d="M112 244 L136 188 L180 146 L224 188 L248 244 L220 266 L140 266 Z" fill="${secondary}"/>
                    <path d="M126 150 L152 82 L208 82 L234 150 L220 208 L140 208 Z" fill="${secondary}"/>
                    <path d="M144 122 L180 60 L216 122 L202 172 L158 172 Z" fill="${primary}"/>
                    <rect x="132" y="176" width="96" height="20" rx="10" fill="${accent}" opacity="0.92"/>
                    <rect x="150" y="180" width="60" height="10" rx="5" fill="#ffb49b"/>
                    <circle cx="164" cy="186" r="5" fill="${dark}"/>
                    <circle cx="196" cy="186" r="5" fill="${dark}"/>
                    <path d="M148 224 H212 L198 238 H162 Z" fill="${shell}" opacity="0.45"/>
                    <path d="M258 120 L272 120 L272 318 L258 318 Z" fill="${accent}"/>
                    <polygon points="265,84 280,120 250,120" fill="${accent}"/>
                    <rect x="238" y="150" width="54" height="12" rx="6" fill="${secondary}"/>
                    <path d="M88 248 L118 214 L128 262 L96 286 Z" fill="${shell}" opacity="0.7"/>
                </svg>
            `;
        }

        if (card?.id === "starter_salvage_prefect") {
            return `
                <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
                    <rect width="360" height="360" fill="transparent"/>
                    <circle cx="184" cy="124" r="92" fill="${accent}" opacity="0.13"/>
                    <path d="M104 318 L138 242 L180 218 L224 242 L256 318 L220 318 L180 286 L140 318 Z" fill="${primary}"/>
                    <rect x="160" y="224" width="40" height="84" rx="14" fill="${secondary}" opacity="0.95"/>
                    <path d="M120 146 C126 98 150 72 180 72 C210 72 234 98 240 146 L220 158 L180 152 L140 158 Z" fill="${secondary}"/>
                    <ellipse cx="180" cy="184" rx="68" ry="78" fill="${shell}"/>
                    <path d="M122 152 L150 108 H236 L214 154 L178 146 Z" fill="${primary}"/>
                    <rect x="128" y="164" width="40" height="12" rx="6" fill="${accent}" opacity="0.88"/>
                    <rect x="186" y="166" width="34" height="10" rx="5" fill="${secondary}"/>
                    <circle cx="146" cy="170" r="5" fill="${dark}"/>
                    <circle cx="204" cy="171" r="4.5" fill="${dark}"/>
                    <rect x="158" y="200" width="36" height="10" rx="5" fill="${secondary}" opacity="0.25"/>
                    <rect x="150" y="230" width="56" height="8" rx="4" fill="${accent}"/>
                    <rect x="90" y="248" width="40" height="60" rx="8" fill="${secondary}"/>
                    <rect x="98" y="248" width="8" height="60" fill="${accent}" opacity="0.8"/>
                    <path d="M236 248 L264 228 L270 284 L248 304 Z" fill="${primary}"/>
                </svg>
            `;
        }

        if (card?.id === "starter_jester_emulator") {
            return `
                <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
                    <rect width="360" height="360" fill="transparent"/>
                    <circle cx="180" cy="126" r="94" fill="${accent}" opacity="0.13"/>
                    <path d="M98 320 L134 246 L180 220 L226 246 L262 320 L222 320 L180 292 L138 320 Z" fill="${primary}"/>
                    <path d="M134 132 L104 92 L138 70 L176 116 L176 248 L132 236 Z" fill="${secondary}"/>
                    <path d="M226 132 L256 92 L222 70 L184 116 L184 248 L228 236 Z" fill="${accent}"/>
                    <ellipse cx="180" cy="186" rx="66" ry="80" fill="${shell}"/>
                    <path d="M120 142 L152 96 L178 136 L150 164 Z" fill="${secondary}"/>
                    <path d="M240 142 L208 96 L182 136 L210 164 Z" fill="${accent}"/>
                    <circle cx="136" cy="100" r="12" fill="${secondary}"/>
                    <circle cx="224" cy="100" r="12" fill="${accent}"/>
                    <rect x="132" y="164" width="40" height="16" rx="8" fill="${primary}" opacity="0.88"/>
                    <rect x="188" y="164" width="40" height="16" rx="8" fill="${primary}" opacity="0.88"/>
                    <circle cx="152" cy="172" r="5" fill="${shell}"/>
                    <circle cx="208" cy="172" r="5" fill="${shell}"/>
                    <rect x="140" y="226" width="80" height="18" rx="9" fill="${secondary}"/>
                    <rect x="154" y="232" width="52" height="6" rx="3" fill="${primary}" opacity="0.72"/>
                    <ellipse cx="102" cy="278" rx="18" ry="24" fill="${secondary}"/>
                    <circle cx="95" cy="276" r="3" fill="${primary}"/>
                    <circle cx="109" cy="276" r="3" fill="${primary}"/>
                </svg>
            `;
        }

        if (card?.id === "empty" || spec.archetype === "sovereign_vault") {
            return `
                <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
                    <rect width="360" height="360" fill="transparent"/>
                    <circle cx="180" cy="128" r="106" fill="${accent}" opacity="0.14"/>
                    <path d="M100 316 L134 246 L180 222 L226 246 L260 316 L220 316 L180 290 L140 316 Z" fill="${primary}"/>
                    <rect x="136" y="92" width="88" height="130" rx="26" fill="${secondary}"/>
                    <rect x="154" y="62" width="52" height="118" rx="18" fill="${primary}"/>
                    <circle cx="180" cy="164" r="58" fill="${shell}"/>
                    <circle cx="180" cy="164" r="84" fill="${accent}" opacity="0.08"/>
                    <rect x="138" y="154" width="84" height="14" rx="7" fill="${secondary}"/>
                    <circle cx="154" cy="161" r="5" fill="${dark}"/>
                    <circle cx="206" cy="161" r="5" fill="${dark}"/>
                    <rect x="150" y="224" width="60" height="8" rx="4" fill="${accent}"/>
                    <path d="M94 246 C94 220 124 220 124 246 L124 296 C124 316 94 316 94 296 Z" fill="${primary}"/>
                    <path d="M236 246 C236 220 266 220 266 246 L266 296 C266 316 236 316 236 296 Z" fill="${primary}"/>
                </svg>
            `;
        }

        return null;
    }

    function makePortraitSvg(card) {
        const spec = (card && card.portrait_spec) || {};
        const authoredPortrait = makeAuthoredPortraitSvg(card, spec);
        if (authoredPortrait) {
            return authoredPortrait;
        }
        const primary = spec.primary_color || "#6d2431";
        const secondary = spec.secondary_color || "#f0e0ca";
        const accent = spec.accent_color || "#ddb45f";
        const skin = spec.skin_tone || "#e7c8a2";
        const faceShape = spec.face_shape || "oval";
        const headwear = spec.headwear || "none";
        const accessory = spec.accessory || "none";
        const mood = spec.mood || "calm";
        const silhouette = spec.silhouette || "layered";
        const seed = hashString([card?.id, spec.archetype, headwear, accessory].join(":"));
        const shoulderShift = (seed % 9) - 4;
        const haloRadius = 94 + (seed % 11);
        const eyeY = mood === "grim" || mood === "stern" ? 166 : 172;
        const mouthY = mood === "playful" ? 224 : 220;
        const robeTop = silhouette === "narrow" ? 232 : 226;
        const robePoints = silhouette === "broad"
            ? `98,316 138,${robeTop} 180,256 222,${robeTop} 262,316 234,348 126,348`
            : silhouette === "narrow"
                ? `116,316 146,${robeTop} 180,258 214,${robeTop} 244,316 222,348 138,348`
                : `102,316 136,${robeTop} 180,258 224,${robeTop} 258,316 234,348 126,348`;

        let headShape = `<ellipse cx="180" cy="182" rx="78" ry="86" fill="${skin}"/>`;
        if (faceShape === "round") {
            headShape = `<circle cx="180" cy="184" r="82" fill="${skin}"/>`;
        } else if (faceShape === "square") {
            headShape = `<rect x="106" y="102" width="148" height="166" rx="34" fill="${skin}"/>`;
        } else if (faceShape === "long") {
            headShape = `<ellipse cx="180" cy="184" rx="72" ry="92" fill="${skin}"/>`;
        }

        let crownOrHat = "";
        if (headwear === "crown") {
            crownOrHat = `
                <polygon points="124,108 146,66 180,96 214,66 236,108 216,126 144,126" fill="${accent}"/>
                <circle cx="146" cy="66" r="7" fill="${secondary}"/>
                <circle cx="180" cy="96" r="7" fill="${secondary}"/>
                <circle cx="214" cy="66" r="7" fill="${secondary}"/>
            `;
        } else if (headwear === "mitre") {
            crownOrHat = `
                <polygon points="146,64 180,28 214,64 214,140 146,140" fill="${secondary}"/>
                <rect x="172" y="64" width="16" height="112" fill="${accent}" opacity="0.9"/>
            `;
        } else if (headwear === "helm") {
            crownOrHat = `
                <path d="M116 148 C120 92 148 64 180 64 C212 64 240 92 244 148 L216 136 L144 136 Z" fill="${secondary}"/>
                <rect x="144" y="132" width="72" height="22" rx="11" fill="${accent}" opacity="0.9"/>
            `;
        } else if (headwear === "cap") {
            crownOrHat = `
                <path d="M122 150 C130 100 154 78 180 78 C206 78 230 100 238 150 L216 144 L180 140 L144 144 Z" fill="${secondary}"/>
            `;
        } else if (headwear === "bells") {
            crownOrHat = `
                <polygon points="128,118 152,80 180,112 208,80 232,118 212,142 148,142" fill="${accent}"/>
                <circle cx="134" cy="128" r="8" fill="${secondary}"/>
                <circle cx="226" cy="128" r="8" fill="${secondary}"/>
            `;
        } else if (headwear === "hood") {
            crownOrHat = `
                <path d="M108 192 C116 118 146 82 180 82 C214 82 244 118 252 192 L222 166 L180 156 L138 166 Z" fill="${secondary}"/>
            `;
        }

        let accessoryShape = "";
        if (accessory === "scroll") {
            accessoryShape = `
                <rect x="92" y="252" width="26" height="64" rx="10" fill="${secondary}"/>
                <circle cx="105" cy="274" r="8" fill="${accent}"/>
            `;
        } else if (accessory === "sword") {
            accessoryShape = `
                <rect x="252" y="166" width="10" height="154" rx="5" fill="${accent}"/>
                <rect x="238" y="188" width="38" height="10" rx="5" fill="${secondary}"/>
                <polygon points="257,140 265,156 249,156" fill="${accent}"/>
            `;
        } else if (accessory === "ledger" || accessory === "book") {
            accessoryShape = `
                <rect x="90" y="250" width="36" height="54" rx="6" fill="${secondary}"/>
                <rect x="100" y="250" width="6" height="54" fill="${accent}" opacity="0.8"/>
            `;
        } else if (accessory === "scepter") {
            accessoryShape = `
                <rect x="252" y="168" width="10" height="152" rx="5" fill="${accent}"/>
                <circle cx="257" cy="154" r="14" fill="${accent}"/>
                <polygon points="257,138 264,154 278,161 264,168 257,182 250,168 236,161 250,154" fill="${accent}"/>
            `;
        } else if (accessory === "mask") {
            accessoryShape = `
                <ellipse cx="102" cy="278" rx="18" ry="24" fill="${secondary}"/>
                <circle cx="95" cy="276" r="3" fill="${primary}"/>
                <circle cx="109" cy="276" r="3" fill="${primary}"/>
            `;
        } else if (accessory === "chalice") {
            accessoryShape = `
                <path d="M90 254 H120 C120 274 112 286 105 292 C98 286 90 274 90 254 Z" fill="${secondary}"/>
                <rect x="101" y="292" width="8" height="20" fill="${accent}"/>
                <rect x="92" y="312" width="26" height="8" rx="4" fill="${accent}"/>
            `;
        } else if (accessory === "banner") {
            accessoryShape = `
                <rect x="252" y="162" width="10" height="156" rx="5" fill="${accent}"/>
                <polygon points="262,168 306,180 262,208" fill="${secondary}"/>
            `;
        } else if (accessory === "coin") {
            accessoryShape = `
                <circle cx="102" cy="280" r="16" fill="${accent}"/>
                <circle cx="102" cy="280" r="8" fill="${secondary}" opacity="0.72"/>
            `;
        } else if (accessory === "wheat") {
            accessoryShape = `
                <rect x="100" y="250" width="6" height="70" rx="3" fill="${accent}"/>
                <ellipse cx="96" cy="262" rx="8" ry="5" fill="${secondary}" transform="rotate(-30 96 262)"/>
                <ellipse cx="110" cy="274" rx="8" ry="5" fill="${secondary}" transform="rotate(30 110 274)"/>
                <ellipse cx="96" cy="286" rx="8" ry="5" fill="${secondary}" transform="rotate(-30 96 286)"/>
                <ellipse cx="110" cy="298" rx="8" ry="5" fill="${secondary}" transform="rotate(30 110 298)"/>
            `;
        }

        const eyeShape = mood === "grim" || mood === "stern"
            ? `
                <rect x="142" y="${eyeY}" width="24" height="7" rx="3.5" fill="${secondary}"/>
                <rect x="194" y="${eyeY}" width="24" height="7" rx="3.5" fill="${secondary}"/>
                <circle cx="154" cy="${eyeY + 3.5}" r="5" fill="#24120c"/>
                <circle cx="206" cy="${eyeY + 3.5}" r="5" fill="#24120c"/>
            `
            : `
                <circle cx="154" cy="${eyeY}" r="18" fill="${secondary}"/>
                <circle cx="206" cy="${eyeY}" r="18" fill="${secondary}"/>
                <circle cx="154" cy="${eyeY}" r="6" fill="#24120c"/>
                <circle cx="206" cy="${eyeY}" r="6" fill="#24120c"/>
            `;

        const mouthShape = mood === "playful"
            ? `<rect x="154" y="${mouthY}" width="52" height="10" rx="5" fill="${accent}"/>`
            : mood === "grim"
                ? `<rect x="156" y="${mouthY}" width="48" height="6" rx="3" fill="${accent}"/>`
                : `<rect x="158" y="${mouthY}" width="44" height="8" rx="4" fill="${accent}"/>`;

        return `
            <svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${card.speaker_name || card.speaker_role || "Court figure"}">
                <rect width="360" height="360" fill="transparent"/>
                <circle cx="${180 + shoulderShift}" cy="132" r="${haloRadius}" fill="${accent}" opacity="0.13"/>
                <polygon points="${robePoints}" fill="${primary}"/>
                <rect x="142" y="246" width="76" height="78" fill="${secondary}" opacity="0.96"/>
                <rect x="168" y="258" width="24" height="66" fill="${accent}" opacity="0.82"/>
                ${headShape}
                ${crownOrHat}
                <rect x="120" y="224" width="120" height="18" rx="9" fill="${secondary}" opacity="0.96"/>
                ${eyeShape}
                <rect x="168" y="196" width="24" height="9" rx="4.5" fill="${primary}" opacity="0.35"/>
                ${mouthShape}
                ${accessoryShape}
            </svg>
        `;
    }

    function renderMetrics() {
        const metrics = getMetrics();
        const config = getMetricConfig();
        elements.metricsGrid.innerHTML = "";

        Object.keys(config).forEach((metricId) => {
            const item = config[metricId] || {};
            const value = Number(metrics[metricId] || 0);
            const card = document.createElement("article");
            card.className = "metric-card";
            card.innerHTML = `
                <header>
                    <strong>${item.label || metricId}</strong>
                    <span class="metric-value">${value}</span>
                </header>
                <div class="meter-track">
                    <div class="meter-fill" style="width: ${clamp(value, 0, 100)}%; background: ${item.color || "#999"};"></div>
                </div>
            `;
            elements.metricsGrid.appendChild(card);
        });
    }

    function renderCard() {
        const runState = getRunState();
        const activeCard = getActiveCard();
        const drawCount = getDrawPile().length;

        elements.turnPill.textContent = `Turn ${runState.turn || 1}`;
        elements.dynastyPill.textContent = `${runState.ruler_name || "Ruler"} • ${runState.dynasty_name || "the regency"}`;
        elements.bufferPill.textContent = `${drawCount} future card${drawCount === 1 ? "" : "s"} ready`;

        if (runState.status === "ended") {
            elements.endBanner.classList.remove("hidden");
            elements.endBanner.textContent = runState.ending_reason || "The reign has ended.";
        } else {
            elements.endBanner.classList.add("hidden");
            elements.endBanner.textContent = "";
        }

        if (!activeCard) {
            const fallbackSpec = {
                archetype: "sovereign_vault",
                face_shape: "oval",
                headwear: "crown",
                accessory: "none",
                mood: "calm",
                silhouette: "layered",
                primary_color: "#5b4a3f",
                secondary_color: "#e7c8a2",
                accent_color: "#ddb45f",
                skin_tone: "#e7c8a2",
            };
            elements.speakerName.textContent = runState.status === "ended" ? "Archive Closed" : "Relay Between Petitions";
            elements.speakerRole.textContent = runState.status === "ended"
                ? "Run complete"
                : state.pendingGeneration
                    ? "Fabrication in progress"
                    : "Awaiting the next signal";
            elements.promptText.textContent = runState.status === "ended"
                ? "The regency has collapsed. Review the archive or return to the menu."
                : state.pendingGeneration
                    ? "New machine petitions are being fabricated. Hold while the relay assembles the next card."
                    : "The next machine petition is being prepared.";
            elements.leftChoiceLabel.textContent = "Unavailable";
            elements.rightChoiceLabel.textContent = "Unavailable";
            if (state.pendingGeneration && runState.status !== "ended") {
                elements.portraitFrame.style.background = [
                    "radial-gradient(circle at 50% 20%, rgba(123, 168, 217, 0.28), transparent 26%)",
                    "radial-gradient(circle at 20% 78%, rgba(221, 180, 95, 0.16), transparent 34%)",
                    "linear-gradient(160deg, rgba(38, 46, 62, 0.96) 0%, rgba(54, 36, 46, 0.9) 52%, rgba(19, 18, 27, 0.98) 100%)",
                ].join(", ");
                elements.portraitFrame.innerHTML = `
                    <div class="portrait-loading" aria-label="Generating new cards">
                        <div class="loading-orbit loading-orbit-a"></div>
                        <div class="loading-orbit loading-orbit-b"></div>
                        <div class="loading-core">
                            <span class="loading-core-ring"></span>
                            <span class="loading-core-dot"></span>
                        </div>
                        <div class="loading-caption">Fabricating petitions</div>
                    </div>
                `;
            } else {
                elements.portraitFrame.style.background = buildPortraitBackground(fallbackSpec);
                elements.portraitFrame.innerHTML = makePortraitSvg({
                    id: "empty",
                    speaker_name: "Vault Relay",
                    portrait_spec: fallbackSpec,
                });
            }
            return;
        }

        elements.speakerName.textContent = activeCard.speaker_name || "Unknown Petitioner";
        elements.speakerRole.textContent = (activeCard.speaker_role || "machine petitioner").replace(/_/g, " ");
        elements.promptText.textContent = activeCard.prompt_text || "No active petition text.";
        elements.leftChoiceLabel.textContent = activeCard.left_choice?.label || "Left";
        elements.rightChoiceLabel.textContent = activeCard.right_choice?.label || "Right";
        elements.portraitFrame.style.background = buildPortraitBackground(activeCard.portrait_spec || {});
        elements.portraitFrame.innerHTML = makePortraitSvg(activeCard);
    }

    function renderStatus() {
        const runState = getRunState();
        const drawCount = getDrawPile().length;
        const activeCard = getActiveCard();
        renderGenerationTone();

        if (runState.status === "ended") {
            setStageStatus(runState.ending_reason || "The realm has fallen out of balance.");
            return;
        }

        if (state.pendingChoice) {
            setStageStatus("Recording the consequence of your decree...");
            return;
        }

        if (state.pendingGeneration) {
            setStageStatus("The machine court is quietly preparing fresh petitions.");
            return;
        }

        if (activeCard) {
            setStageStatus(`Choose how ${getRunState().ruler_name || "the sovereign mind"} will answer ${activeCard.speaker_name || "this petitioning unit"}.`);
        } else {
            setStageStatus("Waiting for the next card.");
        }
    }

    function renderButtons() {
        const runState = getRunState();
        const activeCard = getActiveCard();
        const disabled = !activeCard || state.pendingChoice || runState.status === "ended";
        elements.leftChoiceButton.disabled = disabled;
        elements.rightChoiceButton.disabled = disabled;
    }

    function renderAll() {
        renderMetrics();
        renderCard();
        renderButtons();
        renderStatus();
    }

    function resetSwipePreview() {
        state.exitAnimationToken += 1;
        state.swipeCurrentDx = 0;
        elements.decisionCard.style.transform = "";
        elements.decisionCard.classList.remove(
            "choice-left-preview",
            "choice-right-preview",
            "card-exit-left",
            "card-exit-right"
        );
        elements.swipeLeftIndicator.classList.remove("visible");
        elements.swipeRightIndicator.classList.remove("visible");
    }

    function playSwipeExit(choiceSide) {
        const token = state.exitAnimationToken + 1;
        state.exitAnimationToken = token;
        elements.decisionCard.classList.remove("choice-left-preview", "choice-right-preview", "card-exit-left", "card-exit-right");
        elements.swipeLeftIndicator.classList.remove("visible");
        elements.swipeRightIndicator.classList.remove("visible");
        void elements.decisionCard.offsetWidth;
        elements.decisionCard.classList.add(choiceSide === "left" ? "card-exit-left" : "card-exit-right");
        return new Promise((resolve) => {
            window.setTimeout(() => {
                if (state.exitAnimationToken !== token) {
                    resolve(false);
                    return;
                }
                resolve(true);
            }, 180);
        });
    }

    function applySwipePreview(dx) {
        state.swipeCurrentDx = dx;
        const limitedDx = clamp(dx, -140, 140);
        const rotation = limitedDx / 20;
        elements.decisionCard.style.transform = `translateX(${limitedDx}px) rotate(${rotation}deg)`;
        elements.decisionCard.classList.toggle("choice-left-preview", limitedDx < -20);
        elements.decisionCard.classList.toggle("choice-right-preview", limitedDx > 20);
        elements.swipeLeftIndicator.classList.toggle("visible", limitedDx < -36);
        elements.swipeRightIndicator.classList.toggle("visible", limitedDx > 36);
    }

    function syncGameState(nextState) {
        if (!nextState || typeof nextState !== "object") {
            return;
        }
        state.gameState = nextState;
        renderAll();
    }

    function extractStructuredResult(message) {
        if (!message || typeof message !== "object") {
            return null;
        }
        const content = message.content || {};
        const response = content.response || {};
        return (
            content.structured_result ||
            response.structured_result ||
            null
        );
    }

    function requestGeneration(force) {
        const runState = getRunState();
        const activeCard = getActiveCard();
        const futureCount = getDrawPile().length;
        const bufferTarget = numberOrDefault(runState.buffer_target, 5);
        const refillThreshold = numberOrDefault(runState.refill_threshold, 1);
        const generationBatchSize = numberOrDefault(runState.generation_batch_size, 5);
        const desiredGenerationCount = Math.max(
            0,
            Math.min(generationBatchSize, bufferTarget - futureCount)
        );
        if (!force && desiredGenerationCount <= 0) {
            return;
        }
        const keyPayload = {
            turn: runState.turn || 0,
            active: activeCard ? activeCard.id : null,
            futureCount,
            refillThreshold,
            desiredGenerationCount,
            queue: getGenerationQueue().map((item) => item.id || item.tag || item),
            recent: getRecentGeneratedIds().slice(-4),
        };
        const key = JSON.stringify(keyPayload);
        if (!force && key === state.lastGenerationKey) {
            return;
        }

        state.pendingGeneration = true;
        state.lastGenerationKey = key;
        renderStatus();
        renderButtons();

        bridge.sendArchitectTask("ui_requested_generation", {
            action_id: "reigns_generate_cards",
            active_view: "generation",
            task_profile: "uiDecision",
            player_input: "Generate the next machine petitions.",
            action_hint: "top_up_future_court_cards",
            purpose:
                "Refill the future card buffer for the Crown Council story app in a multi-card batch. Prefer follow-ups to unresolved political threads and persist generated cards into state without narrating to the player.",
            structured_input: {
                buffer_target: bufferTarget,
                refill_threshold: refillThreshold,
                generation_batch_size: generationBatchSize,
                desired_generation_count: desiredGenerationCount,
                current_future_count: futureCount,
                active_card_id: activeCard ? activeCard.id : null,
                active_card: summarizeCard(activeCard, true),
                draw_pile: getDrawPile(),
                kingdom_metrics: getMetrics(),
                open_threads: getOpenThreads(),
                generation_queue: getGenerationQueue(),
                recent_generated_card_ids: getRecentGeneratedIds(),
                choice_history_tail: getChoiceHistory().slice(-Number(runState.max_recent_history || 6)),
                visible_cards: summarizeVisibleCards(),
            },
            expected_output:
                "Return generated_card_ids, generated_count, and a short reason. Persist new cards into variables.card_library and append them to variables.draw_pile.",
            extra_context: {
                ui_mode: "reigns_style_story_app",
                active_view: "generation",
            },
            input_type: "story_app",
        });
    }

    function maybeRequestGeneration(force) {
        const runState = getRunState();
        const activeCard = getActiveCard();
        if (runState.status === "ended" || state.pendingGeneration || state.pendingChoice || state.pendingPromotion) {
            return;
        }
        if (activeCard) {
            return;
        }
        const futureCount = getDrawPile().length;
        const refillThreshold = numberOrDefault(runState.refill_threshold, 1);
        const shouldGenerate = force || futureCount <= refillThreshold;
        if (!shouldGenerate) {
            return;
        }
        requestGeneration(true);
    }

    function maybePromoteQueuedCard() {
        const runState = getRunState();
        if (runState.status === "ended" || state.pendingChoice || state.pendingPromotion) {
            return false;
        }
        if (getActiveCard()) {
            return false;
        }
        const drawPile = getDrawPile();
        if (!Array.isArray(drawPile) || drawPile.length === 0) {
            return false;
        }
        const cardLibrary = cloneValue(getCardLibrary());
        const nextCardId = drawPile[0];
        if (!nextCardId || !cardLibrary[nextCardId]) {
            return false;
        }

        const promotedCard = cloneValue(cardLibrary[nextCardId]);
        promotedCard.status = "active";
        cardLibrary[nextCardId] = promotedCard;

        state.pendingPromotion = true;
        renderButtons();
        renderStatus();
        bridge.sendDeterministicAction(
            "merge_patch",
            {
                patch: {
                    variables: {
                        active_card_id: nextCardId,
                        draw_pile: drawPile.slice(1),
                        card_library: cardLibrary,
                    },
                },
                displayText: "",
            },
            {
                display_text: "",
            }
        );
        return true;
    }

    function normalizeThreadTag(tag) {
        return String(tag || "")
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9_]+/g, "_")
            .replace(/^_+|_+$/g, "");
    }

    function threadLabel(tag) {
        return normalizeThreadTag(tag).replace(/_/g, " ");
    }

    function upsertOpenThreads(existingThreads, tags, turn, summary) {
        const nextThreads = Array.isArray(existingThreads) ? cloneValue(existingThreads) : [];
        const existingTags = new Set(
            nextThreads.map((thread) => normalizeThreadTag(typeof thread === "string" ? thread : thread.tag || thread.id))
        );

        tags.forEach((rawTag) => {
            const tag = normalizeThreadTag(rawTag);
            if (!tag || existingTags.has(tag)) {
                return;
            }
            nextThreads.push({
                id: tag,
                tag,
                label: threadLabel(tag),
                summary,
                urgency: 1,
                introduced_turn: turn,
                status: "open",
            });
            existingTags.add(tag);
        });

        return nextThreads;
    }

    function resolveOpenThreads(existingThreads, resolvedTags) {
        const resolved = new Set((resolvedTags || []).map(normalizeThreadTag).filter(Boolean));
        if (resolved.size === 0) {
            return Array.isArray(existingThreads) ? cloneValue(existingThreads) : [];
        }
        return (Array.isArray(existingThreads) ? existingThreads : []).filter((thread) => {
            const tag = normalizeThreadTag(typeof thread === "string" ? thread : thread.tag || thread.id);
            return !resolved.has(tag);
        }).map((thread) => cloneValue(thread));
    }

    function updateGenerationQueue(existingQueue, openedTags, resolvedTags, turn, summary) {
        const resolved = new Set((resolvedTags || []).map(normalizeThreadTag).filter(Boolean));
        const nextQueue = (Array.isArray(existingQueue) ? existingQueue : [])
            .filter((item) => !resolved.has(normalizeThreadTag(item.tag || item.id)))
            .map((item) => cloneValue(item));
        const existingTags = new Set(nextQueue.map((item) => normalizeThreadTag(item.tag || item.id)));

        (openedTags || []).forEach((rawTag) => {
            const tag = normalizeThreadTag(rawTag);
            if (!tag || existingTags.has(tag)) {
                return;
            }
            nextQueue.push({
                id: `queue_${tag}`,
                tag,
                reason: summary,
                urgency: 1,
                requested_turn: turn,
            });
            existingTags.add(tag);
        });

        return nextQueue;
    }

    function nextActiveFromDrawPile(drawPile, cardLibrary) {
        const queue = Array.isArray(drawPile) ? [...drawPile] : [];
        while (queue.length > 0) {
            const cardId = queue.shift();
            if (cardLibrary[cardId]) {
                return { nextActiveId: cardId, remainingDrawPile: queue };
            }
        }
        return { nextActiveId: null, remainingDrawPile: [] };
    }

    function buildDeterministicChoicePatch(activeCard, choiceSide) {
        const variables = getVariables();
        const runState = getRunState();
        const currentTurn = Number(runState.turn || 1);
        const branch = activeCard && activeCard[`${choiceSide}_choice`];
        if (!activeCard || !branch) {
            return null;
        }

        const currentMetrics = getMetrics();
        const metricChanges = cloneValue(branch.effect_bias || {});
        const nextMetrics = cloneValue(currentMetrics);
        Object.keys(metricChanges).forEach((metricId) => {
            const currentValue = Number(nextMetrics[metricId] || 0);
            nextMetrics[metricId] = clamp(currentValue + Number(metricChanges[metricId] || 0), 0, 100);
        });

        const summary = branch.outcome_summary || `${activeCard.speaker_name || "The machine court"} was answered.`;
        const openedThreads = Array.isArray(branch.opens_threads) ? branch.opens_threads : [];
        const resolvedThreads = Array.isArray(branch.resolves_threads) ? branch.resolves_threads : [];
        const nextChoiceHistory = [...getChoiceHistory(), {
            turn: currentTurn,
            card_id: activeCard.id,
            speaker_name: activeCard.speaker_name || activeCard.id,
            choice_side: choiceSide,
            choice_label: branch.label || choiceSide,
            summary,
            metric_changes: metricChanges,
        }];
        const nextRecentOutcomes = [...(Array.isArray(variables.recent_outcomes) ? variables.recent_outcomes : []), summary].slice(-6);
        const threadsAfterResolution = resolveOpenThreads(getOpenThreads(), resolvedThreads);
        const nextOpenThreads = upsertOpenThreads(threadsAfterResolution, openedThreads, currentTurn, summary);
        const nextGenerationQueue = updateGenerationQueue(getGenerationQueue(), openedThreads, resolvedThreads, currentTurn, summary);
        const nextRecentGenerated = getRecentGeneratedIds().slice(-8);

        const cardLibrary = cloneValue(getCardLibrary());
        const currentCard = cloneValue(cardLibrary[activeCard.id] || activeCard);
        currentCard.times_used = Number(currentCard.times_used || 0) + 1;
        const reuseRules = currentCard.reuse_rules || {};
        const maxUses = Number(reuseRules.max_uses || 1);
        const canReuse = reuseRules.mode === "reusable" && currentCard.times_used < maxUses;
        currentCard.status = canReuse ? "reusable" : "spent";
        currentCard.last_resolved_turn = currentTurn;
        cardLibrary[currentCard.id] = currentCard;

        const selection = nextActiveFromDrawPile(getDrawPile(), cardLibrary);
        let nextActiveId = selection.nextActiveId;
        const nextDrawPile = selection.remainingDrawPile;
        if (nextActiveId && cardLibrary[nextActiveId]) {
            const promoted = cloneValue(cardLibrary[nextActiveId]);
            promoted.status = "active";
            cardLibrary[nextActiveId] = promoted;
        }

        const endingMetric = Object.keys(nextMetrics).find((metricId) => nextMetrics[metricId] <= 0 || nextMetrics[metricId] >= 100);
        const nextRunState = cloneValue(runState);
        if (endingMetric) {
            const metricLabel = (getMetricConfig()[endingMetric] || {}).label || endingMetric;
            nextRunState.status = "ended";
            nextRunState.ending = endingMetric;
            nextRunState.ending_reason = `${metricLabel} fell out of balance and the reign collapsed.`;
            nextActiveId = null;
        } else {
            nextRunState.turn = currentTurn + 1;
        }

        return {
            patch: {
                variables: {
                    kingdom_metrics: nextMetrics,
                    choice_history: nextChoiceHistory,
                    recent_outcomes: nextRecentOutcomes,
                    open_threads: nextOpenThreads,
                    generation_queue: nextGenerationQueue,
                    recent_generated_card_ids: nextRecentGenerated,
                    active_card_id: nextActiveId,
                    draw_pile: nextDrawPile,
                    card_library: cardLibrary,
                    run_state: nextRunState,
                },
            },
            displayText: summary,
        };
    }

    async function submitChoice(choiceSide) {
        const runState = getRunState();
        const activeCard = getActiveCard();
        if (!activeCard || state.pendingChoice || runState.status === "ended") {
            return;
        }

        state.pendingChoice = true;
        renderButtons();
        renderStatus();
        const deterministic = buildDeterministicChoicePatch(activeCard, choiceSide);
        if (!deterministic) {
            state.pendingChoice = false;
            resetSwipePreview();
            renderAll();
            return;
        }

        await playSwipeExit(choiceSide);
        bridge.sendDeterministicAction(
            "merge_patch",
            deterministic,
            {
                display_text: deterministic.displayText,
            }
        );
    }

    function handleInit(payload) {
        state.initPayload = payload || {};
        const runState = (payload && payload.gameState && payload.gameState.variables && payload.gameState.variables.run_state) || {};
        elements.subtitle.textContent = `Guide ${runState.ruler_name || "the preserved ruler"} through the compromises of ${runState.dynasty_name || "the machine regency"}.`;
        syncGameState((payload && payload.gameState) || { variables: {} });
    }

    function handleCommandResult(message) {
        const content = message && message.content ? message.content : {};
        const hadPendingChoice = state.pendingChoice;
        if (content.game_state) {
            syncGameState(content.game_state);
        }

        const structured = extractStructuredResult(message);
        if (structured) {
            state.lastStructured = structured;
            if (state.pendingGeneration) {
                state.pendingGeneration = false;
            }
            if (state.pendingChoice) {
                state.pendingChoice = false;
            }
        }

        const response = content.response || {};
        const isGenerationResponse = response.task_type === "ui_requested_generation";
        if (response.deterministic_result) {
            state.pendingChoice = false;
            state.pendingPromotion = false;
        }
        if (state.pendingGeneration && isGenerationResponse) {
            state.pendingGeneration = false;
        }
        if (state.pendingChoice && response.task_type && !isGenerationResponse) {
            state.pendingChoice = false;
        }

        resetSwipePreview();
        renderAll();
        if (maybePromoteQueuedCard()) {
            return;
        }
        if (hadPendingChoice) {
            window.setTimeout(() => {
                maybeRequestGeneration(false);
            }, 80);
        }
    }

    function handleError(message) {
        state.pendingChoice = false;
        state.pendingGeneration = false;
        state.pendingPromotion = false;
        resetSwipePreview();
        const text = (message && message.content && message.content.text) || "The machine court interface hit an error.";
        setStageStatus(text);
        renderAll();
    }

    function handleEvent(message) {
        if (!message || typeof message !== "object") {
            return;
        }

        if (message.type === "game_start") {
            handleInit({
                gameState: message.content?.game_state,
            });
            return;
        }

        if (message.type === "game_state") {
            syncGameState(message.content);
            maybePromoteQueuedCard();
            return;
        }

        if (message.type === "command_result") {
            handleCommandResult(message);
            return;
        }

        if (message.type === "error") {
            handleError(message);
        }
    }

    function bindInput() {
        elements.leftChoiceButton.addEventListener("click", () => submitChoice("left"));
        elements.rightChoiceButton.addEventListener("click", () => submitChoice("right"));
        elements.returnMenuButton.addEventListener("click", () => {
            bridge.requestReturnToMenu();
        });

        window.addEventListener("keydown", (event) => {
            if (event.key === "ArrowLeft") {
                event.preventDefault();
                submitChoice("left");
            } else if (event.key === "ArrowRight") {
                event.preventDefault();
                submitChoice("right");
            }
        });

        elements.decisionCard.addEventListener("pointerdown", (event) => {
            if (state.pendingChoice || getRunState().status === "ended") {
                return;
            }
            state.swipeStart = { x: event.clientX, y: event.clientY };
            elements.decisionCard.setPointerCapture(event.pointerId);
        });
        elements.decisionCard.addEventListener("pointermove", (event) => {
            if (!state.swipeStart) {
                return;
            }
            const dx = event.clientX - state.swipeStart.x;
            const dy = event.clientY - state.swipeStart.y;
            if (Math.abs(dx) <= Math.abs(dy)) {
                return;
            }
            applySwipePreview(dx);
        });
        elements.decisionCard.addEventListener("pointerup", (event) => {
            if (!state.swipeStart) {
                return;
            }
            const dx = event.clientX - state.swipeStart.x;
            const dy = event.clientY - state.swipeStart.y;
            state.swipeStart = null;
            if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy)) {
                resetSwipePreview();
                return;
            }
            submitChoice(dx < 0 ? "left" : "right");
        });
        elements.decisionCard.addEventListener("pointercancel", () => {
            state.swipeStart = null;
            resetSwipePreview();
        });
    }

    bindInput();
    bridge.on("init", handleInit);
    bridge.on("event", handleEvent);
    bridge.requestInitialState();
})();
