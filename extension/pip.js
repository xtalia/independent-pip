// Enhanced Picture-in-Picture controls for the source video.
(async () => {
  'use strict';
  const key = '__independentPiPState';
  const settings = globalThis.IndependentPiPSettings;
  let preferences = settings.normalize(settings.defaults);
  const previous = globalThis[key];
  if (previous?.window && !previous.window.closed) {
    previous.window.close();
    return { ok: true, mode: 'closed' };
  }
  let capture;
  let pipWindow;
  try {
    const found = new Set();
    const visited = new Set();
    const collect = (root) => {
      if (!root || visited.has(root)) return;
      visited.add(root);
      for (const element of root.querySelectorAll('*')) {
        if (element.localName === 'video') found.add(element);
        if (element.shadowRoot) collect(element.shadowRoot);
        if (element.localName === 'iframe') {
          try { collect(element.contentDocument); } catch { /* Cross-origin frames are intentionally inaccessible. */ }
        }
      }
    };
    collect(document);
    const videos = [...found].filter(v => v.readyState >= 2 && v.videoWidth > 0);
    const source = videos.sort((a, b) => Number(a.paused) - Number(b.paused) || b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
    if (!source) throw new Error('На странице нет готового HTML5-видео. Запусти видео и нажми ещё раз.');
    if (source.ownerDocument.pictureInPictureElement === source) {
      await source.ownerDocument.exitPictureInPicture();
      return { ok: true, mode: 'closed' };
    }
    if (source.disablePictureInPicture) throw new Error('Сайт запретил Picture-in-Picture для этого видео.');
    const nativePiP = async () => {
      capture?.getTracks().forEach(track => track.stop());
      if (!source.ownerDocument.pictureInPictureEnabled || typeof source.requestPictureInPicture !== 'function') throw new Error('Браузер или политика страницы запрещает Picture-in-Picture.');
      await source.requestPictureInPicture();
      return { ok: true, mode: 'native' };
    };
    if (!window.documentPictureInPicture || source.mediaKeys || typeof source.captureStream !== 'function') return await nativePiP();
    try { capture = source.captureStream(); }
    catch { return await nativePiP(); }
    if (!capture.getVideoTracks().length) return await nativePiP();
    try { pipWindow = await documentPictureInPicture.requestWindow({ width: 520, height: 360, disallowReturnToOpener: false }); }
    catch { return await nativePiP(); }
    const doc = pipWindow.document;
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
      button{font:18px 'Segoe UI Symbol','Segoe UI Emoji',system-ui,sans-serif;color:inherit;background:transparent;border:0;border-radius:4px;min-width:30px;height:30px;padding:0;cursor:pointer;flex:none}
      button:hover{background:#ffffff24}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #fff;outline-offset:2px}
      #pip-captions{font:11px system-ui;font-weight:600}#pip-captions[aria-pressed=true]{text-decoration:underline;text-underline-offset:5px}
      #pip-rate{font:12px system-ui;color:#fff;background:transparent;border:0;border-radius:4px;width:64px;height:30px;cursor:pointer}#pip-rate option{background:#171717;color:#fff}
      input[type=range]{appearance:none;min-width:0;width:100%;height:14px;background:transparent;cursor:pointer;margin:0;accent-color:#fff}
      input[type=range]::-webkit-slider-runnable-track{height:3px;border-radius:3px;background:#777}
      #pip-seek::-webkit-slider-runnable-track{background:linear-gradient(to right,#fff var(--progress,0%),#777 var(--progress,0%))}
      input[type=range]::-webkit-slider-thumb{appearance:none;width:11px;height:11px;border-radius:50%;background:#fff;margin-top:-4px}
      #pip-time{font:11px ui-monospace,monospace;white-space:nowrap;text-align:center;min-width:76px}
      #pip-status{color:#ffd1c5;margin:0;font-size:12px;overflow-wrap:anywhere}#pip-status:empty{display:none}
      #pip-menu{position:absolute;z-index:3;right:10px;bottom:66px;width:min(270px,calc(100% - 20px));max-height:calc(100% - 76px);overflow:auto;padding:14px;display:grid;gap:12px;background:#161616f5;border:1px solid #555;border-radius:8px;box-shadow:0 8px 28px #000a}
      #pip-rate-form{display:grid;grid-template-columns:1fr 78px 28px;align-items:center;gap:8px;margin:0}#pip-rate-custom{width:100%;min-width:0;font:13px system-ui;color:#fff;background:#252525;border:1px solid #666;border-radius:4px;padding:6px}
      #pip-volume-control{display:flex;align-items:center;flex:none}
      #pip-volume-popup{position:fixed;z-index:4;display:flex;align-items:center;padding:8px;background:#161616f5;border:1px solid #666;border-radius:6px;box-shadow:0 4px 16px #0008}
      #pip-volume-popup[data-orientation=horizontal]{width:116px;height:32px}
      #pip-volume-popup[data-orientation=vertical]{width:36px}
      #pip-volume-popup[data-orientation=vertical] #pip-volume{writing-mode:vertical-lr;direction:rtl;width:16px;height:100%}
      #pip-volume-popup[data-orientation=horizontal] #pip-volume{width:100%;height:14px}
      @media(max-width:390px){#pip-header{height:38px}#pip-title{font-size:12px}#pip-controls{padding:8px 8px 5px}.pip-row{gap:4px}.pip-group{gap:0}button{min-width:24px;height:28px;font-size:16px}#pip-rate{width:50px;font-size:11px}#pip-time{font-size:10px;min-width:72px}}
    `;
    doc.head.append(style);
    const preview = doc.createElement('video');
    preview.id = 'pip-video';
    preview.muted = true;
    preview.playsInline = true;
    preview.srcObject = new MediaStream(capture.getVideoTracks());
    const abort = new AbortController();
    const nonce = crypto.randomUUID();
    const listen = (target, type, handler) => target.addEventListener(type, handler, { signal: abort.signal });
    const make = (tag, id, text) => {
      const element = doc.createElement(tag);
      if (id) element.id = id;
      if (text) element.textContent = text;
      return element;
    };
    const header = make('header', 'pip-header');
    header.append(make('span', 'pip-title', document.title || 'Picture-in-Picture'));
    const returnButton = make('button', 'pip-return', '↩');
    returnButton.title = 'Вернуться во вкладку';
    returnButton.setAttribute('aria-label', returnButton.title);
    const closeButton = make('button', 'pip-close', '✕');
    closeButton.title = 'Закрыть окно';
    closeButton.setAttribute('aria-label', 'Закрыть окно');
    header.append(returnButton, closeButton);
    const viewport = make('div', 'pip-viewport');
    const subtitles = make('div', 'pip-subtitles');
    let captionsEnabled = true;
    viewport.append(preview, subtitles);
    const controls = make('section', 'pip-controls');
    const timeline = make('div', 'pip-timeline');
    const seek = make('input', 'pip-seek');
    Object.assign(seek, { type: 'range', min: '0', step: '0.05' });
    seek.setAttribute('aria-label', 'Позиция видео');
    const timeLabel = make('span', 'pip-time');
    timeline.append(seek);
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
    const captions = make('button', 'pip-captions', 'CC');
    captions.title = 'Показать или скрыть субтитры';
    captions.setAttribute('aria-label', 'Показать или скрыть субтитры');
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
    const populateRates = () => {
      const values = [...new Set([...settings.rates(preferences), source.playbackRate])].sort((a, b) => a - b);
      rate.replaceChildren(...values.map(value => {
        const option = make('option', '', `${value === 1.1 ? '1.10' : value}×`);
        option.value = String(value);
        return option;
      }));
      rate.value = String(source.playbackRate);
    };
    populateRates();
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
    right.append(rate, captions, menuToggle);
    row.append(left, timeLabel, right);
    controls.append(timeline, row, status);
    doc.body.append(viewport, header, controls, menu);
    const range = () => source.seekable.length
      ? { start: source.seekable.start(0), end: source.seekable.end(source.seekable.length - 1) }
      : { start: 0, end: Number.isFinite(source.duration) ? source.duration : 0 };
    const setTime = (value) => {
      const bounds = range();
      if (bounds.end > bounds.start && Number.isFinite(value)) source.currentTime = Math.max(bounds.start, Math.min(value, bounds.end - 0.01));
    };
    const formatTime = (value) => {
      const seconds = Math.floor(Number.isFinite(value) && value > 0 ? value : 0);
      return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    };
    const watchedTracks = new WeakSet();
    let lastVolume = source.volume > 0 ? source.volume : 0.5;
    let hideTimer;
    let volumeHideTimer;
    let pointerDown = false;
    const keepControlsVisible = () => {
      const focused = doc.activeElement;
      const keyboardControl = focused?.closest('#pip-header,#pip-controls,#pip-menu') && focused.matches(':focus-visible');
      return source.paused || !menu.hidden || !volumePopup.hidden || pointerDown || Boolean(status.textContent) || keyboardControl;
    };
    const revealControls = () => {
      if (abort.signal.aborted || pipWindow.closed) return;
      pipWindow.clearTimeout(hideTimer);
      doc.body.classList.remove('pip-ui-hidden');
      if (preferences.autoHide && !keepControlsVisible()) {
        hideTimer = pipWindow.setTimeout(() => {
          if (!abort.signal.aborted && !keepControlsVisible()) doc.body.classList.add('pip-ui-hidden');
        }, 3000);
      }
    };
    listen(doc, 'pointermove', revealControls);
    const positionVolume = () => {
      if (volumePopup.hidden) return;
      const button = mute.getBoundingClientRect();
      const limit = timeLabel.getBoundingClientRect().left;
      const horizontal = limit - button.right - 6 >= 116;
      volumePopup.dataset.orientation = horizontal ? 'horizontal' : 'vertical';
      volume.setAttribute('aria-orientation', horizontal ? 'horizontal' : 'vertical');
      const height = horizontal ? 32 : Math.max(44, Math.min(120, button.top - 8));
      volumePopup.style.height = `${height}px`;
      const width = horizontal ? 116 : 36;
      const x = horizontal ? button.right + 5 : button.left + (button.width - width) / 2;
      const y = horizontal ? button.top + (button.height - height) / 2 : button.top - height - 3;
      volumePopup.style.left = `${Math.max(2, Math.min(pipWindow.innerWidth - width - 2, x))}px`;
      volumePopup.style.top = `${Math.max(2, Math.min(pipWindow.innerHeight - height - 2, y))}px`;
    };
    const closeVolume = () => {
      pipWindow.clearTimeout(volumeHideTimer);
      volumePopup.hidden = true;
      mute.setAttribute('aria-expanded', 'false');
      revealControls();
    };
    const openVolume = () => {
      pipWindow.clearTimeout(volumeHideTimer);
      volumePopup.hidden = false;
      mute.setAttribute('aria-expanded', 'true');
      positionVolume();
      revealControls();
    };
    const deferVolumeClose = () => {
      pipWindow.clearTimeout(volumeHideTimer);
      volumeHideTimer = pipWindow.setTimeout(() => {
        const keyboardFocus = volumeControl.contains(doc.activeElement) && doc.activeElement.matches(':focus-visible');
        if (!pointerDown && !volumeControl.matches(':hover') && !keyboardFocus) closeVolume();
      }, 180);
    };
    listen(volumeControl, 'pointerenter', openVolume);
    listen(mute, 'pointermove', openVolume);
    listen(volumeControl, 'pointerleave', deferVolumeClose);
    listen(volumeControl, 'focusin', openVolume);
    listen(volumeControl, 'focusout', deferVolumeClose);
    listen(pipWindow, 'resize', positionVolume);
    listen(doc, 'pointerdown', () => { pointerDown = true; revealControls(); });
    for (const event of ['pointerup', 'pointercancel']) listen(doc, event, () => { pointerDown = false; deferVolumeClose(); revealControls(); });
    listen(doc, 'keydown', revealControls);
    listen(doc, 'focusin', revealControls);
    listen(doc, 'focusout', () => queueMicrotask(revealControls));
    listen(source, 'play', revealControls);
    const update = () => {
      if (source.volume > 0) lastVolume = source.volume;
      if (source.paused || status.textContent) revealControls();
      play.textContent = source.paused ? '▶' : '⏸';
      play.setAttribute('aria-label', source.paused ? 'Воспроизвести' : 'Пауза');
      play.title = play.getAttribute('aria-label');
      mute.textContent = source.muted || source.volume === 0 ? '🔇' : '🔊';
      mute.setAttribute('aria-label', source.muted || source.volume === 0 ? 'Включить звук' : 'Выключить звук');
      mute.title = mute.getAttribute('aria-label');
      mute.setAttribute('aria-pressed', String(source.muted));
      volume.value = String(source.muted ? 0 : source.volume);
      if (![...rate.options].some(option => option.value === String(source.playbackRate))) {
        const current = make('option', '', `${source.playbackRate}×`);
        current.value = String(source.playbackRate);
        rate.append(current);
      }
      rate.value = String(source.playbackRate);
      const bounds = range();
      seek.min = String(bounds.start);
      seek.max = String(bounds.end || 1);
      seek.disabled = bounds.end <= bounds.start;
      seek.value = String(source.currentTime);
      seek.style.setProperty('--progress', `${bounds.end > bounds.start ? Math.max(0, Math.min(100, (source.currentTime - bounds.start) / (bounds.end - bounds.start) * 100)) : 0}%`);
      timeLabel.textContent = `${formatTime(source.currentTime)} / ${Number.isFinite(source.duration) ? formatTime(source.duration) : 'LIVE'}`;
      const lines = [];
      for (const track of source.textTracks) {
        if (!watchedTracks.has(track)) {
          watchedTracks.add(track);
          listen(track, 'cuechange', update);
        }
        if (track.mode === 'showing') {
          for (const cue of track.activeCues || []) lines.push(typeof cue.getCueAsHTML === 'function' ? cue.getCueAsHTML().textContent : cue.text || '');
        }
      }
      subtitles.textContent = lines.join('\n');
      subtitles.hidden = !captionsEnabled || !subtitles.textContent;
      captions.setAttribute('aria-pressed', String(captionsEnabled));
    };
    const togglePlay = async () => {
      try { source.paused ? await source.play() : source.pause(); status.textContent = ''; }
      catch (error) { status.textContent = String(error.message || error); }
      update();
    };
    listen(play, 'click', togglePlay);
    let drag;
    let dragTimer;
    let suppressClick = false;
    let dragQueue = Promise.resolve();
    const dragCommand = (type, data = {}) => {
      dragQueue = dragQueue.catch(() => {}).then(async () => {
        if (abort.signal.aborted) return;
        const response = await chrome.runtime.sendMessage({ type: `independent-pip:${type}`, nonce, ...data });
        if (!response?.ok) throw new Error(response?.message || 'Окно PiP недоступно');
      }).catch(error => {
        if (!abort.signal.aborted) { status.textContent = `Перемещение: ${error.message || error}`; revealControls(); }
      });
    };
    const flushDrag = () => {
      pipWindow.clearTimeout(dragTimer);
      dragTimer = undefined;
      if (drag?.moved && drag.latest) {
        dragCommand('drag-move', { gesture: drag.gesture, sequence: ++drag.sequence, ...drag.latest });
        drag.latest = null;
      }
    };
    const finishDrag = () => {
      if (!drag) return;
      flushDrag();
      suppressClick = drag.moved;
      dragCommand('drag-end', { gesture: drag.gesture });
      const pointerId = drag.pointerId;
      drag = undefined;
      preview.style.cursor = '';
      if (preview.hasPointerCapture(pointerId)) preview.releasePointerCapture(pointerId);
    };
    listen(preview, 'pointerdown', event => {
      suppressClick = false;
      if (!event.isTrusted || event.button !== 0 || doc.body.dataset.dragAvailable !== 'true') return;
      drag = { pointerId: event.pointerId, x: event.screenX, y: event.screenY, gesture: crypto.randomUUID(), sequence: 0, moved: false };
      preview.setPointerCapture(event.pointerId);
      dragCommand('drag-start', { gesture: drag.gesture });
    });
    listen(preview, 'pointermove', event => {
      if (!drag || !event.isTrusted || event.pointerId !== drag.pointerId) return;
      const dx = Math.round(event.screenX - drag.x), dy = Math.round(event.screenY - drag.y);
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) drag.moved = true;
      if (!drag.moved) return;
      event.preventDefault();
      preview.style.cursor = 'grabbing';
      drag.latest = { dx, dy };
      if (dragTimer === undefined) dragTimer = pipWindow.setTimeout(flushDrag, 32);
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) listen(preview, event, finishDrag);
    listen(pipWindow, 'blur', () => { finishDrag(); pointerDown = false; });
    listen(preview, 'click', event => {
      if (suppressClick && event.detail !== 0) { suppressClick = false; event.preventDefault(); return; }
      togglePlay();
    });
    preview.tabIndex = 0;
    preview.setAttribute('aria-label', 'Нажми для паузы или продолжения');
    listen(back, 'click', () => setTime(source.currentTime - 10));
    listen(forward, 'click', () => setTime(source.currentTime + 10));
    listen(seek, 'input', () => setTime(Number(seek.value)));
    const toggleMute = () => {
      if (source.muted || source.volume === 0) {
        if (source.volume === 0) source.volume = lastVolume;
        source.muted = false;
      } else source.muted = true;
      update();
    };
    listen(mute, 'click', toggleMute);
    listen(volume, 'input', () => { source.volume = Number(volume.value); source.muted = source.volume === 0; update(); });
    const applyRate = (text) => {
      try { source.playbackRate = settings.parseRate(text); status.textContent = ''; }
      catch (error) { status.textContent = String(error.message || error); }
      update();
    };
    listen(rate, 'change', () => applyRate(rate.value));
    listen(rateForm, 'submit', (event) => { event.preventDefault(); applyRate(customRate.value); });
    const setMenuOpen = (open) => {
      menu.hidden = !open;
      menuToggle.setAttribute('aria-expanded', String(!menu.hidden));
      if (!menu.hidden) customRate.value = String(source.playbackRate);
      revealControls();
    };
    listen(menuToggle, 'click', () => setMenuOpen(menu.hidden));
    listen(doc, 'pointerdown', (event) => {
      if (!menu.hidden && !menu.contains(event.target) && !menuToggle.contains(event.target)) setMenuOpen(false);
    });
    listen(optionsButton, 'click', async () => {
      try {
        const response = await chrome.runtime.sendMessage({ type: 'independent-pip:options' });
        if (!response?.ok) throw new Error(response?.message || 'Настройки не открыты');
        status.textContent = '';
      } catch (error) { status.textContent = String(error.message || error); }
    });
    listen(captions, 'click', () => { captionsEnabled = !captionsEnabled; update(); });
    listen(source.textTracks, 'addtrack', update);
    listen(source.textTracks, 'removetrack', update);
    listen(source.textTracks, 'change', update);
    listen(returnButton, 'click', () => { window.focus(); source.scrollIntoView({ block: 'center' }); pipWindow.close(); });
    listen(closeButton, 'click', () => pipWindow.close());
    listen(doc, 'keydown', (event) => {
      if (event.key === 'Escape' && !volumePopup.hidden) {
        mute.focus();
        closeVolume();
        event.preventDefault();
        return;
      }
      if (event.key === 'Escape' && !menu.hidden) {
        closeVolume();
        setMenuOpen(false);
        menuToggle.focus();
        event.preventDefault();
        return;
      }
      if (event.target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(event.target.tagName)) return;
      if (event.key === ' ') togglePlay();
      else if (event.key === 'ArrowLeft') setTime(source.currentTime - (event.shiftKey ? 30 : 10));
      else if (event.key === 'ArrowRight') setTime(source.currentTime + (event.shiftKey ? 30 : 10));
      else if (event.key.toLowerCase() === 'm') toggleMute();
      else if (event.key === 'Escape') pipWindow.close();
      else return;
      event.preventDefault();
    });
    for (const event of ['play', 'pause', 'timeupdate', 'volumechange', 'ratechange', 'durationchange', 'seeked']) listen(source, event, update);
    update();
    const observer = new MutationObserver(() => { if (!source.isConnected) pipWindow.close(); });
    observer.observe(source.ownerDocument, { childList: true, subtree: true });
    if (source.getRootNode() !== source.ownerDocument) observer.observe(source.getRootNode(), { childList: true, subtree: true });
    listen(source, 'emptied', () => pipWindow.close());
    listen(window, 'pagehide', () => pipWindow.close());
    if (source.ownerDocument.defaultView !== window) listen(source.ownerDocument.defaultView, 'pagehide', () => pipWindow.close());
    const state = { window: pipWindow, capture };
    globalThis[key] = state;
    const applyPreferences = (raw) => {
      if (abort.signal.aborted) return;
      preferences = settings.normalize(raw);
      doc.body.dataset.autoHide = String(preferences.autoHide);
      back.hidden = forward.hidden = !preferences.showSeekButtons;
      positionVolume();
      populateRates();
      update();
      revealControls();
    };
    const storageChanged = (changes, area) => {
      if (area === 'local' && changes[settings.key]) applyPreferences(changes[settings.key].newValue);
    };
    chrome.storage.onChanged.addListener(storageChanged);
    // Read only after requestWindow: storage must not delay the activating gesture.
    settings.read().then(applyPreferences).catch(error => {
      if (!abort.signal.aborted) { status.textContent = `Настройки не прочитаны: ${error.message || error}`; revealControls(); }
    });
    pipWindow.addEventListener('pagehide', () => {
      observer.disconnect();
      pipWindow.clearTimeout(dragTimer);
      drag = undefined;
      chrome.runtime.sendMessage({ type: 'independent-pip:release', nonce }).catch(() => {});
      pipWindow.clearTimeout(hideTimer);
      pipWindow.clearTimeout(volumeHideTimer);
      chrome.storage.onChanged.removeListener(storageChanged);
      abort.abort();
      capture.getTracks().forEach(track => track.stop());
      preview.srcObject = null;
      if (globalThis[key] === state) delete globalThis[key];
    }, { once: true });
    await preview.play();
    try {
      const bound = await chrome.runtime.sendMessage({ type: 'independent-pip:bind', nonce });
      if (!abort.signal.aborted) {
        doc.body.dataset.dragAvailable = String(Boolean(bound?.ok));
        preview.title = bound?.ok ? 'Клик — пауза; удерживай и тяни — перемещение окна' : bound?.message || 'Перемещай окно за рамку Chrome';
      }
    } catch {
      if (!abort.signal.aborted) { doc.body.dataset.dragAvailable = 'false'; preview.title = 'Перемещай окно за рамку Chrome'; }
    }
    return { ok: true, mode: 'document' };
  } catch (error) {
    capture?.getTracks().forEach(track => track.stop());
    pipWindow?.close();
    return { ok: false, message: String(error?.message || error) };
  }
})()
