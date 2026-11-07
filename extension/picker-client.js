// Picker transport: only idempotent discovery may be retried after worker loss.
(() => {
  'use strict';
  const channelClosed = error => /message (?:channel|port) closed|receiving end does not exist/i.test(String(error?.message || error));
  const requestList = async (sourceTabId) => {
    for (let attempt = 0; attempt < 2; attempt++) {
      let timer;
      try {
        return await Promise.race([
          chrome.runtime.sendMessage({ type: 'independent-pip:list', sourceTabId }),
          new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Поиск не завершился вовремя. Нажми «Обновить список».')), 9000); }),
        ]);
      } catch (error) {
        if (attempt === 0 && channelClosed(error)) {
          await new Promise(resolve => setTimeout(resolve, 150));
          continue;
        }
        if (channelClosed(error)) throw new Error('Связь с расширением прервана. Нажми «Обновить список»; после обновления расширения закрой и открой окно выбора заново.', { cause: error });
        throw error;
      } finally { clearTimeout(timer); }
    }
  };
  // Call synchronously from the click handler. Never retry a playback side effect.
  const select = (tabId, videoId) => chrome.runtime.sendMessage({ type: 'independent-pip:select', tabId, videoId }).catch(error => {
    if (channelClosed(error)) throw new Error('Ответ на открытие видео потерян. Проверь окно PiP и обнови список; команда не отправлялась повторно.', { cause: error });
    throw error;
  });
  globalThis.IndependentPiPPickerClient = Object.freeze({ requestList, select });
})();
