'use strict';
const opening = new Map();
const queues = new Map();
const bindingKey = tabId => `pipWindow:${tabId}`;
const validId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
// Only virtual HeadlessChrome PiP windows may report alwaysOnTop=false.
const headless = /HeadlessChrome\//.test(navigator.userAgent);
const ownedWindow = async (binding) => {
  const win = await chrome.windows.get(binding.windowId, { populate: true });
  if (win.id === binding.sourceWindowId || (!win.alwaysOnTop && !headless) || win.tabs?.length !== 1 || win.tabs[0].id !== binding.childTabId || win.tabs[0].openerTabId !== binding.sourceTabId) throw new Error('Привязка окна PiP больше не действительна');
  return win;
};
async function handleDrag(message, sender) {
  if (sender.frameId !== 0 || !Number.isInteger(sender.tab?.id) || !validId(message.nonce)) throw new Error('Некорректный источник команды');
  const key = bindingKey(sender.tab.id);
  if (message.type === 'independent-pip:bind') {
    const snapshot = await opening.get(sender.tab.id);
    if (!snapshot) throw new Error('Окно не было открыто действием расширения');
    const candidates = (await chrome.windows.getAll({ populate: true })).filter(win => !snapshot.has(win.id) && win.id !== sender.tab.windowId && (win.alwaysOnTop || headless) && win.tabs?.length === 1 && win.tabs[0].openerTabId === sender.tab.id);
    if (candidates.length !== 1) throw new Error('Не удалось однозначно определить своё окно PiP. Перемещай за рамку Chrome.');
    const win = candidates[0];
    await chrome.storage.session.set({ [key]: { nonce: message.nonce, windowId: win.id, childTabId: win.tabs[0].id, sourceTabId: sender.tab.id, sourceWindowId: sender.tab.windowId } });
    return { ok: true };
  }
  const binding = (await chrome.storage.session.get(key))[key];
  if (!binding || binding.nonce !== message.nonce || binding.sourceTabId !== sender.tab.id) throw new Error('Команда относится к закрытому окну PiP');
  if (message.type === 'independent-pip:release') { await chrome.storage.session.remove(key); return { ok: true }; }
  const win = await ownedWindow(binding);
  if (!validId(message.gesture)) throw new Error('Некорректный жест');
  if (message.type === 'independent-pip:drag-start') binding.drag = { gesture: message.gesture, left: win.left, top: win.top, sequence: 0 };
  else {
    if (binding.drag?.gesture !== message.gesture) throw new Error('Жест уже завершён');
    if (message.type === 'independent-pip:drag-end') delete binding.drag;
    else if (message.type === 'independent-pip:drag-move') {
      if (![message.dx, message.dy].every(n => Number.isInteger(n) && Math.abs(n) <= 32000) || !Number.isSafeInteger(message.sequence) || message.sequence <= binding.drag.sequence) throw new Error('Некорректные координаты или порядок');
      const left = binding.drag.left + message.dx, top = binding.drag.top + message.dy;
      if (![left, top].every(n => Number.isInteger(n) && Math.abs(n) <= 32767)) throw new Error('Координаты вне диапазона');
      await chrome.windows.update(binding.windowId, { left, top });
      binding.drag.sequence = message.sequence;
    } else throw new Error('Неизвестная команда');
  }
  await chrome.storage.session.set({ [key]: binding });
  return { ok: true };
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message?.type === 'independent-pip:options') {
    chrome.runtime.openOptionsPage().then(() => respond({ ok: true }), error => respond({ ok: false, message: String(error.message || error) }));
    return true;
  }
  if (!['bind', 'release', 'drag-start', 'drag-move', 'drag-end'].some(type => message?.type === `independent-pip:${type}`)) return false;
  const tabId = sender.tab?.id;
  const work = (queues.get(tabId) || Promise.resolve()).catch(() => {}).then(() => handleDrag(message, sender));
  queues.set(tabId, work);
  work.then(respond, error => respond({ ok: false, message: String(error.message || error) })).finally(() => { if (queues.get(tabId) === work) queues.delete(tabId); });
  return true;
});
chrome.tabs.onRemoved.addListener(tabId => chrome.storage.session.remove(bindingKey(tabId)).catch(() => {}));
chrome.action.onClicked.addListener(async (tab) => {
  if (!Number.isInteger(tab.id) || opening.has(tab.id)) return;
  opening.set(tab.id, null);
  try {
    // Invoke the snapshot request first, but never await before executeScript:
    // doing so loses the toolbar's user gesture (notably on later reopen).
    opening.set(tab.id, chrome.windows.getAll().then(windows => new Set(windows.map(win => win.id))));
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: false },
      world: 'ISOLATED',
      files: ['settings.js', 'pip.js'],
    });
    const result = results[0]?.result;
    if (!result?.ok) throw new Error(result?.message || 'Не удалось открыть PiP на этой странице.');
    await chrome.action.setBadgeText({ tabId: tab.id, text: '' });
    const title = result.mode === 'closed'
      ? 'Открыть Picture-in-Picture (Alt+Shift+P)'
      : result.mode === 'native'
        ? 'Нативный PiP: захват недоступен. Нажми, чтобы закрыть.'
        : 'Закрыть Picture-in-Picture (Alt+Shift+P)';
    await chrome.action.setTitle({ tabId: tab.id, title });
  } catch (error) {
    const message = String(error?.message || error);
    await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: '#c0392b' });
    await chrome.action.setBadgeText({ tabId: tab.id, text: '!' });
    await chrome.action.setTitle({ tabId: tab.id, title: message });
  } finally { opening.delete(tab.id); }
});
