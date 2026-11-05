import * as THREE from './vendor/three/three.module.js';

/** Small, self-contained guide character. Coordinates passed to pointAt are viewport pixels. */
export function createGuideRobot(host, { reducedMotion = false } = {}) {
  const fallbackURL = new URL('./assets/robot-reference.webp', import.meta.url).href;
  let active = true, disposed = false, failed = false, pointing = false;
  let frame = 0, lastFrame = -Infinity, renderer, fallback, observer;
  let targetX = 0, targetY = 0, hasTarget = false;
  let poseAngle = 0, poseSide = -1;
  const geometries = new Set(), materials = new Set();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 30);
  camera.position.set(0, 0.23, 7.2);
  camera.lookAt(0, 0.22, 0);
  const robot = new THREE.Group();
  scene.add(robot);
  const rememberMaterial = material => (materials.add(material), material);
  const white = rememberMaterial(new THREE.MeshPhysicalMaterial({ color: 0xf7fbff, roughness: 0.19, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.12 }));
  const edgeWhite = rememberMaterial(new THREE.MeshPhysicalMaterial({ color: 0xe0edf2, roughness: 0.25, metalness: 0.12, clearcoat: 0.85 }));
  const black = rememberMaterial(new THREE.MeshPhysicalMaterial({ color: 0x02070c, roughness: 0.2, metalness: 0.08, clearcoat: 1 }));
  const cyan = rememberMaterial(new THREE.MeshBasicMaterial({ color: 0x08aaff, toneMapped: false }));
  function mesh(geometry, material, parent = robot) {
    geometries.add(geometry);
    const result = new THREE.Mesh(geometry, material);
    parent.add(result);
    return result;
  }
  const bodyProfile = [
    [0, -1.22], [0.14, -1.19], [0.29, -1.06], [0.41, -0.82],
    [0.51, -0.5], [0.59, -0.12], [0.63, 0.2], [0.63, 0.37],
    [0.59, 0.43], [0.47, 0.46], [0.3, 0.44], [0, 0.42],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  mesh(new THREE.LatheGeometry(bodyProfile, 64), white).scale.z = 0.78;
  const neck = mesh(new THREE.SphereGeometry(0.4, 40, 24), edgeWhite);
  neck.position.y = 0.45;
  neck.scale.set(1, 0.25, 0.8);
  const head = new THREE.Group();
  head.position.y = 1.08;
  robot.add(head);
  const shell = mesh(new THREE.SphereGeometry(1, 64, 48), white, head);
  shell.scale.set(0.76, 0.68, 0.61);
  // An oval patch follows the actual head curvature; no flat plate or box visor.
  const vertices = [0, -0.025, 0.628], indices = [];
  const rings = 12, segments = 64;
  for (let ring = 1; ring <= rings; ring++) {
    const radius = ring / rings;
    for (let i = 0; i < segments; i++) {
      const angle = i / segments * Math.PI * 2;
      const x = 0.605 * radius * Math.cos(angle);
      const y = 0.415 * radius * Math.sin(angle) - 0.025;
      const z = 0.61 * Math.sqrt(Math.max(0, 1 - (x / 0.76) ** 2 - (y / 0.68) ** 2)) + 0.018;
      vertices.push(x, y, z);
      if (ring === 1) indices.push(0, 1 + i, 1 + (i + 1) % segments);
      else {
        const a = 1 + (ring - 2) * segments + i;
        const b = 1 + (ring - 2) * segments + (i + 1) % segments;
        const c = 1 + (ring - 1) * segments + i;
        const d = 1 + (ring - 1) * segments + (i + 1) % segments;
        indices.push(a, c, d, a, d, b);
      }
    }
  }
  const visor = new THREE.BufferGeometry();
  visor.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  visor.setIndex(indices);
  visor.computeVertexNormals();
  mesh(visor, black, head);
  for (const side of [-1, 1]) {
    const eye = mesh(new THREE.SphereGeometry(1, 32, 24), cyan, head);
    eye.scale.set(0.14, 0.095, 0.035);
    eye.position.set(side * 0.23, 0.015, 0.607);
    eye.rotation.y = side * 0.22;
  }
  const arms = [];
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.62, 0.26, 0.025);
    robot.add(pivot);
    const joint = mesh(new THREE.SphereGeometry(0.15, 24, 16), edgeWhite, pivot);
    joint.scale.set(0.85, 1, 0.9);
    const profile = [[0, 0.09], [0.11, 0.05], [0.18, -0.1], [0.19, -0.34], [0.16, -0.67], [0.11, -0.94], [0.045, -1.1], [0, -1.13]].reverse().map(([x, y]) => new THREE.Vector2(x, y));
    const flipper = mesh(new THREE.LatheGeometry(profile, 40), white, pivot);
    flipper.scale.z = 0.58;
    flipper.position.x = side * 0.04;
    pivot.rotation.z = side * 0.12;
    arms.push(pivot);
  }
  scene.add(new THREE.HemisphereLight(0xe8f7ff, 0x75808c, 3));
  const key = new THREE.DirectionalLight(0xffffff, 4.1);
  key.position.set(-3, 5, 5); scene.add(key);
  const rim = new THREE.DirectionalLight(0xa9e3ff, 2.7);
  rim.position.set(4, 2, -3); scene.add(rim);

  function showFallback() {
    if (disposed || failed) return;
    failed = true;
    cancelAnimationFrame(frame); frame = 0;
    if (renderer) renderer.domElement.style.display = 'none';
    fallback = document.createElement('img');
    fallback.src = fallbackURL;
    fallback.alt = '';
    fallback.setAttribute('aria-hidden', 'true');
    Object.assign(fallback.style, { width: '100%', height: '100%', objectFit: 'contain', display: 'block', pointerEvents: 'none', borderRadius: '35%' });
    host.appendChild(fallback);
  }
  function updateDirection() {
    if (!hasTarget) return;
    const bounds = host.getBoundingClientRect();
    const dx = targetX - (bounds.left + bounds.width / 2);
    const dy = targetY - (bounds.top + bounds.height / 2);
    poseSide = dx < 0 ? -1 : 1;
    poseAngle = Math.min(2.65, Math.max(0.45, Math.atan2(Math.abs(dx), dy)));
  }
  function applyPose(time, immediate = false) {
    if (pointing) updateDirection();
    const selected = pointing ? poseAngle : 0.12;
    const lerp = reducedMotion || immediate ? 1 : 0.22;
    arms.forEach((arm, index) => {
      const side = index === 0 ? -1 : 1;
      const angle = side * (side === poseSide ? selected : 0.12);
      arm.rotation.z += (angle - arm.rotation.z) * lerp;
      arm.rotation.x = pointing && side === poseSide ? -0.12 : 0;
    });
    const yaw = pointing ? poseSide * 0.1 : -0.08;
    robot.rotation.y += (yaw - robot.rotation.y) * lerp;
    robot.position.y = reducedMotion ? 0 : Math.sin(time * 0.0014) * 0.045;
    head.rotation.z = reducedMotion ? 0 : Math.sin(time * 0.0008) * 0.015;
  }
  function render(time, immediate = false) {
    if (disposed || failed || !renderer) return;
    applyPose(time, immediate);
    try { renderer.render(scene, camera); } catch { showFallback(); }
  }
  function animate(time) {
    frame = 0;
    if (!active || disposed || failed || document.hidden) return;
    if (time - lastFrame >= 1000 / 30) { lastFrame = time; render(time); }
    if (!reducedMotion && !failed) frame = requestAnimationFrame(animate);
  }
  function wake(immediate = false) {
    if (!active || disposed || failed || document.hidden) return;
    if (reducedMotion || immediate) render(performance.now(), true);
    if (!reducedMotion && !frame) frame = requestAnimationFrame(animate);
  }
  function resize() {
    if (disposed) return;
    updateDirection();
    const rect = host.getBoundingClientRect();
    if (renderer && !failed && rect.width > 0 && rect.height > 0) {
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(rect.width, rect.height, false);
      camera.aspect = rect.width / rect.height;
      camera.updateProjectionMatrix();
      if (!document.hidden) render(performance.now(), reducedMotion || !active);
      wake();
    }
  }
  function visibilityChange() {
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else wake(true);
  }
  function contextLost(event) { event.preventDefault(); showFallback(); }
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.12;
    renderer.domElement.setAttribute('aria-hidden', 'true');
    Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%', pointerEvents: 'none' });
    renderer.domElement.addEventListener('webglcontextlost', contextLost);
    host.appendChild(renderer.domElement);
  } catch { showFallback(); }
  document.addEventListener('visibilitychange', visibilityChange);
  window.addEventListener('resize', resize);
  if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(host); }
  resize();
  return {
    pointAt(x, y) {
      if (disposed || !Number.isFinite(x) || !Number.isFinite(y)) return;
      targetX = x; targetY = y; hasTarget = true; updateDirection();
      if (!document.hidden) render(performance.now(), reducedMotion || !active);
      wake();
    },
    setPointing(value) {
      pointing = Boolean(value);
      if (!document.hidden) render(performance.now(), reducedMotion || !active);
      wake();
    },
    setReducedMotion(value) {
      reducedMotion = Boolean(value);
      cancelAnimationFrame(frame); frame = 0;
      if (!document.hidden) render(performance.now(), reducedMotion || !active);
      wake();
    },
    setActive(value) {
      active = Boolean(value);
      if (active) wake(true); else { cancelAnimationFrame(frame); frame = 0; }
    },
    resize,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      document.removeEventListener('visibilitychange', visibilityChange);
      window.removeEventListener('resize', resize);
      for (const geometry of geometries) geometry.dispose();
      for (const material of materials) material.dispose();
      if (renderer) {
        renderer.domElement.removeEventListener('webglcontextlost', contextLost);
        renderer.dispose();
        renderer.domElement.remove();
      }
      fallback?.remove();
      scene.clear();
    },
  };
}
