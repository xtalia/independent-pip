// Own-window binding, durable session identity and ordered drag commands.
(() => {
  'use strict';
  const create = ({ chrome, userAgent = navigator.userAgent }) => {
    const opening = new Map();
    const queues = new Map();
    const bindingKey = tabId => `pipWindow:${tabId}`;
    const { validId } = IndependentPiPProtocol;
    // Only virtual HeadlessChrome PiP windows may report alwaysOnTop=false.
    const headless = /HeadlessChrome\//.test(userAgent);
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

    const dispatch = (message, sender) => {
      const tabId = sender.tab?.id;
      const work = (queues.get(tabId) || Promise.resolve()).catch(() => {}).then(() => handleDrag(message, sender));
      queues.set(tabId, work);
      work.finally(() => { if (queues.get(tabId) === work) queues.delete(tabId); }).catch(() => {});
      return work;
    };
    return Object.freeze({
      hasOpening: tabId => opening.has(tabId),
      begin: tabId => opening.set(tabId, chrome.windows.getAll().then(windows => new Set(windows.map(win => win.id)))),
      finish: tabId => opening.delete(tabId),
      remove: tabId => chrome.storage.session.remove(bindingKey(tabId)),
      dispatch, handleDrag,
    });
  };
  globalThis.IndependentPiPWindows = Object.freeze({ create });
})();
