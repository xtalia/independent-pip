// One synchronous MV3 message router; only recognized requests keep a channel open.
(() => {
  'use strict';
  const register = ({ chrome, windows, discovery, playback }) => {
    const { validId, pickerSender, failure } = IndependentPiPProtocol;
    chrome.runtime.onMessage.addListener((message, sender, respond) => {
      if (sender.id !== chrome.runtime.id) return false;
      let work;
      try {
        if (message?.type === 'independent-pip:options') work = chrome.runtime.openOptionsPage().then(() => ({ ok: true }));
        else if (['bind', 'release', 'drag-start', 'drag-move', 'drag-end'].some(type => message?.type === `independent-pip:${type}`)) work = windows.dispatch(message, sender);
        else if (!pickerSender(chrome.runtime, sender)) return false;
        else if (message?.type === 'independent-pip:list' && Number.isInteger(message.sourceTabId)) work = discovery.listVideos(message.sourceTabId);
        else if (message?.type === 'independent-pip:select' && Number.isInteger(message.tabId) && validId(message.videoId)) {
          // Dispatch now, not in a deferred .then(): this carries the click gesture.
          work = playback.openTab({ id: message.tabId }, message.videoId);
        } else return false;
      } catch (error) { respond(failure(error)); return false; }
      Promise.resolve(work).then(respond, error => respond(failure(error)));
      return true;
    });
  };
  globalThis.IndependentPiPMessages = Object.freeze({ register });
})();
