// Native toolbar context menu. Never add items to a site's own context menu.
(() => {
  'use strict';
  const install = chrome => {
    // Callbacks retain compatibility with the advertised Chrome 116 minimum.
    chrome.contextMenus.removeAll(() => {
      if (chrome.runtime.lastError) return;
      for (const [id, title] of [['pip-settings', 'Настройки'], ['pip-picker', 'Выбор видео']]) {
        chrome.contextMenus.create({ id, title, contexts: ['action'], type: 'normal', enabled: true }, () => { void chrome.runtime.lastError; });
      }
    });
  };
  const register = ({ chrome, playback }) => {
    const handle = (info, tab) => {
      if (info.menuItemId === 'pip-settings') return chrome.runtime.openOptionsPage();
      if (info.menuItemId !== 'pip-picker') return;
      if (Number.isInteger(tab?.id)) return playback.openPicker(tab.id);
      return chrome.tabs.query({ active: true, lastFocusedWindow: true }).then(tabs => playback.openPicker(tabs[0]?.id));
    };
    chrome.runtime.onInstalled.addListener(() => install(chrome));
    chrome.runtime.onStartup.addListener(() => install(chrome));
    chrome.contextMenus.onClicked.addListener((info, tab) => { Promise.resolve(handle(info, tab)).catch(() => {}); });
    return Object.freeze({ handle });
  };
  globalThis.IndependentPiPMenus = Object.freeze({ install, register });
})();
