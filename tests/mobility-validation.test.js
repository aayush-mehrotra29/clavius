import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { loadMobilityValidation } from '../src/mobility-validation.js';

test('published mobility comparison loads only with its pinned numerical bytes', async t=>{
 const manifest=await readFile(new URL('../public/data/manifest.json',import.meta.url),'utf8');
 const report=await readFile(new URL('../public/data/mobility-validation.json',import.meta.url));
 t.mock.method(globalThis,'fetch',async url=>new Response(url==='/data/manifest.json'?manifest:report));
 const result=await loadMobilityValidation();
 assert.equal(result.summary.point_count,18);
 assert.equal(result.summary.all_rig_controls_passed,true);
 assert.equal(result.summary.traction_development_targets_met,false);
 assert.equal(result.summary.lunar_validation_established,false);
});

test('changed traction results cannot silently replace the recorded evidence', async t=>{
 const manifest=await readFile(new URL('../public/data/manifest.json',import.meta.url),'utf8');
 const report=JSON.parse(await readFile(new URL('../public/data/mobility-validation.json',import.meta.url),'utf8'));
 report.summary.traction_rmse_deg=0;
 t.mock.method(globalThis,'fetch',async url=>new Response(url==='/data/manifest.json'?manifest:JSON.stringify(report)));
 await assert.rejects(loadMobilityValidation(),/recorded source hash/);
});
