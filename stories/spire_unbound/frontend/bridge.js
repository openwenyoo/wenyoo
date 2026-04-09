'use strict';

// ──────────────────────────────────────────────────────────────────────────────
// WENYOO BRIDGE INTEGRATION
// ──────────────────────────────────────────────────────────────────────────────

/* global WenyooStorySDK */

let bridge = null;
let _gameState = null;
const BRIDGE_ENEMY_FLOOR_LIMITS = { floor_1: 2, floor_2: 2, floor_3: 3, floor_4: 1 };
const BRIDGE_ENEMY_FLOOR_KEYS = Object.keys(BRIDGE_ENEMY_FLOOR_LIMITS);

// Generation state flags
let _waitingFor = null; // 'plan' | 'enemy_theme' | 'enemy_floor' | 'reward' | null
let _waitingEnemyFloorKey = null;
const _generationQueue = [];

function getVar(key, fallback) {
  if (!_gameState) return fallback;
  const vars = _gameState.variables || {};
  return vars[key] !== undefined ? vars[key] : fallback;
}

function enemyFloorKey(floor) {
  return typeof floor === 'string' ? floor : 'floor_' + floor;
}

function enemyFloorNumber(floorKey) {
  const match = /floor_(\d+)/.exec(String(floorKey || ''));
  return match ? Number(match[1]) : 0;
}

// ──────────────────────────────────────────────────────────────────────────────
// INIT
// ──────────────────────────────────────────────────────────────────────────────
function initBridge() {
  bridge = WenyooStorySDK.createBridge();

  bridge.on('init', (payload) => {
    if (payload && payload.gameState) {
      _gameState = payload.gameState;
      onGameState(_gameState);
    } else {
      showSelectIfNoState();
    }
  });

  bridge.on('game_start', (msg) => {
    if (msg && msg.content && msg.content.game_state) {
      _gameState = msg.content.game_state;
      onGameState(_gameState);
    }
  });

  bridge.on('rejoined', (msg) => {
    if (msg && msg.content && msg.content.game_state) {
      _gameState = msg.content.game_state;
      onGameState(_gameState);
    }
  });

  // Primary response path: Architect commits state → engine sends command_result
  // with full updated game_state in content.game_state (deliveries: [] means
  // no narrative delivery, but the state snapshot is always included).
  bridge.on('command_result', (msg) => {
    const content = (msg && msg.content) || {};
    if (content.game_state) _gameState = content.game_state;
    _checkGenerationResponse();
  });

  // Fallback: some state updates arrive as game_state events
  bridge.on('game_state', (msg) => {
    if (msg && msg.content && msg.content.game_state) {
      _gameState = msg.content.game_state;
      _checkGenerationResponse();
    }
  });

  bridge.on('stream_end', (msg) => {
    const content = (msg && msg.content) || {};
    if (content.game_state) _gameState = content.game_state;
    _checkGenerationResponse();
  });

  bridge.on('error', (msg) => {
    console.error('[Spire Unbound] Bridge error:', msg);
    _handleGenerationError();
  });

  bridge.requestInitialState();
}

// Called after every state-bearing event — checks if the thing we were
// waiting for has now appeared in the game state.
function _checkGenerationResponse() {
  if (!_waitingFor || !_gameState) return;
  const vars = _gameState.variables || {};

  if (_waitingFor === 'plan') {
    const plan = vars.run_plan;
    if (plan && plan.archetype) {
      _waitingFor = null;
      onRunPlanGenerated(plan);
    }
    return;
  }

  if (_waitingFor === 'reward') {
    const offered = vars.offered_cards;
    if (Array.isArray(offered) && offered.length > 0) {
      _waitingFor = null;
      onRewardCardsGenerated(offered);
      _finishGenerationTask();
    }
    return;
  }

  if (_waitingFor === 'enemy_theme') {
    const theme = vars.enemy_run_theme;
    if (theme && theme.session_trait) {
      _waitingFor = null;
      onEnemyThemeGenerated(theme);
      _finishGenerationTask();
    }
    return;
  }

  if (_waitingFor === 'enemy_floor') {
    const configs = vars.enemy_configs;
    const generatedFloors = vars.enemy_generated_floors || {};
    const floorKey = _waitingEnemyFloorKey;
    if (floorKey && configs && generatedFloors[floorKey]) {
      _waitingFor = null;
      onEnemyFloorGenerated(
        floorKey,
        normalizeEnemyFloorConfig(floorKey, configs[floorKey], buildFallbackEnemyConfigs()),
        vars.enemy_run_theme || Run.enemyRunTheme
      );
      _finishGenerationTask();
    }
  }
}

