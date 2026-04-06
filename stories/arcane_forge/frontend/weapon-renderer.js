/* Weapon Renderer — Three.js 3D procedural weapons */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

var W = 200;
var H = 280;

// Cache: one renderer shared across all weapon displays
var sharedRenderer = null;
function getRenderer() {
  if (!sharedRenderer) {
    sharedRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    sharedRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    sharedRenderer.toneMapping = THREE.ACESFilmicToneMapping;
    sharedRenderer.toneMappingExposure = 1.2;
  }
  return sharedRenderer;
}

// ── Color helpers ─────────────────────────────────────────────────────

function hexToColor(hex) {
  return new THREE.Color(hex || "#888888");
}

function adjustBright(hex, amt) {
  var c = hexToColor(hex);
  var hsl = {};
  c.getHSL(hsl);
  hsl.l = Math.max(0, Math.min(1, hsl.l + amt / 255));
  c.setHSL(hsl.h, hsl.s, hsl.l);
  return c;
}

// ── Materials ─────────────────────────────────────────────────────────

function bladeMaterial(color, emissiveColor, emissiveIntensity) {
  return new THREE.MeshStandardMaterial({
    color: hexToColor(color),
    metalness: 0.85,
    roughness: 0.2,
    emissive: hexToColor(emissiveColor || color),
    emissiveIntensity: emissiveIntensity || 0,
  });
}

function handleMaterial(color) {
  return new THREE.MeshStandardMaterial({
    color: hexToColor(color),
    metalness: 0.1,
    roughness: 0.8,
  });
}

function guardMaterial(color) {
  return new THREE.MeshStandardMaterial({
    color: hexToColor(color),
    metalness: 0.7,
    roughness: 0.3,
  });
}

function gemMaterial(color) {
  return new THREE.MeshStandardMaterial({
    color: hexToColor(color),
    metalness: 0.3,
    roughness: 0.1,
    emissive: hexToColor(color),
    emissiveIntensity: 0.8,
    transparent: true,
    opacity: 0.85,
  });
}

// ── Weapon builders ───────────────────────────────────────────────────

function buildSword(shape, colors) {
  var group = new THREE.Group();
  var blade = shape.blade || {};
  var guard = shape.guard || {};
  var handle = shape.handle || {};

  var bLen = (blade.length || 0.6) * 3;
  var bW = (blade.width || 0.15) * 1.2;
  var taper = blade.taper !== undefined ? blade.taper : 0.5;
  var hLen = (handle.length || 0.25) * 2.5;
  var tipW = bW * (1 - taper);

  // Handle
  var hGeo = new THREE.CylinderGeometry(0.06, 0.06, hLen, 8);
  var hMesh = new THREE.Mesh(hGeo, handleMaterial(colors.handle));
  hMesh.position.y = hLen / 2;
  group.add(hMesh);

  // Guard
  var gw = (guard.width || 0.25) * 1.5;
  var guardStyle = guard.style || "cross";
  var gMat = guardMaterial(colors.guard);
  if (guardStyle === "ring" || guardStyle === "disc") {
    var gGeo = new THREE.TorusGeometry(gw / 2, 0.04, 8, 16);
    var gMesh = new THREE.Mesh(gGeo, gMat);
    gMesh.position.y = hLen;
    gMesh.rotation.x = Math.PI / 2;
    group.add(gMesh);
  } else {
    var gGeo2 = new THREE.BoxGeometry(gw, 0.08, 0.12);
    var gMesh2 = new THREE.Mesh(gGeo2, gMat);
    gMesh2.position.y = hLen;
    group.add(gMesh2);
  }

  // Blade — extruded shape
  var bladeShape = new THREE.Shape();
  bladeShape.moveTo(-bW / 2, 0);
  bladeShape.lineTo(-tipW / 2, bLen);
  bladeShape.lineTo(tipW / 2, bLen);
  bladeShape.lineTo(bW / 2, 0);
  bladeShape.closePath();

  var extrudeSettings = { depth: 0.04, bevelEnabled: true, bevelThickness: 0.01, bevelSize: 0.01, bevelSegments: 2 };
  var bladeGeo = new THREE.ExtrudeGeometry(bladeShape, extrudeSettings);
  bladeGeo.rotateX(-Math.PI / 2);
  bladeGeo.translate(0, 0, -0.02);
  var bMesh = new THREE.Mesh(
    bladeGeo,
    bladeMaterial(colors.blade, colors.edge_glow, 0.3)
  );
  bMesh.position.y = hLen + 0.04;
  bMesh.rotation.x = Math.PI / 2;
  group.add(bMesh);

  return group;
}

