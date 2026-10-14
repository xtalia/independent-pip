# Extension architecture

An enhanced Picture-in-Picture extension for Chrome with compact controls and local preferences.

## Video and controls
`action click / Alt+Shift+P → MV3 service worker → isolated-world script in active tab → select playable HTML5 video → capture video stream → Document PiP window → controls mutate original video`.

The source node is never detached, its URL is never copied into another decoder, and its original audio remains authoritative. The mirror is muted and contains only captured video tracks. Closing PiP stops capture tracks, removes listeners/timers/observers and leaves source playback intact.

## Permissions and scope
- `activeTab` + `scripting` + `storage`; no persistent all-sites permissions, cookies, tabCapture, nativeMessaging or remote service. Preferences live in local storage; validated PiP window bindings live in session storage.
- Activation by extension action or `_execute_action` hotkey. No automatic opening on tab switch; opening uses Chrome transient user activation.
- Search active document, open shadow roots and same-origin iframes. Cross-origin iframe access is excluded; user must open that frame/video page directly. No permission-policy override.
- Document PiP requires secure context (HTTPS or loopback) and desktop Chrome with the API. Otherwise use native video PiP if available.

## Controls
Play/pause, ±10 seconds, seek slider, mute/volume, playback rate, VTT active-cue text, return/close; accessible labels and keyboard shortcuts. Caption text is inserted as text, not HTML. Arbitrary site/YouTube custom DOM captions are not supported automatically.

## Failure behavior
No video/metadata → visible action badge/title explaining the problem.
Capture DRM/cross-origin/unavailable or Document PiP unavailable → native PiP fallback; custom controls are not promised in fallback.
An API/user activation/policy denial must be reported rather than bypassed.

## Validation boundaries
Real installed Chrome 155.0.8059.40, isolated scratch profile, extension installed through CDP `Extensions.loadUnpacked` with `--enable-unsafe-extension-debugging`. No Chrome package installation or main-profile modifications.
Browser-integrated tests exercise real Document PiP and real decoded MP4 frames, not a mocked `requestWindow`. Headless validation confirms browser API behavior and actual PiP target, not visible Windows placement/topmost UX; that remains a manual acceptance item unless a headed check is separately run.

References:
- https://developer.chrome.com/docs/web-platform/document-picture-in-picture
- Locally observed CDP `Extensions` schema at http://127.0.0.1:9233/json/protocol
