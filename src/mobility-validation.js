const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number=(value,digits=2)=>Number.isFinite(value)?value.toFixed(digits):'—';

export async function loadMobilityValidation(){
 const source=await fetch('/data/manifest.json');
 if(!source.ok)throw new Error('The dataset manifest is unavailable.');
 const manifest=await source.json();const pin=manifest.mobility_validation?.report;
 if(pin?.url!=='/data/mobility-validation.json'||!/^[a-f0-9]{64}$/.test(pin.sha256))throw new Error('No pinned mobility comparison is available.');
 const response=await fetch(pin.url);
 if(!response.ok)throw new Error('The mobility comparison is unavailable.');
 const raw=await response.arrayBuffer();
 const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(v=>v.toString(16).padStart(2,'0')).join('');
 if(actual!==pin.sha256)throw new Error('The mobility comparison differs from its recorded source hash.');
 const report=JSON.parse(new TextDecoder().decode(raw));
 if(report.points?.length!==18||!report.summary||report.engine?.name!=='MuJoCo')throw new Error('Unsupported mobility evidence format.');
 return report;
}

export async function loadSCMValidation(){
 const source=await fetch('/data/manifest.json');
 if(!source.ok)throw new Error('The dataset manifest is unavailable.');
 const manifest=await source.json();const pin=manifest.scm_validation?.report;
 if(pin?.url!=='/data/scm-validation.json'||!/^[a-f0-9]{64}$/.test(pin.sha256))throw new Error('No pinned soil-contact development report is available.');
 const response=await fetch(pin.url);
 if(!response.ok)throw new Error('The soil-contact report is unavailable.');
 const raw=await response.arrayBuffer();
 const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(v=>v.toString(16).padStart(2,'0')).join('');
 if(actual!==pin.sha256)throw new Error('The soil-contact report differs from its recorded source hash.');
 const report=JSON.parse(new TextDecoder().decode(raw));
 if(report.id!=='clavius-trec-scm-development-v1'||report.holdout?.length!==8||report.training?.length!==10||report.refinements?.length!==6||report.engine?.name!=='Project Chrono CPU SCM'||report.engine?.version!=='9.0.1'||report.active_app_dynamics!==false||report.lunar_validation_established!==false)throw new Error('Unsupported soil-contact evidence format.');
 return report;
}

