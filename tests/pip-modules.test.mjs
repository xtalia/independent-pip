import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const extension = new URL('../extension/', import.meta.url);
function load(name) {
  const file = new URL(name, extension);
  assert.ok(existsSync(file), `${name} feature module must exist`);
  const context = vm.createContext({ AbortController });
  vm.runInContext(readFileSync(file, 'utf8'), context, { filename: name });
  return context;
}

// Minimal DOM boundary: exercise the actual ordinary-script factory without a browser.
class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.style = { setProperty(name, value) { this[name] = value; } };
    this.dataset = {};
    this.textContent = '';
    this.classList = { add() {}, remove() {} };
    this.events = new Target();
  }
  addEventListener(...args) { this.events.addEventListener(...args); }
  emit(...args) { return this.events.emit(...args); }
  play() { return Promise.resolve(); }
  hasPointerCapture() { return false; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  get options() { return this.children; }
}
function documentFixture() {
  const document = {
    head: new Element('head'), body: new Element('body'),
    createElement: tag => new Element(tag),
  };
  return document;
}

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

test('view factory isolates DOM, safe title and accessible controls behind a frozen namespace', () => {
  const context = load('pip-view.js');
  assert.deepEqual(Object.keys(context), ['AbortController', 'IndependentPiPView']);
  assert.ok(Object.isFrozen(context.IndependentPiPView));
  const document = documentFixture();
  const view = context.IndependentPiPView.create({ document, title: 'Long <b>safe</b> title' });
  assert.equal(document.title, 'Independent PiP');
  assert.equal(document.head.children.length, 1);
  assert.equal(document.head.children[0].tagName, 'STYLE');
  assert.deepEqual(document.body.children.map(e => e.id), ['pip-viewport', 'pip-header', 'pip-controls', 'pip-menu']);
  const title = descendants(document.body).find(e => e.id === 'pip-title');
  assert.equal(title.textContent, 'Long <b>safe</b> title');
  assert.equal(title.title, title.textContent);
  assert.equal(title.children.length, 0);
  assert.equal(view.preview.muted, true);
  assert.equal(view.preview.playsInline, true);
  assert.equal(view.preview.srcObject, undefined, 'stream ownership stays in the orchestrator');
  assert.equal(view.preview.tabIndex, 0);
  assert.equal(view.seekTooltip.hidden, true);
  assert.equal(view.seekTooltip.getAttribute('aria-hidden'), 'true');
  assert.equal(view.volumePopup.hidden, true);
  assert.equal(view.menu.hidden, true);
  assert.equal(view.mute.getAttribute('aria-expanded'), 'false');
  assert.equal(view.applyRateButton.type, 'submit');
  assert.equal(view.returnButton.getAttribute('aria-label'), view.returnButton.title);
  assert.ok(!descendants(document.body).some(e => e.id === 'pip-captions'));
});

test('rate population accepts current preferences explicitly and preserves an exact source rate', () => {
  const context = load('pip-view.js');
  const view = context.IndependentPiPView.create({ document: documentFixture(), title: '' });
  assert.equal(typeof view.populateRates, 'function');
  view.populateRates([2, 1.1, 1, 1.1, 0.5], 1.234);
  assert.deepEqual(Array.from(view.rate.options, option => option.value), ['0.5', '1', '1.1', '1.234', '2']);
  assert.equal(view.rate.options[2].textContent, '1.10×');
  assert.equal(view.rate.value, '1.234');
  view.selectRate(1.777);
  assert.equal(view.rate.value, '1.777');
  assert.equal(view.rate.options.at(-1).textContent, '1.777×');
  view.selectRate(1.777);
  assert.equal(view.rate.options.length, 6);
  view.populateRates([0.25, 4], 1.777);
  assert.deepEqual(Array.from(view.rate.options, option => option.value), ['0.25', '1.777', '4']);
  assert.equal(descendants(view.preview).length, 1);
});

