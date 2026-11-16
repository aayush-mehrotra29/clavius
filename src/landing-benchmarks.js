import './landing-benchmarks.css';
import shadows from '../docs/validation/benchmark-evaluation/shadow-baselines.json';
import native from '../docs/validation/benchmark-evaluation/native-results.json';

const evidence = 'https://github.com/aayush-mehrotra29/clavius/blob/9df5fbc/docs/validation/';
const report = evidence + 'benchmark-evaluation/README.md';
const primaryRegions = shadows.rows.filter(row =>
  row.scope === 'regional' && row.thresholds.dark_at_most === .001 && row.thresholds.lit_at_least === .005
  && row.flat_horizon.clavius.balanced_accuracy !== null
);

function shadowChart(comparison, baseline) {
  return {
    title: 'Balanced accuracy', series: ['Clavius', baseline], max: 100, unit: '%', digits: 2,
    groups: primaryRegions.map(row => {
      const { clavius, baseline } = row[comparison];
      return {
        label: row.scene, note: (clavius.dark_count + clavius.lit_count).toLocaleString('en-US') + ' samples',
        values: [clavius.balanced_accuracy * 100, baseline.balanced_accuracy * 100],
      };
    }),
  };
}

const { rigid, scm, horizons, gazebo, gmat } = native;
const scores = primaryRegions.map(row => 100 * row.flat_horizon.clavius.balanced_accuracy);
const topics = [
  { title: 'Surface', description: 'Compare predicted sunlight with bright and dark areas in lunar images.', results: [
    { name: 'Polar shadow prediction', source: 'LROC narrow-angle camera', metric: Math.min(...scores).toFixed(1) + '–' + Math.max(...scores).toFixed(1) + '%',
      label: 'balanced accuracy across two image footprints',
      chart: shadowChart('flat_horizon', 'Flat horizon'),
      note: 'Terrain blocked sunlight that a flat horizon predicted across both scenes. The score gives bright and dark samples equal weight. Image brightness serves as a proxy for sunlight. A third scene lacked terrain coverage.',
      link: evidence + 'benchmark-evaluation/shadow-baselines.json' },
    { name: 'Published sunlight rendering', source: 'NASA PGDA · Product 90', metric: '2 of 2', label: 'regional footprints favored the published rendering',
      chart: shadowChart('published_rendering', 'PGDA rendering'),
      note: 'Both methods predicted whether any direct sunlight reached each point. Clavius scored slightly higher on the Shackleton rim subset under balanced accuracy. The published rendering made one fewer error there overall.',
      link: evidence + 'benchmark-evaluation/shadow-baselines.json' },
  ] },
  { title: 'Rover', description: 'Inspect wheel traction, mechanical alignment and the native dynamics checks.', results: [
    { name: 'Deformable soil traction', source: 'NASA Glenn · GRC-3 wheel tests', metric: scm.relative_reduction_pct.toFixed(1) + '%', label: 'lower RMS traction-angle error on eight held-out points',
      chart: { title:'RMS angle error · lower is better', unit:'°', max:20, digits:2, series:['Chrono SCM','Rigid plane','Target'], groups:[
        {label:'Eight matched test points', values:[scm.scm_rmse_deg, scm.rigid_rmse_deg, 5]}] },
      note: 'The offline Earth-gravity soil model improved on the rigid baseline at all eight points. Both exceeded the 5° target. Time and grid refinements at 40% slip also missed their targets.',
      link: '/data/scm-validation.json' },
    { name: 'Rigid wheel traction', source: 'NASA Glenn · TREC / MGRU3', metric: rigid.traction_rmse_deg.toFixed(2) + '°', label: 'RMS traction-angle error across ' + rigid.point_count + ' test points',
      chart: { title:'RMS angle error · lower is better', unit:'°', max:16, digits:2, series:['MuJoCo fixture','Target'], groups:[
        {label:'Full wheel-test set', values:[rigid.traction_rmse_deg,5]}] },
      note: 'The fixture passed its controls and three finer-timestep checks. The wheel’s traction on a rigid plane missed the physical target for the soil experiment.',
      link: '/data/mobility-validation.json' },
    { name: 'VIPER wheel alignment', source: 'Project Chrono · VIPER assembly', metric: '<0.001 mm', label: 'wheel center-of-gravity discrepancy after frame repair',
      facts:[['Upstream discrepancy','27.59 mm'],['Correction protocol','14 cases'],['Rigid-floor runs','4 cases']],
      note: 'The protocol reproduced the original left-wheel discrepancy and detected a deliberately incorrect shaft axis. The corrected assembly still requires flight hardware and soil calibration.',
      link: evidence + 'viper-frame-repair.json' },
    { name: 'Lunar gravity & driving', source: 'Gazebo Harmonic · DART / ROS 2', metric: Math.abs(gazebo.cases.free_fall.checks.actual_vertical_velocity_m_s).toFixed(2) + ' m/s', label: 'downward speed in the lunar free-fall test',
      facts:[['Expected downward speed','0.81 m/s'],['Flat-drive speed',gazebo.cases.flat_drive.checks.speed_m_s.toFixed(4) + ' m/s'],['ROS 2 clock messages',gazebo.cases.flat_drive.ros2_clock_messages + ' during drive']],
      note: 'The recorded worker passed free fall, flat driving and telemetry checks. Contact-force readings and measured lunar-soil calibration remain unavailable.',
      link: evidence + 'benchmark-evaluation/native-results.json' },
  ] },
  { title: 'Flight & sky', description: 'Check local sky directions and lunar transfer endpoints against archived references.', results: [
    { name: 'Sun & Earth direction', source: 'NASA JPL · Horizons', metric: (Math.ceil(3600 * Math.max(horizons.max_errors.sun.direction_deg,horizons.max_errors.earth.direction_deg) * 1000) / 1000).toFixed(3) + '″',
      label: 'upper bound on the largest direction difference',
      chart: {title:'Maximum direction difference · arcseconds',unit:'″',max:.05,digits:4,series:['Clavius vs. Horizons'],groups:[
        {label:'Sun',values:[3600 * horizons.max_errors.sun.direction_deg]}, {label:'Earth',values:[3600 * horizons.max_errors.earth.direction_deg]}]},
      note: 'All 32 combinations of target, site and time passed the comparison against seven archived Horizons replies. This measures agreement on sky direction before local terrain blocks the view.',
      link: '/data/horizons-geometry.json' },
    { name: 'Lunar transfer endpoints', source: 'NASA · General Mission Analysis Tool', metric: (gmat.case_count - gmat.failures.length) + ' of ' + gmat.case_count, label: 'reference trajectories passed endpoint checks',
      facts:[['Fixed-epoch example','Passed'],['Lunar-transfer example','Passed']],
      note: 'Both GMAT examples converged and passed their encounter and capture checks. These two reference trajectories cover specific scenarios. A search across Earth departure dates remains future work.',
      link: '/data/gmat-reference-validation.json' },
  ] },
];