function buildAxe(shape, colors, isHammer) {
  var group = new THREE.Group();
  var blade = shape.blade || {};
  var handle = shape.handle || {};

  var hLen = (handle.length || 0.35) * 3;
  var headW = (blade.width || 0.2) * 2;
  var headH = (blade.length || 0.4) * 1.5;

  // Handle (long shaft)
  var hGeo = new THREE.CylinderGeometry(0.05, 0.05, hLen, 8);
  var hMesh = new THREE.Mesh(hGeo, handleMaterial(colors.handle));
  hMesh.position.y = hLen / 2;
  group.add(hMesh);

  // Head
  if (isHammer) {
    var headGeo = new THREE.BoxGeometry(headW, headH * 0.6, headH * 0.6);
    var headMesh = new THREE.Mesh(headGeo, bladeMaterial(colors.blade, colors.edge_glow, 0.2));
    headMesh.position.y = hLen;
    group.add(headMesh);
  } else {
    // Axe blade — half-disc shape
    var axeShape = new THREE.Shape();
    axeShape.moveTo(0, 0);
    axeShape.quadraticCurveTo(-headW, headH * 0.3, -headW * 0.6, headH);
    axeShape.lineTo(0, headH * 0.7);
    axeShape.closePath();
    var axeGeo = new THREE.ExtrudeGeometry(axeShape, { depth: 0.06, bevelEnabled: true, bevelThickness: 0.01, bevelSize: 0.01 });
    axeGeo.translate(0, 0, -0.03);
    var axeMesh = new THREE.Mesh(axeGeo, bladeMaterial(colors.blade, colors.edge_glow, 0.3));
    axeMesh.position.y = hLen - headH * 0.3;
    group.add(axeMesh);
  }

  return group;
}

function buildSpear(shape, colors) {
  var group = new THREE.Group();
  var handle = shape.handle || {};
  var blade = shape.blade || {};
  var hLen = (handle.length || 0.4) * 4;
  var tipLen = (blade.length || 0.3) * 1.5;

  // Shaft
  var sGeo = new THREE.CylinderGeometry(0.03, 0.03, hLen, 8);
  var sMesh = new THREE.Mesh(sGeo, handleMaterial(colors.handle));
  sMesh.position.y = hLen / 2;
  group.add(sMesh);

  // Spearhead (cone)
  var tGeo = new THREE.ConeGeometry(0.08, tipLen, 4);
  var tMesh = new THREE.Mesh(tGeo, bladeMaterial(colors.blade, colors.edge_glow, 0.4));
  tMesh.position.y = hLen + tipLen / 2;
  group.add(tMesh);

  return group;
}

function buildDagger(shape, colors) {
  var group = buildSword(shape, colors);
  group.scale.set(0.8, 0.7, 0.8);
  return group;
}

function buildStaff(shape, colors) {
  var group = new THREE.Group();
  var handle = shape.handle || {};
  var hLen = (handle.length || 0.4) * 4;

  // Shaft
  var sGeo = new THREE.CylinderGeometry(0.04, 0.05, hLen, 8);
  var sMesh = new THREE.Mesh(sGeo, handleMaterial(colors.handle));
  sMesh.position.y = hLen / 2;
  group.add(sMesh);

  // Crystal orb on top
  var oGeo = new THREE.IcosahedronGeometry(0.15, 1);
  var oMesh = new THREE.Mesh(oGeo, gemMaterial(colors.edge_glow || colors.blade));
  oMesh.position.y = hLen + 0.15;
  group.add(oMesh);

  // Prongs holding the crystal
  for (var i = 0; i < 3; i++) {
    var a = (i / 3) * Math.PI * 2;
    var pGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.3, 4);
    var pMesh = new THREE.Mesh(pGeo, guardMaterial(colors.guard));
    pMesh.position.set(Math.cos(a) * 0.08, hLen + 0.05, Math.sin(a) * 0.08);
    pMesh.rotation.z = Math.cos(a) * 0.3;
    pMesh.rotation.x = Math.sin(a) * 0.3;
    group.add(pMesh);
  }

  return group;
}