const abortCallbacks = new WeakMap();
class Target {
  listeners = new Map();
  addEventListener(type, handler, { signal } = {}) {
    if (signal?.aborted) return;
    const handlers = this.listeners.get(type) || new Set();
    handlers.add(handler);
    this.listeners.set(type, handlers);
    if (signal) {
      if (!abortCallbacks.has(signal)) {
        const callbacks = [];
        abortCallbacks.set(signal, callbacks);
        signal.addEventListener('abort', () => callbacks.forEach(fn => fn()), { once: true });
      }
      abortCallbacks.get(signal).push(() => handlers.delete(handler));
    }
  }
  emit(type, detail = {}) {
    const event = { isTrusted: true, button: 0, pointerId: 7, screenX: 100, screenY: 100,
      detail: 1, preventDefault() { this.defaultPrevented = true; }, ...detail };
    for (const handler of [...(this.listeners.get(type) || [])]) handler(event);
    return event;
  }
  get listenerCount() { return [...this.listeners.values()].reduce((sum, handlers) => sum + handlers.size, 0); }
}
const settle = () => new Promise(resolve => setImmediate(resolve));
function dragFixture() {
  const context = load('pip-drag.js');
  assert.deepEqual(Object.keys(context), ['AbortController', 'IndependentPiPDrag']);
  assert.ok(Object.isFrozen(context.IndependentPiPDrag));
  const preview = new Target();
  preview.style = {};
  const captures = new Set();
  preview.setPointerCapture = id => captures.add(id);
  preview.hasPointerCapture = id => captures.has(id);
  preview.releasePointerCapture = id => { captures.delete(id); preview.emit('lostpointercapture', { pointerId: id }); };
  const frames = new Map();
  let frameId = 0;
  const pipWindow = new Target();
  pipWindow.requestAnimationFrame = fn => { frames.set(++frameId, fn); return frameId; };
  pipWindow.cancelAnimationFrame = id => frames.delete(id);
  const document = { body: { dataset: { dragAvailable: 'true' } } };
  const abort = new AbortController();
  const requests = [], errors = [];
  let gesture = 0;
  const controller = context.IndependentPiPDrag.attach({
    document, preview, pipWindow, signal: abort.signal, nonce: 'window-nonce',
    createGesture: () => `gesture-${++gesture}`,
    sendMessage: message => new Promise((resolve, reject) => requests.push({ ...message, resolve, reject })),
    onError: error => errors.push(String(error.message || error)),
  });
  return { controller, document, preview, pipWindow, abort, requests, errors, frames, captures,
    tick() { const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(fn => fn()); },
    reply(index, response = { ok: true }) { requests[index].resolve(response); return settle(); },
  };
}

test('drag coalesces unsent positions with one in-flight request and start/end barriers', async () => {
  const f = dragFixture();
  try {
    f.preview.emit('pointerdown');
    await settle();
    assert.equal(f.requests[0].type, 'independent-pip:drag-start');
    assert.equal(f.requests[0].nonce, 'window-nonce');
    for (const x of [110, 120, 130]) f.preview.emit('pointermove', { screenX: x });
    assert.equal(f.frames.size, 1);
    assert.equal(f.requests.length, 1);
    f.tick();
    f.preview.emit('pointermove', { screenX: 140 });
    f.tick();
    assert.equal(f.requests.length, 1, 'start is still in flight');
    await f.reply(0);
    assert.equal(f.requests.length, 2);
    assert.equal(f.requests[1].dx, 40, 'only the latest unsent position survives');
    assert.equal(f.requests[1].sequence, 2);
    f.preview.emit('pointermove', { screenX: 150 });
    f.preview.emit('pointerup');
    assert.equal(f.frames.size, 0, 'pointer release flushes the final position synchronously');
    f.preview.emit('pointerdown', { screenX: 200 });
    f.preview.emit('pointermove', { screenX: 220 });
    f.preview.emit('pointerup');
    assert.equal(f.requests.length, 2, 'the second move is still the only request in flight');
    for (let i = 1; i < 7; i++) await f.reply(i);
    assert.deepEqual(f.requests.map(r => r.type.replace('independent-pip:', '')),
      ['drag-start', 'drag-move', 'drag-move', 'drag-end', 'drag-start', 'drag-move', 'drag-end']);
    assert.equal(f.requests[2].dx, 50);
    assert.equal(f.requests[2].sequence, 3);
    assert.equal(f.requests[3].gesture, 'gesture-1');
    assert.equal(f.requests[4].gesture, 'gesture-2');
    assert.equal(f.requests[5].dx, 20);
    assert.equal(f.requests[5].sequence, 1);
  } finally { f.controller.cleanup(); }
});

