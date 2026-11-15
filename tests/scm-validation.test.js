import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { loadSCMValidation,mobilityValidationHTML } from '../src/mobility-validation.js';

const source=path=>readFile(new URL('../public/data/'+path,import.meta.url),'utf8');

test('the pinned soil report retains its held-out and numerical failures',async t=>{
 const manifest=await source('manifest.json'),report=await source('scm-validation.json');
 t.mock.method(globalThis,'fetch',async url=>new Response(url==='/data/manifest.json'?manifest:report));
 const r=await loadSCMValidation();
 assert.equal(r.holdout.length,8);assert.equal(r.training.length,10);
 assert.equal(r.holdout_targets_met,false);assert.equal(r.numerical_targets_met,false);
 assert.equal(r.lunar_validation_established,false);assert.equal(r.active_app_dynamics,false);
 assert.deepEqual(r.matched_rigid_baseline.source_indices,r.protocol.holdout_source_indices);
});

test('changed soil scores cannot replace source-pinned native evidence',async t=>{
 const manifest=await source('manifest.json'),r=JSON.parse(await source('scm-validation.json'));
 r.holdout_metrics.rmse_deg=0;
 t.mock.method(globalThis,'fetch',async url=>new Response(url==='/data/manifest.json'?manifest:JSON.stringify(r)));
 await assert.rejects(loadSCMValidation(),/recorded source hash/);
});

test('an Earth development report cannot silently become lunar validation',async t=>{
 const manifest=JSON.parse(await source('manifest.json')),r=JSON.parse(await source('scm-validation.json'));
 r.lunar_validation_established=true;const raw=JSON.stringify(r);
 manifest.scm_validation.report.sha256=createHash('sha256').update(raw).digest('hex');
 t.mock.method(globalThis,'fetch',async url=>new Response(url==='/data/manifest.json'?JSON.stringify(manifest):raw));
 await assert.rejects(loadSCMValidation(),/Unsupported soil-contact evidence/);
});

test('passed rig controls do not hide failed refinement targets',async()=>{
 const rigid=JSON.parse(await source('mobility-validation.json')),soil=JSON.parse(await source('scm-validation.json'));
 assert.ok(soil.refinements.every(row=>row.controls_passed));
 const html=mobilityValidationHTML(rigid,soil);
 assert.equal((html.match(/<td>Not met<\/td>/g)||[]).length,2);
 assert.match(html,/9\.68°/);assert.match(html,/15\.60°/);
 assert.match(html,/Mission dynamics still uses the selected MuJoCo or Gazebo/);
});
