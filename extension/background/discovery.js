// Bounded cross-tab discovery. Unresponsive renderers cannot hold the result channel.
(() => {
  'use strict';
  const create = ({ chrome, scripts }) => {
    async function listVideos(sourceTabId) {
      const tabs = await chrome.tabs.query({});
      const rows = [];
      // activeTab alone permits the originating tab, not unrelated tabs.
      const granted = await chrome.permissions.contains({ origins: ['http://*/*', 'https://*/*'] });
      const eligible = tabs.filter(tab => !tab.discarded && (tab.id === sourceTabId || (granted && /^https?:/.test(tab.url || '')))).sort((a, b) => Number(b.id === sourceTabId) - Number(a.id === sourceTabId) || Number(Boolean(b.audible)) - Number(Boolean(a.audible)));
      const deadline = Date.now() + 6000;
      let cursor = 0;
      let skippedTabs = 0;
      await Promise.all(Array.from({ length: Math.min(6, eligible.length) }, async () => {
        while (cursor < eligible.length && Date.now() < deadline) {
          const tab = eligible[cursor++];
          let timer;
          try {
            const scan = async () => {
              await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'ISOLATED', files: [...scripts] });
              return chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'ISOLATED', func: () => globalThis.IndependentPiPMedia.list() });
            };
            const result = await Promise.race([scan(), new Promise((_, reject) => {
              timer = setTimeout(() => reject(new Error('Вкладка не ответила вовремя')), Math.min(2000, Math.max(1, deadline - Date.now())));
            })]);
            for (const video of result[0]?.result || []) rows.push({ ...video, tabId: tab.id, tabTitle: tab.title || 'Вкладка', site: tab.url ? new URL(tab.url).host : '', current: tab.id === sourceTabId });
          } catch { skippedTabs++; }
          finally { clearTimeout(timer); }
        }
      }));
      return { ok: true, granted, incomplete: skippedTabs > 0 || cursor < eligible.length, videos: rows.sort((a, b) => Number(b.playing) - Number(a.playing) || Number(b.current) - Number(a.current) || a.tabId - b.tabId) };
    }
    return Object.freeze({ listVideos });
  };
  globalThis.IndependentPiPDiscovery = Object.freeze({ create });
})();
