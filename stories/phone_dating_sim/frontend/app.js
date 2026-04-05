/* Heartline — Phone Dating Sim frontend */
/* global WenyooStorySDK */

(function () {
  "use strict";

  // ── Data ──────────────────────────────────────────────────────────────────

  var CHARACTERS = {
    sophie: { name: "Sophie", emoji: "📚", tagline: "Librarian & aspiring novelist" },
    marcus: { name: "Marcus", emoji: "💪", tagline: "Personal trainer & DJ" },
    ava:    { name: "Ava",    emoji: "🎨", tagline: "Freelance illustrator" },
  };

  var GIFT_DELIVERY_SECONDS = 120;

  // ── State ─────────────────────────────────────────────────────────────────

  var bridge = null;
  var gameState = null;
  var playerId = null;
  var currentChatTarget = null;
  var waitingForReply = false;
  var shopGenerating = false;

  // ── Screens ───────────────────────────────────────────────────────────────

  function showScreen(id) {
    document.querySelectorAll(".screen").forEach(function (s) { s.classList.remove("active"); });
    var el = document.getElementById("screen-" + id);
    if (el) el.classList.add("active");
  }

  // ── Clock ─────────────────────────────────────────────────────────────────

  function updateClock() {
    var now = new Date();
    document.getElementById("status-time").textContent =
      now.getHours().toString().padStart(2, "0") + ":" +
      now.getMinutes().toString().padStart(2, "0");
  }
  setInterval(updateClock, 10000);
  updateClock();

  // ── Toast ─────────────────────────────────────────────────────────────────

  function showToast(msg, duration) {
    duration = duration || 2500;
    var el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(function () { el.classList.add("hidden"); }, duration);
  }

  // ── State helpers ─────────────────────────────────────────────────────────

  function getCharState(charId) {
    if (!gameState) return null;
    var cs = gameState.character_states || {};
    return cs[charId] || null;
  }

  function getAffection(charId) {
    var c = getCharState(charId);
    return c && c.properties ? (c.properties.affection ?? 50) : 50;
  }

  function getChatHistory(charId) {
    var c = getCharState(charId);
    return c && c.properties ? (c.properties.chat_history || []) : [];
  }

  function getChatHistoryFrom(state, charId) {
    if (!state) return [];
    var cs = state.character_states || {};
    var c = cs[charId];
    return c && c.properties ? (c.properties.chat_history || []) : [];
  }

  function getCoins() {
    if (!gameState) return 9999;
    var vars = gameState.variables || {};
    return vars.player_coins ?? 9999;
  }

  function getShopInventory() {
    if (!gameState) return [];
    var vars = gameState.variables || {};
    return vars.giftbox_inventory || [];
  }

  function getRefreshCost() {
    if (!gameState) return 50;
    var vars = gameState.variables || {};
    return vars.giftbox_refresh_cost ?? 50;
  }

  function updateCoinsDisplay() {
    document.getElementById("status-coins").textContent = "🪙 " + getCoins();
  }

  // ── Contact list ──────────────────────────────────────────────────────────

  function renderContacts() {
    var list = document.getElementById("contact-list");
    list.innerHTML = "";
    for (var charId of Object.keys(CHARACTERS)) {
      var info = CHARACTERS[charId];
      var affection = getAffection(charId);
      var history = getChatHistory(charId);
      var lastMsg = history.length > 0 ? history[history.length - 1] : null;
      var preview = lastMsg
        ? (lastMsg.role === "player" ? "You: " : "") + truncate(lastMsg.text, 40)
        : "Tap to start chatting";

      var row = document.createElement("button");
      row.className = "contact-row";
      row.innerHTML =
        '<span class="contact-avatar">' + info.emoji + "</span>" +
        '<div class="contact-info">' +
          "<strong>" + info.name + "</strong>" +
          '<span class="contact-preview">' + escapeHtml(preview) + "</span>" +
        "</div>" +
        '<span class="contact-affection">' + affectionLabel(affection) + "</span>";
      (function (cid) {
        row.addEventListener("click", function () { openChat(cid); });
      })(charId);
      list.appendChild(row);
    }
  }

  function affectionLabel(n) {
    if (n >= 80) return "❤️ " + n;
    if (n >= 60) return "💛 " + n;
    if (n >= 40) return "💙 " + n;
    return "🤍 " + n;
  }

  function truncate(s, max) {
    return s.length > max ? s.substring(0, max) + "..." : s;
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Chat view ─────────────────────────────────────────────────────────────

  function openChat(charId) {
    currentChatTarget = charId;
    var info = CHARACTERS[charId];
    document.getElementById("chat-name").textContent = info.name;
    document.getElementById("chat-affection").textContent = affectionLabel(getAffection(charId));
    renderChatMessages(charId);
    showScreen("chat");
    scrollChatToBottom();
  }

  function renderChatMessages(charId) {
    var container = document.getElementById("chat-messages");
    container.innerHTML = "";
    var history = getChatHistory(charId);
    for (var i = 0; i < history.length; i++) {
      appendChatBubble(history[i].role, history[i].text, false);
    }
  }

  function appendChatBubble(role, text, scroll) {
    var container = document.getElementById("chat-messages");
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble " + (role === "player" ? "sent" : "received");
    bubble.textContent = text;
    container.appendChild(bubble);
    if (scroll !== false) scrollChatToBottom();
  }

  function showTypingIndicator() {
    var container = document.getElementById("chat-messages");
    var indicator = container.querySelector(".typing-indicator");
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.className = "chat-bubble received typing-indicator";
      indicator.textContent = "typing...";
      container.appendChild(indicator);
      scrollChatToBottom();
    }
  }

  function removeTypingIndicator() {
    var container = document.getElementById("chat-messages");
    var indicator = container.querySelector(".typing-indicator");
    if (indicator) indicator.remove();
  }

  function scrollChatToBottom() {
    var container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
  }

  function sendChatMessage() {
    var input = document.getElementById("chat-input");
    var text = input.value.trim();
    if (!text || !currentChatTarget || waitingForReply) return;

    input.value = "";
    appendChatBubble("player", text);
    showTypingIndicator();
    waitingForReply = true;

    var charId = currentChatTarget;
    var charInfo = CHARACTERS[charId];
    var affection = getAffection(charId);
    var history = getChatHistory(charId);
    var recentHistory = history.slice(-10);

    bridge.sendArchitectTask("character_interaction", {
      action_id: "chat_message_" + charId,
      display_text: text,
      player_input: text,
      purpose:
        "The player sent a chat message to " + charInfo.name + " via HeartChat. " +
        "Role-play " + charInfo.name + "'s reply. Current affection: " + affection + ". " +
        "Recent chat history (last " + recentHistory.length + " messages): " +
        JSON.stringify(recentHistory) + ". " +
        "Respond ONLY as " + charInfo.name + " in 1-3 short texting-style sentences. " +
        "Use commit() with: " +
        "(1) a narrative artifact containing ONLY the character's reply text (no stage directions, no quotes, no attribution), " +
        "(2) state_changes to append both the player's message and the character's reply to " +
        "character_states." + charId + ".properties.chat_history. " +
        "Each chat_history entry is {role: 'player'|'npc', text: '...'}. " +
        "Write the FULL chat_history array (existing + new entries).",
      structured_input: {
        target_character: charId,
        message_text: text,
        current_affection: affection,
        recent_chat_history: recentHistory,
      },
      extra_context: {
        chat_target_character: charId,
        input_type: "story_app",
      },
    });
  }

  // ── GiftBox ───────────────────────────────────────────────────────────────

  function renderProducts() {
    var inventory = getShopInventory();
    var grid = document.getElementById("product-grid");
    var loading = document.getElementById("shop-loading");
    var refreshBtn = document.getElementById("refresh-shop-btn");
    var costSpan = document.getElementById("refresh-cost");

    costSpan.textContent = getRefreshCost();

    if (shopGenerating) {
      grid.innerHTML = "";
      loading.classList.remove("hidden");
      refreshBtn.disabled = true;
      return;
    }

    loading.classList.add("hidden");
    refreshBtn.disabled = false;

    if (inventory.length === 0) {
      grid.innerHTML = '<div class="shop-empty">Shop is empty. Tap Refresh to stock new gifts!</div>';
      return;
    }

    grid.innerHTML = "";
    var coins = getCoins();

    for (var i = 0; i < inventory.length; i++) {
      var p = inventory[i];
      var card = document.createElement("div");
      card.className = "product-card";
      var canAfford = coins >= (p.price || 0);
      var tagsHtml = "";
      if (p.tags && p.tags.length) {
        tagsHtml = '<span class="product-tags">' + p.tags.map(function (t) { return escapeHtml(t); }).join(", ") + "</span>";
      }
      card.innerHTML =
        '<span class="product-emoji">' + (p.emoji || "🎁") + "</span>" +
        '<div class="product-info">' +
          "<strong>" + escapeHtml(p.name || "Gift") + "</strong>" +
          '<span class="product-desc">' + escapeHtml(p.desc || "") + "</span>" +
          tagsHtml +
          '<span class="product-price">🪙 ' + (p.price || 0) + "</span>" +
        "</div>" +
        '<button class="buy-btn"' + (canAfford ? "" : " disabled") + ">Buy</button>";
      (function (product) {
        card.querySelector(".buy-btn").addEventListener("click", function () { buyGift(product); });
      })(p);
      grid.appendChild(card);
    }
  }

  function requestShopGeneration() {
    if (shopGenerating) return;
    shopGenerating = true;
    renderProducts();

    // Collect all gift_history across characters to avoid duplicates
    var allGiftHistory = [];
    for (var charId of Object.keys(CHARACTERS)) {
      var cs = getCharState(charId);
      if (cs && cs.properties && cs.properties.gift_history) {
        allGiftHistory = allGiftHistory.concat(cs.properties.gift_history);
      }
    }

    bridge.sendArchitectTask("ui_requested_generation", {
      action_id: "generate_giftbox",
      player_input: "Generate new gift shop inventory.",
      purpose:
        "Generate 8 gift items for the GiftBox shop. Follow the rules in lore_gift_generation exactly. " +
        "Each item must have: id (snake_case), name, emoji, price (30-500), desc (one sentence), " +
        "tags (2-4 keywords from the allowed vocabulary). " +
        "Do NOT repeat items from gift_history: " + JSON.stringify(allGiftHistory) + ". " +
        "Use commit() with state_changes to write the array to variables.giftbox_inventory. " +
        "Do NOT include any narrative artifact — this is a structured data generation task.",
      structured_input: {
        action: "generate_shop",
        existing_gift_history: allGiftHistory,
      },
      extra_context: {
        input_type: "story_app",
      },
    });
  }

  function refreshShop() {
    var cost = getRefreshCost();
    var coins = getCoins();
    if (coins < cost) {
      showToast("Not enough coins to refresh! Need 🪙 " + cost);
      return;
    }
    // Deduct refresh cost first
    bridge.sendDeterministicAction("merge_patch", {
      patch: {
        variables: { player_coins: coins - cost },
      },
    }, {
      display_text: "Paid " + cost + " coins to refresh shop",
    });
    showToast("Refreshing shop...", 2000);
    requestShopGeneration();
  }

  function buyGift(product) {
    var recipient = document.getElementById("gift-recipient").value;
    var coins = getCoins();
    if (coins < (product.price || 0)) {
      showToast("Not enough coins!");
      return;
    }

    var charInfo = CHARACTERS[recipient];
    var newCoins = coins - product.price;
    var currentPending = getCharState(recipient)?.properties?.pending_gifts || [];

    // Remove the purchased item from shop inventory
    var currentInventory = getShopInventory();
    var updatedInventory = currentInventory.filter(function (item) { return item.id !== product.id; });

    bridge.sendDeterministicAction("merge_patch", {
      patch: {
        variables: {
          player_coins: newCoins,
          giftbox_inventory: updatedInventory,
        },
        character_states: {
          [recipient]: {
            properties: {
              pending_gifts: [
                ...currentPending,
                { gift_id: product.id, gift_name: product.name, gift_tags: product.tags || [] },
              ],
            },
          },
        },
        timed_events: [
          {
            id: "gift_delivery_" + recipient + "_" + Date.now(),
            event_type: "gift_delivery",
            delay_seconds: GIFT_DELIVERY_SECONDS,
            object_id: product.id,
            scope: "player",
            player_id: playerId,
            audience: "self",
            event_context:
              "A gift '" + product.name + "' (tags: " + (product.tags || []).join(", ") + ") " +
              "has been delivered to " + charInfo.name + ". " +
              "Check " + charInfo.name + "'s gift_preferences (tag-based) in " +
              "character_states." + recipient + ".properties.gift_preferences. " +
              "Compare the gift's tags against the character's likes and dislikes tags. " +
              "If more tags match likes than dislikes: increase affection by 8-12. " +
              "If more tags match dislikes: decrease affection by 5-8. " +
              "If neutral: increase by 2-4. " +
              "Update affection, remove this gift from pending_gifts, append gift id to gift_history, " +
              "and send a short in-character reaction from " + charInfo.name + " as a narrative artifact. " +
              "Also append the reaction to chat_history as {role: 'npc', text: '...'}. " +
              "Write the FULL arrays for chat_history, gift_history, and pending_gifts.",
            intended_state_changes: {
              character_states: {
                [recipient]: {
                  properties: {
                    gift_history: "__append:" + product.id,
                  },
                },
              },
            },
          },
        ],
      },
    }, {
      display_text: "Bought " + product.name + " for " + charInfo.name,
    });

    showToast("🎁 " + product.name + " on its way to " + charInfo.name + "! (~2 min)", 3000);
    updateCoinsDisplay();
    renderProducts();
  }

  // ── Bridge message handling ───────────────────────────────────────────────

  function onGameState(state) {
    var prevState = gameState;
    gameState = state;
    if (state.player_state && state.player_state.player_id) {
      playerId = state.player_state.player_id;
    }
    updateCoinsDisplay();

    // Check if shop generation completed
    if (shopGenerating && getShopInventory().length > 0) {
      shopGenerating = false;
    }

    // Detect new chat messages (e.g. gift reactions arriving via timed events)
    if (prevState) {
      for (var charId of Object.keys(CHARACTERS)) {
        var oldLen = getChatHistoryFrom(prevState, charId).length;
        var newLen = getChatHistory(charId).length;
        if (newLen > oldLen) {
          var lastEntry = getChatHistory(charId)[newLen - 1];
          if (lastEntry && lastEntry.role === "npc") {
            var charName = CHARACTERS[charId].name;
            if (!(currentChatTarget === charId && document.getElementById("screen-chat").classList.contains("active"))) {
              showToast(charName + ": " + truncate(lastEntry.text, 50), 4000);
            }
          }
        }
      }
    }

    if (document.getElementById("screen-contacts").classList.contains("active")) {
      renderContacts();
    }
    if (document.getElementById("screen-chat").classList.contains("active") && currentChatTarget) {
      document.getElementById("chat-affection").textContent = affectionLabel(getAffection(currentChatTarget));
      renderChatMessages(currentChatTarget);
      scrollChatToBottom();
    }
    if (document.getElementById("screen-giftbox").classList.contains("active")) {
      renderProducts();
    }
  }

  function handleNpcReply(message) {
    var content = message.content || message;

    if (content.game_state) {
      onGameState(content.game_state);
    }

    // Extract NPC reply from artifacts or narrative response
    var npcReply = null;
    var artifacts = content.artifacts || [];
    for (var i = 0; i < artifacts.length; i++) {
      if (artifacts[i].kind === "narrative" && artifacts[i].payload) {
        npcReply = artifacts[i].payload;
        break;
      }
    }
    if (!npcReply && content.response) {
      var resp = typeof content.response === "string"
        ? content.response
        : content.response.narrative_response;
      if (resp) npcReply = resp;
    }
    if (!npcReply && content.response_client && content.response_client.text) {
      npcReply = content.response_client.text;
    }

    if (npcReply && waitingForReply && currentChatTarget) {
      removeTypingIndicator();
      appendChatBubble("npc", npcReply);
      waitingForReply = false;
    } else if (npcReply) {
      removeTypingIndicator();
      waitingForReply = false;
      if (currentChatTarget && document.getElementById("screen-chat").classList.contains("active")) {
        renderChatMessages(currentChatTarget);
        scrollChatToBottom();
      }
      if (document.getElementById("screen-contacts").classList.contains("active")) {
        renderContacts();
      }
    }
  }

  function setupBridgeListeners() {
    bridge.on("game_start", function (msg) {
      var content = msg.content || {};
      if (content.game_state) onGameState(content.game_state);
      renderContacts();
      // Auto-generate shop if empty
      if (getShopInventory().length === 0 && !shopGenerating) {
        requestShopGeneration();
      } else {
        renderProducts();
      }
    });

    bridge.on("rejoined", function (msg) {
      var content = msg.content || {};
      if (content.game_state) onGameState(content.game_state);
      renderContacts();
      if (getShopInventory().length === 0 && !shopGenerating) {
        requestShopGeneration();
      } else {
        renderProducts();
      }
    });

    bridge.on("game_state", function (msg) {
      onGameState(msg.content || msg);
    });

    bridge.on("command_result", function (msg) {
      handleNpcReply(msg);
    });

    bridge.on("stream_end", function (msg) {
      if (msg.client_content && msg.client_content.text && waitingForReply && currentChatTarget) {
        removeTypingIndicator();
        appendChatBubble("npc", msg.client_content.text);
        waitingForReply = false;
      }
    });

    bridge.on("event", function (msg) {
      console.log("[Heartline] bridge event:", msg.type, msg);
    });
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    bridge = WenyooStorySDK.createBridge();
    setupBridgeListeners();
    bridge.requestInitialState();

    document.getElementById("return-menu-btn").addEventListener("click", function () {
      bridge.requestReturnToMenu();
    });

    document.querySelectorAll(".app-icon[data-app]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var app = btn.dataset.app;
        if (app === "heartchat") {
          renderContacts();
          showScreen("contacts");
        } else if (app === "giftbox") {
          if (getShopInventory().length === 0 && !shopGenerating) {
            requestShopGeneration();
          }
          renderProducts();
          showScreen("giftbox");
        }
      });
    });

    document.querySelectorAll(".app-icon.placeholder").forEach(function (btn) {
      btn.addEventListener("click", function () { showToast("Coming soon!"); });
    });

    document.querySelectorAll(".back-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.dataset.back;
        if (target === "home") showScreen("home");
        else if (target === "contacts") {
          renderContacts();
          showScreen("contacts");
        }
        currentChatTarget = null;
        waitingForReply = false;
      });
    });

    document.getElementById("chat-send-btn").addEventListener("click", sendChatMessage);
    document.getElementById("chat-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") sendChatMessage();
    });

    document.getElementById("gift-recipient").addEventListener("change", renderProducts);
    document.getElementById("refresh-shop-btn").addEventListener("click", refreshShop);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
