import {test} from 'node:test';
import assert from 'node:assert/strict';
import {submitVideo} from '../src/jobs.mjs';

const result = {predicted_label: 'fake', confidence: 0.8, probabilities: {fake: 0.8, real: 0.2}, frame_count: 10, sampled_frames: 10};
const accepted = {job_id: 'job-123', job_token: 'opaque-capability', status: 'queued'};
function harness(responses) {
  let time = 0;
  const calls = [], delays = [], status = [];
  return {calls, delays, status, options: {
    fetch: async (...args) => {calls.push(args); const next = responses.shift(); if (next instanceof Error) throw next; return typeof next === 'number' ? new Response('', {status: next}) : Response.json(next);},
    now: () => time, sleep: async ms => {time += ms; delays.push(ms);},
  }};
}
test('polls with backoff and attaches the opaque capability only to job reads', async () => {
  const h = harness([accepted, {status: 'processing'}, {status: 'completed', result}]);
  assert.deepEqual(await submitVideo('https://example.test', new FormData(), s => h.status.push(s), h.options), result);
  assert.deepEqual(h.delays, [1000, 1500]);
  assert.equal(h.calls[1][1].headers['X-Job-Token'], accepted.job_token);
  assert.equal(h.calls[0][1].headers, undefined);
});
test('recovers from cold-start server and network failures', async () => {
  const h = harness([accepted, 503, new TypeError('offline'), {status: 'completed', result}]);
  assert.deepEqual(await submitVideo('https://example.test', new FormData(), s => h.status.push(s), h.options), result);
  assert.ok(h.status.includes('Reconnecting to the service…'));
});
test('reports terminal failures, missing capabilities and malformed predictions', async () => {
  for (const response of [404, {status: 'failed'}, {status: 'completed', result: null}]) {
    const h = harness([accepted, response]);
    await assert.rejects(submitVideo('https://example.test', new FormData(), () => {}, h.options));
  }
});
test('does not retry uploads on queue saturation', async () => {
  const h = harness([429]);
  await assert.rejects(submitVideo('https://example.test', new FormData(), () => {}, h.options));
  assert.equal(h.calls.length, 1);
});
test('polling has a finite deadline', async () => {
  const h = harness([accepted]);
  let time = 0;
  h.options.now = () => time;
  h.options.sleep = async () => {time = 900_001;};
  await assert.rejects(submitVideo('https://example.test', new FormData(), () => {}, h.options), /longer than expected/);
  assert.equal(h.calls.length, 1);
});
