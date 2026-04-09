'use strict';

class EffectsRenderer {
  constructor() {
    this.svg = document.getElementById('effect-layer');
  }

  // Main entry — plays all layers of a card's svg_effect.
  // targetEnemyId: the id of the specific enemy to target (for single-target cards)
  async playEffect(cardOrEffect, targetEnemyId) {
    const sourceCard = cardOrEffect && cardOrEffect.svg_effect ? cardOrEffect : null;
    const svgEffect = sourceCard ? sourceCard.svg_effect : cardOrEffect;
    if (!svgEffect || !svgEffect.layers || svgEffect.layers.length === 0) return;
    const effectCtx = this._buildEffectContext(sourceCard, svgEffect);

    const target = svgEffect.target || 'single';
    const totalMs = svgEffect.total_duration_ms || 500;

    if (target === 'all') {
      // Play against all alive enemies with slight stagger
      const aliveEnemies = this._getAliveEnemyIds();
      const promises = [];
      aliveEnemies.forEach((eid, i) => {
        const staggerMs = i * 80;
        promises.push(this.delay(staggerMs).then(() =>
          Promise.all(svgEffect.layers.map((layer, idx) => this._playLayer(layer, 'single', eid, this._withLayerContext(effectCtx, layer, idx, eid))))
        ));
      });
      await this.delay(totalMs);
      await Promise.all(promises);
    } else {
      // single or self
      const promises = svgEffect.layers.map((layer, idx) =>
        this._playLayer(layer, target, targetEnemyId, this._withLayerContext(effectCtx, layer, idx, targetEnemyId))
      );
      await this.delay(totalMs);
      await Promise.all(promises);
    }
  }

  async _playLayer(layer, target, targetEnemyId, layerCtx) {
    const startDelay = (layer.timing && layer.timing.start_ms) || 0;
    if (startDelay > 0) await this.delay(startDelay);

    const fromPos = this.getPos('self');
    const toPos = (target === 'self') ? fromPos : this.getPos('enemy', targetEnemyId);

    switch (layer.type) {
      case 'projectile':
        await this.animateProjectile(layer, fromPos, toPos, layerCtx);
        break;
      case 'impact':
        await this.animateImpact(layer, toPos, layerCtx);
        break;
      case 'status_applier':
        await this.animateStatusApplier(layer, toPos, layerCtx);
        break;
      case 'screen':
        await this.animateScreen(layer, layerCtx);
        break;
      case 'aura': {
        const auraPos = (target === 'self') ? fromPos : toPos;
        await this.animateAura(layer, auraPos, layerCtx);
        break;
      }
      default:
        break;
    }
  }

  // Get center coords of an enemy sprite or player area relative to SVG
  getPos(target, enemyId) {
    const svgRect = this.svg.getBoundingClientRect();

    if (target === 'enemy' && enemyId) {
      const unit = document.querySelector(`.enemy-unit[data-enemy-id="${enemyId}"]`);
      if (unit) {
        const sprite = unit.querySelector('.enemy-sprite');
        const el = sprite || unit;
        const r = el.getBoundingClientRect();
        return {
          x: r.left + r.width / 2 - svgRect.left,
          y: r.top + r.height / 2 - svgRect.top
        };
      }
      // fallback: center of enemy area
      const area = document.getElementById('combat-enemy-area');
      if (area) {
        const r = area.getBoundingClientRect();
        return { x: r.left + r.width / 2 - svgRect.left, y: r.top + r.height / 2 - svgRect.top };
      }
      return { x: svgRect.width / 2, y: svgRect.height * 0.28 };
    } else if (target === 'enemy') {
      // No specific ID — target center of enemy area
      const area = document.getElementById('combat-enemy-area');
      if (area) {
        const r = area.getBoundingClientRect();
        return { x: r.left + r.width / 2 - svgRect.left, y: r.top + r.height / 2 - svgRect.top };
      }
      return { x: svgRect.width / 2, y: svgRect.height * 0.28 };
    } else {
      // player / self — bottom center
      return { x: svgRect.width / 2, y: svgRect.height * 0.80 };
    }
  }

  _getAliveEnemyIds() {
    const units = document.querySelectorAll('.enemy-unit:not(.dead)');
    return Array.from(units).map(u => u.dataset.enemyId).filter(Boolean);
  }

