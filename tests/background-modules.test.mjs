import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const files = ['protocol.js', 'background/windows.js', 'background/discovery.js', 'background/playback.js', 'background/messages.js', 'background/menus.js'];
function load() {
  const scope = vm.createContext({ setTimeout, clearTimeout, URL, navigator: { userAgent: 'HeadlessChrome/test' } });
  for (const file of files) vm.runInContext(readFileSync(new URL(`../extension/${file}`, import.meta.url), 'utf8'), scope, { filename: file });
  return scope;
}

test('worker modules expose frozen namespaces, not ambient implementation variables', () => {
  const scope = load();
  for (const name of ['Protocol', 'Windows', 'Discovery', 'Playback', 'Messages', 'Menus']) assert.ok(Object.isFrozen(scope[`IndependentPiP${name}`]), name);
  for (const name of ['opening', 'queues', 'listVideos', 'openTab', 'handleDrag']) assert.equal(name in scope, false, name);
});

test('router ignores unknown or foreign messages and invokes selection before returning', async () => {
  const scope = load();
  let listener, started = false;
  const chrome = { runtime: { id: 'own', getURL: path => `chrome-extension://own/${path}`, onMessage: { addListener: value => { listener = value; } } } };
  scope.IndependentPiPMessages.register({ chrome, windows: {}, discovery: {}, playback: { openTab: () => { started = true; return Promise.resolve({ ok: true }); } } });
  const sender = { id: 'own', url: 'chrome-extension://own/picker.html?source=1' };
  assert.equal(listener({ type: 'unknown' }, sender, () => {}), false);
  assert.equal(listener({ type: 'independent-pip:list', sourceTabId: 1 }, { ...sender, id: 'foreign' }, () => {}), false);
  let response;
  assert.equal(listener({ type: 'independent-pip:select', tabId: 1, videoId: '01234567-89ab-4def-8123-456789abcdef' }, sender, value => { response = value; }), true);
  assert.equal(started, true);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(response.ok, true);
});

test('action menus register settings and explicit chooser only in the toolbar context', async () => {
  const scope = load();
  const items = [];
  const chrome = { runtime: { lastError: undefined }, contextMenus: { removeAll: callback => callback(), create: (item, callback) => { items.push(item); callback(); } } };
  scope.IndependentPiPMenus.install(chrome);
  assert.deepEqual(items.map(item => [item.id, item.title, [...item.contexts]]), [['pip-settings', 'Настройки', ['action']], ['pip-picker', 'Выбор видео', ['action']]]);
});
