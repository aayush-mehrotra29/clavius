import { driveImageBlob, loadGround, groundHeight } from './drive-ground.js';

import { terrainProjection, slopePalette, slopeGradient } from './traverse-relief.js';

// Short-axis field of view, in local east/north meters.
const routeSpan = 120;
const overviewSpan = 640;
const routeLimit = 12;
const insideBoundary = p => Math.max(Math.abs(p.east_m), Math.abs(p.north_m)) <= routeLimit;
const rounded = p => ({
  east_m: Math.round(p.east_m * 10) / 10,
  north_m: Math.round(p.north_m * 10) / 10,
});

export function mountTraverseMap(host, flight, initialRoute, onChange) {
  const center = flight.landing;
  host.innerHTML = `<canvas class="route-surface" aria-label="Oblique landing site. Place waypoints here or enter their coordinates in the waypoint list."></canvas>
    <div class="route-heading"><h2></h2><p>Click to place waypoints inside the boundary. Drag a pin to move it.</p></div>
    <div class="route-layers" role="group" aria-label="Surface layer"><button type="button" aria-pressed="true">Relief</button><button type="button" aria-pressed="false">Slope</button></div>
    <div class="route-legend" hidden><span>Slope</span><i></i><span>0°</span><span>10°</span><span>20°+</span><small>Gray · no data</small></div>
    <div class="route-zoom"><button type="button" aria-label="Zoom in on surface">+</button><button type="button" aria-label="Zoom out on surface">−</button></div>
    <button type="button" class="route-overview" aria-label="Show landing site overview" title="Show landing site overview" hidden><canvas width="120" height="84" aria-hidden="true"></canvas></button>
    <div class="route-foot"><span class="route-scale"></span><span class="route-location"></span><span class="route-source">LROC · 1 m imagery · 2 m relief</span></div>
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
  const layerButtons = host.querySelectorAll('.route-layers button');
  const legend = host.querySelector('.route-legend');
  legend.querySelector('i').style.background = 'linear-gradient(to right, ' + slopeGradient + ')';
  let width = 0, height = 0, image, ground, imageHalf, projection, centerY;
  let slopeCanvas, slopes, showSlope = false;
  let pins = [];

  function message(text) {
    notice.textContent = text;
    notice.hidden = !text;
  }
  const pixelsPerMeter = () => Math.max(Math.min(width, height) / span,
    Math.max(width, height) / (2 * imageHalf));
  const pixel = p => [
    width / 2 + (p.east_m - center.east_m) * pixelsPerMeter(),
    height / 2 - (projection.ordinate(p.east_m,p.north_m) - centerY) * pixelsPerMeter(),
  ];
  function pointer(event) {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const east_m = center.east_m + (x - width / 2) / pixelsPerMeter();
    const projected = centerY - (y - height / 2) / pixelsPerMeter();
    return {x, y, east_m, north_m: projection.northAt(east_m, projected), projected};

  }
  function surfaceLine(a,b) {
    const steps = Math.max(1, Math.ceil(Math.hypot(b.east_m-a.east_m, b.north_m-a.north_m)/2));
    for (let i = 1; i <= steps; i++) {
      const t = i/steps;
      ctx.lineTo(...pixel({east_m:a.east_m+t*(b.east_m-a.east_m), north_m:a.north_m+t*(b.north_m-a.north_m)}));
    }
  }
  function draw() {
    if (!image || !width || !height) return;
    const scale = pixelsPerMeter();
    const sourceScale = image.width / (2 * imageHalf);
    const sw = width / scale * sourceScale, sh = height / scale * sourceScale;
    const sx = (imageHalf + center.east_m) * sourceScale - sw / 2;
    const sy = (imageHalf - centerY) * sourceScale - sh / 2;
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(showSlope ? slopeCanvas : image, sx, sy, sw, sh, 0, 0, width, height);

    const corners = [[-1,1],[1,1],[1,-1],[-1,-1]].map(([e,n]) => ({east_m:e*routeLimit,north_m:n*routeLimit}));
    ctx.beginPath(); ctx.moveTo(...pixel(corners[0]));
    corners.forEach((p,i) => surfaceLine(p,corners[(i+1)%4]));
    ctx.strokeStyle = 'rgba(255,255,255,.65)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    const [cx, cy] = pixel(center);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    route.forEach((point,i) => surfaceLine(i ? route[i-1] : center, point));
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

    pins = [];
    route.forEach((point,index) => {
      const [x,y] = pixel(point);
      let labelY = y - 14;
      while (pins.some(pin => Math.hypot(pin.x-x,pin.y-labelY) < 22)) labelY -= 22;
      ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x,labelY);
      ctx.strokeStyle = '#ebefff'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.beginPath(); ctx.arc(x,labelY,10,0,2*Math.PI);
      ctx.fillStyle = '#3366ef'; ctx.fill(); ctx.stroke();
      ctx.fillStyle = 'white'; ctx.fillText(String(index+1),x,labelY);
      pins.push({x,y:labelY});
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
    const dpr = Math.min(devicePixelRatio, 3);
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
  layerButtons.forEach((button,i) => button.onclick = () => {
    if (!image) return;
    showSlope = i === 1;
    layerButtons.forEach((b,k) => b.setAttribute('aria-pressed',String(i === k)));
    legend.hidden = !showSlope;
    host.querySelector('.route-source').textContent = showSlope ? 'LROC stereo · 2 m terrain' : 'LROC · 1 m imagery · 2 m relief';
    locationLabel.textContent = '';
    draw();
  });
  canvas.onpointerdown = e => {
    if (!image || e.button !== 0 || !e.isPrimary) return;
    cancelAnimationFrame(frame);
    const p = pointer(e);
    let index = -1, distance = 14;
    route.forEach((point, i) => {
      const [x,y] = pixel(point);
      const d = Math.min(Math.hypot(x-p.x,y-p.y), Math.hypot(pins[i].x-p.x,pins[i].y-p.y));
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
    const ix = Math.floor((p.east_m + imageHalf) * image.width / (2*imageHalf));
    const iy = Math.floor((imageHalf - p.projected) * image.height / (2*imageHalf));
    const dn = ix >= 0 && ix < image.width && iy >= 0 && iy < image.height ? slopes[iy*image.width+ix] : 0;
    const detail = showSlope ? (dn ? ((dn-1)/4).toFixed(1)+'° slope' : 'No stereo support')
      : 'Δh '+(Number.isFinite(p.north_m) ? groundHeight(ground,p.east_m,p.north_m).toFixed(1) : '—')+' m';
    locationLabel.textContent = Number.isFinite(p.north_m) ? `E ${p.east_m.toFixed(1)} · N ${p.north_m.toFixed(1)} · ${detail}` : '';
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
    const [index, catalogue] = await Promise.all(['index', 'traverse-relief'].map(async name => {
      const res = await fetch('/data/drive/' + name + '.json', {signal});
      if (!res.ok) throw Error('Site map catalogue unavailable.');
      return res.json();
    }));
    const terrain = index.sites[center.site_id]?.levels.find(l => l.level === 'drive');
    const layers = catalogue.sites[center.site_id];
    if (!layers || !terrain || flight.sources?.terrain_sha256?.[terrain.source] !== terrain.source_sha256 ||
        center.terrain_realization_id !== 'nominal' || terrain.sha256 !== layers.terrain_sha256)
      throw Error('Surface data does not match this landing.');
    const [grid, reliefBlob, slopeBlob] = await Promise.all([
      loadGround(terrain,signal), driveImageBlob(layers.relief,signal,'Relief layer'), driveImageBlob(layers.slope,signal,'Slope layer')
    ]);
    const [relief,encoded] = await Promise.all([createImageBitmap(reliefBlob),createImageBitmap(slopeBlob)]);
    if (signal.aborted) { relief.close(); encoded.close(); return; }
    ground = grid; imageHalf = catalogue.half_extent_m;
    projection = terrainProjection(ground,catalogue.tilt_deg);
    centerY = projection.ordinate(center.east_m,center.north_m);
    slopeCanvas = document.createElement('canvas');
    slopeCanvas.width = encoded.width; slopeCanvas.height = encoded.height;
    const paint = slopeCanvas.getContext('2d');
    paint.drawImage(encoded,0,0); encoded.close();
    const raster = paint.getImageData(0,0,slopeCanvas.width,slopeCanvas.height);
    const colors = slopePalette();
    slopes = new Uint8Array(slopeCanvas.width*slopeCanvas.height);
    for (let i=0; i<slopes.length; i++) {
      const j=i*4, dn=raster.data[j], rgb=colors[dn];
      slopes[i]=dn;
      raster.data[j]=rgb[0]; raster.data[j+1]=rgb[1]; raster.data[j+2]=rgb[2];
    }
    paint.putImageData(raster,0,0);
    image = relief;
    const inset = overview.querySelector('canvas'), thumb = inset.getContext('2d');
    const sw = overviewSpan * inset.width / inset.height * relief.width / (2*imageHalf);
    const sh = sw*inset.height/inset.width;
    thumb.drawImage(relief,(relief.width-sw)/2,(relief.height-sh)/2,sw,sh,0,0,inset.width,inset.height);
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
    dispose() { abort.abort(); cancelAnimationFrame(frame); resize.disconnect(); host.replaceChildren(); image?.close(); image = null; },
  };
}