  // ─── PROJECTILE ─────────────────────────────────────────────────────────────
  async animateProjectile(layer, from, to, ctx) {
    const spec = this._normalizeProjectileSpec(layer, ctx);
    const duration = spec.duration;
    const color = spec.color;
    const accent = spec.accent;
    const rng = ctx && ctx.rng ? ctx.rng : Math.random;

    const group = this._makeSvgEl('g');
    this.svg.appendChild(group);

    const projectileNodes = [];
    const projectileCount = Math.max(1, spec.count);
    for (let i = 0; i < projectileCount; i++) {
      const child = this._makeSvgEl('g');
      const offsetIndex = i - (projectileCount - 1) / 2;
      child.dataset.offset = String(offsetIndex * spec.spacing);
      child.dataset.phase = String(rng() * Math.PI * 2);
      child.dataset.rotation = String((rng() - 0.5) * spec.rotationJitter);
      const proj = this._makeProjectileShape(spec, ctx);
      child.appendChild(proj);
      group.appendChild(child);
      projectileNodes.push(child);
    }

    const trailParticles = [];
    let startTime = null;
    let lastTrailTime = 0;

    return new Promise(resolve => {
      const tick = (ts) => {
        if (!startTime) startTime = ts;
        const elapsed = ts - startTime;
        const t = Math.min(elapsed / duration, 1);
        const x = from.x + (to.x - from.x) * t;
        const y = from.y + (to.y - from.y) * t;
        const angle = Math.atan2(to.y - from.y, to.x - from.x) * 180 / Math.PI;
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy / dist;
        const ny = dx / dist;
        const arcOffset = -Math.sin(Math.PI * t) * spec.arcHeight;
        const wobbleBase = Math.sin((t * Math.PI * 2 * spec.wobbleCycles) + spec.phaseOffset) * spec.wobble;

        projectileNodes.forEach(node => {
          const offset = Number(node.dataset.offset || 0);
          const phase = Number(node.dataset.phase || 0);
          const rotationJitter = Number(node.dataset.rotation || 0);
          const wobble = wobbleBase + Math.sin((t * Math.PI * 2 * spec.wobbleCycles) + phase) * (spec.wobble * 0.35);
          const px = x + nx * (offset + arcOffset + wobble);
          const py = y + ny * (offset + arcOffset + wobble);
          node.setAttribute('transform', `translate(${px},${py}) rotate(${angle + spec.spin * t + rotationJitter})`);
          node.setAttribute('opacity', String(spec.opacity));
        });

        if (spec.trailMode === 'sparks' && ts - lastTrailTime > spec.trailDensityMs) {
          lastTrailTime = ts;
          const spark = this._makeSvgEl('circle');
          spark.setAttribute('r', String(spec.trailSize + rng() * spec.trailSize));
          spark.setAttribute('cx', '0'); spark.setAttribute('cy', '0');
          spark.setAttribute('fill', accent || color); spark.setAttribute('opacity', String(spec.trailOpacity));
          spark.setAttribute('filter', 'url(#strong-glow)');
          const sg = this._makeSvgEl('g');
          sg.setAttribute('transform', `translate(${x + nx * wobbleBase},${y + ny * wobbleBase})`);
          sg.appendChild(spark);
          this.svg.insertBefore(sg, group);
          trailParticles.push({ el: sg, born: ts });
        }
        if (spec.trailMode === 'dissolve' && ts - lastTrailTime > spec.trailDensityMs) {
          lastTrailTime = ts;
          const ghost = this._makeProjectileShape(spec, ctx);
          const gg = this._makeSvgEl('g');
          gg.setAttribute('transform', `translate(${x + nx * wobbleBase},${y + ny * wobbleBase}) rotate(${angle})`);
          gg.setAttribute('opacity', String(spec.trailOpacity * 0.55));
          gg.appendChild(ghost);
          this.svg.insertBefore(gg, group);
          trailParticles.push({ el: gg, born: ts });
        }
        if (spec.trailMode === 'ribbon' && ts - lastTrailTime > spec.trailDensityMs) {
          lastTrailTime = ts;
          const dot = this._makeSvgEl('circle');
          dot.setAttribute('r', String(spec.trailSize));
          dot.setAttribute('cx', String(x + nx * wobbleBase)); dot.setAttribute('cy', String(y + ny * wobbleBase));
          dot.setAttribute('fill', accent || color); dot.setAttribute('opacity', String(spec.trailOpacity));
          dot.setAttribute('filter', 'url(#glow-filter)');
          this.svg.insertBefore(dot, group);
          trailParticles.push({ el: dot, born: ts });
        }
        if (spec.trailMode === 'smoke' && ts - lastTrailTime > spec.trailDensityMs) {
          lastTrailTime = ts;
          const puff = this._makeSvgEl('circle');
          puff.setAttribute('r', String(spec.trailSize * 1.6 + rng() * spec.trailSize));
          puff.setAttribute('cx', String(x + nx * wobbleBase));
          puff.setAttribute('cy', String(y + ny * wobbleBase));
          puff.setAttribute('fill', accent || color);
          puff.setAttribute('opacity', String(spec.trailOpacity * 0.55));
          puff.setAttribute('filter', 'url(#strong-glow)');
          this.svg.insertBefore(puff, group);
          trailParticles.push({ el: puff, born: ts });
        }

        trailParticles.forEach(p => {
          const age = (ts - p.born) / spec.trailLifeMs;
          p.el.setAttribute('opacity', String(Math.max(0, (1 - age) * 0.8)));
          if (age > 1) p.el.remove();
        });

        if (t < 1) { requestAnimationFrame(tick); }
        else { group.remove(); trailParticles.forEach(p => p.el.remove()); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  _makeProjectileShape(spec, ctx) {
    switch (spec.family) {
      case 'beam': {
        const el = this._makeSvgEl('ellipse');
        el.setAttribute('rx', String(spec.length / 2)); el.setAttribute('ry', String(spec.width / 2));
        el.setAttribute('fill', spec.color); el.setAttribute('filter', 'url(#strong-glow)');
        if (spec.accent) {
          el.setAttribute('stroke', spec.accent);
          el.setAttribute('stroke-width', String(spec.strokeWidth));
        }
        return el;
      }
      case 'bolt': {
        const el = this._makeSvgEl('polygon');
        const len = spec.length;
        const w = spec.width;
        el.setAttribute('points', `0,${-w} ${len * 0.6},${-w * 0.25} ${len * 0.3},${-w * 0.25} ${len * 0.75},${w} ${-w * 0.2},${w * 0.25} ${len * 0.15},${w * 0.25}`);
        el.setAttribute('fill', spec.color); el.setAttribute('filter', 'url(#strong-glow)');
        if (spec.accent) {
          el.setAttribute('stroke', spec.accent);
          el.setAttribute('stroke-width', String(Math.max(1.5, spec.strokeWidth * 0.8)));
        }
        return el;
      }
      case 'shard': {
        const el = this._makeSvgEl('path');
        const len = spec.length;
        const w = spec.width;
        el.setAttribute('d', `M${-len * 0.45},0 L${len * 0.1},${-w} L${len * 0.5},0 L${len * 0.08},${w} Z`);
        el.setAttribute('fill', spec.color); el.setAttribute('filter', 'url(#strong-glow)');
        if (spec.accent) {
          el.setAttribute('stroke', spec.accent);
          el.setAttribute('stroke-width', String(spec.strokeWidth));
        }
        return el;
      }
      case 'sigil': {
        const el = this._makeSvgEl('text');
        el.setAttribute('text-anchor', 'middle'); el.setAttribute('dominant-baseline', 'middle');
        el.setAttribute('font-size', String(spec.size)); el.setAttribute('fill', spec.accent || spec.color);
        el.textContent = spec.glyph; el.setAttribute('filter', 'url(#strong-glow)');
        return el;
      }
      case 'wave': {
        const el = this._makeSvgEl('path');
        const len = spec.length;
        const w = spec.width;
        el.setAttribute('d', `M${-len * 0.45},${w * 0.2} C${-len * 0.15},${-w * 1.3} ${len * 0.18},${-w * 1.2} ${len * 0.48},0 C${len * 0.14},${w * 1.2} ${-len * 0.1},${w * 1.1} ${-len * 0.45},${w * 0.2} Z`);
        el.setAttribute('fill', spec.color);
        el.setAttribute('filter', 'url(#strong-glow)');
        if (spec.accent) {
          el.setAttribute('stroke', spec.accent);
          el.setAttribute('stroke-width', String(spec.strokeWidth));
        }
        return el;
      }
      case 'orb':
      default: {
        const el = this._makeSvgEl('circle');
        el.setAttribute('r', String(spec.size * 0.5)); el.setAttribute('fill', spec.color);
        el.setAttribute('filter', 'url(#strong-glow)');
        if (spec.accent) {
          el.setAttribute('stroke', spec.accent);
          el.setAttribute('stroke-width', String(spec.strokeWidth));
        }
        return el;
      }
    }
  }

  // ─── IMPACT ─────────────────────────────────────────────────────────────────
  async animateImpact(layer, pos, ctx) {
    const spec = this._normalizeImpactSpec(layer, ctx);
    switch (spec.family) {
      case 'ring': {
        const ringCount = Math.max(1, spec.count);
        const promises = [];
        for (let i = 0; i < ringCount; i++) {
          const spread = Math.max(18, spec.spread * (1 - i * 0.14));
          const delayMs = i * spec.staggerMs;
          promises.push(this.delay(delayMs).then(() =>
            this._impactShockwaveRing(pos, spec.color, spread, spec.duration, { ...ctx, isRare: spec.isRare, accentColor: spec.accent, thickness: spec.thickness })
          ));
        }
        await Promise.all(promises);
        break;
      }
      case 'splatter':
        await this._impactSplatter(pos, spec.color, spec.spread, spec.duration, { ...ctx, count: spec.count, accentColor: spec.accent });
        break;
      case 'fracture':
        await this._impactCrack(pos, spec.color, spec.spread, spec.duration, { ...ctx, count: spec.count, accentColor: spec.accent, thickness: spec.thickness });
        break;
      case 'implosion':
        await this._impactImplosion(pos, spec.color, spec.spread, spec.duration, { ...ctx, accentColor: spec.accent, thickness: spec.thickness });
        break;
      case 'burst':
      default:
        await this._impactRadialBurst(pos, spec.color, spec.spread, spec.duration, { ...ctx, count: spec.count, accentColor: spec.accent, thickness: spec.thickness });
        break;
    }
  }

  async _impactRadialBurst(pos, color, spread, duration, ctx) {
    const count = Math.max(4, Math.round(ctx && ctx.count ? ctx.count : 8));
    const g = this._makeSvgEl('g');
    this.svg.appendChild(g);
    const lines = [];
    const accent = this._pickAccentColor({}, ctx);
    const thickness = ctx && ctx.thickness ? ctx.thickness : (ctx && ctx.isRare ? 4.5 : 3.5);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const line = this._makeSvgEl('line');
      line.setAttribute('x1', String(pos.x)); line.setAttribute('y1', String(pos.y));
      line.setAttribute('x2', String(pos.x)); line.setAttribute('y2', String(pos.y));
      line.setAttribute('stroke', accent && i % 2 === 1 ? accent : color); line.setAttribute('stroke-width', String(thickness));
      line.setAttribute('stroke-linecap', 'round'); line.setAttribute('filter', 'url(#glow-filter)');
      g.appendChild(line); lines.push({ el: line, angle });
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        const ease = t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2,3)/2;
        lines.forEach(({ el, angle }) => {
          const d = spread * ease;
          el.setAttribute('x2', String(pos.x + Math.cos(angle) * d));
          el.setAttribute('y2', String(pos.y + Math.sin(angle) * d));
          el.setAttribute('opacity', String(1 - ease));
        });
        if (t < 1) requestAnimationFrame(tick);
        else { g.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _impactShockwaveRing(pos, color, spread, duration, ctx) {
    const ring = this._makeSvgEl('circle');
    ring.setAttribute('cx', String(pos.x)); ring.setAttribute('cy', String(pos.y));
    ring.setAttribute('r', '5'); ring.setAttribute('fill', 'none');
    const thickness = ctx && ctx.thickness ? ctx.thickness : (ctx && ctx.isRare ? 5 : 4);
    ring.setAttribute('stroke', color); ring.setAttribute('stroke-width', String(thickness));
    ring.setAttribute('filter', 'url(#strong-glow)');
    this.svg.appendChild(ring);
    const accent = this._pickAccentColor({}, ctx);
    let accentRing = null;
    if (accent && ctx && ctx.isRare) {
      accentRing = this._makeSvgEl('circle');
      accentRing.setAttribute('cx', String(pos.x)); accentRing.setAttribute('cy', String(pos.y));
      accentRing.setAttribute('r', '10'); accentRing.setAttribute('fill', 'none');
      accentRing.setAttribute('stroke', accent); accentRing.setAttribute('stroke-width', '3');
      accentRing.setAttribute('filter', 'url(#strong-glow)');
      this.svg.appendChild(accentRing);
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        ring.setAttribute('r', String(5 + spread * t));
        ring.setAttribute('opacity', String(1 - t));
        ring.setAttribute('stroke-width', String(thickness * (1 - t * 0.45)));
        if (accentRing) {
          accentRing.setAttribute('r', String(10 + spread * t * 0.75));
          accentRing.setAttribute('opacity', String(Math.max(0, 0.7 - t)));
        }
        if (t < 1) requestAnimationFrame(tick);
        else { ring.remove(); if (accentRing) accentRing.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _impactSplatter(pos, color, spread, duration, ctx) {
    const count = Math.max(6, Math.round(ctx && ctx.count ? ctx.count : 12));
    const g = this._makeSvgEl('g');
    this.svg.appendChild(g);
    const dots = [];
    const rng = ctx && ctx.rng ? ctx.rng : Math.random;
    const accent = this._pickAccentColor({}, ctx);
    for (let i = 0; i < count; i++) {
      const angle = rng() * Math.PI * 2;
      const maxDist = spread * (0.5 + rng() * 0.5);
      const dot = this._makeSvgEl('circle');
      dot.setAttribute('cx', String(pos.x)); dot.setAttribute('cy', String(pos.y));
      dot.setAttribute('r', String(4 + rng() * 5)); dot.setAttribute('fill', accent && i % 3 === 0 ? accent : color);
      dot.setAttribute('filter', 'url(#glow-filter)');
      g.appendChild(dot); dots.push({ el: dot, angle, maxDist });
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        dots.forEach(({ el, angle, maxDist }) => {
          const d = maxDist * t;
          el.setAttribute('cx', String(pos.x + Math.cos(angle) * d));
          el.setAttribute('cy', String(pos.y + Math.sin(angle) * d));
          el.setAttribute('opacity', String(1 - t * t));
        });
        if (t < 1) requestAnimationFrame(tick);
        else { g.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _impactCrack(pos, color, spread, duration, ctx) {
    const count = Math.max(3, Math.round(ctx && ctx.count ? ctx.count : 5));
    const g = this._makeSvgEl('g');
    this.svg.appendChild(g);
    const paths = [];
    const rng = ctx && ctx.rng ? ctx.rng : Math.random;
    const accent = this._pickAccentColor({}, ctx);
    const thickness = ctx && ctx.thickness ? ctx.thickness : (ctx && ctx.isRare ? 3.5 : 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 + rng() * 0.4;
      const segs = 3;
      let pts = [[pos.x, pos.y]];
      for (let s = 1; s <= segs; s++) {
        const dist = (spread * s) / segs;
        const jitter = (rng() - 0.5) * 14;
        pts.push([pos.x + Math.cos(angle)*dist + Math.sin(angle)*jitter, pos.y + Math.sin(angle)*dist - Math.cos(angle)*jitter]);
      }
      const d = 'M' + pts.map(p => p.join(',')).join(' L');
      const path = this._makeSvgEl('path');
      path.setAttribute('d', d); path.setAttribute('stroke', accent && i % 2 === 0 ? accent : color);
      path.setAttribute('stroke-width', String(thickness)); path.setAttribute('fill', 'none');
      path.setAttribute('filter', 'url(#strong-glow)');
      g.appendChild(path); paths.push(path);
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        const opacity = t < 0.3 ? t / 0.3 : 1 - (t - 0.3) / 0.7;
        paths.forEach(p => p.setAttribute('opacity', String(opacity)));
        if (t < 1) requestAnimationFrame(tick);
        else { g.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _impactImplosion(pos, color, spread, duration, ctx) {
    const ring = this._makeSvgEl('circle');
    ring.setAttribute('cx', String(pos.x)); ring.setAttribute('cy', String(pos.y));
    ring.setAttribute('r', String(spread)); ring.setAttribute('fill', 'none');
    const thickness = ctx && ctx.thickness ? ctx.thickness : (ctx && ctx.isRare ? 5 : 4);
    ring.setAttribute('stroke', color); ring.setAttribute('stroke-width', String(thickness));
    ring.setAttribute('filter', 'url(#strong-glow)');
    this.svg.appendChild(ring);
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        ring.setAttribute('r', String(Math.max(0, spread * (1 - t))));
        ring.setAttribute('opacity', String(1 - t * 0.5));
        if (t < 1) requestAnimationFrame(tick);
        else { ring.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  // ─── STATUS APPLIER ──────────────────────────────────────────────────────────
  async animateStatusApplier(layer, pos, ctx) {
    const duration = (layer.timing && layer.timing.duration_ms) || 400;
    const color = layer.color || '#ffffff';
    const particle = layer.particle || layer.shape || 'drip';
    const repeat = layer.repeat || 3;
    const count = repeat * 3;
    const g = this._makeSvgEl('g');
    this.svg.appendChild(g);
    const particles = [];
    const rng = ctx && ctx.rng ? ctx.rng : Math.random;
    const accent = this._pickAccentColor(layer, ctx);
    for (let i = 0; i < count; i++) {
      const ox = (rng() - 0.5) * 50;
      const oy = (rng() - 0.5) * 30;
      const dot = this._makeSvgEl('circle');
      dot.setAttribute('r', String(4 + rng() * 4));
      dot.setAttribute('fill', accent && i % 4 === 0 ? accent : color); dot.setAttribute('opacity', '0.8');
      dot.setAttribute('filter', 'url(#glow-filter)');
      dot.setAttribute('cx', String(pos.x + ox)); dot.setAttribute('cy', String(pos.y + oy));
      g.appendChild(dot);
      const delay = rng() * duration * 0.5;
      const dirX = (rng() - 0.5) * 2;
      const dirY = particle === 'drip' ? 1 : particle === 'ember_fall' ? -1 : (rng() - 0.5) * 2;
      particles.push({ el: dot, startX: pos.x+ox, startY: pos.y+oy, dirX, dirY, delay, particle });
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const elapsed = ts - st;
        const totalT = elapsed / duration;
        particles.forEach(p => {
          const localT = Math.max(0, (elapsed - p.delay) / (duration - p.delay));
          if (localT <= 0) return;
          let vx = p.dirX * 12, vy;
          if (p.particle === 'arc_chain') { vx = Math.sin(localT * Math.PI * 3) * 20; vy = -localT * 40; }
          else if (p.particle === 'tendril') { vx = p.dirX*30 + Math.sin(localT*Math.PI*4)*15; vy = p.dirY*30 + Math.cos(localT*Math.PI*4)*15; }
          else if (p.particle === 'frost_crystal') { vx = p.dirX*25*localT; vy = p.dirY*25*localT; }
          else { vy = (p.dirY < 0 ? -1 : 1) * 35 * localT; if (p.particle === 'ember_fall') vx += Math.sin(localT*Math.PI*3)*6; }
          p.el.setAttribute('cx', String(p.startX + vx));
          p.el.setAttribute('cy', String(p.startY + vy));
          p.el.setAttribute('opacity', String(0.9 * (1 - localT)));
        });
        if (totalT < 1) requestAnimationFrame(tick);
        else { g.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  // ─── SCREEN ──────────────────────────────────────────────────────────────────
  async animateScreen(layer, ctx) {
    const duration = (layer.timing && layer.timing.duration_ms) || 300;
    const color = layer.color || '#ffffff';
    const effect = layer.effect || 'flash';
    if (effect === 'shake') return this._screenShake(duration, ctx);
    const rect = this._makeSvgEl('rect');
    const svgRect = this.svg.getBoundingClientRect();
    rect.setAttribute('x', '0'); rect.setAttribute('y', '0');
    rect.setAttribute('width', String(svgRect.width || 1200));
    rect.setAttribute('height', String(svgRect.height || 800));
    rect.setAttribute('fill', effect === 'vignette' ? '#000000' : color);
    this.svg.appendChild(rect);
    const accent = this._pickAccentColor(layer, ctx);
    let accentRect = null;
    if (accent && ctx && ctx.isRare && effect !== 'vignette') {
      accentRect = this._makeSvgEl('rect');
      accentRect.setAttribute('x', '0'); accentRect.setAttribute('y', '0');
      accentRect.setAttribute('width', String(svgRect.width || 1200));
      accentRect.setAttribute('height', String(svgRect.height || 800));
      accentRect.setAttribute('fill', accent);
      this.svg.appendChild(accentRect);
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        const opacity = effect === 'flash'
          ? (t < 0.3 ? (t/0.3)*0.82 : (1-(t-0.3)/0.7)*0.82)
          : (t < 0.4 ? (t/0.4)*0.62 : (1-(t-0.4)/0.6)*0.62);
        rect.setAttribute('opacity', String(opacity));
        if (accentRect) accentRect.setAttribute('opacity', String(opacity * 0.45));
        if (t < 1) requestAnimationFrame(tick);
        else { rect.remove(); if (accentRect) accentRect.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _screenShake(duration, ctx) {
    const combat = document.getElementById('screen-combat');
    if (!combat) return this.delay(duration);
    const rng = ctx && ctx.rng ? ctx.rng : Math.random;
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        const mag = (1 - t) * 10;
        combat.style.transform = `translate(${(rng()-0.5)*mag*2}px,${(rng()-0.5)*mag*2}px)`;
        if (t < 1) requestAnimationFrame(tick);
        else { combat.style.transform = ''; resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  // ─── AURA ────────────────────────────────────────────────────────────────────
  async animateAura(layer, pos, ctx) {
    const duration = (layer.timing && layer.timing.duration_ms) || 400;
    const color = layer.color || '#ffffff';
    switch (layer.shape || 'shield_shell') {
      case 'shield_shell': return this._auraShieldShell(pos, color, duration, ctx);
      case 'pulse_ring': return this._auraPulseRing(pos, color, duration, ctx);
      case 'charge_glow': return this._auraChargeGlow(pos, color, duration, ctx);
      default: return this._auraShieldShell(pos, color, duration, ctx);
    }
  }

  async _auraShieldShell(pos, color, duration, ctx) {
    const g = this._makeSvgEl('g');
    this.svg.appendChild(g);
    const accent = this._pickAccentColor({}, ctx);
    const ring = this._makeSvgEl('circle');
    ring.setAttribute('cx', String(pos.x)); ring.setAttribute('cy', String(pos.y));
    ring.setAttribute('r', '60'); ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', accent || color); ring.setAttribute('stroke-width', ctx && ctx.isRare ? '6' : '5');
    ring.setAttribute('filter', 'url(#strong-glow)'); g.appendChild(ring);
    const fill = this._makeSvgEl('circle');
    fill.setAttribute('cx', String(pos.x)); fill.setAttribute('cy', String(pos.y));
    fill.setAttribute('r', '60'); fill.setAttribute('fill', color);
    fill.setAttribute('opacity', ctx && ctx.isRare ? '0.22' : '0.16'); g.appendChild(fill);
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        const scale = 0.7 + t * 0.4;
        g.setAttribute('transform', `scale(${scale}) translate(${pos.x*(1/scale-1)},${pos.y*(1/scale-1)})`);
        g.setAttribute('opacity', String(t < 0.4 ? t/0.4 : 1-(t-0.4)/0.6));
        if (t < 1) requestAnimationFrame(tick);
        else { g.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  async _auraPulseRing(pos, color, duration, ctx) {
    const promises = [0, 1].map(i =>
      this.delay(i * duration / 2).then(() => this._impactShockwaveRing(pos, color, 50, duration / 2, ctx))
    );
    await Promise.all(promises);
  }

  async _auraChargeGlow(pos, color, duration, ctx) {
    const burst = this._makeSvgEl('circle');
    burst.setAttribute('cx', String(pos.x)); burst.setAttribute('cy', String(pos.y));
    burst.setAttribute('r', '20'); burst.setAttribute('fill', color);
    burst.setAttribute('filter', 'url(#strong-glow)');
    this.svg.appendChild(burst);
    const accent = this._pickAccentColor({}, ctx);
    let accentBurst = null;
    if (accent && ctx && ctx.isRare) {
      accentBurst = this._makeSvgEl('circle');
      accentBurst.setAttribute('cx', String(pos.x)); accentBurst.setAttribute('cy', String(pos.y));
      accentBurst.setAttribute('r', '10'); accentBurst.setAttribute('fill', accent);
      accentBurst.setAttribute('filter', 'url(#strong-glow)');
      this.svg.appendChild(accentBurst);
    }
    return new Promise(resolve => {
      let st = null;
      const tick = (ts) => {
        if (!st) st = ts;
        const t = Math.min((ts - st) / duration, 1);
        burst.setAttribute('r', String(20 + 80 * t));
        burst.setAttribute('opacity', String(t < 0.2 ? t/0.2 : (1-(t-0.2)/0.8)*0.8));
        if (accentBurst) {
          accentBurst.setAttribute('r', String(10 + 56 * t));
          accentBurst.setAttribute('opacity', String(Math.max(0, 0.55 - t * 0.45)));
        }
        if (t < 1) requestAnimationFrame(tick);
        else { burst.remove(); if (accentBurst) accentBurst.remove(); resolve(); }
      };
      requestAnimationFrame(tick);
    });
  }

  // ─── HELPERS ─────────────────────────────────────────────────────────────────
  _buildEffectContext(sourceCard, svgEffect) {
    const visualIdentity = (sourceCard && sourceCard.visual_identity) || {};
    return {
      seed: String((sourceCard && (sourceCard.visual_seed || sourceCard.id || sourceCard.name)) || 'effect'),
      accentColor: this._sanitizeColor(svgEffect && svgEffect.accent_color, this._sanitizeColor(visualIdentity.secondary_color, this._sanitizeColor(visualIdentity.accent_color, null))),
      runeGlyph: String((svgEffect && svgEffect.rune_glyph) || visualIdentity.sigil || '⬡').slice(0, 2),
      isRare: !!(sourceCard && sourceCard.rarity === 'rare')
    };
  }

  _withLayerContext(effectCtx, layer, layerIndex, targetEnemyId) {
    const seed = [
      effectCtx.seed,
      layerIndex,
      layer && layer.type,
      layer && (layer.descriptor || layer.primitive || layer.shape || layer.effect || layer.particle || layer.trail || 'base'),
      targetEnemyId || 'self'
    ].join('|');
    return {
      ...effectCtx,
      layerIndex,
      rng: this._makeRng(seed),
      accentColor: this._sanitizeColor(layer && layer.accent_color, effectCtx.accentColor)
    };
  }

  _pickAccentColor(layer, ctx) {
    return this._sanitizeColor(layer && layer.accent_color, ctx && ctx.accentColor);
  }

  _normalizeProjectileSpec(layer, ctx) {
    const descriptor = String(layer && (layer.descriptor || layer.primitive || layer.style || layer.profile || layer.shape) || 'projectile');
    const family = this._resolveProjectileFamily(descriptor);
    const ferocity = this._ferocityFactor(descriptor, ctx);
    const size = this._num(layer && layer.size, (ctx && ctx.isRare ? 34 : 25) * ferocity, 8, 88);
    const width = this._num(layer && layer.width, (family === 'beam' ? size * 0.42 : size * 0.76) * (0.92 + ferocity * 0.16), 2, 44);
    const length = this._num(layer && layer.length, (family === 'beam' ? size * 2.4 : size * 1.8) * (0.94 + ferocity * 0.18), 6, 128);
    const trailMode = this._resolveTrailMode(layer && layer.trail);
    return {
      family,
      duration: (layer.timing && layer.timing.duration_ms) || 300,
      color: layer.color || '#ffffff',
      accent: this._pickAccentColor(layer, ctx),
      glyph: String((layer && layer.glyph) || (ctx && ctx.runeGlyph) || '⬡').slice(0, 2),
      size,
      width,
      length,
      strokeWidth: this._num(layer && layer.thickness, (ctx && ctx.isRare ? 3.8 : 2.6) * ferocity, 1, 12),
      count: this._num(layer && layer.count, Math.round((ctx && ctx.isRare ? 2 : 1) * Math.min(2, ferocity)), 1, 6),
      spacing: this._num(layer && layer.spacing, Math.max(8, width * 1.2), 0, 48),
      opacity: this._num(layer && layer.opacity, Math.min(1, 0.92 + ferocity * 0.06), 0.1, 1),
      arcHeight: this._num(layer && layer.arc_height, family === 'wave' ? 12 * ferocity : 0, -120, 120),
      wobble: this._num(layer && layer.wobble, family === 'wave' || family === 'bolt' ? 5 * ferocity : 1.2 * (ferocity - 1), 0, 48),
      wobbleCycles: this._num(layer && layer.wobble_cycles, family === 'bolt' ? 2.1 : 1.45, 0.2, 8),
      spin: this._num(layer && layer.spin, family === 'sigil' ? 240 * ferocity : family === 'shard' ? 70 * (ferocity - 1) : 0, -1440, 1440),
      rotationJitter: this._num(layer && layer.rotation_jitter, 18, 0, 360),
      phaseOffset: this._num(layer && layer.phase_offset, 0, -720, 720),
      trailMode,
      trailDensityMs: this._num(layer && layer.trail_density_ms, (trailMode === 'ribbon' ? 16 : 28) / Math.min(1.5, ferocity), 8, 120),
      trailSize: this._num(layer && layer.trail_size, (family === 'beam' ? Math.max(3, width * 0.55) : Math.max(4, size * 0.24)) * Math.min(1.45, ferocity), 1, 30),
      trailLifeMs: this._num(layer && layer.trail_life_ms, trailMode === 'smoke' ? 340 : 250, 80, 800),
      trailOpacity: this._num(layer && layer.trail_opacity, Math.min(1, (trailMode === 'smoke' ? 0.42 : 0.88) * (0.94 + ferocity * 0.08)), 0.05, 1)
    };
  }

  _normalizeImpactSpec(layer, ctx) {
    const descriptor = String(layer && (layer.descriptor || layer.style || layer.profile || layer.shape) || 'impact');
    const ferocity = this._ferocityFactor(descriptor, ctx);
    return {
      family: this._resolveImpactFamily(descriptor),
      duration: (layer.timing && layer.timing.duration_ms) || 250,
      color: layer.color || '#ffffff',
      accent: this._pickAccentColor(layer, ctx),
      spread: this._num(layer && layer.spread, (ctx && ctx.isRare ? 62 : 52) * ferocity, 12, 200),
      count: this._num(layer && layer.count, Math.round((ctx && ctx.isRare ? 11 : 8) * Math.min(1.7, ferocity)), 1, 30),
      thickness: this._num(layer && layer.thickness, (ctx && ctx.isRare ? 6 : 4.4) * ferocity, 1, 16),
      staggerMs: this._num(layer && layer.stagger_ms, 44 / Math.min(1.6, ferocity), 0, 220),
      isRare: !!(ctx && ctx.isRare)
    };
  }

  _resolveProjectileFamily(descriptor) {
    return this._descriptorFamily(descriptor, [
      { family: 'sigil', keywords: ['rune', 'sigil', 'glyph', 'seal', 'mark'] },
      { family: 'bolt', keywords: ['bolt', 'lightning', 'fork', 'arc', 'thunder'] },
      { family: 'beam', keywords: ['beam', 'lance', 'spear', 'needle', 'ray', 'spike'] },
      { family: 'shard', keywords: ['shard', 'blade', 'knife', 'splinter', 'fang', 'comet'] },
      { family: 'wave', keywords: ['wave', 'slash', 'crescent', 'ripple', 'lash'] },
      { family: 'orb', keywords: ['orb', 'sphere', 'seed', 'tear', 'drop', 'nova'] }
    ], ['beam', 'shard', 'bolt', 'sigil', 'wave', 'orb']);
  }

  _resolveImpactFamily(descriptor) {
    return this._descriptorFamily(descriptor, [
      { family: 'implosion', keywords: ['implode', 'collapse', 'vacuum', 'sink', 'maw'] },
      { family: 'fracture', keywords: ['fracture', 'crack', 'rupture', 'split', 'shatter'] },
      { family: 'splatter', keywords: ['splatter', 'spray', 'bloom', 'eruption', 'spill'] },
      { family: 'ring', keywords: ['ring', 'shock', 'pulse', 'halo', 'wave'] },
      { family: 'burst', keywords: ['burst', 'impact', 'detonate', 'flare', 'hit'] }
    ], ['burst', 'ring', 'splatter', 'fracture', 'implosion']);
  }

  _resolveTrailMode(trail) {
    if (trail && typeof trail === 'object') {
      return this._resolveTrailMode(trail.mode || trail.kind || trail.style || trail.descriptor || '');
    }
    return this._descriptorFamily(String(trail || ''), [
      { family: 'smoke', keywords: ['smoke', 'mist', 'fog', 'ash', 'haze'] },
      { family: 'sparks', keywords: ['spark', 'ember', 'dust', 'glitter', 'static'] },
      { family: 'dissolve', keywords: ['dissolve', 'afterimage', 'ghost', 'fade', 'echo'] },
      { family: 'ribbon', keywords: ['ribbon', 'thread', 'trail', 'stream', 'wake'] }
    ], ['sparks', 'dissolve', 'ribbon', 'smoke', 'none']);
  }

  _ferocityFactor(descriptor, ctx) {
    const text = String(descriptor || '').toLowerCase();
    let factor = ctx && ctx.isRare ? 1.18 : 1;
    const brutal = ['fierce', 'violent', 'brutal', 'feral', 'predatory', 'savage', 'ravaging'];
    const piercing = ['spear', 'lance', 'spike', 'needle', 'fang', 'javelin', 'impale', 'pierce'];
    const explosive = ['burst', 'detonate', 'explosion', 'impact', 'nova', 'shock', 'eruption', 'slam'];
    const fracture = ['rupture', 'shatter', 'fracture', 'crack', 'split', 'rend', 'cleave'];
    const storm = ['storm', 'thunder', 'lightning', 'arc', 'maelstrom', 'tempest'];
    const collapse = ['implode', 'collapse', 'vacuum', 'maw', 'sink', 'graviton'];
    const soft = ['gentle', 'soft', 'glimmer', 'whisper', 'mist', 'petal', 'drift'];
    if (brutal.some(word => text.includes(word))) factor += 0.18;
    if (piercing.some(word => text.includes(word))) factor += 0.16;
    if (explosive.some(word => text.includes(word))) factor += 0.16;
    if (fracture.some(word => text.includes(word))) factor += 0.14;
    if (storm.some(word => text.includes(word))) factor += 0.12;
    if (collapse.some(word => text.includes(word))) factor += 0.14;
    if (soft.some(word => text.includes(word))) factor -= 0.12;
    return Math.max(0.88, Math.min(1.75, factor));
  }

  _descriptorFamily(descriptor, mappings, fallbacks) {
    const text = String(descriptor || '').toLowerCase();
    for (const mapping of mappings) {
      if (mapping.keywords.some(keyword => text.includes(keyword))) return mapping.family;
    }
    if (!text || text === 'none') return 'none';
    const idx = Math.floor(this._hash01(text) * fallbacks.length);
    return fallbacks[idx] || fallbacks[0];
  }

  _sanitizeColor(value, fallback) {
    return /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : fallback;
  }

  _num(value, fallback, min, max) {
    const num = Number(value);
    const resolved = Number.isFinite(num) ? num : fallback;
    if (!Number.isFinite(resolved)) return fallback;
    if (Number.isFinite(min) && resolved < min) return min;
    if (Number.isFinite(max) && resolved > max) return max;
    return resolved;
  }

  _hash01(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967296;
  }

  _makeRng(seedText) {
    let h = 1779033703 ^ seedText.length;
    for (let i = 0; i < seedText.length; i++) {
      h = Math.imul(h ^ seedText.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    return () => {
      h = Math.imul(h ^ (h >>> 16), 2246822507);
      h = Math.imul(h ^ (h >>> 13), 3266489909);
      h ^= h >>> 16;
      return (h >>> 0) / 4294967296;
    };
  }

  _makeSvgEl(tag) {
    return document.createElementNS('http://www.w3.org/2000/svg', tag);
  }
  delay(ms) { return new Promise(r => setTimeout(r, ms)); }
}

const FX = new EffectsRenderer();
