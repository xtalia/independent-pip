'use strict';
(() => {
  const key = 'pipSettings';
  const presets = Object.freeze([0.5, 1, 1.10, 1.15, 1.25, 1.5, 2]);
  const defaults = Object.freeze({ speedMode: 'presets', speedStep: 0.05, customRates: Object.freeze([]), autoHide: false, showSeekButtons: true });
  const parseRate = (text) => {
    const input = String(text).trim();
    const value = Number(input.replace(',', '.'));
    if (!/^(?:\d+(?:[.,]\d*)?|[.,]\d+)$/.test(input) || !Number.isFinite(value) || value < 0.25 || value > 4) {
      throw new Error('Скорость должна быть числом от 0.25 до 4, например 1.234');
    }
    return value;
  };
  const normalize = (raw) => {
    const data = raw && typeof raw === 'object' ? raw : {};
    const customRates = Array.isArray(data.customRates) ? [...new Set(data.customRates.filter(value => typeof value === 'number' && Number.isFinite(value) && value >= 0.25 && value <= 4))].slice(0, 64).sort((a, b) => a - b) : [];
    const legacyCustomized = [0.1, 0.25, 0.5].includes(data.speedStep) || customRates.length > 0;
    return {
      speedMode: ['presets', 'step'].includes(data.speedMode) ? data.speedMode : legacyCustomized ? 'step' : defaults.speedMode,
      speedStep: [0.05, 0.1, 0.25, 0.5].includes(data.speedStep) ? data.speedStep : defaults.speedStep,
      customRates,
      autoHide: data.autoHide === true,
      showSeekButtons: data.showSeekButtons !== false,
    };
  };
  const rates = (raw) => {
    const prefs = normalize(raw);
    if (prefs.speedMode === 'presets') return [...new Set([...presets, ...prefs.customRates])].sort((a, b) => a - b);
    const values = new Set([0.25, 1, 4, ...prefs.customRates]);
    const stride = Math.round(prefs.speedStep * 100);
    for (let tick = stride; tick <= 400; tick += stride) if (tick >= 25) values.add(tick / 100);
    return [...values].sort((a, b) => a - b);
  };
  const read = async () => normalize((await chrome.storage.local.get(key))[key]);
  globalThis.IndependentPiPSettings = Object.freeze({ key, defaults, parseRate, normalize, rates, read });
})();