test('orchestrator uses both modules without delaying activation and releases only its capture', async () => {
  const context = load('pip-view.js');
  for (const file of ['pip-drag.js', 'pip.js']) {
    vm.runInContext(readFileSync(new URL(file, extension), 'utf8'), context, { filename: file });
  }
  const order = [], messages = [], storedListeners = new Set();
  const document = Object.assign(new Target(), documentFixture());
  const pipWindow = Object.assign(new Target(), {
    document, closed: false, clearTimeout() {}, cancelAnimationFrame() {},
    close() { this.closed = true; this.emit('pagehide'); },
  });
  const sourceWindow = new Target();
  sourceWindow.documentPictureInPicture = {};
  const sourceDocument = { title: 'source title', defaultView: sourceWindow };
  const videoTrack = { stop() { this.stopped = true; } };
  const audioTrack = { stop() { this.stopped = true; } };
  const sourceTrack = { stop() { throw new Error('must not stop the original source track'); } };
  const capture = { getTracks: () => [videoTrack, audioTrack], getVideoTracks: () => [videoTrack] };
  const textTracks = new Target();
  textTracks[Symbol.iterator] = function* () {};
  const source = Object.assign(new Target(), { ownerDocument: sourceDocument, volume: 0.7, muted: false,
    paused: false, playbackRate: 1.234, currentTime: 2, duration: 10, seekable: { length: 0 }, textTracks,
    isConnected: true, getRootNode: () => sourceDocument, captureStream: () => capture,
    srcObject: { getTracks: () => [sourceTrack] } });
  let viewCalls = 0, dragCalls = 0, dragCleanups = 0, disconnected = false;
  const viewModule = context.IndependentPiPView, dragModule = context.IndependentPiPDrag;
  context.IndependentPiPView = { create(args) { viewCalls++; return viewModule.create(args); } };
  context.IndependentPiPDrag = { attach(args) {
    dragCalls++;
    const drag = dragModule.attach(args);
    return { ...drag, cleanup() { dragCleanups++; drag.cleanup(); } };
  } };
  Object.assign(context, {
    document: sourceDocument, window: sourceWindow, queueMicrotask,
    crypto: { randomUUID: () => 'nonce' },
    MediaStream: class { constructor(tracks) { this.tracks = tracks; } },
    MutationObserver: class { observe() {} disconnect() { disconnected = true; } },
    documentPictureInPicture: { requestWindow() { order.push('requestWindow'); return Promise.resolve(pipWindow); } },
    IndependentPiPMedia: { collect: () => [source], id: () => 'source', allowed: () => true },
    IndependentPiPSettings: { defaults: {}, key: 'prefs', normalize: value => value, rates: prefs => prefs.rates || [1, 1.1, 2],
      read() { order.push('settings.read'); return Promise.resolve({}); } },
    chrome: { runtime: { sendMessage(message) { messages.push(message); return Promise.resolve({ ok: true }); } },
      storage: { onChanged: { addListener: fn => storedListeners.add(fn), removeListener: fn => storedListeners.delete(fn) } } },
  });
  const result = await context.IndependentPiPOpen('source');
  assert.equal(result.mode, 'document', result.message);
  assert.equal(viewCalls, 1, 'view factory must own UI construction');
  assert.equal(dragCalls, 1, 'drag factory must own gesture state');
  assert.deepEqual(order, ['requestWindow', 'settings.read']);
  const preview = descendants(document.body).find(e => e.id === 'pip-video');
  assert.deepEqual(preview.srcObject.tracks, [videoTrack]);
  assert.equal(source.playbackRate, 1.234);
  assert.equal(storedListeners.size, 1);
  [...storedListeners][0]({ prefs: { newValue: { rates: [0.75, 1.5], showSeekButtons: false } } }, 'local');
  const rate = descendants(document.body).find(e => e.id === 'pip-rate');
  assert.deepEqual(Array.from(rate.options, option => option.value), ['0.75', '1.234', '1.5']);
  assert.equal(rate.value, '1.234');
  assert.equal(descendants(document.body).find(e => e.id === 'pip-back').hidden, true);
  assert.equal(source.playbackRate, 1.234);
  pipWindow.close();
  assert.equal(dragCleanups, 1);
  assert.equal(storedListeners.size, 0);
  assert.equal(source.listenerCount, 0);
  assert.equal(preview.events.listenerCount, 0);
  assert.equal(preview.srcObject, null);
  assert.equal(videoTrack.stopped, true);
  assert.equal(audioTrack.stopped, true);
  assert.equal(source.paused, false);
  assert.equal(disconnected, true);
  assert.equal(context.__independentPiPState, undefined);
  assert.deepEqual(messages.map(message => message.type), ['independent-pip:bind', 'independent-pip:release']);
});

