let socket = null;
let playerName = '';
let playerId = ''; // This will now be the persistent player ID
let sessionCode = '';
let saveCode = ''; // 新增：保存的代码
let selectedStory = ''; // 新增：当前选择的故事ID
let selectedStoryTitle = '';
let isAwaitingGameStart = false;
let currentNodeId = null;
let messageQueue = [];
let isTyping = false;
let typingSpeed = 30; // 打字速度（毫秒/字符）
let currentGameMessage = null;
let typewriterEffectEnabled = false; // 控制打字机效果是否启用
let savedGames = []; // 新增：保存的列表
let stashedStoryChoices = null; // For stashing story choices when showing object actions
let pendingObjectActionRequest = null;
let loadingBubbleEl = null;
let isExportingMessages = false;

// --- WebSocket Reconnection ---
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY_MS = 1000; // 1 second, will exponentially back off
let reconnectTimer = null;

// --- Sticky Description State Machine ---
const StickyState = {
    NORMAL: 'normal',      // Description in normal scroll position
    MERGED: 'merged'       // Fully merged into status bar (threshold-based snap)
};

let stickyDescriptionState = {
    state: StickyState.NORMAL,
    trackedNodeId: null,   // The node ID we're tracking for sticky
    rafId: null            // requestAnimationFrame ID
};

const converter = typeof showdown !== 'undefined'
    ? new showdown.Converter({
        literalMidWordUnderscores: true,
        simpleLineBreaks: true
    })
    : { makeHtml: (text) => text };

// DOM元素
const welcomeMessage = document.getElementById('welcome-message');
const playerNameInput = document.getElementById('player-name-input');
const playerNameField = document.getElementById('player-name');
const submitNameButton = document.getElementById('submit-name');
const storySelection = document.getElementById('story-selection');
const storyList = document.querySelector('.story-list');
const sessionSelection = document.getElementById('session-selection');
const createSessionButton = document.getElementById('create-session');
const joinSessionButton = document.getElementById('join-session');
const sessionCodeInput = document.getElementById('session-code-input');
const mainContent = document.querySelector('.main-content');
const gameMessages = document.getElementById('game-messages');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const continueButton = document.getElementById('continue-button');
const sessionCodeDisplay = document.getElementById('session-code-display');
const copySessionCodeButton = document.getElementById('copy-session-code');
const loadingOverlay = document.getElementById('loading-overlay');
const displayToggleBtn = document.getElementById('display-toggle-btn');
const displayPanel = document.getElementById('display-panel');
const nodeDescription = document.getElementById('node-description');
const inventoryDisplay = document.getElementById('inventory-display');
const statsDisplay = document.getElementById('stats-display');
const saveGameButton = document.getElementById('save-game-button');
const exportHistoryButton = document.getElementById('export-history-button');
const languageSelect = document.getElementById('language-select');
const mentionOverlay = document.getElementById('mention-overlay');
const commandPalette = document.getElementById('command-palette');
const mentionSuggestions = document.getElementById('mention-suggestions');

// --- New Persistent ID Logic ---
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function getOrSetPersistentPlayerId() {
    let persistentId = localStorage.getItem('persistentPlayerId');
    if (!persistentId) {
        persistentId = generateUUID();
        localStorage.setItem('persistentPlayerId', persistentId);
    }
    return persistentId;
}
// --- End New Logic ---

function getGameVariables(gameState) {
    if (gameState?.diff?.variables) return gameState.diff.variables;
    return gameState?.variables;
}

function getCurrentPlayerState(gameState) {
    if (gameState?.player_state) return gameState.player_state;
    const variables = getGameVariables(gameState);
    return variables?.players?.[playerId] || null;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function normalizeMentionText(text) {
    if (!text) return '';
    return String(text).trim().replace(/\s+/g, '_');
}

function buildMentionCandidates() {
    const candidates = [];
    const seen = new Set();

    (availableCharacters || []).forEach(character => {
        // Skip player's own character (playable characters)
        if (character.is_playable) return;
        
        const charId = character.id || '';
        const charName = character.name || '';
        
        // Only add character by name (not by ID separately)
        // Use the character ID as mentionText for backend compatibility
        const displayName = charName || charId;
        if (displayName && !seen.has(displayName.toLowerCase())) {
            seen.add(displayName.toLowerCase());
            candidates.push({
                id: charId,
                name: displayName,
                mentionText: charId,  // Use ID for @mention to ensure backend can resolve it
                type: 'character'
            });
        }
    });

    (sessionPlayers || []).forEach(player => {
        if (!player || player.id === playerId) return;
        const rawName = player.name || '';
        const mentionText = normalizeMentionText(rawName);
        const key = mentionText.toLowerCase();
        if (!mentionText || seen.has(key)) return;
        seen.add(key);
        candidates.push({
            id: player.id,
            name: rawName,
            mentionText,
            type: 'player'
        });
    });

    return candidates;
}

function getMentionTokenSet() {
    const tokens = new Set();
    buildMentionCandidates().forEach(candidate => {
        tokens.add(candidate.mentionText.toLowerCase());
    });
    return tokens;
}

function updateMentionOverlay() {
    if (!mentionOverlay) return;
    const value = userInput.value || '';
    if (!value) {
        mentionOverlay.innerHTML = '';
        return;
    }

    const tokenSet = getMentionTokenSet();
    const regex = /@([\w\u4e00-\u9fff]+)/g;
    let result = '';
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(value)) !== null) {
        const start = match.index;
        const end = regex.lastIndex;
        result += escapeHtml(value.slice(lastIndex, start));
        const mentionText = match[1];
        if (tokenSet.has(mentionText.toLowerCase())) {
            result += `<span class="mention-highlight">@${escapeHtml(mentionText)}</span>`;
        } else {
            result += escapeHtml(value.slice(start, end));
        }
        lastIndex = end;
    }

    result += escapeHtml(value.slice(lastIndex));
    mentionOverlay.innerHTML = result;
    mentionOverlay.scrollLeft = userInput.scrollLeft;
}

function getMentionContext(value, caretIndex) {
    const left = value.slice(0, caretIndex);
    const atIndex = left.lastIndexOf('@');
    if (atIndex === -1) return null;

    if (atIndex > 0 && /[\w\u4e00-\u9fff]/.test(value[atIndex - 1])) {
        return null;
    }

    const token = left.slice(atIndex + 1);
    if (/\s/.test(token)) {
        return null;
    }

    return {
        startIndex: atIndex,
        caretIndex,
        query: token || ''
    };
}

function filterMentionCandidates(query) {
    const lowerQuery = query.toLowerCase();
    return buildMentionCandidates().filter(candidate =>
        candidate.mentionText.toLowerCase().includes(lowerQuery) ||
        candidate.name.toLowerCase().includes(lowerQuery)
    );
}

function closeMentionSuggestions() {
    mentionState.isOpen = false;
    mentionState.candidates = [];
    mentionState.query = '';
    mentionState.selectedIndex = 0;
    if (mentionSuggestions) {
        mentionSuggestions.classList.add('hidden');
        mentionSuggestions.innerHTML = '';
    }
}

function renderMentionSuggestions() {
    if (!mentionSuggestions || !mentionState.isOpen) return;
    mentionSuggestions.innerHTML = '';

    mentionState.candidates.forEach((candidate, index) => {
        const item = document.createElement('div');
        item.className = 'mention-suggestion';
        if (index === mentionState.selectedIndex) {
            item.classList.add('active');
        }
        item.innerHTML = `
            <span>${escapeHtml(candidate.name)}</span>
            <span class="mention-type">${candidate.type}</span>
        `;
        item.addEventListener('mouseenter', () => {
            mentionState.selectedIndex = index;
            renderMentionSuggestions();
        });
        item.addEventListener('mousedown', (event) => {
            event.preventDefault();
            applyMentionSelection(candidate);
        });
        mentionSuggestions.appendChild(item);
    });

    mentionSuggestions.classList.remove('hidden');
}

function applyMentionSelection(candidate) {
    const value = userInput.value;
    const before = value.slice(0, mentionState.startIndex);
    const after = value.slice(mentionState.caretIndex);
    const mentionText = `@${candidate.mentionText}`;
    const needsSpace = after.length === 0 || !/^[\s,.!?]/.test(after);
    const insertText = mentionText + (needsSpace ? ' ' : '');

    userInput.value = before + insertText + after;
    const newCaretIndex = before.length + insertText.length;
    userInput.setSelectionRange(newCaretIndex, newCaretIndex);
    userInput.focus();

    closeMentionSuggestions();
    updateMentionOverlay();
}

function handleMentionInput() {
    updateMentionOverlay();
    if (!userInput) return;
    const context = getMentionContext(userInput.value, userInput.selectionStart);
    if (!context) {
        closeMentionSuggestions();
        return;
    }

    const candidates = filterMentionCandidates(context.query);
    if (!candidates.length) {
        closeMentionSuggestions();
        return;
    }

    mentionState.isOpen = true;
    mentionState.startIndex = context.startIndex;
    mentionState.caretIndex = context.caretIndex;
    mentionState.query = context.query;
    mentionState.candidates = candidates;
    mentionState.selectedIndex = 0;
    renderMentionSuggestions();
}

function handleMentionKeydown(event) {
    if (!mentionState.isOpen) return;

    if (event.key === 'ArrowDown') {
        event.preventDefault();
        mentionState.selectedIndex = (mentionState.selectedIndex + 1) % mentionState.candidates.length;
        renderMentionSuggestions();
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        mentionState.selectedIndex = (mentionState.selectedIndex - 1 + mentionState.candidates.length) % mentionState.candidates.length;
        renderMentionSuggestions();
    } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        const candidate = mentionState.candidates[mentionState.selectedIndex];
        if (candidate) {
            applyMentionSelection(candidate);
        }
    } else if (event.key === 'Escape') {
        event.preventDefault();
        closeMentionSuggestions();
    }
}

function setAvailableCharacters(characters) {
    availableCharacters = Array.isArray(characters) ? characters : [];
    updateMentionOverlay();
}

function setSessionPlayers(players) {
    sessionPlayers = Array.isArray(players) ? players : [];
    updateMentionOverlay();
}

function preprocessDescription(text) {
    if (!text) return '';
    const escapeJsString = (value) => String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
    const renderActionLink = (displayText, actionHint = '') =>
        `<a href="#" class="game-action-link" onclick="onActionClick('${escapeJsString(displayText)}', '${escapeJsString(actionHint)}'); return false;">${escapeHtml(displayText)}</a>`;
    const renderObjectLink = (objectId, displayText) =>
        `<a href="#" class="game-object-link" onclick="onObjectClick('${escapeJsString(objectId)}'); return false;">${escapeHtml(displayText)}</a>`;
    const renderCharacterLink = (characterId, displayText) =>
        `<a href="#" class="game-character-link" onclick="onCharacterClick('${escapeJsString(characterId)}'); return false;">${escapeHtml(displayText)}</a>`;

    const colonRegex = /\{([^{}:]+):([^{}]+)\}/g;
    const bareRegex = /\{([^{}]+)\}/g;

    let processed = text.replace(colonRegex, (match, left, right) => {
        const trimmedLeft = left.trim();
        const trimmedRight = right.trim();

        if (trimmedLeft.startsWith('@') && trimmedLeft.length > 1) {
            return renderCharacterLink(trimmedLeft.slice(1), trimmedRight);
        }

        if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(trimmedLeft)) {
            return renderObjectLink(trimmedLeft, trimmedRight);
        }

        return renderActionLink(trimmedLeft, trimmedRight);
    });

    processed = processed.replace(bareRegex, (match, inner) => {
        const trimmedInner = inner.trim();
        if (!trimmedInner || trimmedInner.startsWith('<')) {
            return match;
        }
        return renderActionLink(trimmedInner, '');
    });

    return processed;
}

// 初始化函数
function init() {
    welcomeMessage.style.display = 'none';
    playerId = getOrSetPersistentPlayerId();
    console.log("Persistent Player ID:", playerId);

    document.getElementById('choices-container').classList.add('hidden');
    setupEventListeners();
    setupLanguageSetting();
    connectWebSocket();
    setupTypewriterToggle();
    initStickyDescriptionObserver();
}

