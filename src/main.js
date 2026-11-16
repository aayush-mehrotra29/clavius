import './style.css';
import { mountSimulation } from './simulation.js';
import { mountLanding } from './landing.js';
import { createIcons, ArrowUp, Play, Pause, ArrowUpRight, ArrowRight, ArrowLeft, Globe2, Mountain, Search, Crosshair, Plus, Minus, RotateCcw, Layers, Info, X, ChevronDown, ChevronRight, MapPin, SlidersHorizontal, Menu, Grid2X2, Maximize, Check, MousePointer2, Navigation, ExternalLink } from 'lucide';
import { ElevationGrid, regions, formatCoordinate as coord } from './lunar.js';

const iconSet = {ArrowUp,Play,Pause,ArrowUpRight,ArrowRight,ArrowLeft,Globe2,Mountain,Search,Crosshair,Plus,Minus,RotateCcw,Layers,Info,X,ChevronDown,ChevronRight,MapPin,SlidersHorizontal,Menu,Grid2X2,Maximize,Check,MousePointer2,Navigation,ExternalLink};
const icon = (name, cls='') => `<i data-lucide="${name}" class="${cls}" aria-hidden="true"></i>`;
const icons = () => createIcons({icons:iconSet,attrs:{'stroke-width':1.5}});
const logo = `<img class="brand-mark" src="/images/clavius-mark.svg?v=3" width="28" height="28" alt="" aria-hidden="true"><span class="brand-wordmark">Clavius</span>`;
const root = document.querySelector('#app');
let viewer, grid, activeRegion, mode='globe', filter='all', search='', cleanup;
let alive=0;
function navigate() {
  // Native fragment navigation on the landing page keeps the walkthrough and focus intact.
  if (location.pathname === '/' && root.querySelector('.landing-page')) return;
  const path=location.pathname.replace(/\/$/,'');
  const atlasParams=['region','view','lat','lon'].some(k=>new URLSearchParams(location.search).has(k));
  if(path==='/app'&&!atlasParams){
    const generation=++alive;cleanup?.();cleanup=null;viewer?.dispose();viewer=null;
    document.title='Mission — Clavius';window.scrollTo(0,0);root.replaceChildren();
    import('./expedition.js').then(({mountExpedition})=>{if(alive===generation)cleanup=mountExpedition(root,{logo,icon,icons});});
    return;
  }
  if(location.pathname.replace(/\/$/,'')==='/app/drive'){
    const generation=++alive;cleanup?.();cleanup=null;viewer?.dispose();viewer=null;
    document.title='VIPER surface drive — Clavius';window.scrollTo(0,0);
    root.innerHTML='<p role="status">Opening rover drive…</p>';
    import('./drive-view.js').then(({mountDrive})=>{if(alive===generation)cleanup=mountDrive(root,{logo,icon,icons});});
    return;
  }
  if(location.pathname.replace(/\/$/,'')==='/app/simulation'){
    if(document.querySelector('.sim-workspace'))return;
    alive++;cleanup?.();cleanup=null;viewer?.dispose();viewer=null;
    document.title='Mission simulation — Clavius';window.scrollTo(0,0);
    cleanup=mountSimulation(root,{logo,icon,icons});return;
  }
  const isApp=path==='/app/atlas'||path==='/app';
  if(isApp && document.querySelector('.workspace:not(.sim-workspace)')) return;
  alive++;
  cleanup?.(); cleanup=null; viewer?.dispose(); viewer=null;
  window.scrollTo(0,0);
  isApp ? renderApp() : renderLanding();
}
function renderLanding() {
  document.title='Clavius — Mission Planning from Earth to the Moon';
  cleanup=mountLanding(root,{logo,icon});
  icons();
}
function renderApp() {
  document.title='Lunar explorer — Clavius';
  const param=new URLSearchParams(location.search).get('region');
  activeRegion=regions.find(r=>r.id===param)||regions[0];
  filter='all'; search='';
  mode=new URLSearchParams(location.search).get('view')==='terrain'?'terrain':'globe';
  root.innerHTML=`
    <div class="workspace">
      <header class="app-header">
        <a class="brand" href="/" aria-label="Clavius home">${logo}</a>
        <a class="explorer-sim-link" href="/app">Mission</a>
        <nav class="main-nav" aria-label="Workspace"><span class="nav-active">${icon('globe-2')} Explorer</span><a href="/app/simulation" class="explorer-sim-link">${icon('sliders-horizontal')} Simulation</a><a href="/app/drive" class="explorer-sim-link">${icon('navigation')} Rover drive</a></nav>
        <div class="header-right"><button class="text-button" data-action="sources">${icon('info')} <span>Data & sources</span></button></div>
      </header>
      <div class="work-body">
        <aside class="sidebar" aria-label="Region browser">
          <div class="side-heading"><div><h1>Explore the Moon</h1></div><button class="icon-button mobile-close" data-action="sidebar" aria-label="Close region browser">${icon('x')}</button></div>
          <label class="search-box">${icon('search')}<input type="search" aria-label="Search lunar regions" placeholder="Find a region…" autocomplete="off"><kbd>/</kbd></label>
          <div class="region-filters" role="group" aria-label="Filter regions"><button class="selected" data-filter="all">All regions</button><button data-filter="polar">South pole</button><button data-filter="far">Far side</button></div>
          <div class="list-caption"><span>REGIONS</span><span class="region-count mono">08</span></div>
          <div class="region-list"></div>
          <div class="side-footer"><span class="source-dot"></span><div><strong>Built on NASA data</strong><span>LRO imagery + LOLA elevation</span></div><button class="icon-button" data-action="sources" aria-label="View NASA data sources">${icon('arrow-up-right')}</button></div>
        </aside>
        <main class="explorer" aria-label="Lunar explorer">
          <div id="viewport"></div>
          <div class="viewport-top"><div class="view-title"><button class="icon-button mobile-menu" data-action="sidebar" aria-expanded="false" aria-label="Open region browser">${icon('menu')}</button><span class="eyebrow">EXPLORER</span><span class="crumb-divider">/</span><span id="view-label">Moon</span><span class="mode-tag mono">3D</span></div><span class="data-state"><span class="source-dot"></span><span id="data-status">Loading NASA surface</span></span></div>
          <div class="view-switch" role="group" aria-label="View mode"><button data-mode="globe" class="selected" aria-pressed="true">${icon('globe-2')} Globe</button><button data-mode="terrain" aria-pressed="false">${icon('mountain')} Terrain</button></div>
          <div class="canvas-wordmark" aria-hidden="true"></div>
          <div class="viewport-controls" aria-label="Viewport controls"><button class="icon-button" data-action="zoom-in" aria-label="Zoom in" title="Zoom in">${icon('plus')}</button><button class="icon-button" data-action="zoom-out" aria-label="Zoom out" title="Zoom out">${icon('minus')}</button><span class="control-separator"></span><button class="icon-button" data-action="reset" aria-label="Reset view" title="Reset view">${icon('rotate-ccw')}</button><button class="icon-button" data-action="grid" aria-label="Toggle coordinate grid" aria-pressed="false" title="Coordinate grid">${icon('grid-2-x2')}</button><button class="icon-button" data-action="layers" aria-label="Surface layers" aria-expanded="false" title="Surface layers">${icon('layers')}</button></div>
          <section class="layers-panel floating-panel" hidden aria-label="Surface layers"><div class="panel-label">Surface layers<button class="icon-button" data-action="layers" aria-label="Close layers">${icon('x')}</button></div><label>Display<select id="layer-select"><option value="imagery">LROC natural color</option><option value="relief">Shaded relief</option><option value="wireframe">Terrain mesh</option></select></label><label>Vertical exaggeration <output id="relief-value">1× · true scale</output><input type="range" id="relief-slider" min="1" max="5" step="1" value="1"></label><label>Sun elevation <output id="sun-value">46° · illustrative</output><input type="range" id="sun-slider" min="5" max="70" step="1" value="46"></label><p>LOLA-derived surface shading. Lower the sun angle to reveal crater rims and slopes. Lighting is illustrative; elevation readouts stay at true scale.</p></section>
          <div class="region-indicator" aria-hidden="true"><span></span><span id="indicator-name">${activeRegion.name}</span></div>
          <section class="region-detail floating-panel" aria-label="Selected region"></section>
          <div class="view-bottom"><div class="navigation-help">${icon('mouse-pointer-2')}<span id="nav-help">Drag to orbit <b>·</b> Scroll to zoom <b>·</b> Click to inspect</span></div><div class="scale-indicator"><span class="scale-line"></span><span id="scale-value" class="mono">— km</span></div><button class="source-link" data-action="sources">NASA / LRO ${icon('external-link')}</button></div>
          <div class="loading-screen" role="status"><div class="loading-orbit"></div><strong>Bringing the Moon into view</strong><span>Loading LROC imagery & LOLA terrain…</span></div>
          <div class="toast" role="status" hidden></div>
        </main>
      </div>
      <footer class="status-bar mono"><span></span><span id="cursor-readout">${coord(activeRegion.lat)} &nbsp; ${coord(activeRegion.lon,false)}</span><span id="resolution-readout">LOLA 16 px/° <b>·</b> GLOBAL PREVIEW</span></footer>
    </div>
    <dialog id="sources-dialog" aria-labelledby="sources-title"><div class="dialog-top"><span class="eyebrow">DATA PROVENANCE</span><button class="icon-button" data-action="close-dialog" aria-label="Close data sources">${icon('x')}</button></div><h2 id="sources-title">A real Moon. A first foundation.</h2><p>Clavius builds its own 3D meshes from NASA’s lunar elevation samples, with the LRO camera mosaic wrapped over the surface.</p><div class="source-item"><span class="mono">01 / ELEVATION</span><h3>Lunar Orbiter Laser Altimeter</h3><p>Source file: <code>ldem_16_uint.tif</code>. LOLA global cylindrical DEM, 5,760 × 2,880 samples (16 pixels/degree). About 1.9 km spacing at the equator; physical east–west spacing decreases toward the poles.</p><p>Unsigned 16-bit values are decoded as <code>height = sample × 0.5 − 10,000 m</code>, relative to the 1,737.4 km reference sphere. Samples are bilinearly interpolated for display.</p></div><div class="source-item"><span class="mono">02 / IMAGERY</span><h3>LROC Wide Angle Camera</h3><p>Source file: <code>lroc_color_poles_8k.tif</code>. NASA’s 2019 natural-color Moon Kit mosaic, served at 8,192 × 4,096 pixels. Polar areas beyond ±70° use LOLA albedo fill. This is a visualization mosaic, not scientific reflectance data.</p></div><div class="data-note">This global preview does not resolve rocks, wheel-scale slopes, or landing hazards. Terrain view streams a 400 km patch of NASA’s 64 px/degree LOLA DEM, about 474 m between samples at the equator. It is not the 5 m polar dataset. Regional relief follows the finer mesh. Globe shading uses the 16 px/degree DEM. Adjustable low-angle lighting and mesh shadows improve visibility, but do not add measured resolution or establish real sunlight conditions. The separate Simulation workspace uses measured 5 m Connecting Ridge terrain, date-specific geometry and declared rover models.</div><p class="credit">Credit: NASA’s Scientific Visualization Studio, Ernie Wright, and the LRO / LOLA / LROC instrument teams.</p><div class="dialog-links"><a href="https://svs.gsfc.nasa.gov/4720/" target="_blank" rel="noreferrer">NASA Moon Kit ${icon('arrow-up-right')}</a><a href="/data/manifest.json" target="_blank">Asset manifest ${icon('arrow-up-right')}</a></div></dialog>`;
  renderRegions(); renderDetail(); icons();
  bindApp(); loadScene(alive);
}
function renderRegions() {
  const matches=regions.filter(r=>(filter==='all'||r.group===filter)&&`${r.name} ${r.kind}`.toLowerCase().includes(search));
  document.querySelector('.region-count').textContent=String(matches.length).padStart(2,'0');
  document.querySelector('.region-list').innerHTML=matches.length?matches.map(r=>`<button class="region-row ${r.id===activeRegion.id?'active':''}" data-region="${r.id}" aria-pressed="${r.id===activeRegion.id}"><span class="region-thumbnail thumb-${r.id}" aria-hidden="true"></span><span class="region-row-text"><strong>${r.name}</strong><span>${r.kind}</span></span>${icon(r.id===activeRegion.id?'crosshair':'chevron-right')}</button>`).join(''):`<div class="no-regions">No regions found.<br><button class="text-button" data-action="clear-search">Clear search & filters</button></div>`;
  icons();
}
function renderDetail() {
  const r=activeRegion;
  document.querySelector('.region-detail').innerHTML=`<div class="detail-kicker"><span>${icon('map-pin')} SELECTED REGION</span><span class="detail-number mono">${r.id==='custom'?'PIN':String(regions.indexOf(r)+1).padStart(2,'0')}</span></div><h2>${r.name}</h2><p class="region-description">${r.description}</p><div class="coordinates"><div><span>LATITUDE</span><strong class="mono">${coord(r.lat)}</strong></div><div><span>LONGITUDE</span><strong class="mono">${coord(r.lon,false)}</strong></div></div><div class="elevation-row"><span>Sampled elevation ${icon('info')}</span><strong id="site-elevation" class="mono">${grid?formatElevation((mode==='terrain' && viewer?.detailGrid || grid).sample(r.lat,r.lon)):'Loading…'}</strong></div><button class="primary surface-button" data-action="surface" ${viewer?'':'disabled'}>${icon(mode==='terrain'?'globe-2':'navigation')} ${mode==='terrain'?'Return to globe':'Explore terrain'} ${icon('arrow-up-right')}</button><a class="drive-entry" href="/app/drive?site=${r.id==='shackleton'?'shackleton-rim':'connecting-ridge'}">Drive VIPER at the south pole ${icon('arrow-up-right')}</a><span class="detail-note">${mode==='terrain'?'400 km patch · WASD to move':'NASA LOLA terrain · global resolution'}</span>`;
  icons();
}
function formatElevation(m) { return `${m>=0?'+':'−'}${(Math.abs(m)/1000).toFixed(2)} km`; }
function setRegion(region, flight=true) {
  activeRegion=region; viewer?.select(region,flight);
  document.querySelector('#indicator-name').textContent=region.name;
  document.querySelector('#cursor-readout').textContent=`${coord(region.lat)}   ${coord(region.lon,false)}`;
  renderRegions(); renderDetail(); updateURL();
  if(innerWidth<=900)toggleSidebar(false);
}
function updateURL() {
  const p=new URLSearchParams();
  if(activeRegion.id==='custom'){p.set('lat',activeRegion.lat.toFixed(5));p.set('lon',activeRegion.lon.toFixed(5));}
  else p.set('region',activeRegion.id);
  if(mode==='terrain')p.set('view','terrain');
  history.replaceState({},'',`/app/atlas?${p}`);
}
function setMode(value) {
  if(!viewer)return;
  mode=value; viewer.setMode(value);
  if(value==='globe')document.querySelector('#resolution-readout').textContent='LOLA 16 px/° · GLOBAL PREVIEW';
  document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===value);b.setAttribute('aria-pressed',String(b.dataset.mode===value));});
  document.querySelector('#view-label').textContent=value==='globe'?'Moon':'Regional terrain';
  document.querySelector('.canvas-wordmark').hidden=value==='terrain';
  document.querySelector('.region-indicator').hidden=value==='terrain';
  document.querySelector('#nav-help').textContent=value==='globe'?'Drag to orbit · Scroll to zoom · Click to inspect':'Drag to orbit · Right-drag to pan · WASD to move';
  renderDetail();updateURL();
}
let toastTimer;
function toast(message) { const node=document.querySelector('.toast');node.textContent=message;node.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.hidden=true,4000); }
function toggleSidebar(open) {
  const sidebar=document.querySelector('.sidebar');
  sidebar.classList.toggle('open',open);
  sidebar.inert=innerWidth<=900&&!open;
  document.querySelector('.mobile-menu').setAttribute('aria-expanded',String(open));
}
function bindApp() {
  toggleSidebar(false);
  const onResize=()=>{const sidebar=document.querySelector('.sidebar');if(sidebar)sidebar.inert=innerWidth<=900&&!sidebar.classList.contains('open');};
  window.addEventListener('resize',onResize);
  const input=document.querySelector('.search-box input');
  input.addEventListener('input',()=>{search=input.value.toLowerCase();renderRegions();});
  const key=e=>{
    if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)&&!document.querySelector('dialog').open){e.preventDefault();if(innerWidth<=900)toggleSidebar(true);input.focus();}
    if(e.key==='Escape')toggleSidebar(false);
  };
  document.addEventListener('keydown',key);cleanup=()=>{document.removeEventListener('keydown',key);window.removeEventListener('resize',onResize);};
  document.querySelector('.workspace').addEventListener('click',e=>{
    const btn=e.target.closest('button');if(!btn)return;
    if(btn.dataset.region)setRegion(regions.find(r=>r.id===btn.dataset.region));
    if(btn.dataset.filter){filter=btn.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('selected',b===btn));renderRegions();}
    if(btn.dataset.mode)setMode(btn.dataset.mode);
    switch(btn.dataset.action){
      case 'sources':document.querySelector('#sources-dialog').showModal();break;
      case 'surface':setMode(mode==='globe'?'terrain':'globe');break;
      case 'zoom-in':viewer?.zoom(.8);break;
      case 'zoom-out':viewer?.zoom(1.25);break;
      case 'reset':viewer?.reset();break;
      case 'grid':{const enabled=btn.getAttribute('aria-pressed')!=='true';btn.setAttribute('aria-pressed',String(enabled));viewer?.setGrid(enabled);break;}
      case 'layers':{const panel=document.querySelector('.layers-panel');panel.hidden=!panel.hidden;document.querySelector('.viewport-controls [data-action="layers"]').setAttribute('aria-expanded',String(!panel.hidden));break;}
      case 'sidebar':toggleSidebar(!document.querySelector('.sidebar').classList.contains('open'));break;
      case 'clear-search':search='';filter='all';input.value='';document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('selected',b.dataset.filter==='all'));renderRegions();break;
    }
  });
  document.querySelector('[data-action="close-dialog"]').onclick=()=>document.querySelector('#sources-dialog').close();
  const dialog=document.querySelector('#sources-dialog');dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  document.querySelector('#layer-select').onchange=e=>viewer?.setLayer(e.target.value);
  document.querySelector('#sun-slider').oninput=e=>{const degrees=Number(e.target.value);viewer?.setSunElevation(degrees);document.querySelector('#sun-value').textContent=`${degrees}° · illustrative`;};
  document.querySelector('#relief-slider').oninput=e=>{const v=Number(e.target.value);viewer?.setRelief(v);document.querySelector('#relief-value').textContent=v===1?'1× · true scale':`${v}× · exaggerated`;};
}
async function loadScene(generation) {
  try {
    const module=await import('./scene.js');
    const response=await fetch('/data/lola-elevation.bin');
    if(!response.ok)throw new Error('NASA elevation asset could not be loaded.');
    const [buffer,texture,normalTexture]=await Promise.all([response.arrayBuffer(),module.loadTexture('/data/lroc-color-8k.jpg').catch(()=>module.loadTexture('/data/lroc-color.jpg')),module.loadTexture('/data/lola-normals.png')]);
    if(generation!==alive){texture.dispose();normalTexture.dispose();return;}
    grid=new ElevationGrid(buffer);
    viewer=new module.LunarScene(document.querySelector('#viewport'),grid,texture,normalTexture,{
      onDetail:message=>{document.querySelector('#resolution-readout').textContent=message;renderDetail();},
      onPick:({lat,lon})=>{setRegion({id:'custom',name:'Pinned location',kind:'Surface point',lat,lon,description:'A location selected directly on the lunar surface. Elevation is interpolated from the NASA LOLA global DEM.'},false);toast('Surface location pinned. Select a region to continue exploring.');},
      onCamera:({distance,mode:cameraMode})=>{
        const node=document.querySelector('#scale-value');
        // World-space distance represented by the 48 CSS-pixel scale at the focal plane.
        const focal=cameraMode==='globe'?Math.max(40,distance-1737.4):distance;
        const km=2*focal*Math.tan(19*Math.PI/180)*48/document.querySelector('#viewport').clientHeight;
        node.textContent=`≈ ${Math.max(1,Math.round(km))} km`;
      }
    });
    const params=new URLSearchParams(location.search),lat=Number(params.get('lat')),lon=Number(params.get('lon'));
    if(params.has('lat')&&params.has('lon')&&Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180)activeRegion={id:'custom',name:'Pinned location',kind:'Surface point',lat,lon,description:'A saved location on the lunar surface. Elevation is interpolated from the NASA LOLA global DEM.'};
    viewer.select(activeRegion,false);viewer.reset();viewer.setGrid(false);
    if(mode==='terrain')setMode('terrain');else{renderDetail();updateURL();}
    document.querySelector('#indicator-name').textContent=activeRegion.name;
    document.querySelector('#cursor-readout').textContent=`${coord(activeRegion.lat)}   ${coord(activeRegion.lon,false)}`;
    document.querySelector('.loading-screen').hidden=true;
    document.querySelector('#data-status').textContent='NASA surface loaded';
    document.querySelector('.data-state').classList.add('ready');
  }catch(error){
    if(generation!==alive)return;
    console.error(error);
    document.querySelector('.loading-screen').innerHTML=`${icon('info')}<strong>Couldn’t open the 3D surface</strong><span>Check your connection and enable WebGL in your browser.</span><button class="primary" id="retry-load">Try again ${icon('arrow-right')}</button>`;
    document.querySelector('#data-status').textContent='Surface unavailable';
    document.querySelector('#retry-load').onclick=()=>{viewer?.dispose();viewer=null;document.querySelector('#viewport').replaceChildren();document.querySelector('.loading-screen').innerHTML='<strong>Loading lunar surface…</strong>';loadScene(alive);};icons();
  }
}
document.addEventListener('click',e=>{const a=e.target.closest('a');if(a&&a.origin===location.origin&&['/','/app','/app/atlas','/app/simulation','/app/drive'].includes(a.pathname)&&!a.hash&&!a.target&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.altKey&&e.button===0){e.preventDefault();history.pushState({},'',a.href);navigate();}});
window.addEventListener('popstate',()=>{if(location.pathname==='/app/atlas'&&document.querySelector('.workspace:not(.sim-workspace)')){alive++;cleanup?.();viewer?.dispose();viewer=null;renderApp();}else navigate();});
navigate();
