import comparisonUrl from '../docs/validation/reference-comparison.json?url&no-inline';

const missionSteps = [
  {
    name: 'Rover',
    title: 'Choose the robot.',
    copy: 'Start with Clavius R1, a hypothetical reference rover. Set its battery capacity, solar array and driving power to model the energy available for a trip.',
  },
  {
    name: 'Route',
    title: 'Set a time and a path.',
    copy: 'Place waypoints on Connecting Ridge. Schedule a drive, a science stop or a charging break. Change the rover’s start time to see when the terrain blocks sunlight.',
  },
  {
    name: 'Replay',
    title: 'Find the first constraint.',
    copy: 'Follow the rover and its battery on one timeline. Compare two drive schedules, inspect a contact in MuJoCo or export the inputs so another team can repeat the run.',
  },
];

const atlasLayers = [
  {
    title: 'Global surface',
    copy: 'NASA’s 2019 CGI Moon Kit pairs LROC imagery with elevations measured by the Lunar Orbiter Laser Altimeter. Use the globe to examine a destination before looking at the local terrain along a route.',
    image: 'landing-moon.webp', alt: 'The near side of the Moon in natural color with illustrative lighting.',
    link: '/data/manifest.json', linkText: 'Explorer sources',
  },
  {
    title: 'Height in color',
    copy: 'The same hemisphere looks different through an altimeter. Blues trace low basins. Mint marks the reference sphere, and the warmest colors pick out high ground.',
    image: 'lunar-elevation.webp', alt: 'Elevation heatmap of the same lunar hemisphere, showing blue basins and warm-colored highlands.',
    caption: '<span>−4.5 km</span><i class="elevation-ramp" aria-hidden="true"></i><span>+4.5 km</span>',
  },
  {
    title: 'Connecting Ridge',
    copy: 'At the south pole, PGDA 78 records the surface on a 5 m grid. This relief model shows the ridges and crater walls across its 16 km footprint.',
    image: 'connecting-ridge-relief.webp', alt: 'Oblique terrain model of Connecting Ridge with violet depressions and peach-colored ridges.',
    caption: '200 m contours · 2.4× vertical scale',
    link: 'https://pgda.gsfc.nasa.gov/products/78', linkText: 'NASA terrain data',
  },
  {
    title: 'A rover’s horizon',
    copy: 'From Connecting Ridge, nearby peaks and distant terrain shape the skyline. The simulator combines the 5 m local grid, 80 m regional terrain and DE421 SPICE geometry. At the time shown, the Sun sits above the modeled horizon and Earth lies below it.',
    image: 'connecting-ridge-horizon.svg', alt: 'Skyline from east through south to west. The Sun is above the ridge at about 1.3 degrees elevation and Earth is below it at about −3.3 degrees.',
    caption: '15 November 2026 · 12:00 UTC',
    link: '/data/simulation-manifest.json', linkText: 'Simulation sources',
  },
];

function atlasFigure(layer, index, inline) {
  return `<figure class="atlas-figure ${inline ? 'atlas-inline' : 'atlas-frame'}" data-layer="${index}" ${!inline && index === 0 ? 'data-current' : ''}>
    <img src="/images/${layer.image}" alt="${inline ? layer.alt : ''}" loading="lazy" decoding="async">
    ${layer.caption ? `<figcaption>${layer.caption}</figcaption>` : ''}
  </figure>`;
}

