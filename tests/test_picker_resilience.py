"""Picker lifecycle regressions with real Chrome renderers and service workers."""
import json
import subprocess
import unittest
import test_extension as base
import test_v13
from test_extension import evaluate, wait_for, rpc, fetch, PORT, ROOT


class PickerResilienceTests(test_v13.V13GrantedTests):
    def test_frozen_tab_does_not_block_healthy_video_results(self):
        remote = self.other_video('frozen-renderer')
        result = rpc(remote['webSocketDebuggerUrl'], [{'method': 'Page.setWebLifecycleState', 'params': {'state': 'frozen'}}])[0]
        self.assertTrue(result['ok'], result)
        try:
            evaluate(self.page, 'originalNode.pause()')
            self.activate()
            picker = self.picker()
            self.assertGreaterEqual(evaluate(picker, 'document.querySelectorAll(".video").length'), 1)
            self.assertNotIn('message channel closed', evaluate(picker, 'document.querySelector("#status").textContent'))
        finally:
            rpc(remote['webSocketDebuggerUrl'], [{'method': 'Page.setWebLifecycleState', 'params': {'state': 'active'}}])

    def test_worker_restart_during_list_recovers_without_raw_channel_error(self):
        remote = self.other_video('frozen-worker-restart')
        rpc(remote['webSocketDebuggerUrl'], [{'method': 'Page.setWebLifecycleState', 'params': {'state': 'frozen'}}])
        try:
            evaluate(self.page, 'originalNode.pause()')
            self.activate()
            picker = self.picker()
            worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and self.extension_id in t['url'])
            payload = {'ws': self.page['webSocketDebuggerUrl'], 'collectEvents': True, 'commands': [{'method': 'ServiceWorker.enable'}, {'method': 'Runtime.evaluate', 'params': {'expression': 'new Promise(resolve => setTimeout(resolve, 100))', 'awaitPromise': True}}]}
            run = subprocess.run(['node', str(ROOT / 'tools/cdp.mjs')], input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
            versions = [v for event in json.loads(run.stdout)['events'] if event.get('method') == 'ServiceWorker.workerVersionUpdated' for v in event['params']['versions'] if v.get('scriptURL') == worker['url']]
            self.assertTrue(versions)
            self.click(picker, '#refresh')
            wait_for(picker, 'document.body.dataset.ready === "false"')
            stopped = rpc(self.page['webSocketDebuggerUrl'], [{'method': 'ServiceWorker.enable'}, {'method': 'ServiceWorker.stopWorker', 'params': {'versionId': versions[-1]['versionId']}}])[-1]
            self.assertTrue(stopped['ok'], stopped)
            wait_for(picker, 'document.body.dataset.ready === "true"')
            status = evaluate(picker, 'document.querySelector("#status").textContent')
            self.assertNotIn('message channel closed', status)
            self.assertIn('Играющие видео', status)
            self.assertGreaterEqual(evaluate(picker, 'document.querySelectorAll(".video").length'), 1)
        finally:
            rpc(remote['webSocketDebuggerUrl'], [{'method': 'Page.setWebLifecycleState', 'params': {'state': 'active'}}])


for name in dir(test_v13.V13GrantedTests):
    if name.startswith('test_'):
        setattr(PickerResilienceTests, name, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