// 设置事件监听器
function setupEventListeners() {
    submitNameButton.addEventListener('click', submitPlayerName);
    playerNameField.addEventListener('keypress', (e) => e.key === 'Enter' && submitPlayerName());
    createSessionButton.addEventListener('click', createSession);
    joinSessionButton.addEventListener('click', joinSession);
    sendButton.addEventListener('click', () => {
        console.log('Send button clicked, mainContent display:', mainContent.style.display);
        // Only send command if we're in the game interface
        if (mainContent.style.display !== 'none') {
            console.log('Send button: calling sendCommand()');
            sendCommand();
        } else {
            console.log('Send button: blocked because mainContent is hidden');
        }
    });
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && mainContent.style.display !== 'none') {
            if (mentionState.isOpen || slashCommandState.isOpen) {
                return;
            }
            sendCommand();
        }
    });
    userInput.addEventListener('input', handleComposerInput);
    userInput.addEventListener('keydown', handleComposerKeydown);
    userInput.addEventListener('scroll', () => {
        if (mentionOverlay) {
            mentionOverlay.scrollLeft = userInput.scrollLeft;
        }
    });
    userInput.addEventListener('click', handleComposerInput);
    userInput.addEventListener('blur', () => {
        setTimeout(closeComposerSuggestions, 150);
    });
    if (mentionSuggestions) {
        mentionSuggestions.addEventListener('mousedown', (event) => {
            event.preventDefault();
        });
    }
    if (commandPalette) {
        commandPalette.addEventListener('mousedown', (event) => {
            event.preventDefault();
        });
    }
    copySessionCodeButton.addEventListener('click', copySessionCode);
    continueButton.addEventListener('click', skipToNextMessage);
    displayToggleBtn.addEventListener('click', toggleDisplayPanel);
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.panel-tab-content').forEach(c => c.classList.add('hidden'));
            document.getElementById('tab-' + tab.dataset.tab).classList.remove('hidden');
        });
    });
    saveGameButton.addEventListener('click', () => saveGame({ showUserMessage: false }));
    exportHistoryButton.addEventListener('click', handleExportMessages);
    document.getElementById('return-button').addEventListener('click', handleReturn);
    document.getElementById('reload-button').addEventListener('click', handleReload);
    document.addEventListener('textAdventure:localeChanged', () => {
        if (slashCommandState.isOpen) {
            renderSlashCommandPalette();
        }
    });
    // Add listener to restore stashed choices
    gameMessages.addEventListener('click', () => {
        if (stashedStoryChoices) {
            pendingObjectActionRequest = null;
            displayChoices(stashedStoryChoices, true); // isRestoring = true
            stashedStoryChoices = null;
        }
    });
}

function saveGame(options = {}) {
    const { showUserMessage = true, displayText = '/save' } = options;
    // TODO: Replace manual slash-triggered saves with autosave session support.
    dispatchSocketCommand('save', displayText, null, null, {
        showUserMessage
    });
}

async function handleExportMessages() {
    if (isExportingMessages) {
        return;
    }

    if (typeof html2canvas !== 'function') {
        alert('Export helper failed to load. Please refresh and try again.');
        return;
    }

    let captureRoot = null;
    const originalLabel = exportHistoryButton.textContent;

    try {
        isExportingMessages = true;
        exportHistoryButton.disabled = true;
        exportHistoryButton.textContent = 'Exporting...';

        await flushPendingMessagesForExport();

        const renderedMessages = getRenderableMessages();
        if (!renderedMessages.length) {
            alert('No message history to export yet.');
            return;
        }

        captureRoot = createExportCaptureRoot(gameMessages);
        const exportMessages = buildExportMessagesClone(renderedMessages);
        captureRoot.appendChild(exportMessages);

        const exportWidth = Math.ceil(exportMessages.getBoundingClientRect().width);
        const exportHeight = Math.ceil(exportMessages.getBoundingClientRect().height);
        const exportedParts = await exportMessagesAsPng(captureRoot, exportMessages, exportWidth, exportHeight);

        if (exportedParts === 1) {
            alert('Message history exported as PNG.');
        } else {
            alert(`Message history was too long for one image, so it was exported as ${exportedParts} PNG files.`);
        }
    } catch (error) {
        console.error('Failed to export message history:', error);
        alert('Failed to export message history. Please try again.');
    } finally {
        if (captureRoot) {
            captureRoot.remove();
        }
        exportHistoryButton.disabled = false;
        exportHistoryButton.textContent = originalLabel;
        isExportingMessages = false;
    }
}

async function flushPendingMessagesForExport() {
    const originalTypewriterSetting = typewriterEffectEnabled;
    typewriterEffectEnabled = false;

    try {
        while (currentGameMessage || messageQueue.length > 0) {
            if (currentGameMessage) {
                completeCurrentTypewriterMessage();
            } else {
                processNextMessage();
            }
            await Promise.resolve();
        }
        continueButton.classList.add('hidden');
    } finally {
        typewriterEffectEnabled = originalTypewriterSetting;
    }
}

function completeCurrentTypewriterMessage() {
    if (!currentGameMessage) {
        return;
    }

    if (currentGameMessage.timeoutId) {
        clearTimeout(currentGameMessage.timeoutId);
    }

    currentGameMessage.textNodes.forEach(textNodeInfo => {
        textNodeInfo.node.nodeValue = textNodeInfo.originalText;
    });

    finishCurrentMessage();
}

function getRenderableMessages() {
    return Array.from(gameMessages.children).filter(child => !child.classList.contains('loading-bubble'));
}

function createExportCaptureRoot(sourceElement) {
    const root = document.createElement('div');
    root.className = 'export-capture-root';

    const sourceWidth = Math.max(Math.ceil(sourceElement.getBoundingClientRect().width), 360);
    root.style.width = `${sourceWidth + 48}px`;

    document.body.appendChild(root);
    return root;
}

function buildExportMessagesClone(renderedMessages) {
    const exportMessages = document.createElement('div');
    exportMessages.className = 'game-messages export-capture-messages';
    exportMessages.style.margin = '0';
    exportMessages.style.flex = 'none';
    exportMessages.style.minHeight = '0';
    exportMessages.style.height = 'auto';
    exportMessages.style.maxHeight = 'none';
    exportMessages.style.overflow = 'visible';

    renderedMessages.forEach(message => {
        exportMessages.appendChild(message.cloneNode(true));
    });

    return exportMessages;
}

async function exportMessagesAsPng(captureRoot, exportMessages, exportWidth, exportHeight) {
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    const maxSingleCanvasHeight = Math.max(2400, Math.floor(14000 / scale));
    const baseFilename = buildExportFilenameBase();

    if (exportHeight <= maxSingleCanvasHeight) {
        const canvas = await html2canvas(exportMessages, {
            backgroundColor: '#f5f7fa',
            scale,
            useCORS: true,
            logging: false
        });
        await downloadCanvas(canvas, `${baseFilename}.png`);
        return 1;
    }

    const totalParts = Math.ceil(exportHeight / maxSingleCanvasHeight);

    for (let index = 0; index < totalParts; index++) {
        const startY = index * maxSingleCanvasHeight;
        const sliceHeight = Math.min(maxSingleCanvasHeight, exportHeight - startY);
        const sliceCanvas = await renderExportSlice(captureRoot, exportMessages, exportWidth, startY, sliceHeight, scale);
        const partSuffix = String(index + 1).padStart(2, '0');
        await downloadCanvas(sliceCanvas, `${baseFilename}-part-${partSuffix}.png`);
        await wait(150);
    }

    return totalParts;
}

async function renderExportSlice(captureRoot, exportMessages, exportWidth, startY, sliceHeight, scale) {
    const sliceContainer = document.createElement('div');
    sliceContainer.className = 'export-capture-slice';
    sliceContainer.style.width = `${exportWidth}px`;
    sliceContainer.style.height = `${sliceHeight}px`;

    const sliceContent = exportMessages.cloneNode(true);
    sliceContent.style.position = 'relative';
    sliceContent.style.top = `-${startY}px`;
    sliceContent.style.margin = '0';
    sliceContent.style.overflow = 'visible';

    sliceContainer.appendChild(sliceContent);
    captureRoot.appendChild(sliceContainer);

    try {
        return await html2canvas(sliceContainer, {
            backgroundColor: '#f5f7fa',
            scale,
            useCORS: true,
            logging: false,
            width: exportWidth,
            height: sliceHeight,
            windowWidth: exportWidth,
            windowHeight: sliceHeight
        });
    } finally {
        sliceContainer.remove();
    }
}

function buildExportFilenameBase() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, '0');
    return `wenyoo-history-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

async function downloadCanvas(canvas, filename) {
    const blob = await canvasToBlob(canvas);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => {
        URL.revokeObjectURL(url);
    }, 1000);
}

function canvasToBlob(canvas) {
    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (blob) {
                resolve(blob);
                return;
            }
            reject(new Error('Canvas export returned an empty blob.'));
        }, 'image/png');
    });
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 连接WebSocket
function connectWebSocket() {
    // Clear any pending reconnect timer
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        const payload = {
            type: 'register_or_rejoin',
            player_id: playerId
        };
        const storedToken = localStorage.getItem('sessionToken');
        if (storedToken) {
            payload.session_token = storedToken;
        }
        socket.send(JSON.stringify(payload));
    };
    socket.onmessage = (event) => handleWebSocketMessage(JSON.parse(event.data));
    socket.onclose = (event) => {
        if (event.wasClean) {
            console.log(`WebSocket closed cleanly, code=${event.code}`);
        } else {
            console.warn('WebSocket disconnected unexpectedly. Scheduling reconnect...');
            scheduleReconnect();
        }
    };
    socket.onerror = (error) => console.error(`WebSocket error:`, error);
}

function scheduleReconnect() {
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error(`Max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Please refresh the page.`);
        addGameMessage('Connection lost. Please refresh the page to reconnect.', 'error-message');
        return;
    }
    // Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s
    const delay = Math.min(BASE_RECONNECT_DELAY_MS * Math.pow(2, reconnectAttempts), 30000);
    reconnectAttempts++;
    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
    reconnectTimer = setTimeout(() => {
        connectWebSocket();
    }, delay);
}

function updateStatus(newText) {
    const statusInfo = document.getElementById('status-info');
    const currentStatus = statusInfo.querySelector('.current-status');
    const nextStatus = statusInfo.querySelector('.next-status');

    if (currentStatus.textContent === newText) {
        return; // No change
    }

    nextStatus.textContent = newText;
    statusInfo.classList.add('animating');

    setTimeout(() => {
        currentStatus.textContent = newText;
        statusInfo.classList.remove('animating');

        // Add flash effect
        statusInfo.classList.add('flash');
        setTimeout(() => {
            statusInfo.classList.remove('flash');
        }, 1500); // Duration of the flash animation

    }, 800); // Match CSS transition duration
}

// --- Sticky Description Functions ---

function initStickyDescriptionObserver() {
    const messagesContainer = document.getElementById('game-messages');

    messagesContainer.addEventListener('scroll', () => {
        if (stickyDescriptionState.rafId) {
            cancelAnimationFrame(stickyDescriptionState.rafId);
        }
        stickyDescriptionState.rafId = requestAnimationFrame(updateStickyDescriptionState);
    });
}

function updateStickyDescriptionState() {
    const messagesContainer = document.getElementById('game-messages');
    const statusBar = document.getElementById('status-bar-container');
    const stickyWrapper = document.getElementById('sticky-description-wrapper');

    // Only track current node's description
    const nodeIdToTrack = currentNodeId;
    if (!nodeIdToTrack) {
        transitionStickyTo(StickyState.NORMAL);
        return;
    }

    // Find the current node's description message
    const descriptionMessage = messagesContainer.querySelector(
        `.node-description-message[data-node-id="${nodeIdToTrack}"]`
    );

    if (!descriptionMessage) {
        transitionStickyTo(StickyState.NORMAL);
        return;
    }

    // Update tracked node ID
    if (stickyDescriptionState.trackedNodeId !== nodeIdToTrack) {
        stickyDescriptionState.trackedNodeId = nodeIdToTrack;
        syncStickyContent(descriptionMessage);
    }

    // Calculate positions relative to the messages container
    const statusBarRect = statusBar.getBoundingClientRect();
    const descRect = descriptionMessage.getBoundingClientRect();

    // The "trigger line" is where the status bar ends
    const triggerLine = statusBarRect.bottom;

    // Threshold-based snap states
    // MERGED: when more than 50% of description is hidden behind status bar
    // NORMAL: when description top is below the trigger line
    const hiddenHeight = triggerLine - descRect.top;
    const visibleRatio = 1 - (hiddenHeight / descRect.height);

    if (descRect.top >= triggerLine) {
        // Normal: description is fully below status bar
        transitionStickyTo(StickyState.NORMAL, descriptionMessage);
    } else if (visibleRatio < 0.5) {
        // More than half hidden - snap to merged
        transitionStickyTo(StickyState.MERGED, descriptionMessage);
    } else {
        // Less than half hidden - stay normal (with slight fade)
        transitionStickyTo(StickyState.NORMAL, descriptionMessage);
    }
}

function transitionStickyTo(newState, descriptionMessage = null) {
    const wrapper = document.getElementById('sticky-description-wrapper');
    const content = document.getElementById('sticky-description-content');
    const prevState = stickyDescriptionState.state;

    // Skip if already in this state
    if (prevState === newState) return;

    // Find description message if not provided
    if (!descriptionMessage && currentNodeId) {
        descriptionMessage = document.querySelector(
            `.node-description-message[data-node-id="${currentNodeId}"]`
        );
    }

    switch (newState) {
        case StickyState.NORMAL:
            // Hide sticky version with animation
            wrapper.classList.remove('visible');
            wrapper.style.maxHeight = '0';
            wrapper.style.opacity = '0';
            if (descriptionMessage) {
                descriptionMessage.classList.remove('merged');
            }
            break;

        case StickyState.MERGED:
            // Sync content if needed
            if (!content.innerHTML && descriptionMessage) {
                syncStickyContent(descriptionMessage);
            }

            // Show sticky version with snap animation
            wrapper.classList.add('visible');

            const fullContentHeight = content.scrollHeight;
            const maxHeight = calculateMaxStickyHeight();
            const targetHeight = Math.min(fullContentHeight, maxHeight);
            wrapper.style.maxHeight = targetHeight + 'px';
            wrapper.style.opacity = '1';

            // Update scrollbar visibility
            updateStickyScrollbar(content, targetHeight);

            if (descriptionMessage) {
                descriptionMessage.classList.add('merged');
            }
            break;
    }

    stickyDescriptionState.state = newState;
}

function updateStickyScrollbar(content, containerHeight) {
    // Check if content needs scrolling
    if (content.scrollHeight > containerHeight) {
        content.classList.remove('no-scroll');
    } else {
        content.classList.add('no-scroll');
    }
}

// Animate only the changed parts of description
function animateDescriptionDiff(container, newHtml) {
    const oldText = container.textContent || '';

    // Create a temporary element to extract new text
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = newHtml;
    const newText = tempDiv.textContent || '';

    // Find the differences using a simple word-based diff
    const oldWords = oldText.split(/(\s+)/);
    const newWords = newText.split(/(\s+)/);

    // Find changed regions
    const changes = findTextChanges(oldWords, newWords);

    if (changes.removed.length === 0 && changes.added.length === 0) {
        // No changes, just update
        container.innerHTML = newHtml;
        return;
    }

    // If too many changes, fall back to full animation
    if (changes.removed.length > 20 || changes.added.length > 20) {
        container.classList.add('description-updating-out');
        setTimeout(() => {
            container.innerHTML = newHtml;
            container.classList.remove('description-updating-out');
            container.classList.add('description-updating-in');
            setTimeout(() => {
                container.classList.remove('description-updating-in');
            }, 800);
        }, 1200);
        return;
    }

    // Mark changed words in the current content for blink-out
    let markedOldHtml = container.innerHTML;
    changes.removed.forEach(word => {
        if (word.trim()) {
            // Escape special regex characters
            const escapedWord = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escapedWord})(?![^<]*>)`, 'g');
            markedOldHtml = markedOldHtml.replace(regex, '<span class="text-updating-out">$1</span>');
        }
    });
    container.innerHTML = markedOldHtml;

    // After blink-out, update to new content with fade-in on new parts
    setTimeout(() => {
        let markedNewHtml = newHtml;
        changes.added.forEach(word => {
            if (word.trim()) {
                const escapedWord = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(`(${escapedWord})(?![^<]*>)`, 'g');
                markedNewHtml = markedNewHtml.replace(regex, '<span class="text-updating-in">$1</span>');
            }
        });
        container.innerHTML = markedNewHtml;

        // Clean up animation spans after animation completes
        setTimeout(() => {
            container.innerHTML = newHtml;
        }, 800);
    }, 1200);
}