function scmValidationHTML(r){
 const h=r.holdout_metrics,b=r.matched_rigid_baseline.metrics,p=r.protocol,selected=r.frozen_selection.parameters;
 const controls=[...r.training,...r.holdout].every(row=>row.controls_passed);
 return `<h2>How well do the soil models match a wheel test?</h2>
 <p>NASA Glenn TREC · Earth gravity · frozen training and held-out comparisons</p>
 <div class="data-note sim-validation-limit">Lunar soil calibration remains unresolved. ${r.holdout_targets_met?'The soil model meets the declared held-out traction targets.':'The soil model misses the declared held-out traction targets.'} ${r.numerical_targets_met?'Time-step and terrain-grid checks passed at three tested slips.':'Time-step or terrain-grid targets remain unmet.'} This development fixture is separate from your selected rover.</div>
 <div class="source-item"><h3>Deformable soil: ${esc(r.engine.name)} ${esc(r.engine.version)}</h3><p>The model tracks pressure, plastic sinkage and accumulated shear. Four parameter sets were ranked using ten training points. The selected set was frozen before eight held-out points were simulated. Repeated slip groups stay together; this is one published Earth experiment, rather than an independent lunar test.</p></div>
 <dl class="sim-details sim-validation-metrics"><div><dt>Held-out RMS discrepancy · 8 points</dt><dd>${number(h.rmse_deg)}° <small>target ≤ ${number(p.checks.holdout_traction_rmse_target_deg,0)}°</small></dd></div><div><dt>Rigid baseline · same 8 points</dt><dd>${number(b.rmse_deg)}° <small>unfitted rigid contact</small></dd></div><div><dt>Largest held-out discrepancy</dt><dd>${number(h.maximum_abs_error_deg)}° <small>target ≤ ${number(p.checks.holdout_maximum_abs_traction_error_target_deg,0)}°</small></dd></div><div><dt>Base rig speed, load and settling</dt><dd>${controls?'Passed':'Target not met'}</dd></div></dl>
 <figure class="sim-validation-figure"><img src="/data/scm-validation.png" alt="NASA Glenn wheel observations, frozen soil-model training and held-out predictions, and rigid contact. Signed discrepancies on the eight held-out points appear below." width="1800" height="1440" loading="lazy"><figcaption>Hollow circles identify training predictions; filled squares identify held-out predictions. Scores use the declared base step and grid; the refinement checks below qualify their interpretation. The lower panel compares both models on the same eight observations. No experimental error bars are supplied. <a href="/data/scm-validation.png" target="_blank" rel="noreferrer">Open full-size chart</a></figcaption></figure>
 <details class="sim-repair-all"><summary>Eight held-out comparisons</summary><div class="sim-compare-scroll"><table class="sim-compare-table"><thead><tr><th scope="col">Driving slip</th><th scope="col">Published traction</th><th scope="col">Soil model</th><th scope="col">Difference</th></tr></thead><tbody>${r.holdout.map(row=>`<tr><td>${number(row.configuration.slip*100)}%</td><td>${number(row.published_traction_slope_deg)}°</td><td>${number(row.mean_traction_slope_deg)}°</td><td>${number(row.mean_traction_slope_deg-row.published_traction_slope_deg)}°</td></tr>`).join('')}</tbody></table></div></details>
 <details class="sim-repair-all"><summary>Separate time-step and terrain-grid checks</summary><p class="sim-hint">Changes are relative to the same frozen candidate at the base step and grid. Each check must change mean traction by no more than 1° and pass the rig controls. These checks cover three slips, rather than every operating condition.</p><div class="sim-compare-scroll"><table class="sim-compare-table"><thead><tr><th scope="col">Driving slip</th><th scope="col">Refinement</th><th scope="col">Traction change</th><th scope="col">Rig controls</th><th scope="col">Refinement target</th></tr></thead><tbody>${r.refinements.map(row=>`<tr><td>${number(row.configuration.slip*100)}%</td><td>${row.kind==='time'?'Half time step':'Half grid spacing'}</td><td>${number(row.traction_change_deg)}°</td><td>${row.controls_passed?'Passed':'Target not met'}</td><td>${row.controls_passed&&Math.abs(row.traction_change_deg)<=p.checks['maximum_'+row.kind+'_refinement_traction_change_deg']?'Met':'Not met'}</td></tr>`).join('')}</tbody></table></div></details>
 <div class="source-item"><h3>What the fit can support</h3><p>Selected friction angle ${number(selected.friction_angle_deg,0)}° and shear length ${number(selected.janosi_m,3)} m are effective development inputs, rather than measured GRC-3 properties. Pressure–sinkage stiffness, exponent, cohesion and damping remain declared assumptions. Traction alone does not uniquely identify soil physics. The base step is ${number(p.base_dt_s*1000,1)} ms with a ${number(p.base_grid_m*100,1)} cm soil grid; that grid is a model discretization, not measured lunar terrain.</p><p>This CPU semi-empirical model differs from the study’s GPU continuum/SPH model. It does not establish flight-rover performance, lunar-gravity regolith response, wheel-scale hazards or calibrated electrical and thermal behavior. Mission dynamics still uses the selected MuJoCo or Gazebo rigid-contact engine.</p></div>
 <div class="dialog-links"><a href="/data/scm-validation.json" download="clavius-soil-contact-validation.json">Download soil-contact report &amp; checks</a><a href="https://github.com/projectchrono/chrono/tree/2617649bf687456328a122b63dc0bb64df91394a" target="_blank" rel="noreferrer">Open-source Chrono model</a></div>`;
}