function buildBow(shape, colors) {
  var group = new THREE.Group();
  var blade = shape.blade || {};
  var bLen = (blade.length || 0.6) * 3;

  // Bow limb (curved tube)
  var curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(-0.8, bLen / 2, 0),
    new THREE.Vector3(0, bLen, 0)
  );
  var tubeGeo = new THREE.TubeGeometry(curve, 20, 0.035, 8, false);
  var tubeMesh = new THREE.Mesh(tubeGeo, handleMaterial(colors.blade || colors.handle));
  group.add(tubeMesh);

  // Bowstring
  var stringPoints = [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0.1, bLen / 2, 0),
    new THREE.Vector3(0, bLen, 0),
  ];
  var stringGeo = new THREE.BufferGeometry().setFromPoints(stringPoints);
  var stringMat = new THREE.LineBasicMaterial({ color: hexToColor(colors.edge_glow || "#e0e0e0"), linewidth: 1 });
  var stringLine = new THREE.Line(stringGeo, stringMat);
  group.add(stringLine);

  // Grip wrap
  var gripGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.3, 8);
  var gripMesh = new THREE.Mesh(gripGeo, handleMaterial(colors.handle));
  gripMesh.position.set(-0.3, bLen / 2, 0);
  group.add(gripMesh);

  return group;
}

function buildScythe(shape, colors) {
  var group = new THREE.Group();
  var handle = shape.handle || {};
  var blade = shape.blade || {};
  var hLen = (handle.length || 0.4) * 4;

  // Shaft
  var sGeo = new THREE.CylinderGeometry(0.035, 0.04, hLen, 8);
  var sMesh = new THREE.Mesh(sGeo, handleMaterial(colors.handle));
  sMesh.position.y = hLen / 2;
  group.add(sMesh);

  // Curved blade
  var curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(0, hLen, 0),
    new THREE.Vector3(-0.6, hLen + 0.5, 0),
    new THREE.Vector3(-0.8, hLen - 0.2, 0)
  );
  var bladeGeo = new THREE.TubeGeometry(curve, 12, 0.02, 4, false);
  var bladeMesh = new THREE.Mesh(bladeGeo, bladeMaterial(colors.blade, colors.edge_glow, 0.4));
  group.add(bladeMesh);

  return group;
}

function buildGauntlet(shape, colors) {
  var group = new THREE.Group();
  var col = colors.blade || "#78909c";

  // Palm
  var palmGeo = new THREE.BoxGeometry(0.3, 0.15, 0.2);
  var palmMesh = new THREE.Mesh(palmGeo, bladeMaterial(col, colors.edge_glow, 0.1));
  palmMesh.position.y = 0.2;
  group.add(palmMesh);

  // Fingers
  for (var i = 0; i < 4; i++) {
    var fx = -0.1 + i * 0.07;
    var fGeo = new THREE.CylinderGeometry(0.025, 0.02, 0.2, 6);
    var fMesh = new THREE.Mesh(fGeo, bladeMaterial(col, colors.edge_glow, 0.1));
    fMesh.position.set(fx, 0.37, 0);
    fMesh.rotation.z = (i - 1.5) * 0.05;
    group.add(fMesh);
  }

  // Thumb
  var tGeo = new THREE.CylinderGeometry(0.025, 0.02, 0.15, 6);
  var tMesh = new THREE.Mesh(tGeo, bladeMaterial(col, colors.edge_glow, 0.1));
  tMesh.position.set(0.18, 0.22, 0);
  tMesh.rotation.z = -0.4;
  group.add(tMesh);

  return group;
}