function _handleGenerationError() {
  if (_waitingFor === 'plan') {
    _waitingFor = null;
    console.warn('Plan generation failed — using minimal fallback');
    const cfg = Run.classConfig || {};
    const cats = Object.keys(cfg.categories || {});
    onRunPlanGenerated({
      run_title: 'The Unknown Path',
      archetype: 'Balanced',
      primary_category: cats[0] || 'attack',
      secondary_category: cats[1] || 'skill',
      win_condition: 'Deal consistent damage and survive.',
      flavor: 'The oracle\'s vision is clouded. Your path remains unwritten.',
      floor_guides: [
        { floor: 1, focus: 'Early damage and block', synergy_hint: 'Apply class mechanic early', rarity: 'uncommon' },
        { floor: 2, focus: 'Build on floor 1 cards', synergy_hint: 'Amplify existing effects', rarity: 'uncommon' },
        { floor: 3, focus: 'Powerful finisher', synergy_hint: 'Win condition card', rarity: 'uncommon+rare' }
      ]
    });
    return;
  }

  if (_waitingFor === 'reward') {
    _waitingFor = null;
    console.warn('Reward generation failed — using fallback cards');
    const fallbacks = (Run.classConfig && Run.classConfig.fallback_uncommons) || [];
    onRewardCardsGenerated(fallbacks.slice(0, 3));
    _finishGenerationTask();
    return;
  }

  if (_waitingFor === 'enemy_theme') {
    _waitingFor = null;
    console.warn('Enemy theme generation failed — using fallback doctrine');
    onEnemyThemeGenerated(buildFallbackEnemyTheme());
    _finishGenerationTask();
    return;
  }

  if (_waitingFor === 'enemy_floor') {
    _waitingFor = null;
    console.warn('Enemy floor generation failed — using fallback enemies');
    const floorKey = _waitingEnemyFloorKey || 'floor_1';
    onEnemyFloorGenerated(
      floorKey,
      normalizeEnemyFloorConfig(floorKey, buildFallbackEnemyConfigs()[floorKey], buildFallbackEnemyConfigs()),
      Run.enemyRunTheme || buildFallbackEnemyTheme()
    );
    _finishGenerationTask();
  }
}

function buildFallbackEnemyTheme() {
  const plan = Run.runPlan || {};
  const classConfig = Run.classConfig || {};
  return {
    session_trait: ((plan.visual_motif || classConfig.name || 'Spire Echo') + ' Host').slice(0, 60),
    core_fantasy: 'A defensive host shaped by the Spire\'s current omen.',
    visual_doctrine: 'Shared silhouettes, repeated symbols, and escalating glow convey one hostile lineage.',
    material_language: ['cracked lacquer', 'embers under glass', 'ritual iron'],
    symbol_set: ['halo', 'sigil', 'rift'],
    motion_language: plan.signature_rhythm || 'measured pressure, then rupture',
    counter_pressure: 'Pressure the player with mixed offense and defense without shutting down class mechanics.',
    palette_logic: 'Each floor deepens the same palette toward a boss culmination.',
    floor_traits: [
      { floor: 1, trait_name: 'Scouts of the Omen', manifestation: 'Small, readable expressions of the session trait', combat_pressure: 'Teach the run\'s baseline enemy rhythm' },
      { floor: 2, trait_name: 'Wardens of the Omen', manifestation: 'Heavier and more coordinated variants', combat_pressure: 'Mix block and setup pressure' },
      { floor: 3, trait_name: 'Harbingers of the Omen', manifestation: 'Dangerous late-run expressions with synchronized roles', combat_pressure: 'Force faster, cleaner answers' }
    ],
    boss_culmination: {
      name: 'Crown of the Omen',
      visual_escalation: 'The boss concentrates the same motifs into a singular ritual silhouette.',
      mechanical_escalation: 'The boss rotates between pressure, defense, and a punishing multi-target phase.'
    }
  };
}

function buildFallbackEnemyConfigs() {
  const base = Run.baseEnemyConfigs || Run.enemyConfigs || getVar('enemy_configs', {});
  return JSON.parse(JSON.stringify(base || {}));
}

