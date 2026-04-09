'use strict';

// ──────────────────────────────────────────────────────────────────────────────
// RUN STATE
// ──────────────────────────────────────────────────────────────────────────────
const Run = {
  classId: null,
  classConfig: null,
  classConfigs: null,
  enemyConfigs: null,
  baseEnemyConfigs: null,
  enemyRunTheme: null,
  generatedEnemyFloors: {},
  enemyGenerationReady: false,
  activeCombatFloor: 0,
  pendingCombatFloor: 0,
  currentFloor: 0,
  playerHp: 0,
  playerDeck: [],
  runPlan: null,        // generated once at class select (~5s)
  offeredCards: [],     // populated by background generation during combat
  rewardReady: false    // true when offeredCards arrived before fight ended
};

// ──────────────────────────────────────────────────────────────────────────────
// RUN START  (called when player picks a class)
// ──────────────────────────────────────────────────────────────────────────────
function startRun(classId, classConfig) {
  Run.classId = classId;
  Run.classConfig = classConfig;
  Run.currentFloor = 0;
  Run.playerHp = classConfig.hp;
  Run.playerDeck = [...(classConfig.starting_deck || [])];
  Run.runPlan = null;
  Run.enemyRunTheme = null;
  Run.generatedEnemyFloors = {};
  Run.enemyGenerationReady = false;
  Run.activeCombatFloor = 0;
  Run.pendingCombatFloor = 0;
  Run.offeredCards = [];

  showScreen('loading');
  startPlanLoadingProgress();
  generateRunPlan(classId, classConfig);   // bridge.js — fast call
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 1 COMPLETE: Run plan received (~5s after class select)
// ──────────────────────────────────────────────────────────────────────────────
function onRunPlanGenerated(plan) {
  Run.runPlan = plan;
  completePlanLoadingProgress(plan);

  // Save the plan, then generate the enemy doctrine and concrete floor packages
  saveRunState({
    run_class: Run.classId,
    run_phase: 'loading',
    current_floor: 0,
    player_hp: Run.playerHp,
    player_deck: Run.playerDeck,
    run_plan: plan,
    enemy_run_theme: null,
    enemy_generated_floors: {},
    enemy_generation_ready: false,
    offered_cards: []
  });

  setLoadingStatus('The Spire imagines its defenders...');
  generateEnemyTheme();
}

function onEnemyThemeGenerated(theme) {
  Run.enemyRunTheme = theme;

  saveRunState({
    run_phase: 'loading',
    current_floor: 0,
    player_hp: Run.playerHp,
    player_deck: Run.playerDeck,
    run_plan: Run.runPlan,
    enemy_run_theme: theme,
    enemy_generated_floors: {},
    enemy_generation_ready: false,
    offered_cards: []
  });

  setLoadingStatus('The Spire hardens into a living host...');
  Run.pendingCombatFloor = 1;
  generateEnemyFloor(1);
}

function hasGeneratedEnemyFloor(floor) {
  return !!Run.generatedEnemyFloors['floor_' + floor];
}

function onEnemyFloorGenerated(floorKey, enemies, theme, options = {}) {
  const floor = Number(String(floorKey || '').replace('floor_', '')) || 1;
  Run.enemyRunTheme = theme || Run.enemyRunTheme;
  Run.enemyConfigs = Run.enemyConfigs || {};
  Run.enemyConfigs[floorKey] = Array.isArray(enemies) ? enemies : [];
  Run.generatedEnemyFloors = { ...(Run.generatedEnemyFloors || {}), [floorKey]: true };
  if (floor === 1) Run.enemyGenerationReady = true;

  if (options.hydrated) {
    if (Run.pendingCombatFloor === floor) Run.pendingCombatFloor = 0;
    if (Run.currentFloor <= 0) startNextFight();
    return;
  }

  if (Run.pendingCombatFloor === floor) {
    Run.pendingCombatFloor = 0;
    if (floor === 1) {
      saveRunState({
        run_phase: 'combat',
        current_floor: 0,
        player_hp: Run.playerHp,
        player_deck: Run.playerDeck,
        run_plan: Run.runPlan,
        enemy_run_theme: Run.enemyRunTheme,
        enemy_generated_floors: Run.generatedEnemyFloors,
        enemy_generation_ready: true,
        offered_cards: []
      });
      setLoadingStatus('The enemy host descends.');
      delay(1200).then(() => startNextFight());
    } else {
      beginCombatFloor(floor, { persist: true, prefetchReward: true });
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// FIGHT PROGRESSION
// ──────────────────────────────────────────────────────────────────────────────
function startNextFight() {
  const nextFloor = Run.currentFloor + 1;
  Run.rewardReady = false;
  Run.offeredCards = [];

  if (!hasGeneratedEnemyFloor(nextFloor)) {
    Run.pendingCombatFloor = nextFloor;
    showScreen('loading');
    setLoadingStatus(nextFloor === 1
      ? 'The Spire imagines its first defenders...'
      : 'The next floor gathers itself...');
    generateEnemyFloor(nextFloor);
    return;
  }

  beginCombatFloor(nextFloor, { persist: true, prefetchReward: true });
}

function beginCombatFloor(floor, options = {}) {
  const persist = options.persist !== false;
  const prefetchReward = options.prefetchReward !== false;
  const persistedHp = Run.playerHp > 0 ? Run.playerHp : Run.classConfig.hp;

  Run.currentFloor = floor;
  Run.activeCombatFloor = floor;
  Run.rewardReady = false;
  Run.offeredCards = [];

  if (persist) {
    saveRunState({
      run_phase: 'combat',
      current_floor: Run.currentFloor,
      player_hp: persistedHp,
      player_deck: Run.playerDeck,
      enemy_run_theme: Run.enemyRunTheme,
      enemy_generated_floors: Run.generatedEnemyFloors,
      enemy_generation_ready: Run.enemyGenerationReady,
      offered_cards: []
    });
  }

  showScreen('combat');
  setCombatDeck(Run.playerDeck);
  initCombat(Run.currentFloor, Run.classId, Run.classConfig, Run.enemyConfigs, persistedHp, Run.enemyRunTheme);

  if (Run.currentFloor < 4 && !hasGeneratedEnemyFloor(Run.currentFloor + 1)) {
    generateEnemyFloor(Run.currentFloor + 1);
  }
  if (prefetchReward && Run.currentFloor <= 3) {
    generateRewardCards();
  }
}

// Called by game.js when all enemies are defeated
function onCombatWon(remainingHp) {
  Run.playerHp = remainingHp;

  if (Run.currentFloor >= 4) {
    showVictory();
    return;
  }

  if (Run.rewardReady) {
    // Cards arrived during combat — show instantly, no loading state
    showRewardScreenImmediate(Run.offeredCards);
  } else {
    // Still generating — show loading state; populateRewardScreen fires
    // when onRewardCardsGenerated is called by bridge.js
    showRewardScreenLoading();
  }
}

// Called by game.js when player HP reaches 0
function onCombatLost() {
  showDefeat();
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 2 COMPLETE: Reward cards received — may arrive during or after combat
// ──────────────────────────────────────────────────────────────────────────────
function onRewardCardsGenerated(cards) {
  const valid = (Array.isArray(cards) ? cards : []).filter(c => c && c.name);
  const toShow = valid.length > 0
    ? valid
    : (Run.classConfig.fallback_uncommons || []).slice(0, 3);

  toShow.forEach((c, i) => { if (!c.id) c.id = 'reward_f' + Run.currentFloor + '_' + i; });
  Run.offeredCards = toShow;
  Run.rewardReady = true;

  // Only update the screen if we're already on the reward screen.
  // If combat is still ongoing, onCombatWon will call showRewardScreenImmediate.
  const rewardScreen = document.getElementById('screen-reward');
  if (rewardScreen && rewardScreen.classList.contains('active')) {
    populateRewardScreen(toShow);
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// REWARD SCREEN
// ──────────────────────────────────────────────────────────────────────────────
function showRewardScreenImmediate(cards) {
  showScreen('reward');
  document.getElementById('reward-hp-display').textContent =
    '❤ ' + Run.playerHp + '/' + Run.classConfig.hp + ' HP';
  document.getElementById('reward-floor-display').textContent =
    'After Floor ' + Run.currentFloor;
  populateRewardScreen(cards);
}

function showRewardScreenLoading() {
  showScreen('reward');

  document.getElementById('reward-hp-display').textContent =
    '❤ ' + Run.playerHp + '/' + Run.classConfig.hp + ' HP';
  document.getElementById('reward-floor-display').textContent =
    'After Floor ' + Run.currentFloor;

  // Show the plan flavor as context while cards load
  const planFlavor = Run.runPlan ? Run.runPlan.flavor : '';
  const planTitle = Run.runPlan ? Run.runPlan.run_title : '';

  const row = document.getElementById('reward-cards-row');
  row.innerHTML = `
    <div class="reward-loading-state">
      <div class="reward-loading-title">${planTitle}</div>
      <div class="reward-loading-sub">${planFlavor}</div>
      <div class="reward-loading-dots">
        <span></span><span></span><span></span>
      </div>
      <div class="reward-loading-hint">The oracle is choosing your cards...</div>
    </div>`;

  // Hide skip button while loading
  document.getElementById('btn-skip-reward').style.display = 'none';
}

function populateRewardScreen(cards) {
  const row = document.getElementById('reward-cards-row');
  row.innerHTML = '';

  cards.forEach((card, idx) => {
    const el = buildRewardCard(card);
    // Animate cards appearing
    el.style.opacity = '0';
    el.style.transform = 'translateY(16px)';
    row.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, idx * 120);
    el.addEventListener('click', () => pickReward(idx));
  });

  // Show skip button
  document.getElementById('btn-skip-reward').style.display = '';
  document.getElementById('btn-skip-reward').onclick = skipReward;
}

function buildRewardCard(card) {
  const el = document.createElement('div');
  el.className = 'reward-card';
  el.dataset.rarity = card.rarity || 'uncommon';
  const presentation = applyCardPresentation(el, card);
  el.innerHTML = buildCardMarkup(card, {
    presentation,
    showRarity: true,
    showSignature: true,
    showOrnament: true
  });
  return el;
}

function pickReward(index) {
  const card = Run.offeredCards[index];
  if (!card) return;

  Run.playerDeck.push({ ...card });

  saveRunState({
    run_phase: 'combat',
    current_floor: Run.currentFloor,
    player_hp: Run.playerHp,
    player_deck: Run.playerDeck,
    enemy_generated_floors: Run.generatedEnemyFloors,
    offered_cards: []
  });

  startNextFight();
}

function skipReward() {
  saveRunState({
    run_phase: 'combat',
    current_floor: Run.currentFloor,
    player_hp: Run.playerHp,
    player_deck: Run.playerDeck,
    enemy_generated_floors: Run.generatedEnemyFloors,
    offered_cards: []
  });

  startNextFight();
}

// ──────────────────────────────────────────────────────────────────────────────
// ENDGAME SCREENS
// ──────────────────────────────────────────────────────────────────────────────
function showVictory() {
  showScreen('victory');
  const planTitle = Run.runPlan ? ' — ' + Run.runPlan.run_title : '';
  document.getElementById('victory-stats').innerHTML =
    'Class: ' + Run.classConfig.name + planTitle + '<br>' +
    'HP remaining: ' + Run.playerHp + '/' + Run.classConfig.hp + '<br>' +
    'Cards in deck: ' + Run.playerDeck.length;

  document.getElementById('btn-new-run').onclick = () => { resetRun(); showSelectIfNoState(); };
  document.getElementById('btn-victory-menu').onclick = () => {
    if (typeof bridge !== 'undefined' && bridge) bridge.requestReturnToMenu();
  };
  saveRunState({
    run_phase: 'class_select',
    current_floor: 0,
    run_plan: null,
    offered_cards: [],
    enemy_run_theme: null,
    enemy_generated_floors: {},
    enemy_generation_ready: false,
    enemy_configs: Run.baseEnemyConfigs || Run.enemyConfigs
  });
}

function showDefeat() {
  showScreen('defeat');
  const planTitle = Run.runPlan ? ' (' + Run.runPlan.run_title + ')' : '';
  document.getElementById('defeat-sub').textContent =
    'Fallen on Floor ' + Run.currentFloor + '. The Spire claims another soul.';
  document.getElementById('defeat-stats').innerHTML =
    'Class: ' + (Run.classConfig ? Run.classConfig.name : '?') + planTitle + '<br>' +
    'Floor reached: ' + Run.currentFloor + '/4<br>' +
    'Cards collected: ' + Run.playerDeck.length;

  document.getElementById('btn-try-again').onclick = () => { resetRun(); showSelectIfNoState(); };
  document.getElementById('btn-defeat-menu').onclick = () => {
    if (typeof bridge !== 'undefined' && bridge) bridge.requestReturnToMenu();
  };
  saveRunState({
    run_phase: 'class_select',
    current_floor: 0,
    run_plan: null,
    offered_cards: [],
    enemy_run_theme: null,
    enemy_generated_floors: {},
    enemy_generation_ready: false,
    enemy_configs: Run.baseEnemyConfigs || Run.enemyConfigs
  });
}

function resetRun() {
  Run.classId = null;
  Run.classConfig = null;
  Run.currentFloor = 0;
  Run.playerHp = 0;
  Run.playerDeck = [];
  Run.runPlan = null;
  Run.enemyRunTheme = null;
  Run.generatedEnemyFloors = {};
  Run.enemyGenerationReady = false;
  Run.activeCombatFloor = 0;
  Run.pendingCombatFloor = 0;
  Run.offeredCards = [];
}

// ──────────────────────────────────────────────────────────────────────────────
// CLASS SELECT
// ──────────────────────────────────────────────────────────────────────────────
function buildClassSelectFromState() {
  if (!Run.classConfigs) return;

  const SPRITE_SVGS = {
    plague_doctor: `<ellipse cx="80" cy="90" rx="42" ry="55" fill="#2d6e2d" filter="url(#gf)"/>
      <ellipse cx="80" cy="60" rx="28" ry="32" fill="#4a9e4a"/>
      <circle cx="70" cy="55" r="5" fill="#00ff44" opacity="0.8"/>
      <circle cx="90" cy="55" r="5" fill="#00ff44" opacity="0.8"/>`,
    void_weaver: `<ellipse cx="80" cy="88" rx="38" ry="50" fill="#4a1a7a" filter="url(#gf)"/>
      <ellipse cx="80" cy="55" rx="26" ry="30" fill="#7b2fbe"/>
      <circle cx="72" cy="50" r="5" fill="#c084fc" opacity="0.9"/>
      <circle cx="88" cy="50" r="5" fill="#c084fc" opacity="0.9"/>`,
    storm_caller: `<rect x="44" y="50" width="72" height="80" rx="8" fill="#1a4a8a" filter="url(#gf)"/>
      <rect x="50" y="56" width="60" height="68" rx="6" fill="#2f7abe"/>
      <polygon points="80,10 95,40 65,40" fill="#84c4fc"/>
      <circle cx="70" cy="78" r="7" fill="#84c4fc" opacity="0.8"/>
      <circle cx="90" cy="78" r="7" fill="#84c4fc" opacity="0.8"/>`
  };
  const GLOWS = {
    plague_doctor: 'rgba(74,158,74,0.5)',
    void_weaver: 'rgba(123,47,190,0.5)',
    storm_caller: 'rgba(47,122,190,0.5)'
  };

  const row = document.getElementById('class-cards-row');
  if (!row) return;
  row.innerHTML = '';

  Object.entries(Run.classConfigs).forEach(([id, cfg]) => {
    const card = document.createElement('div');
    card.className = 'class-card ' + id;
    card.innerHTML = `
      <div class="class-card-name">${cfg.name}</div>
      <div class="class-card-sprite">
        <svg width="100" height="100" viewBox="0 0 160 160"
             style="filter:drop-shadow(0 0 16px ${GLOWS[id]||'#aaa'})">
          <defs><filter id="gf" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter></defs>
          ${SPRITE_SVGS[id] || ''}
        </svg>
      </div>
      <div class="class-hp-badge">❤️ ${cfg.hp} HP</div>
      <div class="class-mechanic">
        <div class="class-mechanic-label">Mechanic</div>
        ${cfg.mechanic}
      </div>
      <button class="class-pick-btn">Choose ${cfg.name}</button>
    `;
    card.addEventListener('click', () => startRun(id, cfg));
    row.appendChild(card);
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// LOADING SCREEN (plan generation — fast, ~5s)
// ──────────────────────────────────────────────────────────────────────────────
let _loadingInterval = null;

function startPlanLoadingProgress() {
  const bar = document.getElementById('loading-bar');
  const status = document.getElementById('loading-status');
  const planReveal = document.getElementById('loading-plan-reveal');

  if (bar) bar.style.width = '0%';
  if (status) status.textContent = 'The oracle reads your fate...';
  if (planReveal) planReveal.style.display = 'none';

  let pct = 0;
  clearInterval(_loadingInterval);
  _loadingInterval = setInterval(() => {
    if (pct < 88) {
      pct += (88 - pct) * 0.06 + 0.5;
      if (bar) bar.style.width = pct + '%';
    }
  }, 100);
}

function completePlanLoadingProgress(plan) {
  clearInterval(_loadingInterval);
  const bar = document.getElementById('loading-bar');
  const status = document.getElementById('loading-status');
  const planReveal = document.getElementById('loading-plan-reveal');
  const planTitle = document.getElementById('loading-plan-title');
  const planFlavor = document.getElementById('loading-plan-flavor');
  const planArchetype = document.getElementById('loading-plan-archetype');

  if (bar) bar.style.width = '100%';
  if (status) status.textContent = 'Your fate is written.';

  if (plan && planReveal) {
    if (planTitle) planTitle.textContent = plan.run_title || '';
    if (planFlavor) planFlavor.textContent = plan.flavor || '';
    if (planArchetype) planArchetype.textContent = (plan.archetype || '').toUpperCase();
    planReveal.style.display = 'flex';
  }
}

function setLoadingStatus(text) {
  const status = document.getElementById('loading-status');
  if (status) status.textContent = text;
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
