'use strict';
(() => {
const origins = ['http://*/*', 'https://*/*'];
const sourceTabId = Number(new URLSearchParams(location.search).get('source'));
const status = document.querySelector('#status');
const refreshButton = document.querySelector('#refresh');
const videos = document.querySelector('#videos');
let generation = 0;
function showVideo(video) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `video${video.playing ? ' playing' : ''}`;
  button.dataset.videoId = video.id;
  button.dataset.tabId = String(video.tabId);
  const title = document.createElement('strong');
  title.textContent = `${video.tabTitle} · ${video.title}`;
  const detail = document.createElement('span');
  detail.textContent = `${video.playing ? '▶ Играет' : 'Ⅱ На паузе'} · ${video.current ? 'Текущая вкладка · ' : ''}${video.site} · ${video.width}×${video.height}`;
  button.append(title, detail);
  button.addEventListener('click', async () => {
    const buttons = [...videos.querySelectorAll('button')];
    buttons.forEach(item => { item.disabled = true; });
    status.textContent = 'Открываем PiP…';
    try {
      // Issue sendMessage before any await to preserve the selection gesture.
      const result = await IndependentPiPPickerClient.select(video.tabId, video.id);
      if (!result?.ok) throw new Error(result?.message || 'Не удалось открыть видео. Обнови список.');
      window.close();
    } catch (error) {
      status.textContent = error.message;
      buttons.forEach(item => { item.disabled = false; });
    }
  });
  return button;
}
async function refresh() {
  const request = ++generation;
  refreshButton.disabled = true;
  document.body.dataset.ready = 'false';
  status.textContent = 'Ищем доступные видео…';
  try {
    const result = await IndependentPiPPickerClient.requestList(sourceTabId);
    if (request !== generation) return;
    if (!result?.ok) throw new Error(result?.message || 'Не удалось получить список видео.');
    document.querySelector('#access').hidden = result.granted;
    videos.replaceChildren(...result.videos.map(showVideo));
    document.querySelector('#count').textContent = `Видео: ${result.videos.length}`;
    status.textContent = result.videos.length ? 'Играющие видео — в начале списка. Выбор не запускает видео на паузе.' : 'Доступных HTML5-видео не найдено. Запусти видео на другой вкладке и обнови список. Canvas и запрещённый сайтом PiP не поддерживаются.';
    if (result.incomplete) status.textContent += ' Список частичный: некоторые вкладки не ответили или недоступны. Можно повторить поиск.';
  } catch (error) { if (request === generation) status.textContent = error.message; }
  finally {
    if (request === generation) { refreshButton.disabled = false; document.body.dataset.ready = 'true'; }
  }
}
document.querySelector('#grant-access').addEventListener('click', async () => {
  try {
    const granted = await chrome.permissions.request({ origins });
    if (granted) await refresh();
    else status.textContent = 'Доступ не предоставлен. Видео текущей вкладки остаются доступны; можно повторить запрос.';
  } catch (error) { status.textContent = error.message; }
});
refreshButton.addEventListener('click', refresh);
chrome.permissions.onRemoved.addListener(() => refresh());
refresh();
})();