function normalizeEnemyFloorConfig(floorKey, rawEnemies, fallbackConfigs) {
  const count = BRIDGE_ENEMY_FLOOR_LIMITS[floorKey] || 1;
  const incoming = Array.isArray(rawEnemies) ? rawEnemies : [];
  const fallback = Array.isArray(fallbackConfigs && fallbackConfigs[floorKey]) ? fallbackConfigs[floorKey] : [];
  return incoming.concat(fallback).slice(0, count);
}

function normalizeEnemyConfigSet(rawConfigs, fallbackConfigs) {
  const safeFallback = fallbackConfigs || {};
  const source = rawConfigs && typeof rawConfigs === 'object' ? rawConfigs : {};
  const normalized = {};
  BRIDGE_ENEMY_FLOOR_KEYS.forEach((key) => {
    const chosen = Object.prototype.hasOwnProperty.call(source, key) ? source[key] : safeFallback[key];
    normalized[key] = normalizeEnemyFloorConfig(key, chosen, safeFallback);
  });
  return normalized;
}

function _sameGenerationTask(a, b) {
  return !!a && !!b && a.type === b.type && a.floorKey === b.floorKey;
}

function _drainGenerationQueue() {
  if (_waitingFor || _generationQueue.length === 0) return;
  const nextTask = _generationQueue.shift();
  if (!nextTask) return;
  _startQueuedGeneration(nextTask);
}

function _finishGenerationTask() {
  if (_waitingFor !== 'enemy_floor') {
    _waitingEnemyFloorKey = null;
  }
  if (!_waitingFor) {
    _drainGenerationQueue();
  }
}

function _enqueueGeneration(task) {
  if (!task) return;
  const activeTask = _waitingFor ? { type: _waitingFor, floorKey: _waitingEnemyFloorKey } : null;
  if (_sameGenerationTask(activeTask, task)) return;
  if (_generationQueue.some((queued) => _sameGenerationTask(queued, task))) return;
  if (!_waitingFor) {
    _startQueuedGeneration(task);
    return;
  }
  _generationQueue.push(task);
}

