import './landing.css';
import { mountBenchmarks } from './landing-benchmarks.js';
import { landingSections, landingFooter } from './landing-content.js';

// The scene is decorative art, separate from the explorer's NASA surface data.
export function mountLanding(root, { logo }) {
  root.innerHTML = `
    <div class="landing-page">
      <a class="landing-skip" href="#sky">Skip navigation</a>
      <header class="sky-header">
        <nav class="sky-nav" aria-label="Main navigation">
          <a class="brand sky-brand" href="/#sky" aria-label="Clavius home">${logo}</a>
          <button class="sky-menu-toggle" type="button" aria-controls="sky-sections" aria-expanded="false">Sections</button>
          <div class="sky-links" id="sky-sections">
            <a href="#about">Overview</a>
            <a href="#mission">Surface mission</a>
            <a href="#sources">Lunar atlas</a>
            <a href="#users">Who it’s for</a>
            <a href="#benchmarks">Benchmarks</a>
          </div>
          <a class="get-started sky-explore" href="/app">Get started</a>
        </nav>
      </header>
      <main aria-label="Clavius">
        <section class="sky-hero" id="sky" aria-labelledby="hero-title">
          <div class="sky-backdrop" aria-hidden="true"></div>
          <canvas class="sky-flights" aria-hidden="true"></canvas>
          <div class="sky-intro">
            <h1 id="hero-title">Mission Planning <span>from Earth to the Moon</span></h1>
            <a class="get-started sky-start" href="/app">Get started</a>
          </div>
        </section>
        ${landingSections()}
        <section id="benchmarks" class="benchmarks story-width" aria-labelledby="benchmark-title"></section>
      </main>
      ${landingFooter(logo)}
    </div>`;

  mountBenchmarks(root.querySelector('#benchmarks'));

  const stepButtons = [...root.querySelectorAll('[data-step]')];
  const stepCopy = root.querySelectorAll('[data-step-copy]');
  const scenes = root.querySelectorAll('[data-scene]');
  const stepSwitch = root.querySelector('.step-switch');
  function selectStep(index) {
    stepSwitch.style.setProperty('--step', index);
    stepButtons.forEach((button, i) => {
      const active = index === i;
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      stepCopy[i].inert = !active;
      stepCopy[i].toggleAttribute('data-current', active);
      scenes[i].toggleAttribute('data-current', active);
    });
  }
  stepButtons.forEach((button, index) => {
    button.addEventListener('click', () => selectStep(index));
    button.addEventListener('keydown', event => {
      const last = stepButtons.length - 1;
      const target = { Home: 0, End: last, ArrowRight: (index + 1) % stepButtons.length,
        ArrowLeft: (index + last) % stepButtons.length }[event.key];
      if (target === undefined) return;
      event.preventDefault();
      selectStep(target);
      stepButtons[target].focus();
    });
  });

  const atlasChapters = [...root.querySelectorAll('.atlas-chapter')];
  const atlasFrames = root.querySelectorAll('.atlas-frame');
  const stackedAtlas = matchMedia('(max-width: 800px), (max-height: 540px)');
  let currentLayer = 0;
  function updateAtlas() {
    if (stackedAtlas.matches) return;
    const focusY = window.innerHeight * .54;
    const latest = atlasChapters.findLastIndex(chapter => chapter.getBoundingClientRect().top <= focusY);
    const next = Math.max(0, latest);
    if (next === currentLayer) return;
    atlasFrames[currentLayer].removeAttribute('data-current');
    atlasFrames[next].setAttribute('data-current', '');
    currentLayer = next;
  }

  const header = root.querySelector('.sky-header');
  const hero = root.querySelector('.sky-hero');
  const links = [...root.querySelectorAll('.sky-links a')];
  const navSections = links.map(link => ({ link, section: root.querySelector(link.hash) }));
  const menuToggle = header.querySelector('.sky-menu-toggle');
  const compactNav = matchMedia('(max-width: 960px)');
  function closeMenu() {
    menuToggle.setAttribute('aria-expanded', 'false');
  }
  menuToggle.addEventListener('click', () => {
    menuToggle.setAttribute('aria-expanded', String(menuToggle.getAttribute('aria-expanded') !== 'true'));
  });
  for (const { link, section } of navSections) {
    link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (menuToggle.getAttribute('aria-expanded') === 'true') {
        section.tabIndex = -1;
        section.focus({ preventScroll: true });
      }
      closeMenu();
    });
  }
  header.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') {
      closeMenu();
      menuToggle.focus();
    }
  });
  function dismissOutside(event) {
    if (!header.contains(event.target)) closeMenu();
  }
  document.addEventListener('pointerdown', dismissOutside);
  document.addEventListener('focusin', dismissOutside);
  compactNav.addEventListener('change', closeMenu);

  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const canvas = root.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  let width = 0, height = 0, flights = [], stars = [];
  let frame = 0, previousTime = 0, sceneTime = 0, visible = true, disposed = false;
  let scrollFrame = 0;

  function updateNav() {
    scrollFrame = 0;
    updateAtlas();
    const y = Math.max(0, scrollY);
    header.classList.toggle('is-floating', y > 64);
    const current = navSections.find(({ section }) => {
      const bounds = section.getBoundingClientRect();
      return bounds.top <= 130 && bounds.bottom > 130;
    });
    for (const link of links) {
      if (link === current?.link) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
  }
  const onScroll = () => { if (!scrollFrame) scrollFrame = requestAnimationFrame(updateNav); };
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  updateNav();

  // Deterministic placement avoids a different composition on every resize.
  let seed;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  function resize() {
    width = hero.clientWidth; height = hero.clientHeight;
    const ratio = Math.min(devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx?.setTransform(ratio, 0, 0, ratio, 0, 0);
    seed = 1947;
    stars = Array.from({ length: width < 600 ? 80 : 190 }, () => ({
      x: random() * width, y: random() * height * .76,
      r: .22 + random() * .6, alpha: .12 + random() * .46, phase: random() * Math.PI * 2,
    }));
    flights = Array.from({ length: width < 600 ? 16 : 30 }, (_, i) => ({
      x: random(), y: random(), speed: .006 + random() * .012,
      drift: (i % 5 === 0 ? -.3 : .15 + random() * .38),
      size: .5 + random() * .85, alpha: .35 + random() * .55,
      trail: 15 + random() * 35, phase: random() * 9,
    }));
    draw();
  }

  function drawRocket(flight) {
    const progress = (flight.y + sceneTime * flight.speed) % 1;
    const y = height + 80 - progress * (height + 180);
    const x = ((flight.x * width + progress * flight.drift * width) % (width + 120)) - 60;
    const angle = Math.atan2(-height - 180, flight.drift * width);
    const size = flight.size;
    ctx.save(); ctx.translate(x, y); ctx.rotate(angle);
    ctx.globalAlpha = flight.alpha;
    const trail = flight.trail * size;
    const exhaust = ctx.createLinearGradient(-trail, 0, -3, 0);
    exhaust.addColorStop(0, 'rgba(173,188,255,0)');
    exhaust.addColorStop(.55, 'rgba(188,200,255,.04)');
    exhaust.addColorStop(.88, 'rgba(252,195,147,.36)');
    exhaust.addColorStop(1, 'rgba(255,246,228,.9)');
    ctx.fillStyle = exhaust;
    ctx.beginPath(); ctx.moveTo(-3, -size * .62); ctx.quadraticCurveTo(-trail * .3, -size * 1.4, -trail, 0);
    ctx.quadraticCurveTo(-trail * .3, size * 1.4, -3, size * .62); ctx.fill();
    const glow = ctx.createRadialGradient(-3, 0, 0, -3, 0, size * 5);
    glow.addColorStop(0, 'rgba(255,236,211,.5)'); glow.addColorStop(.3, 'rgba(255,184,126,.12)'); glow.addColorStop(1, 'rgba(255,184,126,0)');
    ctx.fillStyle = glow; ctx.fillRect(-3 - size * 5, -size * 5, size * 10, size * 10);
    const metal = ctx.createLinearGradient(0, -size, 0, size);
    metal.addColorStop(0, '#e9edf5'); metal.addColorStop(.4, '#c6cede'); metal.addColorStop(1, '#55617c');
    ctx.fillStyle = metal;
    ctx.beginPath(); ctx.moveTo(4.5 * size, 0); ctx.quadraticCurveTo(2 * size, -size, -2.7 * size, -size * .65);
    ctx.lineTo(-3.6 * size, -1.45 * size); ctx.lineTo(-3.3 * size, 1.45 * size); ctx.lineTo(-2.7 * size, size * .65);
    ctx.quadraticCurveTo(2 * size, size, 4.5 * size, 0); ctx.fill();
    ctx.fillStyle = '#fff8e9'; ctx.fillRect(-4 * size, -size * .35, 1.8 * size, size * .7);
    ctx.restore();
  }
  function draw() {
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    for (const star of stars) {
      ctx.globalAlpha = star.alpha * (.8 + .2 * Math.sin(sceneTime * .25 + star.phase));
      ctx.fillStyle = '#dce4ff'; ctx.beginPath(); ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2); ctx.fill();
    }
    for (const flight of flights) drawRocket(flight);
    ctx.globalAlpha = 1;
  }
  function tick(now) {
    frame = 0;
    if (disposed || !visible || document.hidden || motion.matches) return;
    if (now - previousTime >= 1000 / 30) {
      sceneTime += Math.min((now - previousTime) / 1000, .06);
      previousTime = now; draw();
    }
    frame = requestAnimationFrame(tick);
  }
  function resume() {
    cancelAnimationFrame(frame); frame = 0; previousTime = performance.now();
    if (!motion.matches && visible && !document.hidden) frame = requestAnimationFrame(tick);
    else draw();
  }
  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; resume(); });
  const resizeObserver = new ResizeObserver(resize);
  observer.observe(hero); resizeObserver.observe(hero);
  motion.addEventListener('change', resume);
  document.addEventListener('visibilitychange', resume);
  resize(); resume();
  const anchor = document.getElementById(location.hash.slice(1));
  if (anchor && root.contains(anchor)) anchor.scrollIntoView();
  return () => {
    disposed = true; cancelAnimationFrame(frame); cancelAnimationFrame(scrollFrame);
    observer.disconnect(); resizeObserver.disconnect();
    motion.removeEventListener('change', resume);
    document.removeEventListener('visibilitychange', resume);
    window.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);
    compactNav.removeEventListener('change', closeMenu);
    document.removeEventListener('pointerdown', dismissOutside);
    document.removeEventListener('focusin', dismissOutside);
  };
}
