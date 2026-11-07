// Pointer gestures and the latest-position queue for one owned PiP window.
(() => {
  'use strict';
  const attach = ({ document: doc, preview, pipWindow, signal, nonce, sendMessage, createGesture, onError }) => {
    const abort = new AbortController();
    const listen = (target, type, handler) => target.addEventListener(type, handler, { signal: abort.signal });
    let drag;
    let dragFrame;
    let suppressClick = false;
    let dragQueue = Promise.resolve();
    let pendingMove;
    const dragCommand = (type, data = {}) => {
      // Keep at most one unsent position; never replay old pointer samples.
      // Start/end remain ordering barriers between independent gestures.
      if (type === 'drag-move' && pendingMove?.data.gesture === data.gesture) {
        pendingMove.data = data;
        return;
      }
      const command = { type, data };
      pendingMove = type === 'drag-move' ? command : undefined;
      dragQueue = dragQueue.catch(() => {}).then(async () => {
        if (pendingMove === command) pendingMove = undefined;
        if (abort.signal.aborted) return;
        const response = await sendMessage({ type: `independent-pip:${command.type}`, nonce, ...command.data });
        if (!response?.ok) throw new Error(response?.message || 'Окно PiP недоступно');
      }).catch(error => {
        if (!abort.signal.aborted) onError(error);
      });
    };
    const flushDrag = () => {
      pipWindow.cancelAnimationFrame(dragFrame);
      dragFrame = undefined;
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
      drag = { pointerId: event.pointerId, x: event.screenX, y: event.screenY, gesture: createGesture(), sequence: 0, moved: false };
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
      if (dragFrame === undefined) dragFrame = pipWindow.requestAnimationFrame(flushDrag);
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) listen(preview, event, finishDrag);
    listen(pipWindow, 'blur', finishDrag);
    const shouldSuppressClick = (event) => {
      if (suppressClick && event.detail !== 0) { suppressClick = false; return true; }
      return false;
    };
    const cleanup = () => {
      abort.abort();
      pipWindow.cancelAnimationFrame(dragFrame);
      dragFrame = undefined;
      pendingMove = undefined;
      const pointerId = drag?.pointerId;
      drag = undefined;
      suppressClick = false;
      preview.style.cursor = '';
      if (pointerId !== undefined && preview.hasPointerCapture(pointerId)) preview.releasePointerCapture(pointerId);
    };
    if (signal.aborted) cleanup();
    else signal.addEventListener('abort', cleanup, { once: true, signal: abort.signal });
    return { cleanup, shouldSuppressClick };
  };
  globalThis.IndependentPiPDrag = Object.freeze({ attach });
})();
