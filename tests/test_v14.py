"""Drag responsiveness regressions with real PiP and controlled reply delays."""
import json
import subprocess
import time
import unittest
import test_extension as base
from test_extension import evaluate, wait_for, fetch, rpc, PORT


class V14Tests(base.ExtensionTests):
    def open_drag_probe(self, hold='drag-start'):
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.body.dataset.dragAvailable === "true"')
        self.pip = self.pip_target()
        self.window_id = rpc(self.browser, [{'method': 'Browser.getWindowForTarget', 'params': {'targetId': self.pip['id']}}])[0]['result']['windowId']
        self.origin = self.bounds()
        payload = {'ws': self.page['webSocketDebuggerUrl'], 'collectEvents': True, 'commands': [{'method': 'Runtime.enable'}]}
        run = subprocess.run(['node', str(base.ROOT / 'tools/cdp.mjs')], input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, check=True, timeout=30)
        contexts = [event['params']['context']['id'] for event in json.loads(run.stdout)['events'] if event.get('method') == 'Runtime.executionContextCreated']
        self.context = next(context for context in contexts if self.isolated('Boolean(globalThis.__independentPiPState)', context))
        self.isolated('''(() => {
          globalThis.__dragProbe = {messages: [], active: 0, maxActive: 0, held: false};
          const original = chrome.runtime.sendMessage.bind(chrome.runtime);
          chrome.runtime.sendMessage = async message => {
            if (!message.type?.startsWith('independent-pip:drag-')) return original(message);
            const probe = __dragProbe;
            probe.messages.push({...message});
            probe.maxActive = Math.max(probe.maxActive, ++probe.active);
            try {
              const response = await original(message);
              if (message.type === 'independent-pip:''' + hold + '''' && !probe.held) {
                probe.held = true;
                await new Promise(resolve => { probe.release = resolve; });
              }
              return response;
            } finally { probe.active--; }
          };
        })()''')

    def isolated(self, expression, context=None):
        response = rpc(self.page['webSocketDebuggerUrl'], [{'method': 'Runtime.evaluate', 'params': {'contextId': self.context if context is None else context, 'expression': expression, 'returnByValue': True, 'awaitPromise': True}}])[0]
        self.assertTrue(response['ok'], response)
        self.assertNotIn('exceptionDetails', response['result'])
        return response['result']['result'].get('value')

    def bounds(self):
        response = rpc(self.browser, [{'method': 'Browser.getWindowBounds', 'params': {'windowId': self.window_id}}])[0]
        self.assertTrue(response['ok'], response)
        return response['result']['bounds']

    def pointer(self, kind, dx=0, dy=0):
        current = self.bounds()
        params = {'type': kind, 'x': 160 + dx - (current['left'] - self.origin['left']), 'y': 100 + dy - (current['top'] - self.origin['top']), 'button': 'left', 'buttons': 0 if kind == 'mouseReleased' else 1}
        if kind != 'mouseMoved':
            params['clickCount'] = 1
        response = rpc(self.pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': params}])[0]
        self.assertTrue(response['ok'], response)

    def wait_probe(self, expression):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = self.isolated(expression)
            if value:
                return value
            time.sleep(.05)
        self.fail(f'Drag probe timed out: {expression}')

    def test_60_slow_start_keeps_only_latest_position_before_release(self):
        self.open_drag_probe()
        self.pointer('mousePressed')
        self.wait_probe('Boolean(__dragProbe.release)')
        for dx in range(10, 91, 10):
            self.pointer('mouseMoved', dx, 20)
            time.sleep(.04)
        self.pointer('mouseReleased', 90, 20)
        self.isolated('__dragProbe.release()')
        self.wait_probe('__dragProbe.messages.some(m => m.type.endsWith("drag-end")) && __dragProbe.active === 0')
        messages = self.isolated('__dragProbe.messages')
        moves = [message for message in messages if message['type'].endswith('drag-move')]
        self.assertEqual(len(moves), 1, f'Obsolete positions were queued: {moves}')
        self.assertEqual((moves[0]['dx'], moves[0]['dy']), (90, 20))
        after = self.bounds()
        self.assertEqual((after['left'], after['top']), (self.origin['left'] + 90, self.origin['top'] + 20))
        self.assertEqual(self.isolated('__dragProbe.maxActive'), 1)
        self.assertTrue(evaluate(self.page, '!originalNode.paused && originalNode.playbackRate === 1'))

    def test_61_moves_on_animation_frames_without_a_fixed_32ms_timer(self):
        self.open_drag_probe(hold='none')
        self.isolated('''(() => {
          const pip = __independentPiPState.window;
          const original = pip.setTimeout.bind(pip);
          __dragProbe.fixedTimers = 0;
          pip.setTimeout = (callback, delay, ...args) => {
            if (delay === 32) { __dragProbe.fixedTimers++; return -1; }
            return original(callback, delay, ...args);
          };
        })()''')
        self.pointer('mousePressed')
        self.pointer('mouseMoved', 30, 10)
        self.wait_probe('__dragProbe.messages.some(m => m.type.endsWith("drag-move")) && __dragProbe.active === 0')
        self.assertEqual(self.isolated('__dragProbe.fixedTimers'), 0)
        after = self.bounds()
        self.assertEqual((after['left'], after['top']), (self.origin['left'] + 30, self.origin['top'] + 10))
        self.pointer('mouseReleased', 30, 10)

    def test_62_slow_move_coalesces_positions_and_applies_final_release(self):
        self.open_drag_probe(hold='drag-move')
        self.pointer('mousePressed')
        self.pointer('mouseMoved', 10, 20)
        self.wait_probe('Boolean(__dragProbe.release)')
        for dx in range(20, 91, 10):
            self.pointer('mouseMoved', dx, 20)
            time.sleep(.04)
        self.pointer('mouseReleased', 90, 20)
        self.isolated('__dragProbe.release()')
        self.wait_probe('__dragProbe.messages.some(m => m.type.endsWith("drag-end")) && __dragProbe.active === 0')
        moves = self.isolated('__dragProbe.messages.filter(m => m.type.endsWith("drag-move"))')
        self.assertEqual([(m['dx'], m['dy']) for m in moves], [(10, 20), (90, 20)])
        self.assertLess(moves[0]['sequence'], moves[1]['sequence'])
        self.assertEqual(self.bounds()['left'], self.origin['left'] + 90)
        self.assertEqual(self.isolated('__dragProbe.maxActive'), 1)
        self.assertFalse(evaluate(self.page, 'originalNode.paused'))

    def test_63_new_gesture_waits_for_previous_final_position_and_end(self):
        self.open_drag_probe()
        self.pointer('mousePressed')
        self.wait_probe('Boolean(__dragProbe.release)')
        self.pointer('mouseMoved', 30)
        self.pointer('mouseReleased', 30)
        self.pointer('mousePressed')
        self.pointer('mouseMoved', 20)
        self.pointer('mouseReleased', 20)
        self.isolated('__dragProbe.release()')
        self.wait_probe('__dragProbe.messages.filter(m => m.type.endsWith("drag-end")).length === 2 && __dragProbe.active === 0')
        messages = self.isolated('__dragProbe.messages')
        self.assertEqual([m['type'].split(':')[1] for m in messages], ['drag-start', 'drag-move', 'drag-end'] * 2)
        self.assertEqual(len({m['gesture'] for m in messages[:3]}), 1)
        self.assertEqual(len({m['gesture'] for m in messages[3:]}), 1)
        self.assertNotEqual(messages[0]['gesture'], messages[3]['gesture'])
        self.assertEqual(self.bounds()['left'], self.origin['left'] + 50)
        self.assertFalse(evaluate(self.page, 'originalNode.paused'))

    def test_64_close_discards_unsent_positions_and_preserves_playback(self):
        self.open_drag_probe()
        self.pointer('mousePressed')
        self.wait_probe('Boolean(__dragProbe.release)')
        self.pointer('mouseMoved', 30, 20)
        time.sleep(.06)
        evaluate(self.page, 'window.closedTrack=documentPictureInPicture.window.document.querySelector("#pip-video").srcObject.getVideoTracks()[0];documentPictureInPicture.window.close()')
        wait_for(self.page, '!documentPictureInPicture.window')
        self.isolated('__dragProbe.release()')
        self.wait_probe('__dragProbe.active === 0')
        time.sleep(.1)
        self.assertEqual(self.isolated('__dragProbe.messages.map(m => m.type)'), ['independent-pip:drag-start'])
        self.assertTrue(evaluate(self.page, 'closedTrack.readyState === "ended" && !originalNode.paused && originalNode.parentNode === originalParent'))


# Reuse the browser harness without repeating inherited regression tests.
for name in dir(base.ExtensionTests):
    if name.startswith('test_'):
        setattr(V14Tests, name, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
