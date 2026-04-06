/* Arcane Forge — AI-Native Weapon Enchantment frontend */
/* global WenyooStorySDK */

(function () {
  "use strict";

  var bridge = null;
  var gameState = null;
  var playerId = null;
  var conjuring = false;
  var forging = false;

  // Forge slots: [materialId | null, materialId | null, materialId | null]
  var forgeSlots = [null, null, null];
  var activePickerSlot = null;

  // ── Helpers ─────────────────────────────────────────────────────────────

  function getVar(key, fallback) {
    if (!gameState) return fallback;
    var vars = gameState.variables || {};
    return vars[key] !== undefined ? vars[key] : fallback;
  }

  function getMaterials() { return getVar("conjured_materials", []); }
  function getWeapons() { return getVar("forged_weapons", []); }
  function getEnergy() { return getVar("forge_energy", 100); }

  function getMaterialById(id) {
    var mats = getMaterials();
    for (var i = 0; i < mats.length; i++) {
      if (mats[i].id === id) return mats[i];
    }
    return null;
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function showToast(msg, dur) {
    var el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(function () { el.classList.add("hidden"); }, dur || 2500);
  }

  // ── Tabs ──────────────────────────────────────────────────────────────

  function showTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
    document.querySelectorAll(".tab-content").forEach(function (t) { t.classList.remove("active"); });
    var tabBtn = document.querySelector('.tab[data-tab="' + name + '"]');
    var tabContent = document.getElementById("tab-" + name);
    if (tabBtn) tabBtn.classList.add("active");
    if (tabContent) tabContent.classList.add("active");
  }

  // ── Energy display ────────────────────────────────────────────────────

  function updateEnergy() {
    document.getElementById("forge-energy").textContent = "⚡ " + getEnergy();
  }

  // ── Material card renderer ────────────────────────────────────────────

  function renderMaterialCard(mat, opts) {
    opts = opts || {};
    var card = document.createElement("div");
    card.className = "material-card";
    card.style.borderColor = mat.visual ? mat.visual.color : "#555";

    var glowColor = mat.visual ? mat.visual.color : "#888";
    var glowIntensity = mat.visual ? (mat.visual.glow_intensity || 0.3) : 0.3;
    card.style.boxShadow = "0 0 " + Math.round(glowIntensity * 20) + "px " + glowColor + "40";

    var effectClass = mat.visual ? ("effect-" + mat.visual.effect) : "";

    card.innerHTML =
      '<div class="mat-header" style="color:' + glowColor + '">' +
        '<span class="mat-effect-dot ' + effectClass + '" style="background:' + glowColor + '"></span>' +
        "<strong>" + escapeHtml(mat.name) + "</strong>" +
      "</div>" +
      '<div class="mat-desc">' + escapeHtml(mat.description) + "</div>" +
      '<div class="mat-tags">' +
        '<span class="mat-element" style="color:' + glowColor + '">' + escapeHtml(mat.element) + "</span> " +
        (mat.properties || []).map(function (p) { return '<span class="mat-prop">' + escapeHtml(p) + "</span>"; }).join(" ") +
      "</div>" +
      '<div class="mat-stats">' +
        "⚔ " + (mat.power || 0) + " &nbsp; 🛡 " + (mat.stability || 0) +
      "</div>";

    if (opts.onClick) {
      card.classList.add("clickable");
      card.addEventListener("click", function () { opts.onClick(mat); });
    }
    return card;
  }

  // ── Weapon card renderer ──────────────────────────────────────────────

  function renderWeaponCard(weapon) {
    var card = document.createElement("div");
    var vis = weapon.visual || {};
    var glowColor = vis.glow_color || "#ffd700";
    var rarity = weapon.rarity || "common";
    card.className = "weapon-card rarity-" + rarity;
    card.style.borderColor = glowColor;

    var glowIntensity = vis.glow_intensity || 0.5;
    card.style.boxShadow = "0 0 " + Math.round(glowIntensity * 30) + "px " + glowColor + "50";

    var runes = (vis.rune_symbols || []).join(" ");
    var stats = weapon.stats || {};

    // Create weapon SVG container
    var weaponDisplay = document.createElement("div");
    weaponDisplay.className = "weapon-svg-container";

    // Build info HTML
    var infoDiv = document.createElement("div");
    infoDiv.className = "weapon-info";
    infoDiv.innerHTML =
      '<div class="weapon-name" style="color:' + glowColor + '">' + escapeHtml(weapon.name) + "</div>" +
      '<div class="weapon-type">' + escapeHtml(weapon.type || "weapon") + " — " + escapeHtml(rarity) +
        (runes ? ' &nbsp; <span class="weapon-runes-inline">' + runes + "</span>" : "") +
      "</div>" +
      '<div class="weapon-stats">' +
        "⚔ " + (stats.damage_min || 0) + "-" + (stats.damage_max || 0) +
        " &nbsp; 🎯 " + Math.round((stats.critical_chance || 0) * 100) + "%" +
        (stats.element ? " &nbsp; ✧ " + escapeHtml(stats.element) : "") +
      "</div>" +
      (stats.special_effect
        ? '<div class="weapon-special">✦ ' + escapeHtml(stats.special_effect) + " — " + escapeHtml(stats.special_description || "") + "</div>"
        : "") +
      (weapon.cursed
        ? '<div class="weapon-curse">☠ CURSED — ' + escapeHtml(weapon.curse_description || "") + "</div>"
        : "") +
      '<div class="weapon-desc">' + escapeHtml(weapon.description) + "</div>";

    card.appendChild(weaponDisplay);
    card.appendChild(infoDiv);

    // Render SVG weapon
    setTimeout(function () {
      if (window.WeaponRenderer) {
        WeaponRenderer.render(weaponDisplay, weapon);
      }
    }, 0);

    return card;
  }

  // ── Conjure Tab ───────────────────────────────────────────────────────

  function renderMaterials() {
    var mats = getMaterials();
    var grid = document.getElementById("materials-grid");
    document.getElementById("material-count").textContent = mats.length;

    if (mats.length === 0) {
      grid.innerHTML = '<div class="empty-state">No materials yet. Conjure some above!</div>';
      return;
    }
    grid.innerHTML = "";
    for (var i = 0; i < mats.length; i++) {
      grid.appendChild(renderMaterialCard(mats[i]));
    }
  }

  function conjureMaterial() {
    var input = document.getElementById("material-input");
    var desc = input.value.trim();
    if (!desc || conjuring) return;

    input.value = "";
    conjuring = true;
    document.getElementById("conjure-loading").classList.remove("hidden");
    document.getElementById("conjure-btn").disabled = true;

    var currentMats = getMaterials();

    bridge.sendArchitectTask("ui_requested_generation", {
      action_id: "conjure_material",
      active_view: "conjure",
      player_input: desc,
      purpose:
        "The player described a material: \"" + desc + "\". " +
        "Generate it following lore_material_generation rules. " +
        "Use commit() with: " +
        "(1) state_changes writing the new material appended to variables.conjured_materials (write FULL array, " + currentMats.length + " existing + 1 new), " +
        "(2) a brief narrative artifact as the forge spirit's 1-sentence reaction to this material.",
      structured_input: {
        action: "conjure_material",
        player_description: desc,
        existing_material_count: currentMats.length,
        existing_material_ids: currentMats.map(function (m) { return m.id; }),
      },
      extra_context: {
        input_type: "story_app",
        active_view: "conjure",
      },
    });
  }

  // ── Forge Tab ─────────────────────────────────────────────────────────

  function renderForgeSlots() {
    for (var i = 0; i < 3; i++) {
      var slot = document.getElementById("slot-" + i);
      var mat = forgeSlots[i] ? getMaterialById(forgeSlots[i]) : null;
      if (mat) {
        slot.innerHTML = "";
        slot.appendChild(renderMaterialCard(mat));
        slot.classList.add("filled");
        // Add remove button
        var removeBtn = document.createElement("button");
        removeBtn.className = "slot-remove";
        removeBtn.textContent = "×";
        (function (idx) {
          removeBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            forgeSlots[idx] = null;
            renderForgeSlots();
          });
        })(i);
        slot.appendChild(removeBtn);
      } else {
        slot.innerHTML =
          '<span class="slot-label">Material ' + (i + 1) + "</span>" +
          '<span class="slot-hint">' + (i < 2 ? "Tap to select" : "(optional)") + "</span>";
        slot.classList.remove("filled");
      }
    }
    // Enable forge button if at least 2 slots filled
    var filledCount = forgeSlots.filter(function (s) { return s !== null; }).length;
    document.getElementById("forge-btn").disabled = filledCount < 2 || forging || getEnergy() < 20;
  }

  function openPicker(slotIndex) {
    activePickerSlot = slotIndex;
    var mats = getMaterials();
    var usedIds = forgeSlots.filter(function (s) { return s !== null; });
    var available = mats.filter(function (m) { return usedIds.indexOf(m.id) === -1; });

    var grid = document.getElementById("picker-materials");
    grid.innerHTML = "";
    if (available.length === 0) {
      grid.innerHTML = '<div class="empty-state">No available materials. Conjure more!</div>';
    } else {
      for (var i = 0; i < available.length; i++) {
        grid.appendChild(renderMaterialCard(available[i], {
          onClick: function (mat) {
            forgeSlots[activePickerSlot] = mat.id;
            closePicker();
            renderForgeSlots();
          },
        }));
      }
    }
    document.getElementById("material-picker").classList.remove("hidden");
  }

  function closePicker() {
    document.getElementById("material-picker").classList.add("hidden");
    activePickerSlot = null;
  }

  function activateForge() {
    var selectedMats = forgeSlots
      .filter(function (s) { return s !== null; })
      .map(function (id) { return getMaterialById(id); })
      .filter(function (m) { return m !== null; });

    if (selectedMats.length < 2) {
      showToast("Need at least 2 materials!");
      return;
    }
    if (getEnergy() < 20) {
      showToast("Not enough forge energy!");
      return;
    }

    forging = true;
    document.getElementById("forge-loading").classList.remove("hidden");
    document.getElementById("forge-btn").disabled = true;
    document.getElementById("forge-result").classList.add("hidden");
    document.getElementById("forge-spirit-speech").classList.add("hidden");

    var weaponType = document.getElementById("weapon-base-select").value;
    var currentWeapons = getWeapons();
    var currentMats = getMaterials();
    var usedIds = selectedMats.map(function (m) { return m.id; });
    var remainingMats = currentMats.filter(function (m) { return usedIds.indexOf(m.id) === -1; });

    bridge.sendArchitectTask("ui_requested_generation", {
      action_id: "forge_weapon",
      active_view: "forge",
      player_input: "Forge a " + weaponType + " from: " + selectedMats.map(function (m) { return m.name; }).join(" + "),
      purpose:
        "The player is combining these materials at the forge to create a " + weaponType + ":\n" +
        JSON.stringify(selectedMats, null, 2) + "\n\n" +
        "Generate a weapon following lore_forging_rules. The weapon type MUST be '" + weaponType + "'. " +
        "IMPORTANT: include the weapon_shape object for canvas rendering. " +
        "Use commit() with: " +
        "(1) state_changes that: " +
        "  - writes the new weapon appended to variables.forged_weapons (FULL array, " + currentWeapons.length + " existing + 1 new), " +
        "  - removes used materials by writing variables.conjured_materials as the remaining array (" + remainingMats.length + " items), " +
        "  - subtracts forge energy (20-40 based on complexity) from variables.forge_energy (current: " + getEnergy() + "), " +
        "(2) a narrative artifact as the forge spirit's dramatic 2-3 sentence description of the forging moment.",
      structured_input: {
        action: "forge_weapon",
        weapon_type: weaponType,
        materials: selectedMats,
        current_weapon_count: currentWeapons.length,
        current_energy: getEnergy(),
        remaining_materials: remainingMats,
      },
      extra_context: {
        input_type: "story_app",
        active_view: "forge",
      },
    });
  }

  // ── Collection Tab ────────────────────────────────────────────────────

  function renderWeapons() {
    var weapons = getWeapons();
    var grid = document.getElementById("weapons-grid");
    document.getElementById("weapon-count").textContent = weapons.length;

    if (weapons.length === 0) {
      grid.innerHTML = '<div class="empty-state">No weapons forged yet. Visit the forge!</div>';
      return;
    }
    grid.innerHTML = "";
    for (var i = weapons.length - 1; i >= 0; i--) {
      grid.appendChild(renderWeaponCard(weapons[i]));
    }
  }

  // ── State & message handling ──────────────────────────────────────────

  function onGameState(state) {
    gameState = state;
    if (state.player_state && state.player_state.player_id) {
      playerId = state.player_state.player_id;
    }
    updateEnergy();

    // Check if conjuring/forging completed
    if (conjuring) {
      conjuring = false;
      document.getElementById("conjure-loading").classList.add("hidden");
      document.getElementById("conjure-btn").disabled = false;
    }
    if (forging) {
      forging = false;
      document.getElementById("forge-loading").classList.add("hidden");
      forgeSlots = [null, null, null];
      renderForgeSlots();

      // Show latest weapon as forge result
      var weapons = getWeapons();
      if (weapons.length > 0) {
        var latest = weapons[weapons.length - 1];
        var resultEl = document.getElementById("forge-result");
        resultEl.innerHTML = "";
        resultEl.appendChild(renderWeaponCard(latest));
        resultEl.classList.remove("hidden");
      }
    }

    renderMaterials();
    renderForgeSlots();
    renderWeapons();
  }

  function handleCommandResult(message) {
    var content = message.content || message;
    if (content.game_state) {
      onGameState(content.game_state);
    }

    // Show forge spirit's speech from narrative artifact
    var npcText = null;
    var artifacts = content.artifacts || [];
    for (var i = 0; i < artifacts.length; i++) {
      if (artifacts[i].kind === "narrative" && artifacts[i].payload) {
        npcText = artifacts[i].payload;
        break;
      }
    }
    if (!npcText && content.response) {
      var resp = typeof content.response === "string" ? content.response : content.response.narrative_response;
      if (resp) npcText = resp;
    }

    if (npcText) {
      // Show in the appropriate spirit speech area
      var conjureTab = document.getElementById("tab-conjure");
      var forgeTab = document.getElementById("tab-forge");
      if (conjureTab.classList.contains("active")) {
        document.getElementById("spirit-speech").innerHTML = "<em>" + escapeHtml(npcText) + "</em>";
      } else if (forgeTab.classList.contains("active")) {
        var speechEl = document.getElementById("forge-spirit-speech");
        speechEl.innerHTML = "<em>" + escapeHtml(npcText) + "</em>";
        speechEl.classList.remove("hidden");
      }
    }
  }

  // ── Bridge setup ──────────────────────────────────────────────────────

  function setupBridge() {
    bridge.on("game_start", function (msg) {
      var content = msg.content || {};
      if (content.game_state) onGameState(content.game_state);
    });
    bridge.on("rejoined", function (msg) {
      var content = msg.content || {};
      if (content.game_state) onGameState(content.game_state);
    });
    bridge.on("game_state", function (msg) {
      onGameState(msg.content || msg);
    });
    bridge.on("command_result", function (msg) {
      handleCommandResult(msg);
    });
    bridge.on("stream_end", function (msg) {
      // Narrative may arrive via stream
      if (msg.client_content && msg.client_content.text) {
        var conjureTab = document.getElementById("tab-conjure");
        if (conjureTab.classList.contains("active")) {
          document.getElementById("spirit-speech").innerHTML = "<em>" + escapeHtml(msg.client_content.text) + "</em>";
        }
      }
    });
    bridge.on("event", function (msg) {
      console.log("[ArcaneForge] bridge event:", msg.type, msg);
    });
  }

  // ── Init ──────────────────────────────────────────────────────────────

  function init() {
    bridge = WenyooStorySDK.createBridge();
    setupBridge();
    bridge.requestInitialState();

    // Tabs
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.addEventListener("click", function () { showTab(btn.dataset.tab); });
    });

    // Return to menu
    document.getElementById("return-menu-btn").addEventListener("click", function () {
      bridge.requestReturnToMenu();
    });

    // Conjure
    document.getElementById("conjure-btn").addEventListener("click", conjureMaterial);
    document.getElementById("material-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") conjureMaterial();
    });

    // Forge slots
    for (var i = 0; i < 3; i++) {
      (function (idx) {
        document.getElementById("slot-" + idx).addEventListener("click", function () {
          if (!forgeSlots[idx]) openPicker(idx);
        });
      })(i);
    }

    // Forge button
    document.getElementById("forge-btn").addEventListener("click", activateForge);

    // Picker close
    document.querySelector(".close-modal").addEventListener("click", closePicker);
    document.getElementById("material-picker").addEventListener("click", function (e) {
      if (e.target === this) closePicker();
    });

    renderForgeSlots();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
