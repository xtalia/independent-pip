'use strict';
(async () => {
  const settings = globalThis.IndependentPiPSettings;
  const mode = document.querySelector('#speed-mode');
  const form = document.querySelector('#prefs-form');
  const step = document.querySelector('#speed-step');
  const custom = document.querySelector('#custom-rates');
  const autoHide = document.querySelector('#auto-hide');
  const showSeekButtons = document.querySelector('#show-seek-buttons');
  const status = document.querySelector('#prefs-status');
  const render = (prefs) => {
    mode.value = prefs.speedMode;
    step.value = String(prefs.speedStep);
    custom.value = prefs.customRates.join('; ');
    autoHide.checked = prefs.autoHide;
    showSeekButtons.checked = prefs.showSeekButtons;
  };
  const save = async (prefs, message) => {
    form.inert = true;
    try {
      await chrome.storage.local.set({ [settings.key]: prefs });
      render(prefs);
      status.textContent = message;
    } catch (error) { status.textContent = `Ошибка: ${error.message || error}`; }
    finally { form.inert = false; }
  };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const tokens = custom.value.trim() ? custom.value.trim().split(/[;\s]+/) : [];
      if (tokens.length > 64) throw new Error('Можно задать не более 64 значений');
      const customRates = [...new Set(tokens.map(settings.parseRate))].sort((a, b) => a - b);
      if (![0.05, 0.1, 0.25, 0.5].includes(Number(step.value))) throw new Error('Выбери допустимый шаг');
      await save(settings.normalize({ speedMode: mode.value, speedStep: Number(step.value), customRates, autoHide: autoHide.checked, showSeekButtons: showSeekButtons.checked }), 'Сохранено');
    } catch (error) { status.textContent = `Ошибка: ${error.message || error}`; }
  });
  document.querySelector('#prefs-reset').addEventListener('click', () => save(settings.normalize(settings.defaults), 'Настройки сброшены'));
  form.inert = true;
  try {
    render(await settings.read());
    form.dataset.ready = 'true';
    form.inert = false;
  } catch (error) { status.textContent = `Ошибка чтения настроек: ${error.message || error}`; }
})();