// Simple word-based diff to find changes
function findTextChanges(oldWords, newWords) {
    const oldSet = new Set(oldWords.filter(w => w.trim()));
    const newSet = new Set(newWords.filter(w => w.trim()));

    const removed = [];
    const added = [];

    // Find removed words (in old but not in new)
    oldWords.forEach(word => {
        if (word.trim() && !newSet.has(word)) {
            removed.push(word);
        }
    });

    // Find added words (in new but not in old)
    newWords.forEach(word => {
        if (word.trim() && !oldSet.has(word)) {
            added.push(word);
        }
    });

    return { removed, added };
}

function calculateMaxStickyHeight() {
    // Calculate max height as 60% of viewport height
    return Math.floor(window.innerHeight * 0.6);
}

function syncStickyContent(descriptionMessage) {
    const content = document.getElementById('sticky-description-content');
    if (!descriptionMessage) {
        descriptionMessage = document.querySelector(
            `.node-description-message[data-node-id="${currentNodeId}"]`
        );
    }

    if (descriptionMessage) {
        const messageContent = descriptionMessage.querySelector('.message-content');
        if (messageContent) {
            content.innerHTML = messageContent.innerHTML;
        }
    }
}

function resetStickyDescription() {
    stickyDescriptionState.state = StickyState.NORMAL;
    stickyDescriptionState.trackedNodeId = null;

    const wrapper = document.getElementById('sticky-description-wrapper');
    const content = document.getElementById('sticky-description-content');

    if (wrapper) {
        wrapper.classList.remove('visible');
        wrapper.style.maxHeight = '0';
        wrapper.style.opacity = '0';
    }
    if (content) {
        content.innerHTML = '';
        content.classList.add('no-scroll');
    }

    // Clear any merge classes from old descriptions
    document.querySelectorAll('.node-description-message.merged')
        .forEach(el => {
            el.classList.remove('merged');
        });
}

// 处理WebSocket消息
function handleWebSocketMessage(message) {
    if (!isAwaitingGameStart) {
        hideLoading();
    }

    // Hide loading bubble for content-bearing responses.
    // stream_start is excluded: the bubble stays until the first stream_token
    // reveals actual content, avoiding a flash of empty space.
    // game_state is excluded: it's a HUD/metadata update, not a chat response.
    const contentTypes = [
        'game', 'system', 'chat', 'combat', 'command_result',
        'node_description', 'description_update', 'dialogue',
        'present_choice', 'display_sequence', 'form', 'form_success',
        'form_error', 'error', 'game_start',
    ];
    if (contentTypes.includes(message.type)) {
        hideLoadingBubble();
    }
    
    // If displaying a sequence, queue certain message types to show after sequence completes
    if (isDisplayingSequence && shouldQueueDuringSequence(message.type)) {
        pendingMessages.push(message);
        return;
    }
    
    switch (message.type) {
        case 'ping':
            // Respond to server keepalive ping to prevent idle disconnection
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: 'pong' }));
            }
            return; // Don't call hideLoading for pings
        case 'registered':
            // Server confirms registration — store the session token for reconnects
            if (message.session_token) {
                localStorage.setItem('sessionToken', message.session_token);
            }
            playerName = message.player_name;
            // If player has no name, show input, otherwise request stories
            if (!playerName) {
                welcomeMessage.style.display = 'none';
                playerNameInput.style.display = 'block';
            } else {
                playerNameInput.style.display = 'none';
                socket.send(JSON.stringify({ type: 'request_stories' }));
            }
            break;
        case 'session_exists':
            // Server tells us we already have a session
            console.log("Player already has an active session.");
            const existingSessionId = message.session_id;

            // Show a dialog asking if they want to rejoin or start new
            const userChoice = confirm(`You already have an active session (${existingSessionId}). Click OK to rejoin it, or Cancel to start a new game.`);

            if (userChoice) {
                // User wants to rejoin - do nothing, the server will handle rejoin automatically
                console.log("User chose to rejoin existing session");
            } else {
                // User wants to start new - send create_session with force_new flag
                console.log("User chose to start new session");
                socket.send(JSON.stringify({
                    type: 'create_session',
                    story_id: selectedStory,
                    force_new: true
                }));
            }
            break;
        case 'rejoined':
            // Server confirms successful rejoin
            console.log("Rejoin successful. Handling game state.");
            handleGameStart(message.content);
            break;
        case 'rejoin_failed':
            // Server could not find a session for this player
            console.log("Rejoin failed. Starting fresh.");
            isAwaitingGameStart = false;
            hideGameLoadingScreen();
            welcomeMessage.style.display = 'none';
            playerNameInput.style.display = 'block';
            break;
        case 'combat':
        case 'game':
            if (message.content.startsWith('Game saved successfully!')) {
                const originalText = saveGameButton.textContent;
                saveGameButton.textContent = '✓';
                setTimeout(() => { saveGameButton.textContent = originalText; }, 1500);
                addGameMessage(String(message.content), 'system-message');
                break;
            }
            if (message._streamed && lastStreamEndTime && (Date.now() - lastStreamEndTime < 3000)) {
                break;
            }
            addGameMessage(String(message.content), 'game-message');
            break;
        case 'system':
        case 'multiplayer':
        case 'chat':
            addGameMessage(String(message.content), `${message.type}-message`);
            break;
        case 'stories':
            displayStories(message.stories);
            break;
        case 'control':
            if (message.subtype === 'story_info') {
                // The server will follow up with a session_selection prompt, do nothing here.
                console.log('Received story info for:', message.story.title);
            } else if (message.subtype === 'session_selection') {
                showSessionSelection();
            } else if (message.subtype === 'ready_for_state_request') {
                socket.send(JSON.stringify({ type: 'request_initial_state' }));
            }
            break;
        case 'session':
            handleSessionMessage(message);
            break;
        case 'session_players':
            setSessionPlayers(message.players || []);
            break;
        case 'game_start':
            handleGameStart(message.content);
            break;
        case 'command_result':
            handleCommandResult(message.content);
            break;
        case 'game_state':
            // New orchestration logic
            if (message.content.upserts) {
                applyUpserts(message.content.upserts);
            }
            // The game_state message itself contains the latest diff
            if (message.content.characters) {
                setAvailableCharacters(message.content.characters);
            }
            updateUIWithGameState(message.content);
            updateDisplayPanel(message.content);
            break;
        case 'characters_update':
            // Lightweight push after local NPC creation or enrichment
            if (message.content && message.content.characters) {
                setAvailableCharacters(message.content.characters);
            }
            break;
        case 'stream_start':
            handleStreamStart(message);
            break;
        case 'stream_token':
            handleStreamToken(message);
            break;
        case 'stream_end':
            handleStreamEnd(message);
            break;
        case 'error':
            isAwaitingGameStart = false;
            hideGameLoadingScreen();
            addGameMessage(message.content, 'error-message');
            break;
        case 'dialogue':
            messageQueue.push({
                type: 'dialogue',
                speaker: message.speaker,
                text: message.text,
                choices: message.choices
            });
            if (!isTyping && messageQueue.length === 1) {
                processNextMessage();
            }
            break;
        case 'present_choice':
            messageQueue.push({
                type: 'present_choice',
                choices: message.choices
            });
            if (!isTyping && messageQueue.length === 1) {
                processNextMessage();
            }
            break;
        case 'node_description': {
            // Skip empty descriptions
            if (!message.content || message.content.trim() === '') {
                break;
            }
            const processedText = preprocessDescription(message.content);
            const descriptionHtml = converter.makeHtml(processedText);
            nodeDescription.innerHTML = `<h3>Description</h3>${descriptionHtml}`;

            // Use node_id from message if available, fallback to currentNodeId
            const nodeId = message.node_id || currentNodeId || 'unknown';

            // Reset sticky state when entering a new node
            if (stickyDescriptionState.trackedNodeId && stickyDescriptionState.trackedNodeId !== nodeId) {
                resetStickyDescription();
            }

            // Create message with special marker for updates
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message game-message node-description-message';
            messageDiv.setAttribute('data-node-id', nodeId);
            const timestamp = new Date().toLocaleTimeString();
            messageDiv.innerHTML = `
                <div class="message-content">${descriptionHtml}</div>
                <div class="message-timestamp">${timestamp}</div>
            `;
            gameMessages.appendChild(messageDiv);
            gameMessages.scrollTop = gameMessages.scrollHeight;

            // Update sticky tracking for the new node
            stickyDescriptionState.trackedNodeId = nodeId;
            // Sync sticky content immediately
            syncStickyContent(messageDiv);

            // Update worldData with processed description so updateDisplayPanel doesn't overwrite
            const worldDataStr = sessionStorage.getItem('worldData');
            if (worldDataStr && nodeId) {
                const worldData = JSON.parse(worldDataStr);
                if (worldData.nodes && worldData.nodes[nodeId]) {
                    worldData.nodes[nodeId].processed_description = message.content;
                    sessionStorage.setItem('worldData', JSON.stringify(worldData));
                }
            }
            break;
        }
        case 'description_update': {
            // Use node_id from message, fallback to currentNodeId
            const nodeId = message.node_id || currentNodeId;

            const updatedText = preprocessDescription(message.content);
            const updatedHtml = converter.makeHtml(updatedText);

            // Update description panel
            nodeDescription.innerHTML = `<h3>Description</h3>${updatedHtml}`;

            // Find the original node description message in chat
            const originalMessage = gameMessages.querySelector(`.node-description-message[data-node-id="${nodeId}"]`);
            const originalContentDiv = originalMessage?.querySelector('.message-content');
            const stickyContent = document.getElementById('sticky-description-content');
            const state = stickyDescriptionState.state;

            // Determine which elements to animate based on sticky state
            const elementsToAnimate = [];

            if (state === StickyState.NORMAL) {
                if (originalContentDiv) elementsToAnimate.push(originalContentDiv);
            } else if (state === StickyState.MERGED) {
                if (stickyContent) elementsToAnimate.push(stickyContent);
            }

            // Apply diff-based animation to each visible element
            elementsToAnimate.forEach(el => {
                animateDescriptionDiff(el, updatedHtml);
            });

            // Update non-visible elements immediately (no animation)
            if (state === StickyState.NORMAL && stickyContent) {
                stickyContent.innerHTML = updatedHtml;
            } else if (state === StickyState.MERGED && originalContentDiv) {
                originalContentDiv.innerHTML = updatedHtml;
            }

            // Update timestamp on original message
            if (originalMessage) {
                const timestamp = new Date().toLocaleTimeString();
                const timestampDiv = originalMessage.querySelector('.message-timestamp');
                if (timestampDiv) {
                    const originalTime = timestampDiv.textContent.split(' (')[0];
                    timestampDiv.textContent = `${originalTime} (updated ${timestamp})`;
                }
                originalMessage.classList.add('description-updated');
            }

            // Also update the cached worldData so updateDisplayPanel doesn't overwrite
            const worldDataStr = sessionStorage.getItem('worldData');
            if (worldDataStr && nodeId) {
                const worldData = JSON.parse(worldDataStr);
                if (worldData.nodes && worldData.nodes[nodeId]) {
                    worldData.nodes[nodeId].processed_description = message.content;
                    sessionStorage.setItem('worldData', JSON.stringify(worldData));
                }
            }
            break;
        }
        case 'item_drop':
            displayItemDrop(message.items);
            break;
        case 'object_actions':
            displayObjectActions(message.object_id, message.actions);
            break;
        case 'status_update':
            updateStatus(`- ${message.text} -`);
            break;
        case 'display_sequence':
            // Display journey segments one by one with adaptive delays
            // Queue subsequent messages until sequence completes
            queueMessagesUntilSequenceComplete(message.segments);
            break;
        case 'form':
            // Display a form for collecting player input
            displayForm(message);
            break;
        case 'form_success':
            // Form submission was successful
            handleFormSuccess(message.form_id);
            break;
        case 'form_error':
            // Form submission had validation errors
            handleFormError(message.form_id, message.errors);
            break;
        default:
            console.log('Unknown message type:', message.type);
    }
}