for (const finishEvent of ['pointerup', 'pointercancel', 'lostpointercapture', 'blur']) {
  test(`${finishEvent} ends a trusted drag, flushes release coordinates and suppresses only pointer clicks`, async () => {
    const f = dragFixture();
    try {
      f.document.body.dataset.dragAvailable = 'false';
      f.preview.emit('pointerdown');
      f.document.body.dataset.dragAvailable = 'true';
      f.preview.emit('pointerdown', { isTrusted: false });
      f.preview.emit('pointerdown', { button: 2 });
      await settle();
      assert.equal(f.requests.length, 0);
      f.preview.emit('pointerdown');
      await settle();
      f.preview.emit('pointermove', { screenX: 104 });
      f.preview.emit('pointermove', { screenX: 130, isTrusted: false });
      f.preview.emit('pointermove', { screenX: 130, pointerId: 99 });
      assert.equal(f.frames.size, 0);
      const event = f.preview.emit('pointermove', { screenX: 105, screenY: 91 });
      assert.equal(event.defaultPrevented, true);
      assert.equal(f.preview.style.cursor, 'grabbing');
      (finishEvent === 'blur' ? f.pipWindow : f.preview).emit(finishEvent);
      assert.equal(f.frames.size, 0);
      assert.equal(f.captures.size, 0);
      assert.equal(f.preview.style.cursor, '');
      assert.equal(f.controller.shouldSuppressClick({ detail: 0 }), false, 'keyboard activation is never suppressed');
      assert.equal(f.controller.shouldSuppressClick({ detail: 1 }), true);
      assert.equal(f.controller.shouldSuppressClick({ detail: 1 }), false);
      await f.reply(0);
      assert.equal(f.requests[1].dx, 5);
      assert.equal(f.requests[1].dy, -9);
      await f.reply(1);
      assert.equal(f.requests[2].type, 'independent-pip:drag-end');
      await f.reply(2);
    } finally { f.controller.cleanup(); }
  });
}

for (const close of ['cleanup', 'abort']) {
  test(`${close} cancels frames/listeners/queued moves and ignores late message failures`, async () => {
    const f = dragFixture();
    f.preview.emit('pointerdown');
    await settle();
    f.preview.emit('pointermove', { screenX: 120 });
    f.tick();
    f.preview.emit('pointermove', { screenX: 130 });
    if (close === 'abort') f.abort.abort();
    else f.controller.cleanup();
    f.controller.cleanup();
    assert.equal(f.frames.size, 0);
    assert.equal(f.captures.size, 0);
    assert.equal(f.preview.listenerCount, 0);
    assert.equal(f.pipWindow.listenerCount, 0);
    f.requests[0].reject(new Error('late failure'));
    await settle();
    f.preview.emit('pointerdown');
    f.tick();
    await settle();
    assert.equal(f.requests.length, 1);
    assert.deepEqual(f.errors, []);
  });
}

test('message failure is reported without poisoning the next ordered drag command', async () => {
  const f = dragFixture();
  try {
    f.preview.emit('pointerdown');
    await settle();
    f.preview.emit('pointermove', { screenX: 120 });
    f.preview.emit('pointerup');
    await f.reply(0, { ok: false, message: 'binding gone' });
    assert.deepEqual(f.errors, ['binding gone']);
    assert.equal(f.requests[1].type, 'independent-pip:drag-move');
    f.requests[1].reject(new Error('transport closed'));
    await settle();
    assert.deepEqual(f.errors, ['binding gone', 'transport closed']);
    assert.equal(f.requests[2].type, 'independent-pip:drag-end');
    await f.reply(2);
  } finally { f.controller.cleanup(); }
});
