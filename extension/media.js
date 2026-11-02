// Shared discovery; identifiers stay in the extension's isolated world, not the DOM.
(() => {
  'use strict';
  if (globalThis.IndependentPiPMedia) return;
  const ids = new WeakMap();
  function collect() {
    const found = new Set(), visited = new Set();
    const visit = root => {
      if (!root || visited.has(root)) return;
      visited.add(root);
      for (const element of root.querySelectorAll('*')) {
        if (element.localName === 'video') found.add(element);
        if (element.shadowRoot) visit(element.shadowRoot);
        if (element.localName === 'iframe') {
          try { visit(element.contentDocument); } catch { /* Cross-origin frames stay inaccessible. */ }
        }
      }
    };
    visit(document);
    return [...found].filter(v => v.readyState >= 2 && v.videoWidth > 0 && !v.error);
  }
  const playing = video => !video.paused && !video.ended;
  function allowed(video) {
    const doc = video.ownerDocument;
    const policy = doc.featurePolicy;
    return !video.disablePictureInPicture && doc.pictureInPictureEnabled && (!policy || policy.allowsFeature('picture-in-picture'));
  }
  function id(video) {
    if (!ids.has(video)) ids.set(video, crypto.randomUUID());
    return ids.get(video);
  }
  function list() {
    return collect().filter(allowed).map((video, index) => ({
      id: id(video), playing: playing(video),
      title: video.getAttribute('aria-label') || video.title || `Видео ${index + 1}`,
      width: video.videoWidth, height: video.videoHeight,
    }));
  }
  globalThis.IndependentPiPMedia = Object.freeze({ collect, allowed, playing, id, list });
})();