export function landingSections() {
  return `
    <section id="about" class="lunar-intro story-width" aria-labelledby="about-title">
      <h2 id="about-title" class="story-title">A rover’s first day on the Moon.</h2>
      <div id="users">
        <p id="challenge" class="story-body">Plan a transfer from Earth orbit, choose a traverse and watch the rover follow it across the lunar surface.</p>
        <details class="story-detail" id="questions">
          <summary>How does the flight set the surface mission?</summary>
          <p class="story-body">Choose a departure and site. Clavius solves the transfer and adds a prescribed descent. The rover starts there at the modeled touchdown time, with sunlight calculated for that place and date.</p>
        </details>
      </div>
    </section>

    <section id="mission" class="mission-story story-width" aria-labelledby="mission-title">
      <div class="mission-heading" id="how-it-works">
        <h2 id="mission-title" class="story-title">Rehearse the surface mission.</h2>
        <p class="story-body">Choose a start time at Connecting Ridge. See whether the rover can finish its science stops with enough sunlight to charge and a clear view of Earth to send data home.</p>
      </div>
      <div class="mission-demo" id="use-cases">
        <div class="mission-controls">
          <div class="step-switch" role="tablist" aria-label="Mission walkthrough">
            ${missionSteps.map(({name}, index) => `<button type="button" role="tab" id="mission-tab-${index}" data-step="${index}" aria-selected="${index === 0}" tabindex="${index ? -1 : 0}" aria-controls="mission-panel-${index}">${name}</button>`).join('')}
          </div>
          <div id="mission-step">
            ${missionSteps.map(({title,copy}, index) => `<div data-step-copy="${index}" role="tabpanel" id="mission-panel-${index}" aria-labelledby="mission-tab-${index}" ${index ? 'inert' : 'data-current'}><h3>${title}</h3><p class="story-body">${copy}</p></div>`).join('')}
          </div>
          <a class="story-link" href="/app">Plan a mission</a>
        </div>
        <div class="mission-visual" aria-hidden="true">
          <div class="mission-scene" data-scene="0" data-current><img loading="lazy" decoding="async" src="/images/rover-study.webp" width="1280" height="854" alt=""></div>
          <div class="mission-scene route-scene" data-scene="1">
            <img loading="lazy" decoding="async" src="/images/polar-ridge.webp" width="1672" height="941" alt="">
            <svg viewBox="0 0 600 400" preserveAspectRatio="none" focusable="false">
              <path class="traverse-path" pathLength="1" d="M-16 361 Q118 301 202 275 T354 232 Q389 221 380 211 T405 193 L467 172"/>
              <g fill="white"><circle cx="202" cy="275" r="4"/><circle cx="354" cy="232" r="4"/><circle cx="467" cy="172" r="4"/></g>
            </svg>
          </div>
          <div class="mission-scene replay-scene" data-scene="2">
            <div class="replay-sequence">
              <div class="replay-axis">Example schedule</div>
              <div class="replay-activities"><span>Drive</span><span>Sample</span><span>Charge</span><i class="replay-cursor"></i></div>
            </div>
          </div>
        </div>
      </div>
      <details id="case-study" class="story-detail mission-example">
        <summary>Compare two start dates at Connecting Ridge</summary>
        <p class="story-body">The hypothetical R1 followed the same 113 m route in two simulations. On January 1, 2028, it finished with 156 Wh and kept Earth in view throughout. On January 14, it finished with 223 Wh, but Earth stayed below its horizon for all twelve hours.</p>
        <a class="story-link" href="${comparisonUrl}" target="_blank" rel="noreferrer">View the recorded comparison</a>
      </details>
    </section>

    <section id="sources" class="data-sky" aria-labelledby="sources-title">
      <div class="data-inner story-width">
        <h2 id="sources-title" class="story-title">Explore the destination.</h2>
        <div class="atlas-story">
          <div class="atlas-chapters">
            ${atlasLayers.map((layer, index) => `<article class="atlas-chapter" data-chapter="${index}">
              <div><h3>${layer.title}</h3><p class="story-body">${layer.copy}</p>
              ${layer.link ? `<a class="story-link" href="${layer.link}" target="_blank" rel="noreferrer">${layer.linkText}</a>` : ''}
              </div>
              ${atlasFigure(layer, index, true)}
            </article>`).join('')}
          </div>
          <div class="atlas-stage" aria-hidden="true">${atlasLayers.map((layer, index) => atlasFigure(layer, index, false)).join('')}</div>
        </div>
      </div>
    </section>

    <section id="research" class="research-story story-width" aria-labelledby="research-title">
      <h2 class="story-title" id="research-title">Research &amp; benchmarks</h2>
      <div class="research-studies">
        <article>
          <h3>When can a spacecraft leave Earth orbit?</h3>
          <p>Campana and Topputo studied how the changing positions of Earth, the Moon and the Sun affect low-energy transfers. Their work shows why departure dates matter.</p>
          <a class="story-link" href="https://doi.org/10.1016/j.actaastro.2025.03.010" aria-label="Read Campana and Topputo’s paper on low-energy Earth–Moon transfers">Campana &amp; Topputo · <cite>Acta Astronautica</cite>, 2025</a>
        </article>
        <article>
          <h3>Will a sunlit route stay lit?</h3>
          <p>Chen and colleagues used hourly maps to find terrain that stayed sunlit for 72 hours, then planned simulated routes within a rover’s slope limits. In Clavius, you can vary the start time and see how sunlight changes the battery reserve along one route.</p>
          <a class="story-link" href="https://doi.org/10.3390/rs18172950" aria-label="Read Chen and colleagues’ paper on illumination mapping and polar rover routes">Chen et al. · <cite>Remote Sensing</cite>, 2026</a>
        </article>
      </div>
      <details id="benchmarks" class="story-detail">
        <summary>Explore the benchmark results</summary>
        <div class="bench-topics">
          <article><h3>Flight planning</h3><p>Two NASA GMAT examples converged and passed their endpoint checks. Searching a range of Earth departure dates remains planned work.</p><a class="story-link" href="/data/gmat-reference-validation.json" target="_blank" rel="noreferrer">Orbital reference results</a></article>
          <article><h3>Terrain &amp; illumination</h3><p>Dated lunar images helped identify a narrow ridge the model had missed. Checks at Connecting Ridge and the Shackleton rim still exceed some horizon-refinement targets.</p><a class="story-link" href="/data/illumination-validation.json" target="_blank" rel="noreferrer">Shadow comparison results</a></article>
          <article><h3>Rover dynamics</h3><p>In a separate NASA Glenn wheel-test comparison, the rigid-plane model missed its 5° traction target. The RMS discrepancy across 18 reference points was 12.83°.</p><a class="story-link" href="/data/mobility-validation.json" target="_blank" rel="noreferrer">Wheel-test results</a></article>
      </div>
      </details>
    </section>`;
}

export function landingFooter(logo) {
  return `<footer class="landing-footer story-width"><a class="brand" href="#sky" aria-label="Clavius home">${logo}</a><a id="get-started" href="/app">Get started</a><a href="#sky">Back to top</a></footer>`;
}
