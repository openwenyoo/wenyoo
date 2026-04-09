'use strict';

// ──────────────────────────────────────────────────────────────────────────────
// GAME STATE
// ──────────────────────────────────────────────────────────────────────────────
const G = {
  classId: null,
  classConfig: null,
  enemyTheme: null,
  enemies: [],       // array of enemy objects
  player: {
    hp: 0, maxHp: 0, block: 0,
    energy: 3, maxEnergy: 3,
    deck: [], hand: [], discard: [],
    // class mechanics
    charge: 0,
    strength: 0,
    weak: 0,
    vulnerable: 0,
    powerCards: []   // played powers (persist, never discarded)
  },
  targeting: {
    active: false,
    cardIndex: -1    // index into G.player.hand
  },
  turn: 1,
  phase: 'player'   // 'player' | 'animating' | 'enemy' | 'over'
};

const ENEMY_FLOOR_LIMITS = { 1: 2, 2: 2, 3: 3, 4: 1 };

// ──────────────────────────────────────────────────────────────────────────────
// SCREEN MANAGEMENT
// ──────────────────────────────────────────────────────────────────────────────
const SCREENS = {};
['select','loading','combat','reward','victory','defeat'].forEach(name => {
  SCREENS[name] = document.getElementById('screen-' + name);
});

function showScreen(name) {
  Object.values(SCREENS).forEach(el => { el.style.display = 'none'; el.classList.remove('active'); });
  const target = SCREENS[name];
  if (!target) return;
  target.style.display = 'flex';
  requestAnimationFrame(() => requestAnimationFrame(() => target.classList.add('active')));
}

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function clampNumber(value, min, max, fallback) {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.min(max, Math.max(min, num));
}

function sanitizeHexColor(value, fallback) {
  return /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : fallback;
}

function hexToRgba(hex, alpha) {
  const safe = sanitizeHexColor(hex, '#888888');
  const r = parseInt(safe.slice(1, 3), 16);
  const g = parseInt(safe.slice(3, 5), 16);
  const b = parseInt(safe.slice(5, 7), 16);
  const a = clampNumber(alpha, 0, 1, 1);
  return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + a + ')';
}

function getFirstEffectColor(card) {
  const svgEffect = card && card.svg_effect ? card.svg_effect : {};
  const firstLayer = Array.isArray(svgEffect.layers) ? svgEffect.layers.find(layer => layer && layer.color) : null;
  return sanitizeHexColor(svgEffect.accent_color, sanitizeHexColor(firstLayer && firstLayer.color, '#8a7a64'));
}

function inferCardTexture(card, accent) {
  const type = (card && card.type) || '';
  const effects = Array.isArray(card && card.effects) ? card.effects : [];
  if (effects.some(effect => effect.type === 'consume_threads')) return 'threads';
  if (effects.some(effect => effect.type === 'spend_charge')) return 'storm';
  if (effects.some(effect => effect.type === 'self_damage')) return 'veins';
  if (type === 'power') return 'runes';
  if (accent.toLowerCase().startsWith('#cc') || accent.toLowerCase().startsWith('#ff')) return 'embers';
  return 'smoke';
}

function getCardPresentation(card) {
  const frame = (card && card.card_frame) || {};
  const identity = (card && card.visual_identity) || {};
  const raritySignature = (card && card.rarity_signature) || {};
  const baseAccent = getFirstEffectColor(card);
  const accent = sanitizeHexColor(frame.border_color, sanitizeHexColor(identity.accent_color, baseAccent));
  const secondary = sanitizeHexColor(identity.secondary_color, sanitizeHexColor(frame.nameplate_color, lightenColor(accent, 1.22)));
  const bgTop = sanitizeHexColor(frame.bg_top, darkenColor(accent, 0.34));
  const bgBottom = sanitizeHexColor(frame.bg_bottom, darkenColor(secondary, 0.2));
  const glow = sanitizeHexColor(frame.glow_color, accent);
  const texture = frame.texture || inferCardTexture(card, accent);
  const halo = clampNumber(frame.halo, 0, 1, card && card.rarity === 'rare' ? 0.92 : 0.54);
  return {
    accent,
    secondary,
    bgTop,
    bgBottom,
    glow,
    nameplate: sanitizeHexColor(frame.nameplate_color, secondary),
    sigil: escapeHtml(identity.sigil || (card && card.svg_effect && card.svg_effect.rune_glyph) || (card && card.rarity === 'rare' ? '✦' : '✧')),
    motif: escapeHtml(identity.motif || identity.mood || frame.frame_name || ''),
    mood: escapeHtml(identity.mood || ''),
    rhythm: escapeHtml(identity.rhythm || ''),
    frameName: escapeHtml(frame.frame_name || (card && card.rarity === 'rare' ? 'Oracle Artifact' : 'Forged Omen')),
    rareTitle: escapeHtml(raritySignature.title || ''),
    ornament: escapeHtml(raritySignature.ornament || ''),
    texture,
    halo
  };
}

function applyCardPresentation(el, card) {
  const presentation = getCardPresentation(card);
  el.style.setProperty('--card-bg-top', presentation.bgTop);
  el.style.setProperty('--card-bg-bottom', presentation.bgBottom);
  el.style.setProperty('--card-accent', presentation.accent);
  el.style.setProperty('--card-accent-soft', hexToRgba(presentation.accent, 0.18));
  el.style.setProperty('--card-glow', hexToRgba(presentation.glow, 0.4));
  el.style.setProperty('--card-nameplate', hexToRgba(presentation.nameplate, 0.24));
  el.style.setProperty('--card-secondary', presentation.secondary);
  el.style.setProperty('--card-secondary-soft', hexToRgba(presentation.secondary, 0.16));
  el.style.setProperty('--card-halo-strength', String(presentation.halo));
  el.dataset.texture = presentation.texture;
  if (card && card.rarity === 'rare') el.dataset.signature = presentation.rareTitle ? 'true' : 'ornate';
  return presentation;
}

