import { driveImageBlob, loadGround, groundHeight } from './drive-ground.js';

// Short-axis field of view, in local east/north meters.
const routeSpan = 40;
const overviewSpan = 640;
const routeLimit = 12;
const insideBoundary = p => Math.max(Math.abs(p.east_m), Math.abs(p.north_m)) <= routeLimit;
const rounded = p => ({
  east_m: Math.round(p.east_m * 10) / 10,
  north_m: Math.round(p.north_m * 10) / 10,
});

export function mountTraverseMap(host, flight, initialRoute, onChange) {
  const center = flight.landing;
  host.innerHTML = `<canvas class="route-surface" aria-label="North-up landing site. Place waypoints here or enter their coordinates in the waypoint list."></canvas>
    <div class="route-heading"><h2></h2><p>Click to place waypoints inside the boundary. Drag a pin to move it.</p></div>
    <div class="route-zoom"><button type="button" aria-label="Zoom in on surface">+</button><button type="button" aria-label="Zoom out on surface">−</button></div>
    <button type="button" class="route-overview" aria-label="Show landing site overview" title="Show landing site overview" hidden><canvas width="120" height="84" aria-hidden="true"></canvas></button>
    <div class="route-foot"><span class="route-scale"></span><span class="route-location"></span><span>LROC NAC · 1 m/px · North up</span></div>
    <p class="route-notice" role="status">Loading site imagery…</p>`;
  host.querySelector('h2').textContent = center.name;
  const canvas = host.querySelector('.route-surface');
  const ctx = canvas.getContext('2d');
  const notice = host.querySelector('.route-notice');
  const locationLabel = host.querySelector('.route-location');
  const scaleBar = host.querySelector('.route-scale');
  const zoom = host.querySelectorAll('.route-zoom button');
  const overview = host.querySelector('.route-overview');
  const abort = new AbortController();
  const { signal } = abort;
  let route = initialRoute, span = routeSpan, frame, drag;
  let width = 0, height = 0, image, ground, imageHalf;

  function message(text) {
    notice.textContent = text;
    notice.hidden = !text;
  }
  const pixelsPerMeter = () => Math.min(width, height) / span;
  const pixel = p => [
    width / 2 + (p.east_m - center.east_m) * pixelsPerMeter(),
    height / 2 - (p.north_m - center.north_m) * pixelsPerMeter(),
  ];
  function pointer(event) {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    return {x, y, east_m: center.east_m + (x - width / 2) / pixelsPerMeter(),
      north_m: center.north_m - (y - height / 2) / pixelsPerMeter()};
  }
  function draw() {
    if (!image || !width || !height) return;
    const scale = pixelsPerMeter();
    const sourceScale = image.width / (2 * imageHalf);
    const sw = width / scale * sourceScale, sh = height / scale * sourceScale;
    const sx = (imageHalf + center.east_m) * sourceScale - sw / 2;
    const sy = (imageHalf - center.north_m) * sourceScale - sh / 2;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(image, sx, sy, sw, sh, 0, 0, width, height);

    const [left, top] = pixel({east_m: -routeLimit, north_m: routeLimit});
    ctx.strokeStyle = 'rgba(255,255,255,.65)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(left, top, 2 * routeLimit * scale, 2 * routeLimit * scale);
    ctx.setLineDash([]);

    const [cx, cy] = pixel(center);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    for (const point of route) ctx.lineTo(...pixel(point));
    ctx.lineWidth = 4; ctx.strokeStyle = '#171717'; ctx.stroke();
    ctx.lineWidth = 2; ctx.strokeStyle = '#f3f3f3'; ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, 2 * Math.PI);
    ctx.fillStyle = '#151515'; ctx.fill();
    ctx.strokeStyle = 'white'; ctx.stroke();
    ctx.font = '500 12px Inter, system-ui';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.lineWidth = 3; ctx.strokeStyle = '#191919'; ctx.strokeText('Landing', cx, cy + 19);
    ctx.fillStyle = 'white'; ctx.fillText('Landing', cx, cy + 19);

    route.forEach((point, index) => {
      const [x, y] = pixel(point);
      ctx.beginPath(); ctx.arc(x, y, 10, 0, 2 * Math.PI);
      ctx.fillStyle = '#3366ef'; ctx.fill();
      ctx.strokeStyle = 'white'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = 'white'; ctx.fillText(String(index + 1), x, y);
    });
    const meters = span > 160 ? 50 : span > 60 ? 20 : 5;
    scaleBar.style.width = meters * scale + 'px';
    scaleBar.textContent = meters + ' m';
    zoom[0].disabled = span <= 28;
    zoom[1].disabled = span >= overviewSpan;
    overview.title = span >= overviewSpan ? 'Zoom to landing' : 'Show landing site overview';
    overview.setAttribute('aria-label', overview.title);
  }

  const resize = new ResizeObserver(() => {
    width = host.clientWidth; height = host.clientHeight;
    const dpr = Math.min(devicePixelRatio, 2);
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  });
  resize.observe(host);
  function setSpan(value) {
    cancelAnimationFrame(frame);
    span = Math.max(28, Math.min(overviewSpan, value));
    draw();
  }
  zoom[0].onclick = () => setSpan(span / 1.6);
  zoom[1].onclick = () => setSpan(span * 1.6);
  overview.onclick = () => setSpan(span >= overviewSpan ? routeSpan : overviewSpan);
  canvas.onpointerdown = e => {
    if (!image || e.button !== 0 || !e.isPrimary) return;
    cancelAnimationFrame(frame);
    const p = pointer(e);
    let index = -1, distance = 14;
    route.forEach((point, i) => {
      const [x, y] = pixel(point), d = Math.hypot(x - p.x, y - p.y);
      if (d <= distance) { distance = d; index = i; }
    });
    drag = {index, id: e.pointerId, before: route, start: p};
    canvas.setPointerCapture(e.pointerId);
  };
  function dragPoint(p) {
    if (drag.index < 0) return p;
    const original = drag.before[drag.index];
    return {east_m: original.east_m + p.east_m - drag.start.east_m,
      north_m: original.north_m + p.north_m - drag.start.north_m};
  }
  canvas.onpointerleave = () => { locationLabel.textContent = ''; };
  canvas.onpointermove = e => {
    if (!image) return;
    const p = pointer(e);
    locationLabel.textContent = insideBoundary(p)
      ? `E ${p.east_m.toFixed(1)} · N ${p.north_m.toFixed(1)} · Δh ${groundHeight(ground, p.east_m, p.north_m).toFixed(1)} m` : '';
    if (!drag || drag.id !== e.pointerId || drag.index < 0) return;
    const point = dragPoint(p);
    if (insideBoundary(point)) {
      route = route.map((v, i) => i === drag.index ? rounded(point) : v);
      draw();
    }
  };
  canvas.onpointercancel = () => {
    if (drag) { route = drag.before; drag = null; draw(); }
  };
  canvas.onpointerup = e => {
    if (!drag || drag.id !== e.pointerId) return;
    const point = dragPoint(pointer(e)), {index, before} = drag;
    drag = null;
    if (!insideBoundary(point)) {
      route = before; draw(); message('Place the waypoint inside the 24 m boundary.'); return;
    }
    if (index < 0 && route.length >= 5) {
      message('Five waypoints placed. Move or remove an existing pin.'); return;
    }
    route = index < 0 ? [...route, rounded(point)] : route.map((v, i) => i === index ? rounded(point) : v);
    onChange(route);
  };
  async function load() {
    const [site, imagery] = await Promise.all(['index', 'imagery'].map(async name => {
      const res = await fetch('/data/drive/' + name + '.json', {signal});
      if (!res.ok) throw Error('Site map catalogue unavailable.');
      return (await res.json()).sites[center.site_id];
    }));
    const terrain = site?.levels.find(l => l.level === 'drive'), tile = imagery?.drive;
    if (!tile || !terrain || flight.sources?.terrain_sha256?.[terrain.source] !== terrain.source_sha256 ||
        center.terrain_realization_id !== 'nominal' || tile.half_extent_m !== terrain.half_extent_m)
      throw Error('Surface data does not match this landing.');
    const [grid, blob] = await Promise.all([loadGround(terrain, signal), driveImageBlob(tile, signal)]);
    const bitmap = await createImageBitmap(blob);
    if (signal.aborted) { bitmap.close(); return; }

    // Change display brightness once at native resolution; preserve the registered pixel positions.
    image = document.createElement('canvas');
    image.width = bitmap.width; image.height = bitmap.height;
    const paint = image.getContext('2d');
    paint.filter = 'brightness(2.5)'; paint.drawImage(bitmap, 0, 0); bitmap.close();
    ground = grid; imageHalf = tile.half_extent_m;
    const inset = overview.querySelector('canvas'), thumb = inset.getContext('2d');
    const sw = overviewSpan * inset.width / inset.height;
    thumb.drawImage(image, imageHalf + center.east_m - sw / 2, imageHalf - center.north_m - overviewSpan / 2,
      sw, overviewSpan, 0, 0, inset.width, inset.height);
    overview.hidden = false; message('');
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { draw(); return; }
    const start = performance.now();
    function focus(now) {
      const t = Math.max(0, Math.min(1, (now - start) / 1250));
      span = routeSpan * (overviewSpan / routeSpan) ** ((1 - t) ** 2);
      draw();
      if (t < 1) frame = requestAnimationFrame(focus);
    }
    frame = requestAnimationFrame(focus);
  }
  load().catch(e => { if (!signal.aborted) message(e.message); });
  return {
    update(points) { route = points; if (image) message(''); draw(); },
    dispose() { abort.abort(); cancelAnimationFrame(frame); resize.disconnect(); host.replaceChildren(); image = null; },
  };
}