function _startQueuedGeneration(task) {
  if (!task) return;
  if (task.type === 'reward') {
    _startRewardCardGeneration();
  } else if (task.type === 'enemy_floor') {
    _startEnemyFloorGeneration(task.floorKey);
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// STATE ROUTING (on init / rejoin)
// ──────────────────────────────────────────────────────────────────────────────
function onGameState(gameState) {
  if (!gameState || !gameState.variables) { showSelectIfNoState(); return; }

  const vars = gameState.variables;
  if (vars.class_configs) Run.classConfigs = vars.class_configs;
  if (vars.enemy_configs) {
    if (!Run.baseEnemyConfigs) Run.baseEnemyConfigs = JSON.parse(JSON.stringify(vars.enemy_configs));
    Run.enemyConfigs = normalizeEnemyConfigSet(vars.enemy_configs, Run.baseEnemyConfigs);
  }

  const runPhase = vars.run_phase || 'class_select';
  if (runPhase === 'class_select') { showSelectIfNoState(); return; }

  const classId = vars.run_class;
  const classConfig = (vars.class_configs || {})[classId];
  if (!classId || !classConfig) { showSelectIfNoState(); return; }

  Run.classId = classId;
  Run.classConfig = classConfig;
  Run.currentFloor = vars.current_floor || 0;
  Run.playerHp = vars.player_hp || classConfig.hp;
  Run.playerDeck = vars.player_deck || [...(classConfig.starting_deck || [])];
  Run.runPlan = vars.run_plan || null;
  Run.enemyRunTheme = vars.enemy_run_theme || null;
  Run.enemyGenerationReady = !!vars.enemy_generation_ready;
  Run.generatedEnemyFloors = vars.enemy_generated_floors || {};

  if (runPhase === 'loading') {
    showScreen('loading');
    if (!Run.runPlan) {
      startPlanLoadingProgress();
      generateRunPlan(classId, classConfig);
      return;
    }
    completePlanLoadingProgress(Run.runPlan);
    if (!Run.enemyRunTheme) {
      generateEnemyTheme();
      return;
    }
    if (!Run.generatedEnemyFloors.floor_1) {
      generateEnemyFloor(1);
      return;
    }
    onEnemyFloorGenerated('floor_1', Run.enemyConfigs.floor_1, Run.enemyRunTheme, { hydrated: true });
    return;
  }

  if (runPhase === 'card_reward') {
    const offered = vars.offered_cards || [];
    if (offered.length > 0) {
      onRewardCardsGenerated(offered);
    } else {
      // Reward cards missing — regenerate them
      generateRewardCards();
    }
  } else if (runPhase === 'combat') {
    if (!Run.runPlan) {
      showScreen('loading');
      startPlanLoadingProgress();
      generateRunPlan(classId, classConfig);
      return;
    }
    if (Run.activeCombatFloor === Run.currentFloor) {
      return;
    }
    if (Run.currentFloor > 0) {
      if (Run.generatedEnemyFloors[enemyFloorKey(Run.currentFloor)]) {
        beginCombatFloor(Run.currentFloor, {
          persist: false,
          prefetchReward: !Array.isArray(vars.offered_cards) || vars.offered_cards.length === 0
        });
      }
    } else {
      startNextFight();
    }
  }
}

function showSelectIfNoState() {
  showScreen('select');
  buildClassSelectFromState();
}

function buildCreativeSeed() {
  const left = ['ember', 'mirror', 'thread', 'storm', 'oracle', 'venom', 'eclipse', 'grave', 'spire', 'echo'];
  const right = ['wake', 'song', 'hunger', 'veil', 'pulse', 'rift', 'oath', 'bloom', 'shiver', 'crown'];
  const a = left[Math.floor(Math.random() * left.length)];
  const b = right[Math.floor(Math.random() * right.length)];
  return a + '-' + b + '-' + Math.floor(Math.random() * 10000);
}

function buildDeckDigest(deckCards) {
  const digest = {
    type_counts: { attack: 0, skill: 0, power: 0 },
    cost_curve: { 0: 0, 1: 0, 2: 0, 3: 0 },
    effects: {
      single_target: 0,
      aoe: 0,
      block: 0,
      draw: 0,
      heal: 0,
      energy_gain: 0,
      self_damage: 0,
      scaling: 0,
      debuff: 0
    },
    statuses: { infection: 0, weak: 0, vulnerable: 0, threads: 0, strength: 0, charge: 0 },
    mechanics: { thread_consumers: 0, charge_spenders: 0, status_build_cards: 0, sustain_cards: 0 },
    average_cost: 0
  };

  let totalCost = 0;
  deckCards.forEach(card => {
    const type = card && card.type ? card.type : 'skill';
    if (digest.type_counts[type] !== undefined) digest.type_counts[type]++;

    const rawCost = card && Number.isFinite(card.cost) ? card.cost : 1;
    const cost = Math.max(0, Math.min(3, rawCost));
    digest.cost_curve[cost]++;
    totalCost += cost;

    const effects = Array.isArray(card.effects) ? card.effects : [];
    effects.forEach(effect => {
      switch (effect.type) {
        case 'damage':
          digest.effects.single_target++;
          break;
        case 'aoe_damage':
          digest.effects.aoe++;
          break;
        case 'block':
          digest.effects.block++;
          break;
        case 'draw':
          digest.effects.draw++;
          break;
        case 'heal':
          digest.effects.heal++;
          digest.mechanics.sustain_cards++;
          break;
        case 'gain_energy':
          digest.effects.energy_gain++;
          break;
        case 'self_damage':
          digest.effects.self_damage++;
          break;
        case 'consume_threads':
          digest.effects.scaling++;
          digest.mechanics.thread_consumers++;
          break;
        case 'spend_charge':
          digest.effects.scaling++;
          digest.mechanics.charge_spenders++;
          break;
        case 'apply_status':
          if (digest.statuses[effect.status] !== undefined) {
            digest.statuses[effect.status] += effect.value || 0;
          }
          if (effect.target === 'enemy') {
            digest.effects.debuff++;
            digest.mechanics.status_build_cards++;
          } else if (effect.status === 'strength' || effect.status === 'charge') {
            digest.effects.scaling++;
          }
          break;
        default:
          break;
      }
    });
  });

  digest.average_cost = deckCards.length > 0 ? Number((totalCost / deckCards.length).toFixed(2)) : 0;
  return digest;
}

function formatDeckDigest(digest) {
  return [
    '  Type mix: attack ' + digest.type_counts.attack + ', skill ' + digest.type_counts.skill + ', power ' + digest.type_counts.power,
    '  Cost curve: 0->' + digest.cost_curve[0] + ', 1->' + digest.cost_curve[1] + ', 2->' + digest.cost_curve[2] + ', 3->' + digest.cost_curve[3] + ' (avg ' + digest.average_cost + ')',
    '  Roles: single-target ' + digest.effects.single_target + ', AoE ' + digest.effects.aoe + ', block ' + digest.effects.block + ', draw ' + digest.effects.draw + ', scaling ' + digest.effects.scaling,
    '  Utility: heal ' + digest.effects.heal + ', energy ' + digest.effects.energy_gain + ', self-damage ' + digest.effects.self_damage + ', debuff ' + digest.effects.debuff,
    '  Status totals: infection ' + digest.statuses.infection + ', weak ' + digest.statuses.weak + ', vulnerable ' + digest.statuses.vulnerable + ', threads ' + digest.statuses.threads + ', strength ' + digest.statuses.strength + ', charge ' + digest.statuses.charge,
    '  Engine pieces: thread consumers ' + digest.mechanics.thread_consumers + ', charge spenders ' + digest.mechanics.charge_spenders + ', status builders ' + digest.mechanics.status_build_cards + ', sustain cards ' + digest.mechanics.sustain_cards
  ].join('\n');
}

function buildEnemyConfigDigest(configs) {
  return ['floor_1', 'floor_2', 'floor_3', 'floor_4']
    .map((key) => {
      const enemies = Array.isArray(configs && configs[key]) ? configs[key] : [];
      return key + ': ' + enemies.map(enemy => enemy.name + ' (' + (enemy.role || enemy.sprite_type || 'enemy') + ', hp ' + enemy.hp + ')').join(', ');
    })
    .join('\n');
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 1: RUN PLAN GENERATION (fast, ~5s)
// ──────────────────────────────────────────────────────────────────────────────
function generateRunPlan(classId, classConfig) {
  if (!bridge) { _handleGenerationError(); return; }

  saveRunState({
    run_class: classId,
    run_phase: 'loading',
    current_floor: 0,
    player_hp: classConfig.hp,
    player_deck: [...(classConfig.starting_deck || [])],
    run_plan: null,
    offered_cards: [],
    enemy_run_theme: null,
    enemy_configs: buildFallbackEnemyConfigs(),
    enemy_generated_floors: {},
    enemy_generation_ready: false
  });
  _waitingFor = 'plan';

  const categories = classConfig.categories || {};
  const categoriesStr = Object.entries(categories).map(([k, v]) => '- ' + k + ': ' + v).join('\n');
  const creativeSeed = buildCreativeSeed();
  const classVfxIdentity = classConfig.vfx_identity || '';

  bridge.sendArchitectTask('ui_requested_generation', {
    action_id: 'generate_run_plan',
    active_view: 'card_generation',
    player_input: 'Design run plan for ' + classConfig.name,
    purpose:
      'Generate a strategic run plan for a ' + classConfig.name + ' run. ' +
      'Class mechanic: ' + classConfig.mechanic + '. ' +
      'Available categories:\n' + categoriesStr + '\n' +
      'Class VFX identity: ' + classVfxIdentity + '\n' +
      'Invent a vivid omen, visual motif, and signature rhythm that later cards can inherit. ' +
      'Use this creative seed for surprise and specificity: ' + creativeSeed + '. ' +
      'Follow lore_run_plan_generation rules exactly. ' +
      'Write to state_changes: { "variables": { "run_plan": { ...plan... } } }. ' +
      'Return ONLY the state_changes JSON.',
    structured_input: {
      action: 'generate_run_plan',
      class_id: classId,
      class_name: classConfig.name,
      class_mechanic: classConfig.mechanic,
      class_categories: categories,
      class_palette: classConfig.palette || [],
      class_vfx_identity: classVfxIdentity,
      creative_seed: creativeSeed
    },
    extra_context: { input_type: 'story_app', active_view: 'card_generation' }
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 2: ENEMY THEME GENERATION
// ──────────────────────────────────────────────────────────────────────────────
function generateEnemyTheme() {
  if (!bridge || !Run.runPlan || !Run.classConfig) { _handleGenerationError(); return; }
  if (_waitingFor === 'enemy_theme') return;

  _waitingFor = 'enemy_theme';

  const plan = Run.runPlan;
  const classConfig = Run.classConfig;
  const purpose =
    'Generate the enemy doctrine for this Spire Unbound run.\n\n' +
    'RUN PLAN:\n' +
    '  Archetype: ' + (plan.archetype || 'Unknown') + '\n' +
    '  Win condition: ' + (plan.win_condition || 'Unknown') + '\n' +
    '  Omen: ' + (plan.omen || 'none') + '\n' +
    '  Visual motif: ' + (plan.visual_motif || 'none') + '\n' +
    '  Signature rhythm: ' + (plan.signature_rhythm || 'none') + '\n' +
    '  Creative constraint: ' + (plan.creative_constraint || 'none') + '\n\n' +
    'CLASS:\n' +
    '  Name: ' + classConfig.name + '\n' +
    '  Mechanic: ' + classConfig.mechanic + '\n' +
    '  Palette: ' + (classConfig.palette || []).join(', ') + '\n' +
    '  VFX identity: ' + (classConfig.vfx_identity || 'none') + '\n\n' +
    'Design one enemy civilization or corruption pattern for the full session.\n' +
    'Keep all floors related by a shared doctrine, with escalating floor traits and a boss culmination.\n' +
    'Follow lore_enemy_theme_generation exactly.\n' +
    'Write to state_changes: { "variables": { "enemy_run_theme": { ...theme... } } }.\n' +
    'Return ONLY the state_changes JSON.';

  bridge.sendArchitectTask('ui_requested_generation', {
    action_id: 'generate_enemy_theme',
    active_view: 'enemy_generation',
    player_input: 'Generate enemy doctrine for this run',
    purpose,
    structured_input: {
      action: 'generate_enemy_theme',
      class_id: Run.classId,
      class_name: classConfig.name,
      class_mechanic: classConfig.mechanic,
      class_palette: classConfig.palette || [],
      class_vfx_identity: classConfig.vfx_identity || '',
      run_plan: plan
    },
    extra_context: { input_type: 'story_app', active_view: 'enemy_generation' }
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 3: ENEMY FLOOR GENERATION
// ──────────────────────────────────────────────────────────────────────────────
function generateEnemyFloor(floor) {
  _enqueueGeneration({ type: 'enemy_floor', floorKey: enemyFloorKey(floor) });
}

function _startEnemyFloorGeneration(floorKey) {
  if (!bridge || !Run.runPlan || !Run.classConfig || !Run.enemyRunTheme) { _handleGenerationError(); return; }
  _waitingFor = 'enemy_floor';
  _waitingEnemyFloorKey = floorKey;

  const floorNumber = enemyFloorNumber(floorKey);
  const classConfig = Run.classConfig;
  const plan = Run.runPlan;
  const theme = Run.enemyRunTheme;
  const fallbackBaseline = buildFallbackEnemyConfigs();
  const floorTrait = Array.isArray(theme.floor_traits)
    ? theme.floor_traits.find((entry) => Number(entry && entry.floor) === floorNumber)
    : null;
  const isBossFloor = floorKey === 'floor_4';
  const count = BRIDGE_ENEMY_FLOOR_LIMITS[floorKey] || 1;
  const purpose =
    'Generate the concrete enemy package for ' + floorKey + ' of this run.\n\n' +
    'SESSION ENEMY DOCTRINE:\n' +
    '  Session trait: ' + theme.session_trait + '\n' +
    '  Core fantasy: ' + (theme.core_fantasy || 'unknown') + '\n' +
    '  Visual doctrine: ' + (theme.visual_doctrine || 'unknown') + '\n' +
    '  Motion language: ' + (theme.motion_language || 'unknown') + '\n' +
    '  Counter pressure: ' + (theme.counter_pressure || 'unknown') + '\n\n' +
    'TARGET FLOOR:\n' +
    '  Floor: ' + floorNumber + '\n' +
    '  Shared trait: ' + ((floorTrait && floorTrait.trait_name) || (isBossFloor && theme.boss_culmination && theme.boss_culmination.name) || theme.session_trait) + '\n' +
    '  Manifestation: ' + ((floorTrait && floorTrait.manifestation) || (theme.boss_culmination && theme.boss_culmination.visual_escalation) || 'Escalate the session doctrine') + '\n' +
    '  Combat pressure: ' + ((floorTrait && floorTrait.combat_pressure) || (theme.boss_culmination && theme.boss_culmination.mechanical_escalation) || 'Escalate the run fairly') + '\n\n' +
    'RUN PLAN:\n' +
    '  Archetype: ' + (plan.archetype || 'Unknown') + '\n' +
    '  Win condition: ' + (plan.win_condition || 'Unknown') + '\n' +
    '  Omen: ' + (plan.omen || 'none') + '\n' +
    '  Visual motif: ' + (plan.visual_motif || 'none') + '\n\n' +
    'CLASS:\n' +
    '  Name: ' + classConfig.name + '\n' +
    '  Mechanic: ' + classConfig.mechanic + '\n' +
    '  Palette: ' + (classConfig.palette || []).join(', ') + '\n\n' +
    'Fallback baseline for pacing only:\n' + floorKey + ': ' + ((fallbackBaseline[floorKey] || []).map(enemy => enemy.name + ' (' + enemy.hp + ' hp)').join(', ')) + '\n\n' +
    'Rules:\n' +
    '- Generate exactly ' + count + ' ' + (isBossFloor ? 'boss package' : 'enemies') + ' for ' + floorKey + '\n' +
    '- Return ONLY the package for ' + floorKey + ', not the whole run\n' +
    '- All enemies in this package must share one trait_name and feel like one family\n' +
    '- Preserve session-wide coherence while escalating by floor\n' +
    '- Use only the allowed deterministic intent grammar\n' +
    '- Keep this floor fair, readable, and suited to its place in the run arc\n' +
    '- sprite_svg should be handwritten raw SVG fragments inside the stated safety boundaries\n' +
    '- Include sprite_type, color, and glow fallbacks even when sprite_svg is present\n' +
    '- Follow lore_enemy_config_generation exactly\n' +
    'Write to state_changes so only variables.enemy_configs.' + floorKey + ' is updated, variables.enemy_generated_floors.' + floorKey + ' becomes true, and set enemy_generation_ready to true only when generating floor_1.\n' +
    'Return ONLY the state_changes JSON.';

  bridge.sendArchitectTask('ui_requested_generation', {
    action_id: 'generate_enemy_floor_' + floorNumber,
    active_view: 'enemy_generation',
    player_input: 'Generate enemies for ' + floorKey,
    purpose,
    structured_input: {
      action: 'generate_enemy_floor',
      target_floor: floorNumber,
      target_floor_key: floorKey,
      class_id: Run.classId,
      class_name: classConfig.name,
      class_mechanic: classConfig.mechanic,
      class_palette: classConfig.palette || [],
      run_plan: plan,
      enemy_run_theme: theme,
      floor_trait: floorTrait,
      boss_culmination: theme.boss_culmination || null,
      requested_count: count,
      fallback_baseline: { [floorKey]: fallbackBaseline[floorKey] || [] },
      first_floor_generation: floorKey === 'floor_1'
    },
    extra_context: { input_type: 'story_app', active_view: 'enemy_generation' }
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// STAGE 4: REWARD CARD GENERATION (lazy, ~15s, called after each fight)
// ──────────────────────────────────────────────────────────────────────────────
function generateRewardCards() {
  _enqueueGeneration({ type: 'reward' });
}

function _startRewardCardGeneration() {
  if (!bridge) { _handleGenerationError(); return; }

  const floor = Run.currentFloor;
  const plan = Run.runPlan;
  const classConfig = Run.classConfig;

  if (!plan || !classConfig) { _handleGenerationError(); return; }

  // Determine floor guide and rarity mix
  const floorGuides = plan.floor_guides || [];
  const guide = floorGuides[floor - 1] || floorGuides[floorGuides.length - 1] || {};
  const includeRare = (guide.rarity || '').includes('rare');

  // Summarise current deck to guide generation (avoid duplicates, fill gaps)
  const deckSummary = Run.playerDeck.map(c => c.name + ' (' + c.type + ')').join(', ');
  const deckDigest = buildDeckDigest(Run.playerDeck);
  const deckDigestText = formatDeckDigest(deckDigest);
  const classVfxIdentity = classConfig.vfx_identity || '';

  _waitingFor = 'reward';

  const purpose =
    'Generate exactly 3 reward cards for floor ' + floor + ' of a ' + classConfig.name + ' run.\n\n' +
    'RUN PLAN:\n' +
    '  Archetype: ' + plan.archetype + '\n' +
    '  Win condition: ' + plan.win_condition + '\n' +
    '  Primary category: ' + plan.primary_category + '\n' +
    '  Secondary category: ' + plan.secondary_category + '\n' +
    '  Omen: ' + (plan.omen || 'none') + '\n' +
    '  Visual motif: ' + (plan.visual_motif || 'none') + '\n' +
    '  Signature rhythm: ' + (plan.signature_rhythm || 'none') + '\n' +
    '  Creative constraint: ' + (plan.creative_constraint || 'none') + '\n\n' +
    'FLOOR ' + floor + ' GUIDANCE:\n' +
    '  Focus: ' + (guide.focus || 'balanced') + '\n' +
    '  Synergy hint: ' + (guide.synergy_hint || 'complement existing cards') + '\n' +
    '  Visual direction: ' + (guide.visual_direction || 'match the run motif') + '\n' +
    '  Rarity: ' + (guide.rarity || 'uncommon') + '\n\n' +
    'PLAYER\'S CURRENT DECK (' + Run.playerDeck.length + ' cards): ' + (deckSummary || 'starting deck only') + '\n\n' +
    'DECK DIGEST:\n' + deckDigestText + '\n\n' +
    'CLASS MECHANIC: ' + classConfig.mechanic + '\n' +
    'CLASS VFX IDENTITY: ' + classVfxIdentity + '\n' +
    'PALETTE: ' + (classConfig.palette || []).join(', ') + '\n\n' +
    'Rules:\n' +
    '- Generate 3 cards total' + (includeRare ? ': 2 uncommons + 1 rare' : ': all uncommons') + '\n' +
    '- Each card must serve the stated floor focus and synergy hint\n' +
    '- Do NOT duplicate cards already in the player\'s deck\n' +
    '- The batch must show contrast: do not offer 3 cards with the same role, cost profile, or visual mood\n' +
    '- Use the run omen, motif, rhythm, and creative constraint to make these cards feel like part of the same prophecy\n' +
    '- Give every card a distinct visual fingerprint via visual_seed, visual_identity, and card_frame\n' +
    '- Keep the class VFX identity unmistakable; do not let this class look like another class with recolored particles\n' +
    '- Rare cards must feel stranger and more luxurious than uncommons, with a rarity_signature and more dramatic effect composition\n' +
    '- Follow lore_reward_card_generation for effect types, SVG grammar, and balance\n' +
    'Write to state_changes: { "variables": { "offered_cards": [ ...3 cards... ] } }\n' +
    'Return ONLY the state_changes JSON.';

  bridge.sendArchitectTask('ui_requested_generation', {
    action_id: 'generate_reward_cards',
    active_view: 'card_generation',
    player_input: 'Generate reward cards for floor ' + floor,
    purpose: purpose,
    structured_input: {
      action: 'generate_reward_cards',
      floor: floor,
      class_id: Run.classId,
      class_name: classConfig.name,
      run_plan: plan,
      floor_guide: guide,
      class_vfx_identity: classVfxIdentity,
      include_rare: includeRare,
      current_deck_names: Run.playerDeck.map(c => c.name),
      current_deck_size: Run.playerDeck.length,
      deck_digest: deckDigest
    },
    extra_context: { input_type: 'story_app', active_view: 'card_generation' }
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// STATE PERSISTENCE
// ──────────────────────────────────────────────────────────────────────────────
function saveRunState(patch) {
  if (!bridge) return;
  bridge.sendDeterministicAction('merge_patch', { patch: { variables: patch } }, { display_text: 'Save run state' });
}

// ──────────────────────────────────────────────────────────────────────────────
// BOOT
// ──────────────────────────────────────────────────────────────────────────────
(function boot() {
  if (typeof WenyooStorySDK === 'undefined') {
    console.warn('[Spire Unbound] WenyooStorySDK not found — standalone mode');
    _runStandalone();
    return;
  }
  initBridge();
})();

function _runStandalone() {
  Run.classConfigs = {
    plague_doctor: {
      name: 'Plague Doctor', hp: 75,
      mechanic: 'Infection stacks accumulate on enemies.',
      categories: { venom: 'Apply infection', remedy: 'Spend HP', miasma: 'AoE debuffs' },
      palette: ['#4a9e4a', '#2d6e2d', '#7bc67b'],
      starting_deck: [], fallback_uncommons: []
    }
  };
  Run.enemyConfigs = {
    floor_1: [{ id: 'slime_a', name: 'Slime', hp: 25, sprite_type: 'blob', color: '#55aa55', glow: 'rgba(85,170,85,0.5)', ai_cycle: [{type:'attack',value:8},{type:'attack',value:8},{type:'defend',value:6}] }]
  };
  Run.baseEnemyConfigs = buildFallbackEnemyConfigs();
  Run.enemyRunTheme = buildFallbackEnemyTheme();
  Run.enemyGenerationReady = true;
  buildClassSelectFromState();
  showScreen('select');
}
