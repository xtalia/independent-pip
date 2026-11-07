'use strict';
importScripts('protocol.js', 'background/windows.js', 'background/discovery.js', 'background/playback.js', 'background/messages.js', 'background/menus.js');
(() => {
  const scripts = IndependentPiPProtocol.scripts;
  const windows = IndependentPiPWindows.create({ chrome });
  const discovery = IndependentPiPDiscovery.create({ chrome, scripts });
  const playback = IndependentPiPPlayback.create({ chrome, windows, scripts });
  IndependentPiPMessages.register({ chrome, windows, discovery, playback });
  const menus = IndependentPiPMenus.register({ chrome, playback });
  chrome.action.onClicked.addListener(tab => { playback.openTab(tab).catch(() => {}); });
  chrome.tabs.onRemoved.addListener(tabId => { windows.remove(tabId).catch(() => {}); });
  globalThis.IndependentPiPWorker = Object.freeze({ windows, discovery, playback, menus });
})();