// Sequence display state
let isDisplayingSequence = false;
let pendingMessages = [];

// Determine which message types should be queued during sequence display
function shouldQueueDuringSequence(messageType) {
    // Queue content messages that should wait for sequence to complete
    const queueableTypes = [
        'game', 'system', 'chat', 'node_description', 'description_update',
        'command_result', 'dialogue', 'present_choice', 'combat'
    ];
    return queueableTypes.includes(messageType);
}

// Queue messages until sequence display completes
async function queueMessagesUntilSequenceComplete(segments) {
    isDisplayingSequence = true;
    
    await displaySequence(segments);
    
    isDisplayingSequence = false;
    
    // Process any messages that arrived during the sequence
    while (pendingMessages.length > 0) {
        const pendingMsg = pendingMessages.shift();
        handleWebSocketMessage(pendingMsg);
    }
}

// Display sequence of messages with adaptive delays based on character count
async function displaySequence(segments) {
    if (!segments || !Array.isArray(segments) || segments.length === 0) {
        console.warn('displaySequence: Invalid or empty segments');
        return;
    }
    
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        if (!segment || segment.trim() === '') continue;
        
        // Add message to display (using game-message style)
        addGameMessage(segment, 'game-message');
        
        // Scroll to bottom
        gameMessages.scrollTop = gameMessages.scrollHeight;
        
        // Adaptive delay: ~50ms per character, min 1.5s, max 4s
        if (i < segments.length - 1) {
            const charCount = segment.length;
            const delayMs = Math.min(3000, Math.max(1000, charCount * 40));
            await sleep(delayMs);
        }
    }
}

// Helper function for async delays
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// New function to apply upserts
function applyUpserts(upserts) {
    const worldDataString = sessionStorage.getItem('worldData');
    let worldData = worldDataString ? JSON.parse(worldDataString) : { nodes: {}, items: {} };

    if (upserts.nodes) {
        for (const nodeId in upserts.nodes) {
            worldData.nodes[nodeId] = { ...worldData.nodes[nodeId], ...upserts.nodes[nodeId] };
        }
    }

    if (upserts.all_object_definitions) {
        for (const objectId in upserts.all_object_definitions) {
            worldData.items[objectId] = { ...worldData.items[objectId], ...upserts.all_object_definitions[objectId] };
        }
    }

    sessionStorage.setItem('worldData', JSON.stringify(worldData));
}

// 处理会话消息
function handleSessionMessage(message) {
    switch (message.subtype) {
        case 'created':
        case 'joined':
            sessionCode = message.session_code;
            displaySessionCode(sessionCode);
            // DO NOT request state here. Wait for character selection or other signal.
            break;
        case 'error':
            isAwaitingGameStart = false;
            hideGameLoadingScreen();
            addGameMessage(`会话错误: ${message.message}`, 'system-message');
            sessionSelection.style.display = 'block';
            break;
        case 'saved_games':
            // 处理保存的列表
            if (message.games) {
                savedGames = message.games;
                displaySavedGames();
            }
            break;
    }
}

let isReturningToMenu = false; // Flag to track return to menu state

function handleReturn() {
    if (confirm("Are you sure you want to return to the story list? You will be disconnected from the current session.")) {
        console.log('handleReturn: user confirmed, sending leave_session');

        // 1. Notify the server that the player is leaving.
        console.log('[CLIENT_SEND]', 'Sending leave_session message to server.');
        socket.send(JSON.stringify({ type: 'leave_session' }));

        // 2. Clean up the UI immediately.
        mainContent.style.display = 'none';
        displayPanel.classList.add('hidden');
        gameMessages.innerHTML = '';
        userInput.value = '';
        currentNodeId = null;
        sessionCode = '';
        selectedStory = '';
        selectedStoryTitle = '';
        isAwaitingGameStart = false;
        localStorage.removeItem('selectedStory');

        // Reset sticky description state
        resetStickyDescription();

        // Remove in-game class to allow container scrolling
        document.querySelector('.container').classList.remove('in-game');

        // 3. Show the story selection screen. 
        // It will be populated when the server sends the 'stories' message.
        storySelection.style.display = 'block';
    }
}

function handleReload(_options = {}) {
    if (confirm("Are you sure you want to reload the game? This will start a new game of the current story and disconnect you from the current session.")) {
        // Don't send leave_session - just clear local state and restart story

        // Hide game interface
        mainContent.style.display = 'none';
        displayPanel.classList.add('hidden');

        // Clear game state but keep the selected story
        gameMessages.innerHTML = '';
        currentNodeId = null;
        sessionCode = '';

        // Reset sticky description state
        resetStickyDescription();

        // Remove in-game class temporarily
        document.querySelector('.container').classList.remove('in-game');

        // Restart the same story
        if (selectedStory) {
            isAwaitingGameStart = true;
            showGameLoadingScreen(selectedStoryTitle || selectedStory);
            socket.send(JSON.stringify({ type: 'select_story', story_id: selectedStory }));
        } else {
            // Fallback: show story selection if no story is selected
            socket.send(JSON.stringify({ type: 'request_stories' }));
        }
    }
}

// 提交玩家名称
function submitPlayerName() {
    playerName = playerNameField.value.trim();
    if (playerName) {
        socket.send(JSON.stringify({ type: 'set_player_name', name: playerName, player_id: playerId }));

        const reloadStoryId = localStorage.getItem('reload_story_id');
        if (reloadStoryId) {
            // If reloading, automatically select the story
            localStorage.removeItem('reload_story_id');
            selectStory(reloadStoryId);
        } else {
            // Otherwise, request the story list
            socket.send(JSON.stringify({ type: 'request_stories' }));
        }

        playerNameInput.style.display = 'none';
        console.log(`玩家名称设置为: ${playerName}`);
    } else {
        alert('请输入有效的名称');
    }
}

function displayStories(stories) {
    const predefinedList = document.getElementById('story-list-predefined');
    predefinedList.innerHTML = '';

    const createStoryCard = (story) => {
        const card = document.createElement('div');
        card.className = 'story-card';

        const title = story.title ? story.title : story.name;
        const description = story.description || 'No description available.';

        card.innerHTML = `
            <div class="story-card-content">
                <h3>${title}</h3>
                <p class="story-description">${description}</p>
            </div>
        `;

        card.addEventListener('click', () => selectStory(story.id, title));

        return card;
    };

    if (stories && stories.length > 0) {
        document.getElementById('handcrafted-stories').style.display = 'block';
        stories.forEach(story => {
            predefinedList.appendChild(createStoryCard(story));
        });
    } else {
        document.getElementById('handcrafted-stories').style.display = 'none';
    }

    // Only show story selection if we're not currently in a game
    if (mainContent.style.display === 'none') {
        storySelection.style.display = 'block';
    }
}

// 选择故事
function selectStory(storyId, title) {
    selectedStory = storyId;
    selectedStoryTitle = title || storyId;
    localStorage.setItem('selectedStory', storyId);
    showLoading('Loading story...');
    socket.send(JSON.stringify({ type: 'select_story', story_id: storyId }));
    storySelection.style.display = 'none';
    console.log(`已选择故事: ${storyId}`);
}

// 显示会话选择界面
function showSessionSelection() {
    // Fetch saved games for this player and selected story
    fetch(`/api/saved-games?player_name=${encodeURIComponent(playerName)}&story_id=${selectedStory}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.saves) {
                savedGames = data.saves;
                displaySavedGames();
            }
        })
        .catch(error => {
            console.error('Error fetching saved games:', error);
        });

    sessionSelection.style.display = 'block';
}

// Display saved games in the load panel
function displaySavedGames() {
    const joinSessionContainer = document.querySelector('.join-session');

    // Remove any existing load panel
    const existingLoadPanel = document.getElementById('load-panel');
    if (existingLoadPanel) {
        existingLoadPanel.remove();
    }

    // Create load panel if there are saved games
    if (savedGames.length > 0) {
        const loadPanel = document.createElement('div');
        loadPanel.id = 'load-panel';
        loadPanel.className = 'load-panel';
        loadPanel.innerHTML = `
            <h3>saved games</h3>
            <div class="saved-games-list">
                ${savedGames.map(game => `
                    <div class="saved-game-item" data-code="${game.save_code}">
                        <span>saving code: ${game.save_code}</span>
                        <span>last saved: ${new Date(game.updated_at).toLocaleString()}</span>
                        <button class="load-game-btn" data-code="${game.save_code}">load</button>
                    </div>
                `).join('')}
            </div>
            <div class="load-by-code">
                <h4>or enter the saving code:</h4>
                <input type="text" id="save-code-input" placeholder="input saving code">
                <button id="load-by-code-btn">load</button>
            </div>
        `;

        // Insert the load panel before the join session container
        joinSessionContainer.parentNode.insertBefore(loadPanel, joinSessionContainer);

        // Add event listeners for load buttons
        document.querySelectorAll('.load-game-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const saveCode = e.target.getAttribute('data-code');
                loadGame(saveCode);
            });
        });

        // Add event listener for load by code button
        document.getElementById('load-by-code-btn').addEventListener('click', () => {
            const saveCodeInput = document.getElementById('save-code-input');
            const saveCode = saveCodeInput.value.trim();
            if (saveCode) {
                loadGame(saveCode);
            }
        });
    }
}

// Load a saved game
function loadGame(saveCode) {
    isAwaitingGameStart = true;
    showGameLoadingScreen(selectedStoryTitle || selectedStory || 'Saved Game');
    sessionSelection.style.display = 'none';

    // Send load request to server
    const message = {
        type: 'load_game',
        save_code: saveCode,
        player_name: playerName,
        story_id: selectedStory
    };

    console.log('Sending WebSocket message:', JSON.stringify(message));
    socket.send(JSON.stringify(message));
}

// 创建会话
function createSession() {
    isAwaitingGameStart = true;
    showGameLoadingScreen(selectedStoryTitle || selectedStory);
    socket.send(JSON.stringify({ type: 'create_session', story_id: selectedStory }));
    sessionSelection.style.display = 'none';
    console.log('正在创建新会话...');
}

// 加入会话
function joinSession() {
    const code = sessionCodeInput.value.trim();
    if (code) {
        isAwaitingGameStart = true;
        showGameLoadingScreen(selectedStoryTitle || 'Adventure');
        socket.send(JSON.stringify({ type: 'join_session', session_code: code }));
        sessionSelection.style.display = 'none';
        console.log(`正在尝试加入会话: ${code}`);
    } else {
        alert('请输入有效的代码');
    }
}

// 显示界面
function showGameInterface() {
    welcomeMessage.style.display = 'none';
    playerNameInput.style.display = 'none';
    storySelection.style.display = 'none';
    sessionSelection.style.display = 'none';
    mainContent.style.display = 'flex';
    // Add in-game class to container to prevent container scrolling
    document.querySelector('.container').classList.add('in-game');
    userInput.focus();
}

// 显示会话代码
function displaySessionCode(code) {
    sessionCodeDisplay.textContent = `${code}`;
}

// 复制会话代码
function copySessionCode() {
    if (sessionCode) {
        navigator.clipboard.writeText(sessionCode).then(() => {
            console.log('代码已复制到剪贴板');
            const label = copySessionCodeButton.querySelector('.copy-label');
            if (label) {
                const originalText = label.textContent;
                label.textContent = 'Copied!';
                setTimeout(() => { label.textContent = originalText; }, 1500);
            }
        }).catch(err => console.error(`复制失败: ${err}`));
    }
}

// 发送命令
// displayText: optional text to show in the message panel (defaults to command if not provided)
// inputType: optional string ('action_click' for link clicks, omitted for typed input)
function sendCommand(command, displayText, inputType, actionHint) {
    console.log('sendCommand called with:', command, 'typeof:', typeof command);
    if (typeof command !== 'string') {
        command = userInput.value.trim();
        displayText = command;
        console.log('sendCommand: got command from userInput:', command);
    }

    if (!command || command === '') {
        console.log('sendCommand called with empty command, ignoring');
        return;
    }

    const legacyCommand = getLegacySystemCommand(command);
    if (legacyCommand) {
        clearComposerInput();
        addGameMessage(`System commands now use \`/\`. Try \`/${legacyCommand}\`.`, 'system-message');
        return;
    }

    if (command.startsWith('/')) {
        executeSlashCommand(command);
        return;
    }

    console.log('sendCommand: sending command to server:', command);
    dispatchSocketCommand(command, displayText || command, inputType, actionHint);
}

