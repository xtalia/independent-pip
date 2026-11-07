// Enhanced Picture-in-Picture controls for the source video.
globalThis.IndependentPiPOpen = async (selectedId) => {
  'use strict';
  const key = '__independentPiPState';
  const settings = globalThis.IndependentPiPSettings;
  let preferences = settings.normalize(settings.defaults);
  const previous = globalThis[key];
  if (!selectedId && previous?.window && !previous.window.closed) {
    previous.window.close();
    return { ok: true, mode: 'closed' };
  }
  let capture;
  let pipWindow;
  try {
    const media = globalThis.IndependentPiPMedia;
    const videos = media.collect();
    const source = selectedId
      ? videos.find(video => media.id(video) === selectedId)
      : videos.filter(media.allowed).sort((a, b) => Number(media.playing(b)) - Number(media.playing(a)) || b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
    if (selectedId && !source) throw new Error('Видео больше недоступно. Обнови список и выбери заново.');
    const nativeSource = videos.find(video => video.ownerDocument.pictureInPictureElement === video);
    if (!selectedId && nativeSource) {
      await nativeSource.ownerDocument.exitPictureInPicture();
      return { ok: true, mode: 'closed' };
    }
    if (!selectedId && (!source || !media.playing(source))) return { ok: true, mode: 'choose' };
    if (source.ownerDocument.pictureInPictureElement === source) {
      return { ok: true, mode: 'native' };
    }
    if (source.disablePictureInPicture) throw new Error('Сайт запретил Picture-in-Picture для этого видео.');
    if (selectedId && !media.allowed(source)) throw new Error('Браузер или политика страницы запрещает Picture-in-Picture.');
    if (selectedId && previous?.window && !previous.window.closed) previous.window.close();
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
    const { preview, returnButton, closeButton, subtitles, seek, seekTooltip, timeLabel,
      back, play, forward, mute, volume, volumeControl, volumePopup, rate, status,
      rateForm, customRate, menuToggle, menu, optionsButton, populateRates, selectRate
    } = globalThis.IndependentPiPView.create({ document: doc, title: document.title });
    preview.srcObject = new MediaStream(capture.getVideoTracks());
    const abort = new AbortController();
    const nonce = crypto.randomUUID();
    const listen = (target, type, handler) => target.addEventListener(type, handler, { signal: abort.signal });
    populateRates(settings.rates(preferences), source.playbackRate);
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
    const hideSeekTooltip = () => { seekTooltip.hidden = true; };
    const previewTime = (event) => {
      const bounds = range();
      if (bounds.end <= bounds.start) { hideSeekTooltip(); return; }
      const rect = seek.getBoundingClientRect();
      // The thumb centre travels between half-thumb insets, not edge to edge.
      const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left - 5.5) / Math.max(1, rect.width - 11)));
      seekTooltip.textContent = formatTime(bounds.start + fraction * (bounds.end - bounds.start));
      seekTooltip.hidden = false;
      const tip = seekTooltip.getBoundingClientRect();
      seekTooltip.style.left = `${Math.max(2, Math.min(pipWindow.innerWidth - tip.width - 2, event.clientX - tip.width / 2))}px`;
      seekTooltip.style.top = `${Math.max(2, Math.min(pipWindow.innerHeight - tip.height - 2, event.clientY + 16))}px`;
    };
    listen(seek, 'pointerenter', previewTime);
    listen(seek, 'pointermove', previewTime);
    for (const event of ['pointerleave', 'pointercancel']) listen(seek, event, hideSeekTooltip);
    listen(pipWindow, 'blur', hideSeekTooltip);
    listen(pipWindow, 'resize', hideSeekTooltip);
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
      selectRate(source.playbackRate);
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
      subtitles.hidden = !subtitles.textContent;
    };
    const togglePlay = async () => {
      try { source.paused ? await source.play() : source.pause(); status.textContent = ''; }
      catch (error) { status.textContent = String(error.message || error); }
      update();
    };
    listen(play, 'click', togglePlay);
    const dragController = globalThis.IndependentPiPDrag.attach({
      document: doc, preview, pipWindow, signal: abort.signal, nonce,
      sendMessage: message => chrome.runtime.sendMessage(message),
      createGesture: () => crypto.randomUUID(),
      onError: error => { status.textContent = `Перемещение: ${error.message || error}`; revealControls(); }
    });
    listen(pipWindow, 'blur', () => { pointerDown = false; });
    listen(preview, 'click', event => {
      if (dragController.shouldSuppressClick(event)) { event.preventDefault(); return; }
      togglePlay();
    });
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
      populateRates(settings.rates(preferences), source.playbackRate);
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
      dragController.cleanup();
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
};
