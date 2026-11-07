import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../extension/picker-client.js', import.meta.url), 'utf8');
function load(sendMessage) {
  const context = vm.createContext({ chrome: { runtime: { sendMessage } }, setTimeout, clearTimeout });
  vm.runInContext(source, context);
  return context.IndependentPiPPickerClient;
}
const closed = () => new Error('A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received');

test('list retries once after transport closure, not after an ordinary error', async () => {
  let calls = 0;
  const client = load(() => ++calls === 1 ? Promise.reject(closed()) : Promise.resolve({ ok: true, videos: [] }));
  assert.equal((await client.requestList(1)).ok, true);
  assert.equal(calls, 2);
  calls = 0;
  await assert.rejects(load(() => { calls++; return Promise.reject(new Error('Permission denied')); }).requestList(1), /Permission denied/);
  assert.equal(calls, 1);
});

test('two lost list responses return an actionable error and stop retrying', async () => {
  let calls = 0;
  const client = load(() => { calls++; return Promise.reject(closed()); });
  await assert.rejects(client.requestList(1), /Обновить список/);
  assert.equal(calls, 2);
});

test('selection sends immediately and never retries a possibly applied side effect', async () => {
  let calls = 0;
  const client = load(() => { calls++; return Promise.reject(closed()); });
  const response = client.select(1, 'video-id');
  assert.equal(calls, 1);
  await assert.rejects(response, /команда не отправлялась повторно/);
  assert.equal(calls, 1);
});