function dispatchSocketCommand(command, displayText, inputType, actionHint, options = {}) {
    const { showUserMessage = true, showLoading = true } = options;
    stashedStoryChoices = null;
    pendingObjectActionRequest = null;
    const choicesContainer = document.getElementById('choices-container');
    choicesContainer.innerHTML = '';
    choicesContainer.classList.add('hidden');
    choicesContainer.classList.remove('object-actions-loading');
    choicesContainer.removeAttribute('aria-busy');

    const msg = { type: 'command', content: command };
    if (inputType) msg.input_type = inputType;
    if (actionHint) msg.action_hint = actionHint;
    console.log('Sending WebSocket message:', JSON.stringify(msg));
    socket.send(JSON.stringify(msg));
    if (showUserMessage) {
        addGameMessage(displayText || command, 'user-message');
    }
    if (showLoading) {
        showLoadingBubble();
    }
    clearComposerInput();
}

function clearComposerInput() {
    userInput.value = '';
    closeComposerSuggestions();
    updateMentionOverlay();
}

function closeComposerSuggestions() {
    closeMentionSuggestions();
    closeSlashCommandPalette();
}

function getObjectActionsLoadingText() {
    return window.TextAdventureI18n?.t?.('loading.objectActions') || 'Loading actions';
}

function showObjectActionsLoading(objectId) {
    const choicesContainer = document.getElementById('choices-container');

    if (!choicesContainer.classList.contains('hidden') &&
        choicesContainer.innerHTML &&
        !choicesContainer.classList.contains('object-actions-loading')) {
        stashedStoryChoices = Array.from(choicesContainer.children).map(node => ({
            text: node.textContent,
            onclick: node.onclick
        }));
    }

    pendingObjectActionRequest = objectId;
    choicesContainer.innerHTML = '';
    choicesContainer.classList.remove('hidden');
    choicesContainer.classList.add('object-actions-loading');
    choicesContainer.setAttribute('aria-busy', 'true');

    const button = document.createElement('button');
    button.type = 'button';
    button.disabled = true;
    button.className = 'loading-choice-button';

    const label = document.createElement('span');
    label.className = 'loading-choice-label';
    label.textContent = getObjectActionsLoadingText();

    const dots = document.createElement('span');
    dots.className = 'loading-choice-dots';
    dots.setAttribute('aria-hidden', 'true');

    button.appendChild(label);
    button.appendChild(dots);
    choicesContainer.appendChild(button);
}

function onObjectClick(objectId) {
    showObjectActionsLoading(objectId);
    socket.send(JSON.stringify({ type: 'command', content: `get_object_actions:${objectId}` }));
}

function onCharacterClick(characterId) {
    const character = (availableCharacters || []).find(entry => entry.id === characterId);
    const displayText = character?.name ? `Talk to ${character.name}` : `Talk to ${characterId}`;
    sendCommand(`@${characterId}`, displayText);
}


function onActionClick(displayText, actionHint) {
    sendCommand(displayText, displayText, 'action_click', actionHint || '');
}

function displayObjectActions(objectId, actions) {
    const choicesContainer = document.getElementById('choices-container');

    if (objectId !== pendingObjectActionRequest) {
        return;
    }

    pendingObjectActionRequest = null;
    choicesContainer.classList.remove('object-actions-loading');
    choicesContainer.removeAttribute('aria-busy');
    choicesContainer.innerHTML = ''; // Clear previous actions/choices

    if (actions && actions.length > 0) {
        choicesContainer.classList.remove('hidden');
        actions.forEach(action => {
            const button = document.createElement('button');
            button.textContent = action.text;
            const commandToSend = action.keywords && action.keywords.length > 0 ? action.keywords[0] : action.text;
            button.onclick = () => sendCommand(commandToSend);
            choicesContainer.appendChild(button);
        });
    } else {
        choicesContainer.classList.add('hidden');
        choicesContainer.removeAttribute('aria-busy');
    }
}

function refreshObjectActionLoadingText() {
    const label = document.querySelector('.loading-choice-label');
    if (label) {
        label.textContent = getObjectActionsLoadingText();
    }
}

let availableChoices = [];
let availableCharacters = [];
let sessionPlayers = [];
let mentionState = {
    isOpen: false,
    startIndex: 0,
    caretIndex: 0,
    query: '',
    candidates: [],
    selectedIndex: 0
};
let slashCommandState = {
    isOpen: false,
    query: '',
    commands: [],
    selectedIndex: 0
};

function toggleDisplayPanel() {
    const isOpen = displayPanel.classList.toggle('visible');
    displayToggleBtn.classList.toggle('is-open', isOpen);
    return isOpen;
}

function showSessionPlayersMessage() {
    addGameMessage('/players', 'user-message');

    if (!sessionPlayers.length) {
        addGameMessage('No session player information is available yet.', 'system-message');
        return;
    }

    const lines = sessionPlayers.map((player) => {
        const isCurrentPlayer = player.id === playerId;
        const name = player.name || player.id || 'Unknown player';
        return `- ${name}${isCurrentPlayer ? ' (you)' : ''}`;
    });

    addGameMessage(`**Players**\n\n${lines.join('\n')}`, 'system-message');
}

function toggleStatusPanelFromCommand() {
    addGameMessage('/status', 'user-message');
    toggleDisplayPanel();
}

function exportFromCommand() {
    addGameMessage('/export', 'user-message');
    handleExportMessages();
}

function getSlashCommandDefinitions() {
    const t = window.TextAdventureI18n?.t;
    return [
        {
            id: 'help',
            label: '/help',
            description: t?.('commands.helpDescription') || 'Show available slash commands',
            execute: () => showSlashCommandHelp()
        },
        {
            id: 'save',
            label: '/save',
            description: t?.('commands.saveDescription') || 'Save the current game',
            execute: () => saveGame({ showUserMessage: true, displayText: '/save' })
        },
        {
            id: 'reload',
            label: '/reload',
            description: t?.('commands.reloadDescription') || 'Restart the current story',
            execute: () => handleReload({ fromSlashCommand: true })
        },
        {
            id: 'export',
            label: '/export',
            description: t?.('commands.exportDescription') || 'Export the current message history',
            execute: () => exportFromCommand()
        },
        {
            id: 'players',
            label: '/players',
            description: t?.('commands.playersDescription') || 'Show the players in this session',
            execute: () => showSessionPlayersMessage()
        },
        {
            id: 'status',
            label: '/status',
            description: t?.('commands.statusDescription') || 'Toggle the detail panel',
            execute: () => toggleStatusPanelFromCommand()
        }
    ];
}

function getLegacySystemCommand(command) {
    const normalized = String(command || '').trim().toLowerCase();
    const legacyCommands = new Set(['help', 'reload', 'save']);
    return legacyCommands.has(normalized) ? normalized : '';
}

function getSlashCommandContext(value, caretIndex) {
    if (!value || !value.startsWith('/')) return null;
    const left = value.slice(0, caretIndex);
    if (!left.startsWith('/')) return null;
    const token = left.slice(1);
    if (/\s/.test(token)) return null;
    return { query: token.toLowerCase() };
}

function filterSlashCommands(query) {
    return getSlashCommandDefinitions().filter(command =>
        !query || command.id.includes(query)
    );
}

function closeSlashCommandPalette() {
    slashCommandState.isOpen = false;
    slashCommandState.query = '';
    slashCommandState.commands = [];
    slashCommandState.selectedIndex = 0;
    if (commandPalette) {
        commandPalette.classList.add('hidden');
        commandPalette.innerHTML = '';
    }
}

function renderSlashCommandPalette() {
    if (!commandPalette || !slashCommandState.isOpen) return;
    commandPalette.innerHTML = '';
    slashCommandState.commands.forEach((command, index) => {
        const item = document.createElement('div');
        item.className = 'mention-suggestion';
        if (index === slashCommandState.selectedIndex) {
            item.classList.add('active');
        }
        item.title = command.description;
        item.innerHTML = `
            <span class="mention-token">${escapeHtml(command.label)}</span>
            <span class="mention-type">command</span>
        `;
        item.addEventListener('mouseenter', () => {
            slashCommandState.selectedIndex = index;
            renderSlashCommandPalette();
        });
        item.addEventListener('mousedown', (event) => {
            event.preventDefault();
            executeSlashCommand(command.label);
        });
        commandPalette.appendChild(item);
    });
    commandPalette.classList.remove('hidden');
}

function handleSlashCommandInput() {
    const context = getSlashCommandContext(userInput.value, userInput.selectionStart);
    if (!context) {
        closeSlashCommandPalette();
        return false;
    }

    const commands = filterSlashCommands(context.query);
    if (!commands.length) {
        closeSlashCommandPalette();
        return true;
    }

    slashCommandState.isOpen = true;
    slashCommandState.query = context.query;
    slashCommandState.commands = commands;
    slashCommandState.selectedIndex = 0;
    renderSlashCommandPalette();
    return true;
}

function handleComposerInput() {
    if (handleSlashCommandInput()) {
        closeMentionSuggestions();
        updateMentionOverlay();
        return;
    }
    handleMentionInput();
}

function handleComposerKeydown(event) {
    if (slashCommandState.isOpen) {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            slashCommandState.selectedIndex = (slashCommandState.selectedIndex + 1) % slashCommandState.commands.length;
            renderSlashCommandPalette();
            return;
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            slashCommandState.selectedIndex = (slashCommandState.selectedIndex - 1 + slashCommandState.commands.length) % slashCommandState.commands.length;
            renderSlashCommandPalette();
            return;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
            event.preventDefault();
            const selectedCommand = slashCommandState.commands[slashCommandState.selectedIndex];
            if (selectedCommand) {
                executeSlashCommand(selectedCommand.label);
            }
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            closeSlashCommandPalette();
            return;
        }
    }

    handleMentionKeydown(event);
}

function executeSlashCommand(commandText) {
    const normalized = String(commandText || '').trim().toLowerCase();
    if (!normalized.startsWith('/')) {
        return false;
    }

    const commandName = normalized.slice(1).split(/\s+/, 1)[0];
    const command = getSlashCommandDefinitions().find(entry => entry.id === commandName);
    clearComposerInput();

    if (!command) {
        addGameMessage(`Unknown command \`${commandText}\`. Try \`/help\`.`, 'system-message');
        return true;
    }

    command.execute();
    return true;
}

function showSlashCommandHelp() {
    const title = window.TextAdventureI18n?.t?.('commands.helpTitle') || 'Slash Commands';
    const commandList = getSlashCommandDefinitions()
        .map(command => `- \`${command.label}\` ${command.description}`)
        .join('\n');
    addGameMessage('/help', 'user-message');
    addGameMessage(`**${title}**\n\n${commandList}`, 'system-message');
}

function handleChoice(choiceIndex) {
    const choice = availableChoices[choiceIndex - 1];
    if (choice) {
        addGameMessage(choice.text, 'user-message');
    }
    // showLoading('Processing choice...');
    stashedStoryChoices = null; // Clear stashed choices
    socket.send(JSON.stringify({ type: 'command', content: `choose ${choiceIndex}` }));
    const choicesContainer = document.getElementById('choices-container');
    choicesContainer.innerHTML = ''; // Clear choices
    choicesContainer.classList.add('hidden'); // Hide container
    userInput.disabled = false; // Re-enable input
    sendButton.disabled = false; // Re-enable send button
    userInput.focus();
}

// 添加消息
// --- Streaming Message Support ---
let streamingState = null; // { messageDiv, contentDiv, rawText, messageType }
let lastStreamEndTime = 0; // timestamp of last stream_end, for dedup

