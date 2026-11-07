"""Menu callbacks use real Chrome APIs; native desktop menu painting is separate."""
import unittest
import test_extension as base
from test_extension import evaluate, wait_for, fetch, rpc, PORT, URL


class ContextMenuTests(base.ExtensionTests):
    def test_action_menu_routes_to_settings_and_explicit_picker(self):
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState >= 2')
        evaluate(self.page, 'window.savedPip = documentPictureInPicture.window; void 0')
        worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and self.extension_id in t['url'])
        registered = evaluate(worker, '''Promise.all(['pip-settings', 'pip-picker'].map(id => new Promise(resolve => {
          chrome.contextMenus.update(id, {enabled: true}, () => resolve(!chrome.runtime.lastError));
        })))''')
        self.assertEqual(registered, [True, True])
        result = evaluate(worker, f'''(async () => {{
          const tab = (await chrome.tabs.query({{}})).find(t => t.url === {URL!r});
          return IndependentPiPWorker.menus.handle({{menuItemId: 'pip-picker'}}, tab);
        }})()''')
        self.assertTrue(result['ok'], result)
        picker = self.picker_target()
        self.assertGreaterEqual(evaluate(picker, 'document.querySelectorAll(".video").length'), 1)
        self.assertTrue(evaluate(self.page, 'documentPictureInPicture.window === savedPip && !savedPip.closed && !originalNode.paused'))
        self.close_picker(picker)
        evaluate(worker, 'IndependentPiPWorker.menus.handle({menuItemId: "pip-settings"})')
        options = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['url'] == f'chrome-extension://{self.extension_id}/options.html')
        try:
            wait_for(options, 'document.querySelector("#prefs-form")?.dataset.ready === "true"')
            self.assertTrue(evaluate(self.page, 'documentPictureInPicture.window === savedPip && !savedPip.closed'))
        finally:
            rpc(self.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': options['id']}}])


for name in dir(base.ExtensionTests):
    if name.startswith('test_'):
        setattr(ContextMenuTests, name, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
