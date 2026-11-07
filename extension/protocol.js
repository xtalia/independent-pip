// Shared wire contract. This module has no browser side effects.
(() => {
  'use strict';
  const validId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const scripts = Object.freeze(['media.js', 'settings.js', 'pip-view.js', 'pip-drag.js', 'pip.js']);
  const failure = error => ({ ok: false, message: String(error?.message || error) });
  const pickerSender = (runtime, sender) => sender.id === runtime.id && sender.url?.split('?')[0] === runtime.getURL('picker.html');
  globalThis.IndependentPiPProtocol = Object.freeze({ validId, scripts, failure, pickerSender });
})();
