// DOM and styling for the PiP document; media ownership stays with the caller.
(() => {
  'use strict';
  const create = ({ document: doc, title: titleText }) => {
    doc.title = 'Independent PiP';
    const style = doc.createElement('style');
    style.textContent = `
      *{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;background:#000;color:#fff;font:13px system-ui;color-scheme:dark}
      body{position:relative;overflow:hidden}[hidden]{display:none!important}
      #pip-viewport{position:absolute;inset:0;background:#000}
      video{display:block;width:100%;height:100%;object-fit:contain;cursor:pointer}
      #pip-header{position:absolute;z-index:2;inset:0 0 auto;display:flex;align-items:center;gap:8px;height:44px;padding:0 10px;background:linear-gradient(#000e,#0009,transparent)}
      #pip-header,#pip-controls{transition:opacity .15s}.pip-ui-hidden #pip-header,.pip-ui-hidden #pip-controls{opacity:0;pointer-events:none}.pip-ui-hidden #pip-subtitles{bottom:12px}
      #pip-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:15px;font-weight:600}
      #pip-subtitles{position:absolute;bottom:72px;left:5%;right:5%;padding:6px 10px;text-align:center;white-space:pre-line;font-size:16px;line-height:1.35;background:#000b;border-radius:5px;pointer-events:none}
      #pip-controls{position:absolute;z-index:2;inset:auto 0 0;padding:10px 12px 7px;display:grid;gap:5px;background:linear-gradient(transparent,#000c 30%,#000f)}
      .pip-row{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}
      .pip-group{display:flex;align-items:center;gap:4px;min-width:0}.pip-right{justify-content:flex-end}
      button{display:inline-flex;align-items:center;justify-content:center;font:18px/1 'Segoe UI Symbol','Segoe UI Emoji',system-ui,sans-serif;color:inherit;background:transparent;border:0;border-radius:4px;min-width:30px;height:30px;padding:0;cursor:pointer;flex:none}
      button:hover{background:#ffffff24}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #fff;outline-offset:2px}
      #pip-rate{appearance:none;font:12px/30px system-ui;text-align:center;padding:0;color:#fff;background:transparent;border:0;border-radius:4px;width:64px;height:30px;cursor:pointer}#pip-rate option{background:#171717;color:#fff}
      input[type=range]{appearance:none;min-width:0;width:100%;height:14px;background:transparent;cursor:pointer;margin:0;accent-color:#fff}
      input[type=range]::-webkit-slider-runnable-track{height:3px;border-radius:3px;background:#777}
      #pip-seek::-webkit-slider-runnable-track{background:linear-gradient(to right,#fff var(--progress,0%),#777 var(--progress,0%))}
      #pip-seek-tooltip{position:fixed;z-index:5;padding:4px 7px;border:1px solid #666;border-radius:4px;background:#161616f5;font:11px ui-monospace,monospace;white-space:nowrap;pointer-events:none}
      input[type=range]::-webkit-slider-thumb{appearance:none;width:11px;height:11px;border-radius:50%;background:#fff;margin-top:-4px}
      #pip-time{display:flex;align-items:center;justify-content:center;height:30px;font:11px/1 ui-monospace,monospace;white-space:nowrap;text-align:center;min-width:76px}
      #pip-status{color:#ffd1c5;margin:0;font-size:12px;overflow-wrap:anywhere}#pip-status:empty{display:none}
      #pip-menu{position:absolute;z-index:3;right:10px;bottom:66px;width:min(270px,calc(100% - 20px));max-height:calc(100% - 76px);overflow:auto;padding:14px;display:grid;gap:12px;background:#161616f5;border:1px solid #555;border-radius:8px;box-shadow:0 8px 28px #000a}
      #pip-rate-form{display:grid;grid-template-columns:1fr 78px 28px;align-items:center;gap:8px;margin:0}#pip-rate-custom{width:100%;min-width:0;font:13px system-ui;color:#fff;background:#252525;border:1px solid #666;border-radius:4px;padding:6px}
      #pip-volume-control{display:flex;align-items:center;flex:none}
      #pip-volume-popup{position:fixed;z-index:4;display:flex;align-items:center;padding:8px;background:#161616f5;border:1px solid #666;border-radius:6px;box-shadow:0 4px 16px #0008}
      #pip-volume-popup[data-orientation=horizontal]{width:116px;height:32px}
      #pip-volume-popup[data-orientation=vertical]{width:36px}
      #pip-volume-popup[data-orientation=vertical] #pip-volume{writing-mode:vertical-lr;direction:rtl;width:16px;height:100%}
      #pip-volume-popup[data-orientation=horizontal] #pip-volume{width:100%;height:14px}
      @media(max-width:390px){#pip-header{height:38px}#pip-title{font-size:12px}#pip-controls{padding:8px 8px 5px}.pip-row{gap:4px}.pip-group{gap:0}button{min-width:24px;height:28px;font-size:16px}#pip-rate{width:50px;height:28px;font-size:11px;line-height:28px}#pip-time{height:28px;font-size:10px;min-width:72px}}
    `;
    doc.head.append(style);
    const preview = doc.createElement('video');
    preview.id = 'pip-video';
    preview.muted = true;
    preview.playsInline = true;
    const make = (tag, id, text) => {
      const element = doc.createElement(tag);
      if (id) element.id = id;
      if (text) element.textContent = text;
      return element;
    };
    const header = make('header', 'pip-header');
    const title = make('span', 'pip-title', titleText || 'Picture-in-Picture');
    title.title = title.textContent;
    header.append(title);
    const returnButton = make('button', 'pip-return', '↩');
    returnButton.title = 'Вернуться во вкладку';
    returnButton.setAttribute('aria-label', returnButton.title);
    const closeButton = make('button', 'pip-close', '✕');
    closeButton.title = 'Закрыть окно';
    closeButton.setAttribute('aria-label', 'Закрыть окно');
    header.append(returnButton, closeButton);
    const viewport = make('div', 'pip-viewport');
    const subtitles = make('div', 'pip-subtitles');
    viewport.append(preview, subtitles);
    const controls = make('section', 'pip-controls');
    const timeline = make('div', 'pip-timeline');
    const seek = make('input', 'pip-seek');
    Object.assign(seek, { type: 'range', min: '0', step: '0.05' });
    seek.setAttribute('aria-label', 'Позиция видео');
    const seekTooltip = make('span', 'pip-seek-tooltip');
    seekTooltip.hidden = true;
    seekTooltip.setAttribute('aria-hidden', 'true');
    const timeLabel = make('span', 'pip-time');
    timeline.append(seek, seekTooltip);
    const row = make('div');
    row.className = 'pip-row';
    const back = make('button', 'pip-back', '⏪');
    back.title = 'Назад на 10 секунд';
    back.setAttribute('aria-label', 'Назад на 10 секунд');
    const play = make('button', 'pip-play', '⏸');
    const forward = make('button', 'pip-forward', '⏩');
    forward.title = 'Вперёд на 10 секунд';
    forward.setAttribute('aria-label', 'Вперёд на 10 секунд');
    const mute = make('button', 'pip-mute', '🔊');
    const volume = make('input', 'pip-volume');
    Object.assign(volume, { type: 'range', min: '0', max: '1', step: '0.01' });
    volume.setAttribute('aria-label', 'Громкость');
    const volumeControl = make('div', 'pip-volume-control');
    const volumePopup = make('div', 'pip-volume-popup');
    volumePopup.hidden = true;
    volumePopup.append(volume);
    volumeControl.append(mute, volumePopup);
    mute.setAttribute('aria-controls', volumePopup.id);
    mute.setAttribute('aria-expanded', 'false');
    const rate = make('select', 'pip-rate');
    rate.setAttribute('aria-label', 'Скорость воспроизведения');
    const selectRate = (currentRate) => {
      if (![...rate.options].some(option => option.value === String(currentRate))) {
        const current = make('option', '', `${currentRate}×`);
        current.value = String(currentRate);
        rate.append(current);
      }
      rate.value = String(currentRate);
    };
    const populateRates = (rates, currentRate) => {
      const values = [...new Set([...rates, currentRate])].sort((a, b) => a - b);
      rate.replaceChildren(...values.map(value => {
        const option = make('option', '', `${value === 1.1 ? '1.10' : value}×`);
        option.value = String(value);
        return option;
      }));
      rate.value = String(currentRate);
    };
    const status = make('p', 'pip-status');
    status.setAttribute('role', 'status');
    const rateForm = make('form', 'pip-rate-form');
    rateForm.className = 'pip-row';
    const customRate = make('input', 'pip-rate-custom');
    Object.assign(customRate, { type: 'text', inputMode: 'decimal', placeholder: '1.234', size: 6 });
    customRate.setAttribute('aria-label', 'Точная скорость от 0.25 до 4');
    customRate.title = 'Точная скорость 0.25–4×; Enter — применить';
    const applyRateButton = make('button', 'pip-rate-apply', '✓');
    applyRateButton.type = 'submit';
    applyRateButton.title = 'Применить точную скорость';
    applyRateButton.setAttribute('aria-label', applyRateButton.title);
    rateForm.append(make('label', '', 'Скорость ×'), customRate, applyRateButton);
    const menuToggle = make('button', 'pip-menu-toggle', '⋮');
    menuToggle.title = 'Меню: точная скорость, громкость и настройки';
    menuToggle.setAttribute('aria-label', menuToggle.title);
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-controls', 'pip-menu');
    const menu = make('section', 'pip-menu');
    menu.hidden = true;
    menu.setAttribute('aria-label', 'Дополнительные настройки видео');

    const optionsButton = make('button', 'pip-options', '⚙ Настройки');
    optionsButton.title = 'Открыть настройки расширения';
    optionsButton.setAttribute('aria-label', optionsButton.title);
    menu.append(rateForm, optionsButton);
    const left = make('div');
    left.className = 'pip-group';
    left.append(play, back, forward, volumeControl);
    const right = make('div');
    right.className = 'pip-group pip-right';
    right.append(rate, menuToggle);
    row.append(left, timeLabel, right);
    controls.append(timeline, row, status);
    doc.body.append(viewport, header, controls, menu);
    preview.tabIndex = 0;
    preview.setAttribute('aria-label', 'Нажми для паузы или продолжения');
    return { preview, returnButton, closeButton, subtitles, seek, seekTooltip, timeLabel,
      back, play, forward, mute, volume, volumeControl, volumePopup, rate, status,
      rateForm, customRate, applyRateButton, menuToggle, menu, optionsButton, populateRates, selectRate };
  };
  globalThis.IndependentPiPView = Object.freeze({ create });
})();
