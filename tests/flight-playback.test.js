import test from 'node:test';
import assert from 'node:assert/strict';
import {advanceSample} from '../src/flight/playback.js';

test('the first frame and an earlier frame timestamp keep a valid flight sample', () => {
  assert.equal(advanceSample(0, undefined, 900, 50, 391), 0);
  assert.equal(advanceSample(0, 905, 900, 50, 391), 0);
  assert.equal(advanceSample(0, 900, 910, 50, 391), 0.5);
});

test('playback limits long gaps and wraps at the saved sample count', () => {
  assert.equal(advanceSample(390, 100, 3000, 10, 391), 1.5);
});