function buildCardMarkup(card, options = {}) {
  const presentation = options.presentation || getCardPresentation(card);
  const typeLabel = escapeHtml((card && card.type ? card.type : '').toUpperCase() + (options.targetHint || ''));
  const rarityLabel = options.showRarity ? ' · ' + escapeHtml(((card && card.rarity) || '').toUpperCase()) : '';
  const identityLine = presentation.motif || presentation.mood || presentation.rhythm;
  const compact = !!options.compact;
  const signatureBlock = options.showSignature && presentation.rareTitle
    ? `<div class="card-signature">${presentation.rareTitle}</div>`
    : '';
  const ornamentBlock = options.showOrnament && presentation.ornament
    ? `<div class="card-ornament">${presentation.ornament}</div>`
    : '';
  const identityRow = compact
    ? `<div class="card-identity-row compact">
         <div class="card-sigil">${presentation.sigil}</div>
         ${presentation.rareTitle ? `<div class="card-mini-tag">${presentation.rareTitle}</div>` : `<div class="card-mini-tag">${typeLabel}${rarityLabel}</div>`}
       </div>`
    : `<div class="card-identity-row">
         <div class="card-sigil">${presentation.sigil}</div>
         <div class="card-frame-name">${presentation.frameName}</div>
       </div>`;
  const compactTypeLine = compact
    ? ''
    : `<div class="card-type-badge ${(card && card.type) || ''}">${typeLabel}${rarityLabel}</div>`;
  const compactMotif = compact || !identityLine
    ? ''
    : `<div class="card-motif">${identityLine}</div>`;
  const flavorBlock = compact
    ? ''
    : (card && card.flavor ? `<div class="card-flavor">${escapeHtml(card.flavor)}</div>` : '');

  return `
    ${identityRow}
    <div class="card-header">
      <div class="card-name">${escapeHtml(card && card.name)}</div>
      <div class="card-cost cost-${card && card.cost || 0}">${escapeHtml(card && card.cost || 0)}</div>
    </div>
    ${compactTypeLine}
    ${compactMotif}
    <div class="card-desc">${escapeHtml(card && card.description)}</div>
    ${signatureBlock}
    ${ornamentBlock}
    ${flavorBlock}
  `;
}

function sanitizeRgbaColor(value, fallback) {
  return /^rgba?\(\s*(\d{1,3}\s*,\s*){2}\d{1,3}(\s*,\s*(0|0?\.\d+|1(\.0)?))?\s*\)$/i.test(value || '') ? value : fallback;
}