function chartMarkup(chart) {
  const legend = chart.series.map((name, i) => `<span><i class="bm-series-${i}"></i>${name}</span>`).join('');
  const groups = chart.groups.map(({ label, values, note }) => `<div class="bm-group">
    <div class="bm-bars">${values.map((v, i) => `<div class="bm-bar bm-series-${i}" style="--height:${100*v/chart.max}%">
      <span><span class="bm-sr">${chart.series[i]} </span>${v.toFixed(chart.digits)}${chart.unit}</span></div>`).join('')}</div>
    <div class="bm-xlabel">${label}${note ? `<small>${note}</small>` : ''}</div></div>`).join('');
  return `<figure class="bm-chart"><figcaption>${chart.title}</figcaption><div class="bm-legend">${legend}</div>
    <div class="bm-plot"><div class="bm-axis" aria-hidden="true">${[chart.max,chart.max/2,0].map(v=>`<span>${v}${chart.unit}</span>`).join('')}</div>
      <div class="bm-groups">${groups}</div></div></figure>`;
}

function resultMarkup(result) {
  const data = result.chart ? chartMarkup(result.chart) : `<dl class="bm-facts">${result.facts.map(([label,value]) =>
    `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>`;
  return `<header><p class="bm-source">${result.source}</p><h3>${result.name}</h3></header>
    <p class="bm-metric">${result.metric}</p> <p class="bm-metric-label">${result.label}</p>${data}
    <p class="bm-note">${result.note}</p><a class="bm-link" href="${result.link}" target="_blank" rel="noreferrer">View benchmark data <span aria-hidden="true">↗</span></a>`;
}

export function mountBenchmarks(section) {
  section.innerHTML = `<h2 id="benchmark-title" class="story-title">Benchmarks</h2>
    <div class="bm-filters" role="group" aria-label="Benchmark category">${topics.map((topic,i) =>
      `<button type="button" data-topic="${i}" aria-pressed="${i===0}">${topic.title}</button>`).join('')}</div>
    <div class="bm-layout"><div class="bm-library"><h3></h3><p></p><div class="bm-choices" role="group" aria-label="Choose a benchmark"></div>
      <a class="bm-link" href="${report}" target="_blank" rel="noreferrer">Read the evaluation <span aria-hidden="true">↗</span></a></div>
    <article class="bm-result" id="benchmark-result" aria-label="Selected benchmark" aria-live="polite"></article></div>`;
  const filters = section.querySelector('.bm-filters');
  const library = section.querySelector('.bm-library');
  const choices = library.querySelector('.bm-choices');
  const panel = section.querySelector('.bm-result');
  let activeTopic = 0;

  function selectResult(index) {
    Array.from(choices.children).forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
    panel.innerHTML = resultMarkup(topics[activeTopic].results[index]);
  }
  function selectTopic(index) {
    activeTopic = index;
    const topic = topics[index];
    Array.from(filters.children).forEach((button,i) => button.setAttribute('aria-pressed', String(i === index)));
    library.querySelector('h3').textContent = topic.title;
    library.querySelector('p').textContent = topic.description;
    choices.innerHTML = topic.results.map((result,i) => `<button type="button" aria-controls="benchmark-result" data-result="${i}">${result.name}<span aria-hidden="true">›</span></button>`).join('');
    selectResult(0);
  }
  filters.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (button) selectTopic(Number(button.dataset.topic));
  });
  choices.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (button) selectResult(Number(button.dataset.result));
  });
  selectTopic(0);
}
