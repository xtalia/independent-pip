"""UI regressions exercised in the owned Chrome Document PiP window."""
import base64
import json
import math
import unittest
import test_extension as base
from test_extension import evaluate, wait_for, rpc, ROOT


class UITests(base.ExtensionTests):
    def open_pip(self):
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState >= 2')
        return self.pip_target()

    def test_unavailable_caption_toggle_is_not_offered(self):
        pip = self.open_pip()
        self.assertTrue(evaluate(pip, '!document.querySelector("#pip-captions")'))

    def test_title_tooltip_contains_full_untruncated_safe_title(self):
        title = ('Длинное название видео <b>без HTML</b> — ' * 8).strip()

        evaluate(self.page, f'document.title = {json.dumps(title)}')
        pip = self.open_pip()
        result = evaluate(pip, '''(() => {
          const title = document.querySelector('#pip-title');
          return {text: title.textContent, tooltip: title.title,
            truncated: title.scrollWidth > title.clientWidth, children: title.children.length};
        })()''')
        self.assertEqual(result['text'], title)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['children'], 0)
        self.assertEqual(result['tooltip'], title)

    def test_timeline_hover_previews_pointer_time_without_seeking(self):
        pip = self.open_pip()
        evaluate(self.page, 'originalNode.pause(); originalNode.currentTime = 1')
        wait_for(pip, 'document.querySelector("#pip-seek").value === "1"')
        self.assertTrue(evaluate(pip, 'Boolean(document.querySelector("#pip-seek-tooltip"))'), 'Timeline time tooltip is missing')
        self.assertTrue(evaluate(pip, 'document.querySelector("#pip-seek-tooltip").hidden'))
        bounds = evaluate(pip, '''(() => {
          const e = document.querySelector('#pip-seek'), r = e.getBoundingClientRect();
          return {x: r.x, y: r.y + r.height / 2, width: r.width, min: +e.min, max: +e.max};
        })()''')

        for fraction in [0, .25, .75, 1]:
            x = bounds['x'] + 5.5 + (bounds['width'] - 11) * fraction
            result = rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseMoved', 'x': x, 'y': bounds['y']}}])[0]
            self.assertTrue(result['ok'], result)
            wait_for(pip, '!document.querySelector("#pip-seek-tooltip").hidden')
            seconds = math.floor(bounds['min'] + (bounds['max'] - bounds['min']) * fraction)
            expected = f'{seconds // 60}:{seconds % 60:02d}'
            self.assertEqual(evaluate(pip, 'document.querySelector("#pip-seek-tooltip").textContent'), expected)
            self.assertTrue(evaluate(pip, '''(() => {
              const e = document.querySelector('#pip-seek-tooltip'), r = e.getBoundingClientRect();
              return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight && getComputedStyle(e).pointerEvents === 'none';
            })()'''))
        self.assertAlmostEqual(evaluate(self.page, 'originalNode.currentTime'), 1, places=2)
        rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseMoved', 'x': 160, 'y': 100}}])
        wait_for(pip, 'document.querySelector("#pip-seek-tooltip").hidden')

    def test_time_and_speed_share_icon_row_height_at_both_sizes(self):
        pip = self.open_pip()
        window_id = rpc(self.browser, [{'method': 'Browser.getWindowForTarget', 'params': {'targetId': pip['id']}}])[0]['result']['windowId']
        for width in [520, 320]:
            rpc(self.browser, [{'method': 'Browser.setWindowBounds', 'params': {'windowId': window_id, 'bounds': {'width': width, 'height': 350}}}])
            wait_for(pip, f'innerWidth <= {width} && innerWidth >= {width - 32}')
            geometry = evaluate(pip, '''(() => {
              const ids = ['pip-play', 'pip-mute', 'pip-time', 'pip-rate', 'pip-menu-toggle'];
              return ids.map(id => {
                const e = document.getElementById(id), r = e.getBoundingClientRect();
                return {id, height: r.height, center: r.y + r.height / 2};
              });
            })()''')
            for item in geometry:
                self.assertAlmostEqual(item['height'], geometry[0]['height'], delta=.5, msg=str(geometry))
                self.assertAlmostEqual(item['center'], geometry[0]['center'], delta=.5, msg=str(geometry))
            point = evaluate(pip, '(() => {const r = document.querySelector("#pip-seek").getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseMoved', **point}}])
            wait_for(pip, '!document.querySelector("#pip-seek-tooltip").hidden')
            screenshot = rpc(pip['webSocketDebuggerUrl'], [{'method': 'Page.captureScreenshot', 'params': {'format': 'png', 'captureBeyondViewport': False}}])[0]
            self.assertTrue(screenshot['ok'], screenshot)
            folder = ROOT / 'reports/screenshots'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'pip-ui-{width}.png').write_bytes(base64.b64decode(screenshot['result']['data']))

    def test_speed_selector_remains_keyboard_operable(self):
        pip = self.open_pip()
        evaluate(pip, 'document.querySelector("#pip-rate").focus()')
        result = rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': 'ArrowDown', 'windowsVirtualKeyCode': 40}}])[0]
        self.assertTrue(result['ok'], result)
        wait_for(self.page, 'originalNode.playbackRate > 1')
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), float(evaluate(pip, 'document.querySelector("#pip-rate").value')))

    def test_unseekable_live_stream_does_not_offer_hover_time(self):
        evaluate(self.page, '''(() => {
          const canvas = document.createElement('canvas');
          canvas.width = 320; canvas.height = 180;
          canvas.getContext('2d').fillRect(0, 0, 320, 180);
          window.liveStream = canvas.captureStream(10);
          originalNode.srcObject = liveStream;
          return originalNode.play();
        })()''', True)
        wait_for(self.page, 'originalNode.readyState >= 2 && originalNode.duration === Infinity')
        pip = self.open_pip()
        try:
            self.assertTrue(evaluate(pip, 'document.querySelector("#pip-seek").disabled'))
            point = evaluate(pip, '(() => {const r = document.querySelector("#pip-seek").getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseMoved', **point}}])
            self.assertTrue(evaluate(pip, 'document.querySelector("#pip-seek-tooltip").hidden'))
            self.assertIn('LIVE', evaluate(pip, 'document.querySelector("#pip-time").textContent'))
        finally:
            evaluate(self.page, 'liveStream.getTracks().forEach(track => track.stop())')


# Reuse only the harness, not inherited regression cases.
for name in dir(base.ExtensionTests):
    if name.startswith('test_'):
        setattr(UITests, name, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