const ENEMY_SVG_ALLOWED_TAGS = new Set(['g', 'path', 'circle', 'ellipse', 'rect', 'polygon', 'polyline', 'line', 'text']);
const ENEMY_SVG_COLOR_RE = /^(#[0-9a-fA-F]{3,8}|rgba?\([\d\s.,%]+\)|hsla?\([\d\s.,%]+\)|none|currentColor)$/i;
const ENEMY_SVG_NUMBER_RE = /^-?\d+(\.\d+)?%?$/;
const ENEMY_SVG_TRANSFORM_RE = /^[a-zA-Z0-9(),.\-\s]+$/;
const ENEMY_SVG_PATH_RE = /^[MmLlHhVvCcSsQqTtAaZz0-9,\.\-\s]+$/;
const ENEMY_SVG_POINTS_RE = /^[-0-9.,\s]+$/;

function _sanitizeEnemySvgAttr(name, value) {
  const text = String(value == null ? '' : value).trim();
  if (!text) return null;

  if (['fill', 'stroke'].includes(name)) {
    return ENEMY_SVG_COLOR_RE.test(text) ? text : null;
  }
  if (['opacity', 'fill-opacity', 'stroke-opacity'].includes(name)) {
    const num = clampNumber(text, 0, 1, null);
    return num == null ? null : String(num);
  }
  if (['stroke-width', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height', 'x1', 'y1', 'x2', 'y2', 'font-size'].includes(name)) {
    return ENEMY_SVG_NUMBER_RE.test(text) ? text : null;
  }
  if (name === 'transform') {
    return text.length <= 120 && ENEMY_SVG_TRANSFORM_RE.test(text) ? text : null;
  }
  if (name === 'd') {
    return text.length <= 900 && ENEMY_SVG_PATH_RE.test(text) ? text : null;
  }
  if (name === 'points') {
    return text.length <= 500 && ENEMY_SVG_POINTS_RE.test(text) ? text : null;
  }
  if (name === 'text-anchor' || name === 'dominant-baseline') {
    return /^[a-z-]+$/i.test(text) ? text : null;
  }
  return null;
}

function sanitizeEnemySvgFragment(rawSvg) {
  if (typeof rawSvg !== 'string') return null;
  const trimmed = rawSvg.trim();
  if (!trimmed || trimmed.length > 5000 || typeof DOMParser === 'undefined') return null;

  const source = /^<svg[\s>]/i.test(trimmed)
    ? trimmed
    : '<svg xmlns="http://www.w3.org/2000/svg">' + trimmed + '</svg>';
  const parser = new DOMParser();
  const doc = parser.parseFromString(source, 'image/svg+xml');
  const root = doc && doc.documentElement;
  if (!root || /parsererror/i.test(root.nodeName)) return null;

  const sourceRoot = root.nodeName.toLowerCase() === 'svg' ? root : doc.querySelector('svg');
  if (!sourceRoot) return null;

  let nodeCount = 0;
  const cleanDoc = document.implementation.createDocument('http://www.w3.org/2000/svg', 'svg', null);
  const cleanRoot = cleanDoc.documentElement;

  function cloneNode(node, parentTag) {
    if (nodeCount > 36) return null;
    if (node.nodeType === 3) {
      if (parentTag !== 'text') return null;
      const text = String(node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 8);
      return text ? cleanDoc.createTextNode(text) : null;
    }
    if (node.nodeType !== 1) return null;

    const tag = node.nodeName.toLowerCase();
    if (!ENEMY_SVG_ALLOWED_TAGS.has(tag)) return null;
    nodeCount++;

    const el = cleanDoc.createElementNS('http://www.w3.org/2000/svg', tag);
    Array.from(node.attributes || []).forEach((attr) => {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on') || name === 'style' || name === 'href' || name === 'xlink:href') return;
      const safeValue = _sanitizeEnemySvgAttr(name, attr.value);
      if (safeValue != null) el.setAttribute(name, safeValue);
    });

    Array.from(node.childNodes || []).forEach((child) => {
      const cleanChild = cloneNode(child, tag);
      if (cleanChild) el.appendChild(cleanChild);
    });
    return el;
  }

  Array.from(sourceRoot.childNodes || []).forEach((child) => {
    const cleanChild = cloneNode(child, 'svg');
    if (cleanChild) cleanRoot.appendChild(cleanChild);
  });

  if (!cleanRoot.childNodes.length) return null;
  return Array.from(cleanRoot.childNodes).map((node) => new XMLSerializer().serializeToString(node)).join('');
}

function getEnemySpriteMarkup(enemy) {
  const generated = sanitizeEnemySvgFragment(enemy && enemy.spriteSvg);
  if (generated) return generated;

  const color = sanitizeHexColor(enemy && enemy.color, '#888888');
  const lc = lightenColor(color, 1.4);
  const spriteShape = SPRITE_SHAPES[(enemy && enemy.spriteType) || 'generic'] || SPRITE_SHAPES.generic;
  return spriteShape(color, lc);
}

// ──────────────────────────────────────────────────────────────────────────────
// COMBAT INIT (called by map.js)
// ──────────────────────────────────────────────────────────────────────────────
function initCombat(floor, classId, classConfig, enemyConfigs, persistedHp, enemyTheme) {
  G.classId = classId;
  G.classConfig = classConfig;
  G.enemyTheme = enemyTheme || null;

  const floorKey = 'floor_' + floor;
  const floorEnemies = ((enemyConfigs && enemyConfigs[floorKey]) || []).slice(0, ENEMY_FLOOR_LIMITS[floor] || 3);

  // Build enemy objects
  G.enemies = floorEnemies.map(cfg => {
    const phases = cfg.phases || null;
    const aiCycle = phases ? phases[0].ai_cycle : (cfg.ai_cycle || [{type:'attack',value:8}]);
    return {
      id: cfg.id,
      name: cfg.name,
      role: cfg.role || 'enemy',
      traitName: cfg.trait_name || '',
      hp: clampNumber(cfg.hp, 1, 999, 24),
      maxHp: clampNumber(cfg.hp, 1, 999, 24),
      block: 0,
      infection: 0,
      threads: 0,
      weak: 0,
      vulnerable: 0,
      strength: 0,
      alive: true,
      spriteType: cfg.sprite_type || 'generic',
      spriteSvg: cfg.sprite_svg || '',
      color: sanitizeHexColor(cfg.color, '#888888'),
      glow: sanitizeRgbaColor(cfg.glow, 'rgba(136,136,136,0.5)'),
      aiCycle: aiCycle,
      aiTurn: 0,
      phaseIndex: 0,
      phases: phases,
      intent: null
    };
  });

  // Player hp: use persisted or class default
  const hp = (persistedHp != null && persistedHp > 0) ? persistedHp : classConfig.hp;
  G.player.hp = hp;
  G.player.maxHp = classConfig.hp;
  G.player.block = 0;
  G.player.energy = 3;
  G.player.maxEnergy = 3;
  G.player.charge = 0;
  G.player.strength = 0;
  G.player.weak = 0;
  G.player.vulnerable = 0;
  G.player.powerCards = [];
  G.player.hand = [];
  G.player.discard = [];
  // deck is set externally by map.js via setCombatDeck()

  G.turn = 1;
  G.phase = 'player';
  G.targeting = { active: false, cardIndex: -1 };

  // Compute initial intents
  G.enemies.forEach(e => { e.intent = computeEnemyIntent(e, G.turn); });

  // Build enemy UI
  buildEnemyArea();
  setupCombatButtons();
  updateFloorBadge(floor);

  if (classId === 'storm_caller') G.player.charge += 1;

  drawCards(5);
  render();
}

function setCombatDeck(deckCards) {
  G.player.deck = deckCards.map(c => ({ ...c }));
  shuffle(G.player.deck);
}

// ──────────────────────────────────────────────────────────────────────────────
// ENEMY AREA BUILDING
// ──────────────────────────────────────────────────────────────────────────────
const SPRITE_SHAPES = {
  blob: (color, lc) => `
    <ellipse cx="60" cy="70" rx="45" ry="40" fill="${color}" filter="url(#eg)"/>
    <ellipse cx="60" cy="60" rx="35" ry="30" fill="${lc}" opacity="0.6"/>
    <circle cx="48" cy="54" r="7" fill="#fff" opacity="0.9"/><circle cx="50" cy="54" r="4" fill="#111"/>
    <circle cx="72" cy="54" r="7" fill="#fff" opacity="0.9"/><circle cx="74" cy="54" r="4" fill="#111"/>
    <path d="M50,72 Q60,80 70,72" stroke="${lc}" stroke-width="2" fill="none"/>`,
  humanoid: (color, lc) => `
    <rect x="30" y="55" width="60" height="60" rx="5" fill="${color}" filter="url(#eg)"/>
    <ellipse cx="60" cy="45" rx="24" ry="26" fill="${lc}" filter="url(#eg)"/>
    <circle cx="51" cy="40" r="5" fill="#fff" opacity="0.9"/><circle cx="53" cy="40" r="3" fill="#111"/>
    <circle cx="69" cy="40" r="5" fill="#fff" opacity="0.9"/><circle cx="71" cy="40" r="3" fill="#111"/>
    <path d="M52,55 Q60,62 68,55" stroke="${lc}" stroke-width="2" fill="none"/>`,
  robed: (color, lc) => `
    <path d="M30,120 Q28,80 60,70 Q92,80 90,120 Z" fill="${color}" filter="url(#eg)"/>
    <ellipse cx="60" cy="55" rx="22" ry="24" fill="${lc}" filter="url(#eg)"/>
    <circle cx="52" cy="50" r="5" fill="${lc}" opacity="0.9"/><circle cx="68" cy="50" r="5" fill="${lc}" opacity="0.9"/>
    <path d="M53,64 Q60,70 67,64" stroke="${color}" stroke-width="2" fill="none"/>`,
  armored: (color, lc) => `
    <rect x="25" y="50" width="70" height="70" rx="4" fill="${color}" filter="url(#eg)"/>
    <rect x="32" y="58" width="56" height="56" rx="3" fill="${lc}" opacity="0.5"/>
    <ellipse cx="60" cy="40" rx="20" ry="22" fill="${color}" filter="url(#eg)"/>
    <circle cx="52" cy="36" r="5" fill="#fff" opacity="0.8"/><circle cx="54" cy="36" r="3" fill="#222"/>
    <circle cx="68" cy="36" r="5" fill="#fff" opacity="0.8"/><circle cx="70" cy="36" r="3" fill="#222"/>`,
  mage: (color, lc) => `
    <ellipse cx="60" cy="85" rx="35" ry="42" fill="${color}" filter="url(#eg)"/>
    <ellipse cx="60" cy="45" rx="20" ry="22" fill="${lc}" filter="url(#eg)"/>
    <polygon points="60,5 75,30 45,30" fill="${lc}" opacity="0.9"/>
    <circle cx="52" cy="40" r="5" fill="${lc}" opacity="0.9"/><circle cx="68" cy="40" r="5" fill="${lc}" opacity="0.9"/>
    <circle cx="60" cy="80" r="8" fill="${lc}" opacity="0.6" filter="url(#eg)"/>`,
  boss: (color, lc) => `
    <ellipse cx="60" cy="90" rx="52" ry="56" fill="${color}" filter="url(#eg)"/>
    <ellipse cx="60" cy="78" rx="40" ry="44" fill="${lc}" opacity="0.5"/>
    <circle cx="44" cy="68" r="10" fill="#fff" opacity="0.85"/><circle cx="47" cy="66" r="6" fill="#111"/>
    <circle cx="76" cy="68" r="10" fill="#fff" opacity="0.85"/><circle cx="79" cy="66" r="6" fill="#111"/>
    <path d="M44,92 Q60,106 76,92" stroke="${lc}" stroke-width="3" fill="none"/>
    <path d="M20,50 Q10,30 28,20 Q36,42 48,50" fill="${lc}" opacity="0.7"/>
    <path d="M100,50 Q110,30 92,20 Q84,42 72,50" fill="${lc}" opacity="0.7"/>`,
  generic: (color, lc) => `
    <ellipse cx="60" cy="80" rx="42" ry="48" fill="${color}" filter="url(#eg)"/>
    <circle cx="48" cy="68" r="7" fill="#fff" opacity="0.8"/><circle cx="50" cy="68" r="4" fill="#222"/>
    <circle cx="72" cy="68" r="7" fill="#fff" opacity="0.8"/><circle cx="74" cy="68" r="4" fill="#222"/>`
};

function buildEnemyArea() {
  const area = document.getElementById('combat-enemy-area');
  area.innerHTML = '';

  G.enemies.forEach(enemy => {
    const unit = document.createElement('div');
    unit.className = 'enemy-unit' + (enemy.spriteType === 'boss' ? ' boss-unit' : '');
    unit.dataset.enemyId = enemy.id;

    // Sprite SVG
    const svgSize = enemy.spriteType === 'boss' ? 160 : 120;
    const floorTrait = enemy.traitName || (G.enemyTheme && G.enemyTheme.session_trait) || enemy.role;

    const spriteDiv = document.createElement('div');
    spriteDiv.innerHTML = `
      <svg class="enemy-sprite" width="${svgSize}" height="${svgSize}" viewBox="0 0 120 120"
           style="--sprite-glow:${enemy.glow}">
        <defs>
          <filter id="eg" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <radialGradient id="eg-grad-${enemy.id}" cx="40%" cy="35%" r="65%">
            <stop offset="0%" stop-color="${lightenColor(enemy.color, 1.4)}"/><stop offset="100%" stop-color="${darkenColor(enemy.color, 0.5)}"/>
          </radialGradient>
        </defs>
        ${getEnemySpriteMarkup(enemy)}
      </svg>`;
    unit.appendChild(spriteDiv.firstElementChild);

    // Info
    const info = document.createElement('div');
    info.className = 'enemy-info';
    info.innerHTML = `
      <div class="enemy-trait-row">
        <div class="enemy-trait-badge">${escapeHtml(floorTrait)}</div>
        ${enemy.phases ? `<div class="boss-phase-badge" id="ephase-${enemy.id}">Phase 1</div>` : ''}
      </div>
      <div class="enemy-name-row">
        <div class="enemy-name">${escapeHtml(enemy.name)}</div>
        <div class="enemy-block-badge" id="eblock-${enemy.id}" style="display:none">🛡 <span id="eblockval-${enemy.id}">0</span></div>
      </div>
      <div class="enemy-role">${escapeHtml(enemy.role)}</div>
      <div class="enemy-hp-wrap">
        <div class="enemy-hp-bar" id="ehp-bar-${enemy.id}" style="width:100%"></div>
        <span class="enemy-hp-text" id="ehp-text-${enemy.id}">${enemy.hp}/${enemy.maxHp}</span>
      </div>
      <div class="enemy-status-row" id="estatus-${enemy.id}"></div>
      <div class="enemy-intent" id="eintent-${enemy.id}">
        <span class="intent-icon" id="eintent-icon-${enemy.id}">⚔️</span>
        <span id="eintent-text-${enemy.id}">...</span>
      </div>`;
    unit.appendChild(info);

    // Click handler for targeting
    unit.addEventListener('click', () => {
      if (G.targeting.active && enemy.alive) {
        resolveCardOnTarget(G.targeting.cardIndex, enemy.id);
      }
    });

    area.appendChild(unit);
  });
}

function setupCombatButtons() {
  const endBtn = document.getElementById('btn-end-turn');
  endBtn.disabled = false;
  endBtn.onclick = () => { if (G.phase === 'player') endTurn(); };

  const deckBtn = document.getElementById('btn-view-deck');
  deckBtn.onclick = showDeckModal;

  document.getElementById('btn-close-modal').onclick = () => {
    document.getElementById('deck-modal').style.display = 'none';
  };

  // ESC to cancel targeting
  document.onkeydown = (e) => {
    if (e.key === 'Escape' && G.targeting.active) cancelTargeting();
  };
}

function updateFloorBadge(floor) {
  document.getElementById('floor-label').textContent = 'Floor ' + floor + '/4';
  const dotsEl = document.getElementById('floor-dots');
  dotsEl.innerHTML = '';
  for (let i = 1; i <= 4; i++) {
    const dot = document.createElement('div');
    dot.className = 'floor-dot' + (i < floor ? ' done' : i === floor ? ' current' : '') + (i === 4 ? ' boss' : '');
    dotsEl.appendChild(dot);
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// DECK HELPERS
// ──────────────────────────────────────────────────────────────────────────────
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

function drawCards(n) {
  for (let i = 0; i < n; i++) {
    if (G.player.deck.length === 0) {
      if (G.player.discard.length === 0) break;
      G.player.deck = [...G.player.discard];
      G.player.discard = [];
      shuffle(G.player.deck);
    }
    if (G.player.deck.length > 0) G.player.hand.push(G.player.deck.shift());
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// TARGETING
// ──────────────────────────────────────────────────────────────────────────────
function enterTargetingMode(cardIndex) {
  G.targeting = { active: true, cardIndex };
  // Highlight targetable enemies
  document.querySelectorAll('.enemy-unit').forEach(unit => {
    const eid = unit.dataset.enemyId;
    const enemy = G.enemies.find(e => e.id === eid);
    if (enemy && enemy.alive) unit.classList.add('targetable');
  });
  // Highlight the source card
  const handCards = document.querySelectorAll('.hand-card');
  if (handCards[cardIndex]) handCards[cardIndex].classList.add('targeting-source');
  document.getElementById('targeting-hint').style.display = 'flex';
}

function cancelTargeting() {
  G.targeting = { active: false, cardIndex: -1 };
  document.querySelectorAll('.enemy-unit').forEach(u => u.classList.remove('targetable'));
  document.querySelectorAll('.hand-card').forEach(c => c.classList.remove('targeting-source'));
  document.getElementById('targeting-hint').style.display = 'none';
}

// ──────────────────────────────────────────────────────────────────────────────
// PLAY CARD
// ──────────────────────────────────────────────────────────────────────────────
function canPlayCard(card) {
  if (G.phase !== 'player') return false;
  if (G.player.energy < card.cost) return false;
  return true;
}

function onCardClick(cardIndex) {
  if (G.targeting.active) {
    // Second click on same card = cancel
    if (cardIndex === G.targeting.cardIndex) { cancelTargeting(); return; }
    return; // Click on different card while targeting = ignore
  }
  const card = G.player.hand[cardIndex];
  if (!card || !canPlayCard(card)) return;

  const target = (card.svg_effect && card.svg_effect.target) || 'single';

  if (target === 'self' || target === 'all') {
    // Auto-resolve — no targeting needed
    const aliveEnemy = G.enemies.find(e => e.alive);
    resolveCardOnTarget(cardIndex, aliveEnemy ? aliveEnemy.id : null);
  } else {
    // single or random — enter targeting mode
    const aliveEnemies = G.enemies.filter(e => e.alive);
    if (aliveEnemies.length === 1) {
      // Only one enemy alive — auto-target
      resolveCardOnTarget(cardIndex, aliveEnemies[0].id);
    } else {
      enterTargetingMode(cardIndex);
    }
  }
}

async function resolveCardOnTarget(cardIndex, targetEnemyId) {
  const card = G.player.hand[cardIndex];
  if (!card || !canPlayCard(card)) { cancelTargeting(); return; }

  cancelTargeting();
  G.phase = 'animating';
  G.player.energy -= card.cost;
  G.player.hand.splice(cardIndex, 1);
  render();

  // Play SVG effect
  if (card.svg_effect) {
    await FX.playEffect(card, targetEnemyId);
  }

  // Trigger hit animation on targeted enemy
  const cardTarget = (card.svg_effect && card.svg_effect.target) || 'single';
  const hasAttack = (card.effects || []).some(e =>
    ['damage','aoe_damage','consume_threads','spend_charge'].includes(e.type)
  );
  if (hasAttack) {
    if (cardTarget === 'all') {
      G.enemies.filter(e => e.alive).forEach(e => flashEnemyHit(e.id));
    } else if (targetEnemyId) {
      flashEnemyHit(targetEnemyId);
    }
  }

  applyEffects(card.effects || [], card, targetEnemyId);

  // Powers are played to powerCards, not discarded
  if (card.type === 'power') {
    G.player.powerCards.push(card);
  } else {
    G.player.discard.push(card);
  }

  // Remove dead enemies
  G.enemies.forEach(e => {
    if (e.alive && e.hp <= 0) { e.alive = false; markEnemyDead(e.id); }
  });

  const winner = checkWin();
  if (winner) { G.phase = 'over'; render(); handleGameOver(winner); return; }

  G.phase = 'player';
  render();
}

function flashEnemyHit(enemyId) {
  const unit = document.querySelector(`.enemy-unit[data-enemy-id="${enemyId}"]`);
  const sprite = unit && unit.querySelector('.enemy-sprite');
  if (!sprite) return;
  sprite.classList.remove('taking-hit');
  void sprite.offsetWidth; // reflow
  sprite.classList.add('taking-hit');
  setTimeout(() => sprite.classList.remove('taking-hit'), 400);
}

function markEnemyDead(enemyId) {
  const unit = document.querySelector(`.enemy-unit[data-enemy-id="${enemyId}"]`);
  if (unit) unit.classList.add('dead');
}

function applyPlayerAttackModifiers(baseDamage, enemy) {
  let dmg = Math.max(0, (baseDamage || 0) + (G.player.strength || 0));
  if (G.player.weak > 0) dmg = Math.floor(dmg * 0.75);
  if (enemy && enemy.vulnerable > 0) dmg = Math.floor(dmg * 1.5);
  return dmg;
}

function chooseEnemyTarget(sourceEnemy, mode) {
  const aliveEnemies = G.enemies.filter(e => e.alive);
  if (mode === 'self') return sourceEnemy;
  const allies = aliveEnemies.filter(e => e.id !== sourceEnemy.id);
  if (mode === 'ally') return allies[0] || sourceEnemy;
  return null;
}

function applyStatusToPlayer(status, val) {
  const amount = Math.max(0, val || 0);
  if (status === 'weak') G.player.weak += amount;
  else if (status === 'vulnerable') G.player.vulnerable += amount;
  else if (status === 'strength') G.player.strength += amount;
}

function describeIntent(enemy, intent) {
  if (!intent) return { icon: '…', text: 'Preparing', className: 'intent-buff' };

  if (intent.type === 'attack') {
    let dmg = (intent.value || 0) + (enemy.strength || 0);
    if (enemy.weak > 0) dmg = Math.floor(dmg * 0.75);
    return { icon: '⚔️', text: 'Attack ' + dmg, className: 'intent-attack' };
  }
  if (intent.type === 'attack_all') {
    let dmg = (intent.value || 0) + (enemy.strength || 0);
    if (enemy.weak > 0) dmg = Math.floor(dmg * 0.75);
    return { icon: '💥', text: 'AoE ' + dmg, className: 'intent-aoe' };
  }
  if (intent.type === 'defend') {
    return { icon: '🛡️', text: 'Block +' + (intent.value || 0), className: 'intent-defend' };
  }
  if (intent.type === 'buff_self') {
    return { icon: '⬆️', text: 'Self +' + (intent.value || 0) + ' ' + (intent.status || 'strength'), className: 'intent-buff' };
  }
  if (intent.type === 'buff_ally') {
    return { icon: '✨', text: 'Buff Ally +' + (intent.value || 0), className: 'intent-buff' };
  }
  if (intent.type === 'apply_status') {
    const target = intent.target === 'player' ? 'Inflict' : intent.target === 'ally' ? 'Grant Ally' : 'Grant Self';
    return { icon: '☄️', text: target + ' ' + (intent.value || 0) + ' ' + (intent.status || 'status'), className: 'intent-debuff' };
  }
  return { icon: '…', text: 'Prepare', className: 'intent-buff' };
}

// ──────────────────────────────────────────────────────────────────────────────
// EFFECT RESOLUTION
// ──────────────────────────────────────────────────────────────────────────────
function applyEffects(effects, card, targetEnemyId) {
  const cardTarget = (card && card.svg_effect && card.svg_effect.target) || 'single';

  effects.forEach(effect => {
    switch (effect.type) {
      case 'damage': {
        const enemy = G.enemies.find(e => e.id === targetEnemyId && e.alive);
        if (enemy) {
          dealDamageToEnemy(applyPlayerAttackModifiers(effect.value || 0, enemy), enemy);
        }
        break;
      }
      case 'aoe_damage': {
        G.enemies.filter(e => e.alive).forEach(enemy => {
          dealDamageToEnemy(applyPlayerAttackModifiers(effect.value || 0, enemy), enemy);
        });
        break;
      }
      case 'block':
        G.player.block += (effect.value || 0);
        break;
      case 'apply_status': {
        const status = effect.status;
        const val = effect.value || 1;
        const t = effect.target || 'enemy';
        if (t === 'enemy') {
          if (cardTarget === 'all') {
            G.enemies.filter(e => e.alive).forEach(e => applyStatusToEnemy(e, status, val));
          } else {
            const enemy = G.enemies.find(e => e.id === targetEnemyId && e.alive);
            if (enemy) applyStatusToEnemy(enemy, status, val);
          }
        } else {
          // self
          if (status === 'strength') G.player.strength += val;
          else if (status === 'charge') G.player.charge += val;
        }
        break;
      }
      case 'draw':
        drawCards(effect.value || 1);
        break;
      case 'gain_energy':
        G.player.energy = Math.min(G.player.maxEnergy + 1, G.player.energy + (effect.value || 1));
        break;
      case 'heal':
        G.player.hp = Math.min(G.player.maxHp, G.player.hp + (effect.value || 0));
        break;
      case 'self_damage': {
        const dmg = effect.value || 0;
        G.player.hp -= dmg;
        document.querySelector('.combat-player-area')?.classList.add('player-hit-flash');
        setTimeout(() => document.querySelector('.combat-player-area')?.classList.remove('player-hit-flash'), 400);
        break;
      }
      case 'consume_threads': {
        // Target specific enemy's threads
        if (cardTarget === 'all') {
          G.enemies.filter(e => e.alive).forEach(enemy => {
            if (enemy.threads > 0) {
              dealDamageToEnemy(applyPlayerAttackModifiers((effect.bonus_damage || 0) * enemy.threads, enemy), enemy);
              enemy.threads = 0;
            }
          });
        } else {
          const enemy = G.enemies.find(e => e.id === targetEnemyId && e.alive);
          if (enemy && enemy.threads > 0) {
            dealDamageToEnemy(applyPlayerAttackModifiers((effect.bonus_damage || 0) * enemy.threads, enemy), enemy);
            enemy.threads = 0;
          }
        }
        break;
      }
      case 'spend_charge': {
        const charge = G.player.charge;
        if (charge > 0) {
          if (cardTarget === 'all') {
            G.enemies.filter(e => e.alive).forEach(enemy => {
              dealDamageToEnemy(applyPlayerAttackModifiers((effect.damage_per_charge || 0) * charge, enemy), enemy);
            });
          } else {
            const enemy = G.enemies.find(e => e.id === targetEnemyId && e.alive);
            if (enemy) {
              dealDamageToEnemy(applyPlayerAttackModifiers((effect.damage_per_charge || 0) * charge, enemy), enemy);
            }
          }
          G.player.charge = 0;
        }
        break;
      }
      default: break;
    }
  });
}

function applyStatusToEnemy(enemy, status, val) {
  if (status === 'infection') enemy.infection = (enemy.infection || 0) + val;
  else if (status === 'threads') enemy.threads = (enemy.threads || 0) + val;
  else if (status === 'weak') enemy.weak = (enemy.weak || 0) + val;
  else if (status === 'vulnerable') enemy.vulnerable = (enemy.vulnerable || 0) + val;
  else if (status === 'strength') enemy.strength = (enemy.strength || 0) + val;
}

function dealDamageToEnemy(dmg, enemy) {
  if (!enemy || dmg <= 0) return;
  if (enemy.block > 0) {
    const blocked = Math.min(enemy.block, dmg);
    enemy.block -= blocked;
    dmg -= blocked;
  }
  enemy.hp = Math.max(0, enemy.hp - dmg);
}

function dealDamageToPlayer(dmg) {
  if (dmg <= 0) return;
  if (G.player.vulnerable > 0) dmg = Math.floor(dmg * 1.5);
  if (G.player.block > 0) {
    const blocked = Math.min(G.player.block, dmg);
    G.player.block -= blocked;
    dmg -= blocked;
  }
  if (dmg > 0) {
    G.player.hp = Math.max(0, G.player.hp - dmg);
    document.querySelector('.combat-player-area')?.classList.add('player-hit-flash');
    setTimeout(() => document.querySelector('.combat-player-area')?.classList.remove('player-hit-flash'), 400);
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// ENEMY AI
// ──────────────────────────────────────────────────────────────────────────────
function computeEnemyIntent(enemy, turn) {
  // Boss phase transitions
  if (enemy.phases) {
    const hpPct = enemy.hp / enemy.maxHp;
    let newPhaseIndex = 0;
    for (let i = enemy.phases.length - 1; i >= 0; i--) {
      if (hpPct <= enemy.phases[i].threshold) { newPhaseIndex = i; break; }
    }
    if (newPhaseIndex !== enemy.phaseIndex) {
      enemy.phaseIndex = newPhaseIndex;
      enemy.aiCycle = enemy.phases[newPhaseIndex].ai_cycle;
    }
  }

  const idx = enemy.aiTurn % enemy.aiCycle.length;
  return { ...enemy.aiCycle[idx] };
}

async function enemyAct() {
  const aliveEnemies = G.enemies.filter(e => e.alive);

  for (const enemy of aliveEnemies) {
    const intent = enemy.intent;
    if (!intent) continue;

    if (intent.type === 'attack') {
      let dmg = intent.value;
      if (enemy.weak > 0) dmg = Math.floor(dmg * 0.75);
      dmg += (enemy.strength || 0);
      dealDamageToPlayer(dmg);
    } else if (intent.type === 'attack_all') {
      let dmg = intent.value;
      if (enemy.weak > 0) dmg = Math.floor(dmg * 0.75);
      dmg += (enemy.strength || 0);
      dealDamageToPlayer(dmg);
    } else if (intent.type === 'defend') {
      enemy.block += intent.value;
    } else if (intent.type === 'buff_self') {
      applyStatusToEnemy(enemy, intent.status || 'strength', intent.value || 1);
    } else if (intent.type === 'buff_ally') {
      const target = chooseEnemyTarget(enemy, 'ally');
      if (target) applyStatusToEnemy(target, intent.status || 'strength', intent.value || 1);
    } else if (intent.type === 'apply_status') {
      if (intent.target === 'player') {
        applyStatusToPlayer(intent.status || 'weak', intent.value || 1);
      } else {
        const target = chooseEnemyTarget(enemy, intent.target === 'ally' ? 'ally' : 'self');
        if (target) applyStatusToEnemy(target, intent.status || 'strength', intent.value || 1);
      }
    }

    // Advance AI turn counter
    enemy.aiTurn++;

    // Decrement status effects
    if (enemy.weak > 0) enemy.weak--;
    if (enemy.vulnerable > 0) enemy.vulnerable--;

    await delay(150); // small delay between enemies acting
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// TURN FLOW
// ──────────────────────────────────────────────────────────────────────────────
async function endTurn() {
  if (G.phase !== 'player') return;
  G.phase = 'enemy';
  document.getElementById('btn-end-turn').disabled = true;

  // Discard hand (power cards stay in powerCards, not discarded again)
  G.player.discard.push(...G.player.hand);
  G.player.hand = [];

  // Infection damage (Plague Doctor) — fires before enemy acts
  if (G.classId === 'plague_doctor') {
    G.enemies.filter(e => e.alive && e.infection > 0).forEach(enemy => {
      enemy.hp = Math.max(0, enemy.hp - enemy.infection);
      if (enemy.hp <= 0) { enemy.alive = false; markEnemyDead(enemy.id); }
    });
    render();
    await delay(300);

    const winner = checkWin();
    if (winner) { G.phase = 'over'; render(); handleGameOver(winner); return; }
  }

  render();
  await delay(400);

  // Enemy acts
  await enemyAct();
  render();
  await delay(300);

  const winner = checkWin();
  if (winner) { G.phase = 'over'; render(); handleGameOver(winner); return; }

  startTurn();
}

function startTurn() {
  G.turn++;
  G.player.block = 0;
  G.player.energy = G.player.maxEnergy;
  if (G.player.weak > 0) G.player.weak--;
  if (G.player.vulnerable > 0) G.player.vulnerable--;

  // Class mechanics: Storm Caller gains charge
  if (G.classId === 'storm_caller') G.player.charge += 1;

  // Power card effects (apply_status with target self, once per turn)
  G.player.powerCards.forEach(power => {
    (power.effects || []).forEach(eff => {
      if (eff.type === 'apply_status' && eff.target === 'self') {
        if (eff.status === 'strength') G.player.strength += (eff.value || 1);
        else if (eff.status === 'charge') G.player.charge += (eff.value || 1);
      } else if (eff.type === 'apply_status' && eff.target === 'enemy') {
        // Virulence-type: apply to all enemies
        G.enemies.filter(e => e.alive).forEach(e => applyStatusToEnemy(e, eff.status, eff.value || 1));
      }
    });
  });

  // Recompute intents for alive enemies
  G.enemies.filter(e => e.alive).forEach(e => {
    e.intent = computeEnemyIntent(e, G.turn);
  });

  drawCards(5);
  G.phase = 'player';
  document.getElementById('btn-end-turn').disabled = false;
  render();
}

// ──────────────────────────────────────────────────────────────────────────────
// WIN CONDITION
// ──────────────────────────────────────────────────────────────────────────────
function checkWin() {
  if (G.enemies.every(e => !e.alive)) return 'player';
  if (G.player.hp <= 0) return 'enemy';
  return null;
}

function handleGameOver(winner) {
  // Delegate to map.js
  if (winner === 'player') {
    onCombatWon(G.player.hp);
  } else {
    onCombatLost();
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// RENDER
// ──────────────────────────────────────────────────────────────────────────────
function render() {
  renderEnemies();
  renderPlayer();
  renderEnergyOrbs();
  renderMechanicDisplay();
  renderHand();
  renderDeckInfo();
}

function renderEnemies() {
  G.enemies.forEach(enemy => {
    const hpBar = document.getElementById('ehp-bar-' + enemy.id);
    const hpText = document.getElementById('ehp-text-' + enemy.id);
    if (hpBar) hpBar.style.width = Math.max(0, (enemy.hp / enemy.maxHp) * 100) + '%';
    if (hpText) hpText.textContent = Math.max(0, enemy.hp) + '/' + enemy.maxHp;

    const blockBadge = document.getElementById('eblock-' + enemy.id);
    const blockVal = document.getElementById('eblockval-' + enemy.id);
    if (blockBadge) {
      blockBadge.style.display = enemy.block > 0 ? 'flex' : 'none';
      if (blockVal) blockVal.textContent = enemy.block;
    }

    const statusRow = document.getElementById('estatus-' + enemy.id);
    if (statusRow) {
      statusRow.innerHTML = '';
      if (enemy.infection > 0) statusRow.appendChild(makeStatusBadge('infection', '☣', enemy.infection));
      if (enemy.threads > 0) statusRow.appendChild(makeStatusBadge('threads', '🕸', enemy.threads));
      if (enemy.weak > 0) statusRow.appendChild(makeStatusBadge('weak', '↓', enemy.weak));
      if (enemy.vulnerable > 0) statusRow.appendChild(makeStatusBadge('vulnerable', '⚠', enemy.vulnerable));
      if (enemy.strength > 0) statusRow.appendChild(makeStatusBadge('strength', '⬆', enemy.strength));
    }

    const intentEl = document.getElementById('eintent-' + enemy.id);
    const intentIcon = document.getElementById('eintent-icon-' + enemy.id);
    const intentText = document.getElementById('eintent-text-' + enemy.id);
    if (intentEl && enemy.alive && enemy.intent) {
      const preview = describeIntent(enemy, enemy.intent);
      if (intentIcon) { intentIcon.textContent = preview.icon; intentIcon.className = 'intent-icon ' + preview.className; }
      if (intentText) { intentText.textContent = preview.text; intentText.className = preview.className; }
    }

    const phaseBadge = document.getElementById('ephase-' + enemy.id);
    if (phaseBadge && enemy.phases) {
      const activePhase = enemy.phases[enemy.phaseIndex] || {};
      phaseBadge.textContent = activePhase.phase_name || ('Phase ' + (enemy.phaseIndex + 1));
    }
  });
}

function makeStatusBadge(type, icon, count) {
  const span = document.createElement('span');
  span.className = 'status-badge ' + type;
  span.textContent = icon + ' ' + count;
  return span;
}

function renderPlayer() {
  const { player } = G;
  const pct = Math.max(0, (player.hp / player.maxHp) * 100);
  document.getElementById('player-hp-bar').style.width = pct + '%';
  document.getElementById('player-hp-text').textContent = Math.max(0, player.hp) + '/' + player.maxHp;

  const blockBadge = document.getElementById('player-block-badge');
  if (blockBadge) {
    blockBadge.style.display = player.block > 0 ? 'flex' : 'none';
    const bv = document.getElementById('player-block-val');
    if (bv) bv.textContent = player.block;
  }
  const ti = document.getElementById('turn-info');
  if (ti) ti.textContent = 'Turn ' + G.turn;
}

function renderEnergyOrbs() {
  const orbs = document.getElementById('energy-orbs');
  if (!orbs) return;
  orbs.innerHTML = '';
  for (let i = 0; i < G.player.maxEnergy; i++) {
    const orb = document.createElement('div');
    orb.className = 'energy-orb' + (i < G.player.energy ? '' : ' empty');
    orbs.appendChild(orb);
  }
  const el = document.getElementById('energy-label');
  if (el) el.textContent = G.player.energy + '/' + G.player.maxEnergy + ' Energy';
}

function renderMechanicDisplay() {
  const wrap = document.getElementById('mechanic-display-wrap');
  if (!wrap) return;
  wrap.innerHTML = '';

  if (G.player.weak > 0) {
    const el = document.createElement('div');
    el.className = 'mechanic-display weak-display';
    el.textContent = '↓ Weak: ' + G.player.weak;
    wrap.appendChild(el);
  }
  if (G.player.vulnerable > 0) {
    const el = document.createElement('div');
    el.className = 'mechanic-display vulnerable-display';
    el.textContent = '⚠ Vulnerable: ' + G.player.vulnerable;
    wrap.appendChild(el);
  }
  if (G.player.strength > 0) {
    const el = document.createElement('div');
    el.className = 'mechanic-display strength-display';
    el.textContent = '⬆ Strength: ' + G.player.strength;
    wrap.appendChild(el);
  }

  if (G.classId === 'plague_doctor') {
    const totalInfection = G.enemies.reduce((sum, e) => sum + (e.infection || 0), 0);
    if (totalInfection > 0) {
      const el = document.createElement('div');
      el.className = 'mechanic-display infection-display';
      el.textContent = '☣ Infection: ' + totalInfection;
      wrap.appendChild(el);
    }
  } else if (G.classId === 'void_weaver') {
    const totalThreads = G.enemies.reduce((sum, e) => sum + (e.threads || 0), 0);
    const el = document.createElement('div');
    el.className = 'mechanic-display threads-display';
    el.textContent = '🕸 Threads: ' + totalThreads;
    wrap.appendChild(el);
  } else if (G.classId === 'storm_caller') {
    const el = document.createElement('div');
    el.className = 'mechanic-display charge-display';
    el.textContent = '⚡ Charge: ' + G.player.charge;
    wrap.appendChild(el);
  }
}

function renderHand() {
  const area = document.getElementById('hand-area');
  if (!area) return;
  area.innerHTML = '';

  const hand = G.player.hand;
  const total = hand.length;
  if (total === 0) return;

  const cardW = 156;
  const areaWidth = Math.max(area.clientWidth || 0, area.getBoundingClientRect().width || 0);
  if (areaWidth <= cardW + 24) {
    requestAnimationFrame(() => renderHand());
    return;
  }

  const maxSpread = 176;
  const comfortableSpread = 118;
  const edgePadding = 28;
  const naturalSpread = total === 1 ? 0 : (areaWidth - cardW - edgePadding * 2) / Math.max(1, total - 1);
  const fittableSpread = total === 1 ? 0 : (areaWidth - cardW - edgePadding) / Math.max(1, total - 1);
  const spread = total === 1
    ? 0
    : Math.max(64, Math.min(maxSpread, Math.max(Math.min(fittableSpread, comfortableSpread), naturalSpread)));
  const totalWidth = cardW + spread * (total - 1);
  const startX = Math.max(12, (areaWidth - totalWidth) / 2);
  const arcDeg = Math.min(2 * total, 12);

  hand.forEach((card, i) => {
    const el = buildCardElement(card, i);
    const x = startX + i * spread;
    const midI = (total - 1) / 2;
    const angle = total === 1 ? 0 : (i - midI) * (arcDeg / Math.max(1, total - 1));
    const lift = Math.abs(i - midI) * 4;
    el.style.left = x + 'px';
    el.style.bottom = lift + 'px';
    el.style.transform = `rotate(${angle}deg)`;
    el.style.zIndex = String(i + 1);
    el.addEventListener('click', () => onCardClick(i));
    area.appendChild(el);
  });
}

function buildCardElement(card, index) {
  const el = document.createElement('div');
  el.className = 'hand-card';
  el.dataset.rarity = card.rarity || 'basic';
  const presentation = applyCardPresentation(el, card);

  const playable = canPlayCard(card);
  if (!playable) el.classList.add('unplayable');

  const target = (card.svg_effect && card.svg_effect.target) || 'single';
  const targetHint = target === 'all' ? ' (AoE)' : target === 'self' ? '' : '';

  el.innerHTML = buildCardMarkup(card, {
    presentation,
    targetHint,
    compact: true,
    showRarity: false,
    showSignature: false,
    showOrnament: false
  });
  return el;
}

function renderDeckInfo() {
  const dc = document.getElementById('deck-count');
  const dsc = document.getElementById('discard-count');
  if (dc) dc.textContent = G.player.deck.length;
  if (dsc) dsc.textContent = G.player.discard.length;
}

// ──────────────────────────────────────────────────────────────────────────────
// DECK MODAL
// ──────────────────────────────────────────────────────────────────────────────
function showDeckModal() {
  const modal = document.getElementById('deck-modal');
  const grid = document.getElementById('modal-deck-grid');
  const countEl = document.getElementById('modal-deck-count');
  if (!modal || !grid) return;

  const allCards = [...G.player.deck, ...G.player.hand, ...G.player.discard, ...G.player.powerCards];
  countEl.textContent = allCards.length;
  grid.innerHTML = '';

  allCards.forEach(card => {
    const el = document.createElement('div');
    el.className = 'modal-card';
    el.dataset.rarity = card.rarity || 'basic';
    el.innerHTML = `
      <div style="font-size:10px;font-weight:bold">${card.name}</div>
      <div style="font-size:9px;color:#888;margin:2px 0">${(card.type||'').toUpperCase()} · ${card.cost||0} ⚡</div>
      <div style="font-size:9px;color:#ccc;line-height:1.3">${card.description||''}</div>`;
    grid.appendChild(el);
  });

  modal.style.display = 'flex';
}

// ──────────────────────────────────────────────────────────────────────────────
// UTILITY
// ──────────────────────────────────────────────────────────────────────────────
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function darkenColor(hex, factor) {
  const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return '#' + [r,g,b].map(c => Math.round(c*factor).toString(16).padStart(2,'0')).join('');
}

function lightenColor(hex, factor) {
  const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return '#' + [r,g,b].map(c => Math.min(255,Math.round(c*factor)).toString(16).padStart(2,'0')).join('');
}