function buildWhip(shape, colors) {
  var group = new THREE.Group();
  var handle = shape.handle || {};
  var hLen = 0.4;

  // Handle
  var hGeo = new THREE.CylinderGeometry(0.04, 0.05, hLen, 8);
  var hMesh = new THREE.Mesh(hGeo, handleMaterial(colors.handle));
  hMesh.position.y = hLen / 2;
  group.add(hMesh);

  // Whip body (sinuous curve)
  var points = [];
  var segments = 30;
  for (var i = 0; i <= segments; i++) {
    var t = i / segments;
    var x = Math.sin(t * Math.PI * 3) * 0.15 * t;
    var y = hLen + t * 2.5;
    var z = Math.cos(t * Math.PI * 2) * 0.1 * t;
    points.push(new THREE.Vector3(x, y, z));
  }
  var curve = new THREE.CatmullRomCurve3(points);
  var whipGeo = new THREE.TubeGeometry(curve, 30, 0.02, 6, false);
  var whipMesh = new THREE.Mesh(whipGeo, bladeMaterial(colors.blade, colors.edge_glow, 0.2));
  group.add(whipMesh);

  return group;
}

// ── Weapon builder dispatch ───────────────────────────────────────────

function buildWeapon(type, shape, colors) {
  switch (type) {
    case "axe": return buildAxe(shape, colors, false);
    case "hammer": return buildAxe(shape, colors, true);
    case "spear": return buildSpear(shape, colors);
    case "dagger": return buildDagger(shape, colors);
    case "staff": return buildStaff(shape, colors);
    case "bow": return buildBow(shape, colors);
    case "scythe": return buildScythe(shape, colors);
    case "gauntlet": return buildGauntlet(shape, colors);
    case "whip": return buildWhip(shape, colors);
    default: return buildSword(shape, colors);
  }
}

// ── Particles ─────────────────────────────────────────────────────────