export function mobilityValidationHTML(r,scm=null){
 const s=r.summary,p=r.policy;
 return `${scm?scmValidationHTML(scm):''}${scm?'<hr><h3>Original rigid-contact baseline</h3>':'<h2>How well does rigid contact match a wheel test?</h2>'}
 <p>NASA Glenn TREC reference · Earth gravity · ${r.points.length} published traction points</p>
 <div class="data-note sim-validation-limit">Lunar soil calibration remains unresolved. ${s.traction_development_targets_met?'This rigid fixture meets the declared comparison targets.':'This rigid fixture misses the declared traction targets.'} These laboratory results do not validate performance on lunar regolith.</div>
 <dl class="sim-details sim-validation-metrics"><div><dt>RMS traction discrepancy</dt><dd>${number(s.traction_rmse_deg)}° <small>target ≤ ${number(p.traction_rmse_target_deg,0)}°</small></dd></div><div><dt>Largest traction discrepancy</dt><dd>${number(s.maximum_abs_traction_error_deg)}° <small>target ≤ ${number(p.maximum_traction_error_target_deg,0)}°</small></dd></div><div><dt>Rig speed and load checks</dt><dd>${s.all_rig_controls_passed?'Passed':'Incomplete or failed'}</dd></div><div><dt>Half-step numerical checks</dt><dd>${s.refinement_targets_met?'Passed at three tested slips':'Target not met'}</dd></div></dl>
 <figure class="sim-validation-figure"><img src="/data/mobility-validation.png" alt="Published NASA Glenn wheel traction points compared with the rigid-contact model, with their signed discrepancies below." width="1620" height="1260" loading="lazy"><figcaption>The model uses a rigid plane and declared friction 0.7. The published tests use deformable GRC-3 simulant. All repeats and small negative observations are retained. <a href="/data/mobility-validation.png" target="_blank" rel="noreferrer">Open full-size chart</a></figcaption></figure>
 <div class="source-item"><h3>What was compared</h3><p>A ${number(r.rig.wheel_outer_radius_m,2)} m radius, ${number(r.rig.wheel_width_m,2)} m wide wheel with ${r.rig.grouser_count} grousers, ${number(r.rig.normal_loaded_mass_kg,1)} kg of normal-loaded mass and ${number(r.rig.translation_m_s,1)} m/s controlled translation. Drawbar pull comes from native contact forces and the rig's inertial balance.</p><p>${esc(r.engine.name)} ${esc(r.engine.version)} · ${number(p.timestep_s*1e6,3)} μs base step · final 10 s averaged. No parameters were fitted to the observed points. Numerical and traction thresholds are development targets, not experimental error bars.</p></div>
 <details class="sim-repair-all"><summary>All ${r.points.length} published comparisons</summary><div class="sim-compare-scroll"><table class="sim-compare-table"><thead><tr><th scope="col">Driving slip</th><th scope="col">Published traction</th><th scope="col">Rigid model</th><th scope="col">Difference</th></tr></thead><tbody>${r.points.map(point=>`<tr><td>${number(point.requested_slip_fraction*100)}%</td><td>${number(point.published_traction_slope_deg)}°</td><td>${number(point.mean_traction_slope_deg)}°</td><td>${number(point.mean_traction_slope_deg-point.published_traction_slope_deg)}°</td></tr>`).join('')}</tbody></table></div></details>
 <p class="sim-hint">The observations are numeric plotting points distributed by the paper's authors, rather than raw rig telemetry. Wheel inertia and the guide implementation are declared approximations. This is an independent reference fixture, separate from your selected rover and its measured-terrain run.</p>
 <div class="dialog-links"><a href="/data/mobility-validation.json" download="clavius-wheel-validation.json">Download comparison & checks</a><a href="/data/mobility-reference.json" download="clavius-wheel-reference.json">Published points & source hashes</a><a href="https://ntrs.nasa.gov/citations/20250001809" target="_blank" rel="noreferrer">NASA-hosted study</a></div>`;
}
