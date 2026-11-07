// Activation-sensitive PiP launch and explicit chooser entry points.
(() => {
  'use strict';
  const create = ({ chrome, windows, scripts }) => {
    async function openPicker(sourceTabId) {
      if (!Number.isInteger(sourceTabId)) return { ok: false, message: 'Вкладка недоступна' };
          const url = chrome.runtime.getURL(`picker.html?source=${sourceTabId}`);
          const existing = (await chrome.windows.getAll({ populate: true })).find(win => win.tabs?.some(item => item.url === url));
          if (existing) await chrome.windows.update(existing.id, { focused: true });
          else await chrome.windows.create({ url, type: 'popup', width: 500, height: 600 });
          await chrome.action.setBadgeText({ tabId: sourceTabId, text: '' });
          await chrome.action.setTitle({ tabId: sourceTabId, title: 'Выбрать видео для Picture-in-Picture' });
          return { ok: true, mode: 'choose' };
    }
    async function openTab(tab, selectedId) {
      if (!Number.isInteger(tab?.id)) return { ok: false, message: 'Вкладка недоступна' };
      if (windows.hasOpening(tab.id)) return { ok: false, message: 'Окно уже открывается. Попробуй ещё раз.' };
      try {
        // Invoke the snapshot request first, but never await before executeScript:
        // doing so loses the toolbar's user gesture (notably on later reopen).
        windows.begin(tab.id);
        const results = await chrome.scripting.executeScript(selectedId ? {
          target: { tabId: tab.id }, world: 'ISOLATED',
          func: id => globalThis.IndependentPiPOpen?.(id) || { ok: false, message: 'Страница изменилась. Обнови список видео.' },
          args: [selectedId],
        } : {
          target: { tabId: tab.id, allFrames: false },
          world: 'ISOLATED',
          files: [...scripts, 'launch.js'],
        }).catch(error => {
          if (selectedId) throw error;
          // Browser/internal pages cannot be injected; other tabs can still play.
          return [{ result: { ok: true, mode: 'choose' } }];
        });
        const result = results[0]?.result;
        if (result?.mode === 'choose') {
          return await openPicker(tab.id);
        }
        if (!result?.ok) throw new Error(result?.message || 'Не удалось открыть PiP на этой странице.');
        await chrome.action.setBadgeText({ tabId: tab.id, text: '' });
        const title = result.mode === 'closed'
          ? 'Открыть Picture-in-Picture (Alt+Shift+P)'
          : result.mode === 'native'
            ? 'Нативный PiP: захват недоступен. Нажми, чтобы закрыть.'
            : 'Закрыть Picture-in-Picture (Alt+Shift+P)';
        await chrome.action.setTitle({ tabId: tab.id, title });
        return result;
      } catch (error) {
        const message = String(error?.message || error);
        await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: '#c0392b' });
        await chrome.action.setBadgeText({ tabId: tab.id, text: '!' });
        await chrome.action.setTitle({ tabId: tab.id, title: message });
        return { ok: false, message };
      } finally { windows.finish(tab.id); }
    }
    return Object.freeze({ openTab, openPicker });
  };
  globalThis.IndependentPiPPlayback = Object.freeze({ create });
})();