function createParticles(color, count, spread) {
  var positions = new Float32Array(count * 3);
  for (var i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * spread;
    positions[i * 3 + 1] = (Math.random() - 0.5) * spread;
    positions[i * 3 + 2] = (Math.random() - 0.5) * spread;
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  var mat = new THREE.PointsMaterial({
    color: hexToColor(color),
    size: 0.03,
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Points(geo, mat);
}

// ── Ornament ──────────────────────────────────────────────────────────

function addOrnament(group, ornament, colors, y) {
  if (!ornament || ornament === "none") return;
  var col = colors.ornament || colors.edge_glow || "#e040fb";

  if (ornament === "gem" || ornament === "crystal" || ornament === "rune_stone") {
    var geo = ornament === "crystal"
      ? new THREE.OctahedronGeometry(0.06)
      : new THREE.SphereGeometry(0.05, 8, 8);
    var mesh = new THREE.Mesh(geo, gemMaterial(col));
    mesh.position.y = y;
    group.add(mesh);
  } else if (ornament === "skull") {
    var sGeo = new THREE.SphereGeometry(0.06, 8, 6);
    var sMesh = new THREE.Mesh(sGeo, new THREE.MeshStandardMaterial({ color: 0xddddcc, roughness: 0.9 }));
    sMesh.position.y = y;
    sMesh.scale.set(1, 1.2, 0.9);
    group.add(sMesh);
  } else if (ornament === "eye") {
    var eGeo = new THREE.SphereGeometry(0.05, 8, 8);
    var eMesh = new THREE.Mesh(eGeo, gemMaterial(col));
    eMesh.position.y = y;
    group.add(eMesh);
    var pupilGeo = new THREE.SphereGeometry(0.02, 6, 6);
    var pupilMesh = new THREE.Mesh(pupilGeo, new THREE.MeshBasicMaterial({ color: 0x000000 }));
    pupilMesh.position.set(0, y, 0.04);
    group.add(pupilMesh);
  }
}

// ── Point light from weapon ───────────────────────────────────────────

function addWeaponLight(scene, color, intensity, y) {
  var light = new THREE.PointLight(hexToColor(color), intensity, 5);
  light.position.set(0, y, 0.5);
  scene.add(light);
  return light;
}

// ── Main render ───────────────────────────────────────────────────────

function renderWeapon(container, weapon) {
  container.innerHTML = "";

  var shape = weapon.weapon_shape || {};
  var vis = weapon.visual || {};
  var colors = shape.colors || {};
  var rarity = weapon.rarity || "common";
  var type = weapon.type || "sword";

  // Create canvas
  var canvas = document.createElement("canvas");
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.cursor = "grab";
  container.appendChild(canvas);

  var w = container.clientWidth || W;
  var h = container.clientHeight || H;

  // Scene
  var scene = new THREE.Scene();

  // Camera (positioned after weapon is built, see below)
  var camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 50);

  // Renderer
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;

  // Lights
  var ambient = new THREE.AmbientLight(0x404050, 0.6);
  scene.add(ambient);

  var dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
  dirLight.position.set(3, 5, 4);
  scene.add(dirLight);

  var rimLight = new THREE.DirectionalLight(0x8888ff, 0.4);
  rimLight.position.set(-3, 2, -2);
  scene.add(rimLight);

  // Weapon glow light (placed after centering below)
  var glowColor = vis.glow_color || colors.edge_glow || "#ffffff";
  var glowIntensity = (vis.glow_intensity || 0.3) * 3;
  if (rarity === "legendary") glowIntensity *= 2;
  else if (rarity === "epic") glowIntensity *= 1.5;

  // Build weapon
  var weaponGroup = buildWeapon(type, shape, colors);
  scene.add(weaponGroup);

  // Ornament
  var handleLen = (shape.handle ? shape.handle.length || 0.25 : 0.25) * 2.5;
  addOrnament(weaponGroup, shape.ornament, colors, handleLen);

  // Center the weapon at origin using bounding box
  var bbox = new THREE.Box3().setFromObject(weaponGroup);
  var center = new THREE.Vector3();
  bbox.getCenter(center);
  weaponGroup.position.sub(center);

  var bboxSize = new THREE.Vector3();
  bbox.getSize(bboxSize);
  var maxDim = Math.max(bboxSize.x, bboxSize.y, bboxSize.z);
  var camDist = maxDim * 2.2;

  // Position camera to frame the weapon
  camera.position.set(camDist * 0.5, camDist * 0.4, camDist * 0.7);
  camera.lookAt(0, 0, 0);

  // Weapon glow light relative to weapon center
  addWeaponLight(scene, glowColor, glowIntensity, 0);

  // Particles centered around weapon
  var particleCount = rarity === "legendary" ? 80 : rarity === "epic" ? 50 : rarity === "rare" ? 30 : 15;
  var particleSpread = maxDim * 1.2;
  var particles = createParticles(glowColor, particleCount, particleSpread);
  scene.add(particles);

  // Controls — orbit around weapon center
  var controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.5;
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.minPolarAngle = Math.PI * 0.2;
  controls.maxPolarAngle = Math.PI * 0.8;

  // Post-processing (bloom for rare+)
  var composer = null;
  if (rarity === "rare" || rarity === "epic" || rarity === "legendary") {
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    var bloomStrength = rarity === "legendary" ? 1.2 : rarity === "epic" ? 0.8 : 0.4;
    var bloomPass = new UnrealBloomPass(
      new THREE.Vector2(w, h),
      bloomStrength,
      0.4,
      0.85
    );
    composer.addPass(bloomPass);
  }

  // Animation loop
  var animFrame = null;
  var clock = new THREE.Clock();

  function animate() {
    animFrame = requestAnimationFrame(animate);
    var t = clock.getElapsedTime();

    // Weapon gentle bob
    weaponGroup.position.y = Math.sin(t * 0.8) * 0.03;
    weaponGroup.rotation.y = Math.sin(t * 0.3) * 0.05;

    // Particle drift
    var posArr = particles.geometry.attributes.position.array;
    for (var i = 0; i < posArr.length; i += 3) {
      posArr[i + 1] += 0.002;
      if (posArr[i + 1] > particleSpread) posArr[i + 1] = -particleSpread * 0.5;
    }
    particles.geometry.attributes.position.needsUpdate = true;
    particles.rotation.y = t * 0.1;

    controls.update();

    if (composer) {
      composer.render();
    } else {
      renderer.render(scene, camera);
    }
  }

  animate();

  // Cleanup on container removal (MutationObserver)
  var observer = new MutationObserver(function (mutations) {
    for (var m of mutations) {
      for (var n of m.removedNodes) {
        if (n === canvas || n.contains && n.contains(canvas)) {
          cancelAnimationFrame(animFrame);
          renderer.dispose();
          observer.disconnect();
          return;
        }
      }
    }
  });
  if (container.parentNode) {
    observer.observe(container.parentNode, { childList: true, subtree: true });
  }
}

// ── Import OrbitControls workaround ─────────────────────────────────

// OrbitControls loaded as ES module — import at top

// ── Export ───────────────────────────────────────────────────────────

window.WeaponRenderer = { render: renderWeapon, W: W, H: H };
