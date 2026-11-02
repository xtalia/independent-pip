"""Cross-tab picker regression: actual Chrome actions, media and pointer input."""
import json
import hashlib
import time
import unittest
import test_extension as base
from test_extension import evaluate, wait_for, fetch, rpc, PORT, URL


class V13Tests(base.ExtensionTests):
    @classmethod
    def setUpClass(cls):
        # Bootstrap prior consent in an isolated copied extension, then reload
        # the exact production manifest. Chrome remembers previously accepted
        # host access for granted-state tests without a native dialog. Actual
        # first-use native consent remains unverified. No API responses mocked.
        import shutil
        from browser_lab import RUNTIME
        cls.original_root = base.ROOT
        cls.stage = RUNTIME / 'cross-tab-consent-fixture'
        shutil.copytree(cls.original_root / 'extension', cls.stage / 'extension', dirs_exist_ok=True)
        path = cls.stage / 'extension/manifest.json'
        production = path.read_bytes()
        manifest = json.loads(production)
        manifest['host_permissions'] = manifest.pop('optional_host_permissions')
        path.write_text(json.dumps(manifest), encoding='utf-8')
        base.ROOT = cls.stage
        cls.addClassCleanup(setattr, base, 'ROOT', cls.original_root)
        try:
            super().setUpClass()
        finally:
            path.write_bytes(production)
        manager_id = rpc(cls.browser, [{'method':'Target.createTarget','params':{'url':'chrome://extensions/'}}])[0]['result']['targetId']
        manager = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==manager_id)
        try:
            evaluate(manager, 'chrome.developerPrivate.updateProfileConfiguration({inDeveloperMode:true})')
            evaluate(manager, f'chrome.developerPrivate.reload({json.dumps(cls.extension_id)})')
        finally:
            rpc(cls.browser, [{'method':'Target.closeTarget','params':{'targetId':manager_id}}])
        cls.production_hashes = {p.relative_to(cls.stage/'extension').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (cls.stage/'extension').rglob('*') if p.is_file()}
        assert all((cls.stage/'extension'/p.relative_to(cls.original_root/'extension')).read_bytes()==p.read_bytes() for p in (cls.original_root/'extension').rglob('*') if p.is_file())

    @classmethod
    def tearDownClass(cls):
        base.ROOT = cls.original_root

    def setUp(self):
        super().setUp()
        self.extra_targets = []
        self.assertEqual({p.relative_to(self.stage/'extension').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.stage/'extension').rglob('*') if p.is_file()}, self.production_hashes)
        # Start each test with optional access off. Prior consent remains known
        # to Chrome, exactly as after a user revokes and re-enables access.
        tid = rpc(self.browser, [{'method':'Target.createTarget','params':{'url':f'chrome-extension://{self.extension_id}/options.html'}}])[0]['result']['targetId']
        target = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==tid)
        wait_for(target, 'document.querySelector("#prefs-form")?.dataset.ready==="true"')
        evaluate(target, 'chrome.permissions.remove({origins:["http://*/*","https://*/*"]})')
        rpc(self.browser, [{'method':'Target.closeTarget','params':{'targetId':tid}}])

    def tearDown(self):
        super().tearDown()
        for tid in self.extra_targets:
            rpc(self.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': tid}}])
        for t in fetch(f'http://127.0.0.1:{PORT}/json/list'):
            if t['url'].startswith(f'chrome-extension://{self.extension_id}/picker.html'):
                rpc(self.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': t['id']}}])

    def picker(self):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            target = next((t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['url'].startswith(f'chrome-extension://{self.extension_id}/picker.html')), None)
            if target:
                wait_for(target, 'document.body.dataset.ready === "true"')
                return target
            time.sleep(.1)
        self.fail('No video picker opened after toolbar activation')

    def click(self, target, selector):
        point = evaluate(target, f'(() => {{const e=document.querySelector({json.dumps(selector)});e.scrollIntoView();const r=e.getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()')
        result = rpc(target['webSocketDebuggerUrl'], [
            {'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **point}},
            {'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, **point}},
        ])
        self.assertTrue(all(r['ok'] for r in result), result)

    def test_40_no_video_opens_picker_with_permission_explanation(self):
        evaluate(self.page, 'originalNode.remove()')
        self.activate()
        picker = self.picker()
        self.assertTrue(evaluate(picker, 'Boolean(document.querySelector("#grant-access"))'))
        self.assertIn('других вкладках', evaluate(picker, 'document.body.textContent'))
        self.assertFalse(evaluate(self.page, 'Boolean(documentPictureInPicture.window)'))


    def test_41_paused_local_videos_can_be_selected_without_autoplay(self):
        evaluate(self.page, 'originalNode.pause();window.second=originalNode.cloneNode();second.id="second";document.body.append(second)')
        wait_for(self.page, 'second.readyState>=2')
        self.activate()
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length === 2')
        self.click(picker, '.video:last-child')
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.assertTrue(evaluate(self.page, 'originalNode.paused && second.paused'))
        self.click_control('pip-play')
        wait_for(self.page, '!second.paused')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        self.assertEqual(evaluate(self.pip_target(), 'document.body.dataset.dragAvailable'), 'true')


    def test_45_repeated_toolbar_click_reuses_the_same_picker(self):
        evaluate(self.page, 'originalNode.remove()')
        self.activate()
        first = self.picker()
        self.activate()
        time.sleep(.4)
        pickers = [t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['url'].startswith(f'chrome-extension://{self.extension_id}/picker.html')]
        self.assertEqual([t['id'] for t in pickers], [first['id']])

    def other_video(self, suffix='remote'):
        url = f'http://localhost:8766/?{suffix}'
        tid = rpc(self.browser, [{'method':'Target.createTarget','params':{'url':url}}])[0]['result']['targetId']
        self.extra_targets.append(tid)
        target = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==tid)
        wait_for(target, 'document.querySelector("video")?.readyState>=2')
        evaluate(target, 'document.title="Remote <img src=x onerror=alert(1)>";document.querySelector("video").play()', True)
        return target

    def test_42_other_tab_playing_video_is_first_and_opens_from_real_click(self):
        remote = self.other_video()
        evaluate(self.page, 'originalNode.pause()')
        self.activate()
        picker = self.picker()
        self.assertTrue(evaluate(picker, 'document.querySelector("#access").hidden'))
        wait_for(picker, 'document.querySelectorAll(".video").length===2')
        self.assertTrue(evaluate(picker, 'document.querySelector(".video").classList.contains("playing")'))
        self.assertEqual(evaluate(picker, 'document.querySelectorAll("#videos img").length'), 0)
        self.assertIn('<img', evaluate(picker, 'document.querySelector(".video").textContent'))
        import base64
        screenshot = rpc(picker['webSocketDebuggerUrl'], [{'method':'Page.captureScreenshot','params':{'format':'png'}}])[0]
        self.assertTrue(screenshot['ok'], screenshot)
        folder = self.original_root/'reports/screenshots'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'picker-v1.3.png').write_bytes(base64.b64decode(screenshot['result']['data']))
        self.click(picker, '.video')
        wait_for(remote, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.assertTrue(evaluate(self.page, 'originalNode.paused && !documentPictureInPicture.window'))
        self.assertEqual(evaluate(self.pip_target(), 'document.body.dataset.dragAvailable'), 'true')
        self.click_control('pip-play')
        wait_for(remote, 'document.querySelector("video").paused')
        print('REAL_CROSS_TAB_SELECTION', json.dumps({'source': remote['url'], 'gesture': 'Input.dispatchMouseEvent', 'dragBound': True}))


# Reuse the harness without duplicating its regression suite.
for name in dir(base.ExtensionTests):
    if name.startswith('test_'):
        setattr(V13Tests, name, None)

class V13GrantedTests(V13Tests):
    test_42_other_tab_playing_video_is_first_and_opens_from_real_click = V13Tests.test_42_other_tab_playing_video_is_first_and_opens_from_real_click

    def test_43_restricted_current_tab_offers_remote_video(self):
        remote = self.other_video('restricted-source')
        evaluate(self.page, 'originalNode.remove()')
        tid = rpc(self.browser, [{'method':'Target.createTarget','params':{'url':'chrome://version/'}}])[0]['result']['targetId']
        self.extra_targets.append(tid)
        target = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==tid)
        rpc(target['webSocketDebuggerUrl'], [{'method':'Page.bringToFront'}])
        tabs = rpc(self.browser, [{'method':'Target.getTargets','params':{'filter':[{'exclude':False}]}}])[0]['result']['targetInfos']
        wrapper = next(t for t in tabs if t['type']=='tab' and t['url']=='chrome://version/')
        rpc(self.browser, [{'method':'Extensions.triggerAction','params':{'id':self.extension_id,'targetId':wrapper['targetId']}}])
        picker = self.picker()
        wait_for(picker, 'Boolean(document.querySelector(".video.playing"))')
        self.click(picker, '.video.playing')
        wait_for(remote, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')

    def test_44_stale_video_does_not_open_a_different_player(self):
        remote = self.other_video('stale-source')
        evaluate(self.page, 'originalNode.remove()')
        self.activate()
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length===1')
        evaluate(remote, 'document.querySelector("video").remove()')
        self.click(picker, '.video')
        wait_for(picker, 'document.querySelector("#status").textContent.includes("больше недоступно")')
        self.assertFalse(evaluate(remote, 'Boolean(documentPictureInPicture.window)'))
        self.click(picker, '#refresh')
        wait_for(picker, 'document.body.dataset.ready==="true" && document.querySelectorAll(".video").length===0')

    def setUp(self):
        base.ExtensionTests.setUp(self)
        self.extra_targets = []

    test_40_no_video_opens_picker_with_permission_explanation = None
    test_41_paused_local_videos_can_be_selected_without_autoplay = None
    def test_46_stale_selection_preserves_existing_pip(self):
        evaluate(self.page, 'window.second=originalNode.cloneNode();second.id="second";document.body.append(second)')
        wait_for(self.page, 'second.readyState>=2')
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        evaluate(self.page, 'window.oldPip=documentPictureInPicture.window;window.oldTrack=oldPip.document.querySelector("#pip-video").srcObject.getVideoTracks()[0]')
        remote = self.other_video('stale-existing-picker')
        evaluate(remote, 'document.querySelector("video").remove()')
        rpc(remote['webSocketDebuggerUrl'], [{'method':'Page.bringToFront'}])
        tabs = rpc(self.browser, [{'method':'Target.getTargets','params':{'filter':[{'exclude':False}]}}])[0]['result']['targetInfos']
        wrapper = next(t for t in tabs if t['type']=='tab' and t['url']==remote['url'])
        rpc(self.browser, [{'method':'Extensions.triggerAction','params':{'id':self.extension_id,'targetId':wrapper['targetId']}}])
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length===2')
        evaluate(self.page, 'second.remove()')
        self.click(picker, '.video:last-child')
        wait_for(picker, 'document.querySelector("#status").textContent.includes("больше недоступно")')
        self.assertTrue(evaluate(self.page, 'documentPictureInPicture.window===oldPip && !oldPip.closed && oldTrack.readyState==="live" && !originalNode.paused'))

    def test_48_selection_replaces_existing_pip_with_the_chosen_video(self):
        evaluate(self.page, 'window.second=originalNode.cloneNode();second.id="second";second.title="Second source";document.body.append(second)')
        wait_for(self.page, 'second.readyState>=2')
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        evaluate(self.page, 'window.oldPip=documentPictureInPicture.window;window.oldTrack=oldPip.document.querySelector("#pip-video").srcObject.getVideoTracks()[0]')
        remote = self.other_video('replacement-picker')
        evaluate(remote, 'document.querySelector("video").remove()')
        rpc(remote['webSocketDebuggerUrl'], [{'method':'Page.bringToFront'}])
        tabs = rpc(self.browser, [{'method':'Target.getTargets','params':{'filter':[{'exclude':False}]}}])[0]['result']['targetInfos']
        wrapper = next(t for t in tabs if t['type']=='tab' and t['url']==remote['url'])
        rpc(self.browser, [{'method':'Extensions.triggerAction','params':{'id':self.extension_id,'targetId':wrapper['targetId']}}])
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length===2')
        self.assertIn('Second source', evaluate(picker, 'document.querySelector(".video:last-child").textContent'))
        self.click(picker, '.video:last-child')
        wait_for(self.page, 'documentPictureInPicture.window && documentPictureInPicture.window!==oldPip && documentPictureInPicture.window.document.querySelector("#pip-video")?.readyState>=2')
        self.assertTrue(evaluate(self.page, 'oldPip.closed && oldTrack.readyState==="ended" && second.paused && !originalNode.paused'))
        self.click_control('pip-play')
        wait_for(self.page, '!second.paused')

    def test_50_selecting_existing_native_pip_keeps_it_open(self):
        evaluate(self.page, 'originalNode.src="http://localhost:8766/flower.mp4"')
        wait_for(self.page, 'originalNode.readyState>=2')
        evaluate(self.page, 'originalNode.play()', True)
        self.activate()
        wait_for(self.page, 'document.pictureInPictureElement===originalNode')
        remote = self.other_video('native-picker')
        evaluate(remote, 'document.querySelector("video").remove()')
        rpc(remote['webSocketDebuggerUrl'], [{'method':'Page.bringToFront'}])
        tabs = rpc(self.browser, [{'method':'Target.getTargets','params':{'filter':[{'exclude':False}]}}])[0]['result']['targetInfos']
        wrapper = next(t for t in tabs if t['type']=='tab' and t['url']==remote['url'])
        rpc(self.browser, [{'method':'Extensions.triggerAction','params':{'id':self.extension_id,'targetId':wrapper['targetId']}}])
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length===1')
        self.click(picker, '.video')
        deadline = time.monotonic()+5
        while any(t['id']==picker['id'] for t in fetch(f'http://127.0.0.1:{PORT}/json/list')) and time.monotonic()<deadline:
            time.sleep(.1)
        self.assertFalse(any(t['id']==picker['id'] for t in fetch(f'http://127.0.0.1:{PORT}/json/list')))
        self.assertTrue(evaluate(self.page, 'document.pictureInPictureElement===originalNode'))

    def test_59_revoking_access_removes_remote_videos(self):
        remote = self.other_video('permission-source')
        evaluate(self.page, 'originalNode.remove()')
        self.activate()
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video.playing").length===1 && document.querySelector("#access").hidden')
        evaluate(picker, 'chrome.permissions.remove({origins:["http://*/*","https://*/*"]})')
        wait_for(picker, 'document.body.dataset.ready==="true" && document.querySelectorAll(".video").length===0 && !document.querySelector("#access").hidden')
        self.assertTrue(evaluate(remote, '!document.querySelector("video").paused'))

    def test_47_unsupported_current_video_offers_remote_playback(self):
        remote = self.other_video('unsupported-current')
        evaluate(self.page, 'originalNode.disablePictureInPicture=true')
        self.activate()
        picker = self.picker()
        wait_for(picker, 'document.querySelectorAll(".video").length===1')
        self.assertFalse(evaluate(picker, 'Boolean(document.querySelector(".video").textContent.includes("Текущая вкладка"))'))
        self.click(picker, '.video')
        wait_for(remote, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.assertFalse(evaluate(self.page, 'Boolean(documentPictureInPicture.window || document.pictureInPictureElement)'))

V13Tests.test_42_other_tab_playing_video_is_first_and_opens_from_real_click = None

if __name__ == '__main__':
    unittest.main(verbosity=2)