function handleStreamStart(message) {
    const messageType = message.message_type || 'game';
    const className = `${messageType}-message`;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${className} streaming`;
    messageDiv.style.display = 'none';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = '';

    const timestampDiv = document.createElement('div');
    timestampDiv.className = 'message-timestamp';
    timestampDiv.textContent = new Date().toLocaleTimeString();

    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timestampDiv);
    gameMessages.appendChild(messageDiv);

    streamingState = {
        messageDiv,
        contentDiv,
        rawText: '',
        messageType,
        revealed: false,
    };
}

function handleStreamToken(message) {
    if (!streamingState) return;
    const token = message.content || '';
    streamingState.rawText += token;
    if (!streamingState.revealed) {
        streamingState.revealed = true;
        hideLoadingBubble();
        streamingState.messageDiv.style.display = '';
    }
    streamingState.contentDiv.textContent = streamingState.rawText;
    gameMessages.scrollTop = gameMessages.scrollHeight;
}

function handleStreamEnd(message) {
    if (!streamingState) return;
    hideLoadingBubble();
    const mdConverter = new showdown.Converter({
        literalMidWordUnderscores: true,
        simpleLineBreaks: true
    });
    const source = message.final_html || streamingState.rawText;
    if (source) {
        streamingState.messageDiv.style.display = '';
        const processedSource = preprocessDescription(source);
        streamingState.contentDiv.innerHTML = mdConverter.makeHtml(processedSource);
    } else {
        streamingState.messageDiv.remove();
    }
    streamingState.messageDiv.classList.remove('streaming');
    gameMessages.scrollTop = gameMessages.scrollHeight;
    streamingState = null;
    lastStreamEndTime = Date.now();
}

function addGameMessage(content, className) {
    const converter = new showdown.Converter({
        literalMidWordUnderscores: true,
        simpleLineBreaks: true
    });
    const htmlContent = converter.makeHtml(content);

    // 如果是用户消息，直接显示
    if (className === 'user-message') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${className}`;
        messageDiv.innerHTML = `<div class="message-content">${htmlContent}</div><div class="message-timestamp">${new Date().toLocaleTimeString()}</div>`;
        gameMessages.appendChild(messageDiv);
        gameMessages.scrollTop = gameMessages.scrollHeight;
        return;
    }

    // 如果是消息，添加到消息队列
    messageQueue.push({
        content: htmlContent,
        className: className,
        timestamp: new Date().toLocaleTimeString()
    });

    // 如果当前没有正在显示的消息，开始显示
    if (!isTyping && messageQueue.length === 1) {
        processNextMessage();
    }
}

// 处理下一条消息
function processNextMessage() {
    if (messageQueue.length === 0) {
        isTyping = false;
        return;
    }

    isTyping = true;
    const message = messageQueue[0];

    // 检查是否是选项消息
    if (message.type === 'dialogue') {
        // 显示选项
        displayDialogue(message.speaker, message.text, message.choices);

        // 移除队列中的选项消息
        messageQueue.shift();
        isTyping = false;

        // 如果队列中还有消息，继续处理
        if (messageQueue.length > 0) {
            // 如果禁用了打字机效果，立即处理所有消息
            if (!typewriterEffectEnabled) {
                processNextMessage();
            } else {
                setTimeout(processNextMessage, 500); // 短暂延迟后处理下一条消息
            }
        }
        return;
    }
    if (message.type === 'present_choice') {
        // 显示选项
        displayChoices(message.choices);

        // 移除队列中的选项消息
        messageQueue.shift();
        isTyping = false;

        // 如果队列中还有消息，继续处理
        if (messageQueue.length > 0) {
            // 如果禁用了打字机效果，立即处理所有消息
            if (!typewriterEffectEnabled) {
                processNextMessage();
            } else {
                setTimeout(processNextMessage, 500); // 短暂延迟后处理下一条消息
            }
        }
        return;
    }

    // 处理普通文本消息
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${message.className}`;

    // 创建消息内容容器
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (typewriterEffectEnabled) {
        continueButton.classList.remove('hidden');
        // 创建两个层：一个用于保持布局（隐藏），一个用于显示打字机效果
        const layoutDiv = document.createElement('div');
        layoutDiv.className = 'layout-text';
        layoutDiv.innerHTML = message.content;
        layoutDiv.setAttribute('aria-hidden', 'true');
        layoutDiv.setAttribute('role', 'presentation');

        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-text';

        // 将两个层添加到内容容器
        contentDiv.appendChild(layoutDiv);
        contentDiv.appendChild(typingDiv);

        // 创建时间戳
        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'message-timestamp';
        timestampDiv.textContent = message.timestamp;

        // 组装消息元素
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timestampDiv);

        // 添加消息元素到DOM
        gameMessages.appendChild(messageDiv);
        gameMessages.scrollTop = gameMessages.scrollHeight;

        // 保存当前正在显示的消息元素和文本内容
        const plainText = stripHtml(message.content);

        // 克隆布局层的内容到打字层，但初始设置所有文本为不可见
        typingDiv.innerHTML = message.content;
        const textNodes = getAllTextNodes(typingDiv);

        currentGameMessage = {
            element: messageDiv,
            contentDiv: contentDiv,
            layoutDiv: layoutDiv,
            typingDiv: typingDiv,
            htmlContent: message.content,
            plainText: plainText,
            textNodes: textNodes,
            currentIndex: 0,
            totalLength: plainText.length,
            timeoutId: null
        };

        // 开始打字机效果
        hideAllTextInContent(typingDiv);
        typeNextCharacter();
    } else {
        // 禁用打字机效果，直接显示完整内容
        contentDiv.innerHTML = message.content;

        // 创建时间戳
        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'message-timestamp';
        timestampDiv.textContent = message.timestamp;

        // 组装消息元素
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timestampDiv);

        // 添加消息元素到DOM
        gameMessages.appendChild(messageDiv);
        gameMessages.scrollTop = gameMessages.scrollHeight;

        // 立即完成当前消息
        messageQueue.shift();

        // 如果队列中还有消息，立即处理下一条
        if (messageQueue.length > 0) {
            processNextMessage(); // 立即处理下一条消息，不需要延迟
        } else {
            isTyping = false;
        }
    }
}

// 获取元素中的所有文本节点
function getAllTextNodes(element) {
    const textNodes = [];
    const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );

    let node;
    while (node = walker.nextNode()) {
        if (node.nodeValue.trim() !== '') {
            textNodes.push({
                node: node,
                originalText: node.nodeValue,
                visibleText: ''
            });
        }
    }

    return textNodes;
}

// 隐藏内容中的所有文本
function hideAllTextInContent(element) {
    const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );

    let node;
    while (node = walker.nextNode()) {
        if (node.nodeValue.trim() !== '') {
            // 不需要在节点上存储originalText，因为我们已经在textNodes数组中存储了这些信息
            node.nodeValue = '';
        }
    }
}

// 去除HTML标签，获取纯文本
function stripHtml(html) {
    const temp = document.createElement('div');
    temp.innerHTML = html;
    return temp.textContent || temp.innerText || '';
}

// 打字机效果 - 逐字显示文本
function typeNextCharacter() {
    if (!currentGameMessage) return;

    if (currentGameMessage.currentIndex < currentGameMessage.totalLength) {
        // 增加一个字符
        currentGameMessage.currentIndex++;

        // 计算每个文本节点应该显示多少字符
        let remainingChars = currentGameMessage.currentIndex;

        // 重置所有节点的可见文本
        currentGameMessage.textNodes.forEach(textNodeInfo => {
            const originalLength = textNodeInfo.originalText.length;

            if (remainingChars <= 0) {
                // 这个节点不应该显示任何字符
                textNodeInfo.node.nodeValue = '';
            } else if (remainingChars >= originalLength) {
                // 这个节点应该完全显示
                textNodeInfo.node.nodeValue = textNodeInfo.originalText;
                remainingChars -= originalLength;
            } else {
                // 这个节点应该部分显示
                textNodeInfo.node.nodeValue = textNodeInfo.originalText.substring(0, remainingChars);
                remainingChars = 0;
            }
        });

        gameMessages.scrollTop = gameMessages.scrollHeight;

        // 继续打字
        currentGameMessage.timeoutId = setTimeout(typeNextCharacter, typingSpeed);
    } else {
        // 打字完成，确保所有文本都完全显示
        currentGameMessage.textNodes.forEach(textNodeInfo => {
            textNodeInfo.node.nodeValue = textNodeInfo.originalText;
        });

        finishCurrentMessage();
    }
}

// 完成当前消息的显示
function finishCurrentMessage() {
    if (!currentGameMessage) return;

    // 不再替换整个内容，而是保持双层结构
    // 只需确保打字层显示完整内容即可
    // 这样可以避免格式变化

    // 移除队列中的第一条消息
    messageQueue.shift();
    currentGameMessage = null;

    // 如果队列中还有消息，继续处理
    if (messageQueue.length > 0) {
        if (!typewriterEffectEnabled) {
            processNextMessage(); // 立即处理下一条消息，不需要延迟
        } else {
            setTimeout(processNextMessage, 500); // 短暂延迟后显示下一条消息
        }
    } else {
        isTyping = false;
        continueButton.classList.add('hidden');
    }
}

// 立即完成当前消息并显示下一条
function skipToNextMessage() {
    if (!currentGameMessage || !isTyping) return;

    clearTimeout(currentGameMessage.timeoutId);

    // 立即显示所有文本节点的完整内容
    currentGameMessage.textNodes.forEach(textNodeInfo => {
        textNodeInfo.node.nodeValue = textNodeInfo.originalText;
    });

    // 完成当前消息
    finishCurrentMessage();
}

// 处理命结果
function handleCommandResult(content) {
    const gameState = content.game_state;
    const responseData = content.response; // This is now the dictionary from backend

    if (gameState) {
        const upserts = {};
        if (gameState.nodes) upserts.nodes = gameState.nodes;
        if (gameState.diff?.all_object_definitions) upserts.all_object_definitions = gameState.diff.all_object_definitions;
        if (Object.keys(upserts).length > 0) applyUpserts(upserts);

        if (gameState.characters) {
            setAvailableCharacters(gameState.characters);
        }
        updateUIWithGameState(gameState);
        updateDisplayPanel(gameState);
    }

    // narrative_response is NOT displayed here -- it was already streamed
    // to the player during the Architect's commit_world_event tool call.
    // It exists in command_result only for build_game_state_dict's
    // current_perception (to avoid a redundant render_perception LLM call).

    // Control input based on script_paused status
    if (responseData && responseData.script_paused) {
        userInput.disabled = true;
        sendButton.disabled = true;
        continueButton.classList.remove('hidden');
    } else {
        userInput.disabled = false;
        sendButton.disabled = false;
        continueButton.classList.add('hidden');
        userInput.focus();
    }
}

function handleGameStart(content) {
    const gameState = content.game_state;
    const response = content.response; // This can be a string or an object

    if (gameState) {
        if (gameState.characters) {
            setAvailableCharacters(gameState.characters);
        }
        const data = gameState.diff || gameState;
        sessionCode = gameState.session_id;
        // Initialize world data.
        const initialWorldData = {
            nodes: gameState.nodes || {},
            items: data.all_object_definitions || {}
        };
        sessionStorage.setItem('worldData', JSON.stringify(initialWorldData));

        updateUIWithGameState(gameState);
        updateDisplayPanel(gameState);

        displaySessionCode(sessionCode);

        // Set initial status bar text
        const playerState = getCurrentPlayerState(gameState);
        if (playerState?.location) {
            const startNodeId = playerState.location;
            const initialNode = gameState.nodes[startNodeId];
            if (initialNode) {
                updateStatus(`- ${initialNode.name || initialNode.id} -`);
            }
        }
    }

    // Display the response, handling both string and object formats
    if (response) {
        let narrativeResponse = "";
        let scriptPaused = false;

        if (typeof response === 'string') {
            narrativeResponse = response;
        } else if (response.narrative_response) {
            narrativeResponse = response.narrative_response;
            scriptPaused = response.script_paused;
        }

        if (narrativeResponse) {
            const processedNarrative = preprocessDescription(narrativeResponse);
            addGameMessage(processedNarrative, 'game-message');
            const descriptionHtml = converter.makeHtml(processedNarrative);
            nodeDescription.innerHTML = `<h3>Description</h3>${descriptionHtml}`;
        }

        // Control input based on script_paused status
        if (scriptPaused) {
            userInput.disabled = true;
            sendButton.disabled = true;
        } else {
            userInput.disabled = false;
            sendButton.disabled = false;
            userInput.focus();
        }
    }
    showGameInterface();
    isAwaitingGameStart = false;
    hideGameLoadingScreen();
}

function updateUIWithGameState(gameState) {
    console.log("Updating UI with game state:", gameState);
    const player = getCurrentPlayerState(gameState);

    if (player) {
        console.log("Player data:", player);
        currentNodeId = player.location;
    } else {
        console.error("Invalid game state or missing player data:", gameState);
    }
}

function renderStatsDisplay(gameState) {
    if (!statsDisplay) return;
    
    const statsData = gameState?.stats_display;
    
    if (!statsData || statsData.length === 0) {
        statsDisplay.classList.remove('has-stats');
        statsDisplay.innerHTML = '';
        return;
    }
    
    let html = '<h3>Status</h3><div class="stats-list">';
    
    for (const stat of statsData) {
        html += `
            <div class="stat-item">
                <span class="stat-label">${stat.label}:</span>
                <span class="stat-value">${stat.display}</span>
            </div>
        `;
    }
    
    html += '</div>';
    statsDisplay.innerHTML = html;
    statsDisplay.classList.add('has-stats');
}

function updateDisplayPanel(gameState) {
    if (!gameState) return;
    const player = getCurrentPlayerState(gameState);
    const worldDataString = sessionStorage.getItem('worldData');
    const worldData = worldDataString ? JSON.parse(worldDataString) : null;

    if (!worldData) return;

    // Render stats display if available
    renderStatsDisplay(gameState);

    // Render description
    if (player && player.location) {
        const currentNode = worldData.nodes[player.location];
        if (currentNode) {
            const description = currentNode.processed_description || currentNode.description;
            if (description) {
                const processedDescription = preprocessDescription(description);
                const descriptionHtml = converter.makeHtml(processedDescription);
                nodeDescription.innerHTML = `<h3>Description</h3>${descriptionHtml}`;
            }
        }
        if (currentNode && currentNode.name) {
            updateStatus(`- ${currentNode.name} -`);
        }
    }

    // Render inventory
    if (player && player.inventory) {
        let inventoryHtml = '<h3>Inventory</h3>';
        const inventory = player.inventory;
        if (inventory.length > 0) {
            inventoryHtml += '<ul>';
            const itemCounts = inventory.reduce((acc, item) => {
                const itemId = typeof item === 'string' ? item : item.id;
                acc[itemId] = (acc[itemId] || 0) + 1;
                return acc;
            }, {});

            for (const itemId in itemCounts) {
                const itemDetails = worldData.items[itemId];
                const itemCount = itemCounts[itemId];
                if (itemDetails) {
                    const currentStateDescription = (
                        Array.isArray(itemDetails.states)
                            ? (itemDetails.states.find(state => state.name === itemDetails.state)?.description)
                            : undefined
                    ) || itemDetails.explicit_state || itemDetails.description || 'No description.';
                    let itemNameHtml = itemDetails.name;
                    if (itemDetails.actions && itemDetails.actions.length > 0) {
                        itemNameHtml = `<a href="javascript:void(0)" onclick="onObjectClick('${itemId}'); return false;">${itemDetails.name}</a>`;
                    }
                    inventoryHtml += `<li>${itemNameHtml} (x${itemCount}): ${currentStateDescription}</li>`;
                } else {
                    inventoryHtml += `<li>${itemId} (x${itemCount}) - details not found</li>`;
                }
            }
            inventoryHtml += '</ul>';
        } else {
            inventoryHtml += '<p>Your inventory is empty.</p>';
        }
        inventoryDisplay.innerHTML = inventoryHtml;
    }
}


function displayChoices(choices, isRestoring = false) {
    if (!isRestoring) {
        stashedStoryChoices = null;
        availableChoices = choices;
    }

    const choicesContainer = document.getElementById('choices-container');
    choicesContainer.classList.remove('object-actions-loading');
    choicesContainer.removeAttribute('aria-busy');
    choicesContainer.innerHTML = ''; // Clear previous choices

    if (choices && choices.length > 0) {
        choicesContainer.classList.remove('hidden');
        userInput.disabled = true;
        sendButton.disabled = true;

        choices.forEach((choice, index) => {
            const button = document.createElement('button');
            button.textContent = choice.text;
            if (isRestoring) {
                button.onclick = choice.onclick;
            } else {
                button.onclick = () => handleChoice(index + 1);
            }
            choicesContainer.appendChild(button);
        });
    } else {
        choicesContainer.classList.add('hidden');
        userInput.disabled = false;
        sendButton.disabled = false;
    }
}

function displayDialogue(speaker, text, choices) {
    addGameMessage(`**${speaker}:** ${text}`, 'game-message');
    displayChoices(choices);
}

function setupLanguageSetting() {
    if (!languageSelect || !window.TextAdventureI18n) {
        return;
    }

    const syncLanguageValue = () => {
        languageSelect.value = window.TextAdventureI18n.getLocale();
    };

    syncLanguageValue();

    languageSelect.addEventListener('change', function () {
        const locale = window.TextAdventureI18n.setLocale(this.value);
        this.value = locale;
    });

    document.addEventListener('textAdventure:localeChanged', syncLanguageValue);
    document.addEventListener('textAdventure:localeChanged', refreshObjectActionLoadingText);
}

// 设置打字机效果开关
function setupTypewriterToggle() {
    const typewriterToggle = document.getElementById('typewriter-effect');

    // 从本地存储中获取打字机效果设置
    const savedSetting = localStorage.getItem('typewriterEffectEnabled');
    if (savedSetting !== null) {
        typewriterEffectEnabled = savedSetting === 'true';
        typewriterToggle.checked = typewriterEffectEnabled;
    }

    // 添加事件监听器
    typewriterToggle.addEventListener('change', function () {
        typewriterEffectEnabled = this.checked;
        // 保存设置到本地存储
        localStorage.setItem('typewriterEffectEnabled', typewriterEffectEnabled);

        // 显示设置已更改的提示
        const message = {
            content: typewriterEffectEnabled ?
                'typewriter effect enabled' :
                'typewriter effect disabled',
            className: 'system-message',
            timestamp: getCurrentTimestamp()
        };

        // 临时禁用打字机效果来显示系统消息
        const originalSetting = typewriterEffectEnabled;
        typewriterEffectEnabled = false;

        // 添加消息到队列并处理
        addMessageToQueue(message);

        // 恢复原始设置
        typewriterEffectEnabled = originalSetting;
    });

    // 注释掉对未定义函数的调用
    // setupSaveShortcut(); // This function is not implemented
}

// 获取当前时间戳
function getCurrentTimestamp() {
    return new Date().toLocaleTimeString();
}

// 添加消息到队列
function addMessageToQueue(message) {
    messageQueue.push(message);

    // 如果当前没有正在显示的消息，开始处理队列
    if (!isTyping && messageQueue.length === 1) {
        processNextMessage();
    }
}

function showLoading(message) {
    const overlay = document.getElementById('loading-overlay');
    const messageElement = overlay.querySelector('p');
    if (message) {
        messageElement.textContent = message;
    }
    overlay.style.display = 'flex';
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    overlay.style.display = 'none';
}

function showGameLoadingScreen(storyTitle) {
    const overlay = document.getElementById('loading-overlay');
    overlay.innerHTML = `
        <div class="game-loading-content">
            <div class="game-loading-quill"></div>
            <h2 class="game-loading-title">${storyTitle || ''}</h2>
            <div class="game-loading-status">
                <span>Loading</span><span class="loading-ellipsis"></span>
            </div>
        </div>
    `;
    overlay.classList.add('game-entry');
    overlay.style.display = 'flex';

    welcomeMessage.style.display = 'none';
    playerNameInput.style.display = 'none';
    storySelection.style.display = 'none';
    sessionSelection.style.display = 'none';
}

function hideGameLoadingScreen() {
    const overlay = document.getElementById('loading-overlay');
    if (!overlay.classList.contains('game-entry')) return;

    overlay.classList.add('fade-out');
    overlay.addEventListener('transitionend', function handler() {
        overlay.removeEventListener('transitionend', handler);
        overlay.style.display = 'none';
        overlay.classList.remove('game-entry', 'fade-out');
        overlay.innerHTML = `<div class="loading-spinner"></div><p>Generating story...</p>`;
    });
}

function showLoadingBubble() {
    hideLoadingBubble();
    const bubble = document.createElement('div');
    bubble.className = 'message game-message loading-bubble';
    bubble.innerHTML = `<div class="message-content"><span class="loading-ellipsis"></span></div>`;
    loadingBubbleEl = bubble;
    gameMessages.appendChild(bubble);
    gameMessages.scrollTop = gameMessages.scrollHeight;
}

function hideLoadingBubble() {
    if (loadingBubbleEl) {
        loadingBubbleEl.remove();
        loadingBubbleEl = null;
    }
}

// ============================================================================
// Form Handling Functions
// ============================================================================

let currentFormId = null;
let currentFormData = {};

/**
 * Display a form to collect player input
 * @param {Object} formMessage - The form message from the server
 */
function displayForm(formMessage) {
    currentFormId = formMessage.form_id;
    currentFormData = {};
    
    const formDiv = document.createElement('div');
    formDiv.className = 'message game-message form-message';
    formDiv.id = `form-${formMessage.form_id}`;
    
    let formHtml = `
        <div class="form-container">
            <div class="form-header">
                <h3>${escapeHtml(formMessage.title || 'Form')}</h3>
                ${formMessage.description ? `<p class="form-description">${escapeHtml(formMessage.description)}</p>` : ''}
            </div>
            <form class="game-form" onsubmit="submitForm(event, '${formMessage.form_id}')">
    `;
    
    // Render each field
    formMessage.fields.forEach(field => {
        formHtml += renderFormField(field, formMessage.prefill);
    });
    
    formHtml += `
                <div class="form-actions">
                    <button type="submit" class="form-submit-btn">${escapeHtml(formMessage.submit_text || 'Submit')}</button>
                </div>
            </form>
            <div class="form-errors" id="form-errors-${formMessage.form_id}" style="display: none;"></div>
        </div>
    `;
    
    formDiv.innerHTML = formHtml;
    gameMessages.appendChild(formDiv);
    gameMessages.scrollTop = gameMessages.scrollHeight;
    
    // Disable regular input while form is active
    userInput.disabled = true;
    sendButton.disabled = true;
    
    // Add event listeners for conditional fields
    setupConditionalFields(formMessage.form_id, formMessage.fields);
}

/**
 * Render a single form field
 * @param {Object} field - The field definition
 * @param {Object} prefill - Pre-fill values
 * @returns {string} HTML string for the field
 */
function renderFormField(field, prefill = {}) {
    const prefillValue = prefill && prefill[field.id] !== undefined ? prefill[field.id] : (field.default || '');
    const requiredAttr = field.required ? 'required' : '';
    const requiredMark = field.required ? '<span class="required-mark">*</span>' : '';
    
    // Check server-side visibility (from game state variable conditions)
    // _server_visible is set by the server when show_if.variable is evaluated
    const serverVisible = field._server_visible !== false;  // Default to visible if not set
    const displayStyle = serverVisible ? '' : 'display: none;';
    
    let html = `<div class="form-field" id="field-wrapper-${field.id}" data-field-id="${field.id}" style="${displayStyle}">`;
    
    // Skip label for hidden fields
    if (field.type !== 'hidden') {
        html += `<label for="field-${field.id}">${escapeHtml(field.label)}${requiredMark}</label>`;
    }
    
    switch (field.type) {
        case 'text':
            html += `<input type="text" id="field-${field.id}" name="${field.id}" 
                     value="${escapeHtml(String(prefillValue))}" 
                     placeholder="${escapeHtml(field.placeholder || '')}"
                     ${requiredAttr}
                     ${field.validation?.max_length ? `maxlength="${field.validation.max_length}"` : ''}
                     ${field.validation?.pattern ? `pattern="${field.validation.pattern}"` : ''}>`;
            break;
            
        case 'textarea':
            html += `<textarea id="field-${field.id}" name="${field.id}" 
                     placeholder="${escapeHtml(field.placeholder || '')}"
                     rows="${field.rows || 4}"
                     ${requiredAttr}
                     ${field.validation?.max_length ? `maxlength="${field.validation.max_length}"` : ''}>${escapeHtml(String(prefillValue))}</textarea>`;
            break;
            
        case 'number':
            html += `<input type="number" id="field-${field.id}" name="${field.id}" 
                     value="${prefillValue}" 
                     ${field.validation?.min !== undefined ? `min="${field.validation.min}"` : ''}
                     ${field.validation?.max !== undefined ? `max="${field.validation.max}"` : ''}
                     ${field.validation?.step ? `step="${field.validation.step}"` : ''}
                     ${requiredAttr}>`;
            break;
            
        case 'select':
            html += `<select id="field-${field.id}" name="${field.id}" ${requiredAttr}>`;
            html += `<option value="">-- Select --</option>`;
            (field.options || []).forEach(opt => {
                const optValue = typeof opt === 'string' ? opt : opt.value;
                const optText = typeof opt === 'string' ? opt : opt.text;
                const selected = prefillValue === optValue ? 'selected' : '';
                const disabled = opt.disabled ? 'disabled' : '';
                html += `<option value="${escapeHtml(optValue)}" ${selected} ${disabled}>${escapeHtml(optText)}</option>`;
            });
            html += `</select>`;
            break;
            
        case 'multiselect':
            html += `<select id="field-${field.id}" name="${field.id}" multiple ${requiredAttr}>`;
            (field.options || []).forEach(opt => {
                const optValue = typeof opt === 'string' ? opt : opt.value;
                const optText = typeof opt === 'string' ? opt : opt.text;
                const selected = Array.isArray(prefillValue) && prefillValue.includes(optValue) ? 'selected' : '';
                html += `<option value="${escapeHtml(optValue)}" ${selected}>${escapeHtml(optText)}</option>`;
            });
            html += `</select>`;
            break;
            
        case 'checkbox':
            const checked = prefillValue ? 'checked' : '';
            html += `<input type="checkbox" id="field-${field.id}" name="${field.id}" ${checked}>`;
            break;
            
        case 'checkboxgroup':
            html += `<div class="checkbox-group">`;
            (field.options || []).forEach(opt => {
                const optValue = typeof opt === 'string' ? opt : opt.value;
                const optText = typeof opt === 'string' ? opt : opt.text;
                const isChecked = Array.isArray(prefillValue) && prefillValue.includes(optValue) ? 'checked' : '';
                html += `
                    <label class="checkbox-option">
                        <input type="checkbox" name="${field.id}" value="${escapeHtml(optValue)}" ${isChecked}>
                        ${escapeHtml(optText)}
                    </label>`;
            });
            html += `</div>`;
            break;
            
        case 'radio':
            html += `<div class="radio-group">`;
            (field.options || []).forEach(opt => {
                const optValue = typeof opt === 'string' ? opt : opt.value;
                const optText = typeof opt === 'string' ? opt : opt.text;
                const optDesc = typeof opt === 'string' ? '' : (opt.description || '');
                const isChecked = prefillValue === optValue ? 'checked' : '';
                const descRendered = optDesc ? converter.makeHtml(optDesc).replace(/^<p>/, '').replace(/<\/p>$/, '') : '';
                const descHtml = descRendered ? `<span class="radio-option-desc">${descRendered}</span>` : '';
                html += `
                    <label class="radio-option${optDesc ? ' has-desc' : ''}">
                        <input type="radio" name="${field.id}" value="${escapeHtml(optValue)}" ${isChecked} ${requiredAttr}>
                        <span class="radio-option-content">
                            <span class="radio-option-text">${escapeHtml(optText)}</span>
                            ${descHtml}
                        </span>
                    </label>`;
            });
            html += `</div>`;
            break;
            
        case 'slider':
            const minVal = field.validation?.min || 1;
            const maxVal = field.validation?.max || 10;
            const sliderValue = prefillValue || field.default || minVal;
            html += `
                <div class="slider-container">
                    <input type="range" id="field-${field.id}" name="${field.id}" 
                           min="${minVal}" max="${maxVal}" value="${sliderValue}"
                           ${field.validation?.step ? `step="${field.validation.step}"` : ''}
                           oninput="updateSliderLabel('${field.id}', this.value)">
                    <span class="slider-value" id="slider-value-${field.id}">${sliderValue}</span>
                </div>`;
            if (field.validation?.labels) {
                html += `<div class="slider-labels">`;
                for (const [key, label] of Object.entries(field.validation.labels)) {
                    html += `<span>${key}: ${escapeHtml(label)}</span>`;
                }
                html += `</div>`;
            }
            break;
            
        case 'rating':
            const maxRating = field.max_rating || 5;
            const ratingValue = prefillValue || 0;
            html += `<div class="rating-container" id="rating-${field.id}">`;
            for (let i = 1; i <= maxRating; i++) {
                const activeClass = i <= ratingValue ? 'active' : '';
                html += `<span class="rating-star ${activeClass}" data-value="${i}" onclick="setRating('${field.id}', ${i})">★</span>`;
            }
            html += `<input type="hidden" id="field-${field.id}" name="${field.id}" value="${ratingValue}">`;
            html += `</div>`;
            break;
            
        case 'file':
            const acceptAttr = field.accept ? `accept="${field.accept.join(',')}"` : '';
            html += `
                <div class="file-upload-container">
                    <input type="file" id="field-${field.id}" name="${field.id}" 
                           ${acceptAttr} ${requiredAttr}
                           onchange="handleFileSelect('${field.id}', this, ${field.max_size_mb || 5})">
                    <div class="file-info" id="file-info-${field.id}"></div>
                </div>`;
            break;
            
        case 'hidden':
            html += `<input type="hidden" id="field-${field.id}" name="${field.id}" value="${escapeHtml(String(field.value || prefillValue))}">`;
            break;
            
        case 'date':
            html += `<input type="date" id="field-${field.id}" name="${field.id}" 
                     value="${prefillValue}" ${requiredAttr}>`;
            break;
            
        case 'time':
            html += `<input type="time" id="field-${field.id}" name="${field.id}" 
                     value="${prefillValue}" ${requiredAttr}>`;
            break;
            
        default:
            html += `<input type="text" id="field-${field.id}" name="${field.id}" 
                     value="${escapeHtml(String(prefillValue))}" ${requiredAttr}>`;
    }
    
    // Add hint if provided
    if (field.hint) {
        html += `<div class="field-hint">${escapeHtml(field.hint)}</div>`;
    }
    
    // Add error placeholder
    html += `<div class="field-error" id="error-${field.id}"></div>`;
    
    html += `</div>`;
    return html;
}

/**
 * Update slider label when value changes
 */
function updateSliderLabel(fieldId, value) {
    const label = document.getElementById(`slider-value-${fieldId}`);
    if (label) {
        label.textContent = value;
    }
}

/**
 * Set rating value
 */
function setRating(fieldId, value) {
    const container = document.getElementById(`rating-${fieldId}`);
    const input = document.getElementById(`field-${fieldId}`);
    if (container && input) {
        input.value = value;
        const stars = container.querySelectorAll('.rating-star');
        stars.forEach((star, index) => {
            star.classList.toggle('active', index < value);
        });
    }
}

/**
 * Handle file selection
 */
function handleFileSelect(fieldId, input, maxSizeMb) {
    const fileInfo = document.getElementById(`file-info-${fieldId}`);
    const file = input.files[0];
    
    if (!file) {
        fileInfo.innerHTML = '';
        return;
    }
    
    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > maxSizeMb) {
        fileInfo.innerHTML = `<span class="error">File too large (${sizeMb.toFixed(2)}MB > ${maxSizeMb}MB)</span>`;
        input.value = '';
        return;
    }
    
    fileInfo.innerHTML = `<span class="success">${escapeHtml(file.name)} (${sizeMb.toFixed(2)}MB)</span>`;
}

/**
 * Setup conditional field visibility
 */
function setupConditionalFields(formId, fields) {
    fields.forEach(field => {
        if (field.show_if) {
            const dependentField = document.getElementById(`field-${field.show_if.field}`);
            const targetWrapper = document.getElementById(`field-wrapper-${field.id}`);
            
            if (dependentField && targetWrapper) {
                const checkVisibility = () => {
                    let value = dependentField.type === 'checkbox' ? dependentField.checked : dependentField.value;
                    let shouldShow = false;
                    
                    switch (field.show_if.operator) {
                        case 'eq':
                            shouldShow = value == field.show_if.value;
                            break;
                        case 'ne':
                            shouldShow = value != field.show_if.value;
                            break;
                        case 'contains':
                            shouldShow = String(value).includes(field.show_if.value);
                            break;
                        default:
                            shouldShow = value == field.show_if.value;
                    }
                    
                    targetWrapper.style.display = shouldShow ? 'block' : 'none';
                };
                
                dependentField.addEventListener('change', checkVisibility);
                dependentField.addEventListener('input', checkVisibility);
                checkVisibility(); // Initial check
            }
        }
    });
}

/**
 * Submit the form
 */
async function submitForm(event, formId) {
    event.preventDefault();
    
    const form = event.target;
    const formData = {};
    const filesData = {};
    
    // Collect form data
    const formElements = form.elements;
    for (let i = 0; i < formElements.length; i++) {
        const element = formElements[i];
        if (!element.name || element.type === 'submit') continue;
        
        const fieldWrapper = document.getElementById(`field-wrapper-${element.name}`);
        if (fieldWrapper && fieldWrapper.style.display === 'none') continue; // Skip hidden conditional fields
        
        if (element.type === 'checkbox' && !element.closest('.checkbox-group')) {
            formData[element.name] = element.checked;
        } else if (element.type === 'checkbox') {
            // Checkbox group
            if (!formData[element.name]) formData[element.name] = [];
            if (element.checked) {
                formData[element.name].push(element.value);
            }
        } else if (element.type === 'radio') {
            if (element.checked) {
                formData[element.name] = element.value;
            }
        } else if (element.type === 'select-multiple') {
            formData[element.name] = Array.from(element.selectedOptions).map(o => o.value);
        } else if (element.type === 'file') {
            const file = element.files[0];
            if (file) {
                try {
                    const base64Data = await fileToBase64(file);
                    filesData[element.name] = {
                        data: base64Data,
                        mime_type: file.type,
                        filename: file.name
                    };
                } catch (err) {
                    console.error('Error reading file:', err);
                }
            }
        } else {
            formData[element.name] = element.value;
        }
    }
    
    // Show loading state
    const submitBtn = form.querySelector('.form-submit-btn');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Submitting...';
    submitBtn.disabled = true;
    
    // Send to server
    showLoadingBubble();
    socket.send(JSON.stringify({
        type: 'form_submit',
        form_id: formId,
        data: formData,
        files: filesData
    }));
}

/**
 * Convert file to base64
 */
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            // Remove data URL prefix
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/**
 * Handle form submission success
 */
function handleFormSuccess(formId) {
    const formDiv = document.getElementById(`form-${formId}`);
    if (formDiv) {
        // Replace form with a simple success message matching the bubble style
        formDiv.innerHTML = `
            <div class="message-content">
                <div class="form-success-message">
                    <span class="success-icon">✓</span>
                    <span>Submitted successfully</span>
                </div>
            </div>
            <div class="message-timestamp">${new Date().toLocaleTimeString()}</div>
        `;
        // Change to a green success style
        formDiv.style.backgroundColor = '#e8f5e9';
        formDiv.style.color = '#2e7d32';
        formDiv.style.borderLeft = '3px solid #4caf50';
    }
    
    // Re-enable regular input
    userInput.disabled = false;
    sendButton.disabled = false;
    userInput.focus();
    currentFormId = null;
}

/**
 * Handle form validation errors
 */
function handleFormError(formId, errors) {
    const formDiv = document.getElementById(`form-${formId}`);
    if (!formDiv) return;
    
    // Clear previous errors
    formDiv.querySelectorAll('.field-error').forEach(el => {
        el.textContent = '';
        el.style.display = 'none';
    });
    
    // Display new errors
    for (const [fieldId, errorMsg] of Object.entries(errors)) {
        if (fieldId === '_form') {
            // General form error
            const errorsDiv = document.getElementById(`form-errors-${formId}`);
            if (errorsDiv) {
                errorsDiv.textContent = errorMsg;
                errorsDiv.style.display = 'block';
            }
        } else {
            const errorDiv = document.getElementById(`error-${fieldId}`);
            if (errorDiv) {
                errorDiv.textContent = errorMsg;
                errorDiv.style.display = 'block';
            }
        }
    }
    
    // Re-enable submit button
    const submitBtn = formDiv.querySelector('.form-submit-btn');
    if (submitBtn) {
        submitBtn.textContent = 'Submit';
        submitBtn.disabled = false;
    }
}

// ============================================================================
// End Form Handling Functions
// ============================================================================

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

function displayItemDrop(items) {
    const animationType = 'sparkle-and-rise'; // or 'flip-and-collect'

    items.forEach(item => {
        if (!item) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message item-drop-message';
        messageDiv.innerHTML = `<div class="message-content">${item.name}</div>`;
        messageDiv.dataset.itemId = item.id;

        messageDiv.addEventListener('click', () => {
            let animationDuration = 0;
            const currentHeight = messageDiv.offsetHeight;

            if (animationType === 'flip-and-collect') {
                const geminiButton = document.getElementById('display-toggle-btn');
                const itemRect = messageDiv.getBoundingClientRect();
                const buttonRect = geminiButton.getBoundingClientRect();
                const x = buttonRect.left - itemRect.left + (buttonRect.width / 2) - (itemRect.width / 2);
                const y = buttonRect.top - itemRect.top + (buttonRect.height / 2) - (itemRect.height / 2);
                messageDiv.style.setProperty('--zoom-transform', `translate(${x}px, ${y}px)`);
                messageDiv.classList.add('item-pickup-animation', 'flip-and-collect');
                animationDuration = 625;
            } else if (animationType === 'sparkle-and-rise') {
                messageDiv.classList.add('item-pickup-animation', 'sparkle-and-rise');
                animationDuration = 500;
            }

            messageDiv.style.pointerEvents = 'none';

            setTimeout(() => {
                messageDiv.style.height = `${currentHeight}px`;
                messageDiv.style.visibility = 'hidden';
                // Remove the content to prevent any lingering elements
                messageDiv.innerHTML = '';
            }, animationDuration);

            socket.send(JSON.stringify({ type: 'command', content: `pickup ${item.id}` }));
        }, { once: true });

        gameMessages.appendChild(messageDiv);
        gameMessages.scrollTop = gameMessages.scrollHeight;
    });
}