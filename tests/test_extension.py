"""Browser integration tests against the real unpacked extension and Chrome PiP."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from browser_lab import ensure_owned, fetch, rpc

PORT = 9233
URL = 'http://127.0.0.1:8766/'


def evaluate(target, expression, gesture=False):
    item = rpc(target['webSocketDebuggerUrl'], [{'method': 'Runtime.evaluate', 'params': {'expression': expression, 'returnByValue': True, 'awaitPromise': True, 'userGesture': gesture}}])[0]
    if not item['ok']:
        raise AssertionError(item)
    data = item['result']
    if 'exceptionDetails' in data:
        raise AssertionError(data['exceptionDetails'])
    return data['result'].get('value')


def wait_for(target, expression, timeout=8):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = evaluate(target, expression)
        if last:
            return last
        time.sleep(0.15)
    raise AssertionError(f'Timed out: {expression}; last={last!r}')


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / 'extension/manifest.json').exists(), 'Extension is not implemented: missing manifest.json'
        cls.browser = ensure_owned('chrome')['webSocketDebuggerUrl']
        current = rpc(cls.browser, [{'method': 'Extensions.getExtensions'}])[0]
        if current['ok']:
            for ext in current['result'].get('extensions', []):
                if ext['name'] == 'Independent PiP':
                    rpc(cls.browser, [{'method': 'Extensions.uninstall', 'params': {'id': ext['id']}}])
        result = rpc(cls.browser, [{'method': 'Extensions.loadUnpacked', 'params': {'path': str(ROOT / 'extension'), 'enableInIncognito': False}}])[0]
        assert result['ok'], result
        cls.extension_id = result['result']['id']
        verify = rpc(cls.browser, [{'method': 'Extensions.getExtensions'}])[0]
        assert verify['ok'] and any(e['id'] == cls.extension_id for e in verify['result']['extensions']), verify
        targets = fetch(f'http://127.0.0.1:{PORT}/json/list')
        cls.page = next(t for t in targets if t['type'] == 'page' and t['url'] == URL)

    def setUp(self):
        result = rpc(self.page['webSocketDebuggerUrl'], [{'method': 'Page.navigate', 'params': {'url': URL}}])[0]
        self.assertTrue(result['ok'], result)
        wait_for(self.page, 'document.querySelector("#main")?.readyState >= 2')
        evaluate(self.page, 'window.originalNode=document.querySelector("#main");window.originalParent=originalNode.parentNode;originalNode.currentTime=1;originalNode.play()', True)

    def tearDown(self):
        evaluate(self.page, 'documentPictureInPicture.window?.close(); document.pictureInPictureElement ? document.exitPictureInPicture() : undefined', True)

    def activate(self):
        # A real toolbar click acts on the active tab; return from options first.
        front = rpc(self.page['webSocketDebuggerUrl'], [{'method': 'Page.bringToFront'}])[0]
        self.assertTrue(front['ok'], front)
        targets = rpc(self.browser, [{'method': 'Target.getTargets', 'params': {'filter': [{'exclude': False}]}}])[0]
        tab_target = next(t for t in targets['result']['targetInfos'] if t['type'] == 'tab' and t['url'] == URL)
        result = rpc(self.browser, [{'method': 'Extensions.triggerAction', 'params': {'id': self.extension_id, 'targetId': tab_target['targetId']}}])[0]
        self.assertTrue(result['ok'], result)

    def pip_target(self):
        for target in fetch(f'http://127.0.0.1:{PORT}/json/list'):
            if target['type'] == 'page' and target['url'] == 'about:blank':
                if evaluate(target, 'Boolean(document.querySelector("#pip-video"))'):
                    return target
        raise AssertionError('PiP page target was not found')

    def click_control(self, element_id):
        target = self.pip_target()
        point = evaluate(target, f'(() => {{const e=document.getElementById({json.dumps(element_id)}); if(!e) return null; const r=e.getBoundingClientRect(); return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()')
        self.assertIsNotNone(point, f'Control is not implemented: {element_id}')
        results = rpc(target['webSocketDebuggerUrl'], [
            {'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **point}},
            {'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, **point}},
        ])
        self.assertTrue(all(r['ok'] for r in results), results)

    def test_02_controls_change_master_not_an_independent_player(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        pip = self.pip_target()
        evaluate(pip, 'const seek=document.querySelector("#pip-seek");seek.value=2;seek.dispatchEvent(new Event("input",{bubbles:true}))')
        self.assertAlmostEqual(evaluate(self.page, 'originalNode.currentTime'), 2, places=1)
        self.click_control('pip-forward')
        self.assertLessEqual(evaluate(self.page, 'originalNode.currentTime'), evaluate(self.page, 'originalNode.duration'))
        self.click_control('pip-back')
        self.assertEqual(evaluate(self.page, 'originalNode.currentTime'), 0)
        self.click_control('pip-mute')
        self.assertTrue(evaluate(self.page, 'originalNode.muted'))
        evaluate(pip, 'const volume=document.querySelector("#pip-volume");volume.value=0.3;volume.dispatchEvent(new Event("input",{bubbles:true}));const rate=document.querySelector("#pip-rate");rate.value="1.5";rate.dispatchEvent(new Event("change",{bubbles:true}))')
        result = evaluate(self.page, '({volume:originalNode.volume,muted:originalNode.muted,rate:originalNode.playbackRate})')
        self.assertAlmostEqual(result['volume'], 0.3)
        self.assertFalse(result['muted'])
        self.assertEqual(result['rate'], 1.5)
        self.click_control('pip-play')
        wait_for(self.page, '!originalNode.paused')
        self.click_control('pip-return')
        wait_for(self.page, '!documentPictureInPicture.window')
        self.assertTrue(evaluate(self.page, 'originalNode.parentNode===originalParent && !originalNode.paused'))
        print('REAL_CONTROLS', json.dumps(result))

    def test_03_source_removal_closes_window_and_releases_capture(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        evaluate(self.page, 'window.mirrorTrack=documentPictureInPicture.window.document.querySelector("#pip-video").srcObject.getVideoTracks()[0];originalNode.remove()')
        wait_for(self.page, '!documentPictureInPicture.window', timeout=3)
        self.assertEqual(evaluate(self.page, 'mirrorTrack.readyState'), 'ended')

    def test_04_playing_video_wins_over_larger_paused_video(self):
        evaluate(self.page, 'window.second=originalNode.cloneNode();second.id="second";second.style.width="1100px";document.body.prepend(second)')
        wait_for(self.page, 'second.readyState>=2')
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused && second.paused'))

    def test_05_cross_origin_capture_denial_uses_real_native_pip(self):
        evaluate(self.page, 'originalNode.src="http://localhost:8766/flower.mp4"')
        wait_for(self.page, 'originalNode.readyState>=2')
        evaluate(self.page, 'originalNode.play()', True)
        denied = evaluate(self.page, '(() => {try{const s=originalNode.captureStream();s.getTracks().forEach(t=>t.stop());return null;}catch(e){return e.name;}})()')
        self.assertEqual(denied, 'SecurityError')
        self.activate()
        wait_for(self.page, 'document.pictureInPictureElement===originalNode', timeout=3)
        self.assertFalse(evaluate(self.page, 'Boolean(documentPictureInPicture.window)'))
        self.activate()
        wait_for(self.page, '!document.pictureInPictureElement', timeout=3)
        print('REAL_FALLBACK', denied)

    def test_06_same_origin_iframe_video_is_discovered(self):
        evaluate(self.page, 'originalNode.remove();window.frame=document.createElement("iframe");frame.src="/index.html";frame.style.width="800px";frame.style.height="600px";document.body.append(frame)')
        wait_for(self.page, 'frame.contentDocument?.querySelector("video")?.readyState>=2')
        evaluate(self.page, 'window.originalNode=frame.contentDocument.querySelector("video");window.originalParent=originalNode.parentNode;originalNode.play()', True)
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))', timeout=3)
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused && originalNode.parentNode===originalParent'))

    def test_07_open_shadow_root_video_is_discovered(self):
        evaluate(self.page, 'window.host=document.createElement("div");document.body.append(host);host.attachShadow({mode:"open"}).append(originalNode)')
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))', timeout=3)
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused && originalNode.getRootNode()===host.shadowRoot'))
        evaluate(self.page, 'originalNode.remove()')
        wait_for(self.page, '!documentPictureInPicture.window', timeout=3)

    def test_08_active_vtt_cues_are_rendered_as_safe_text(self):
        evaluate(self.page, 'window.track=originalNode.addTextTrack("captions","Lab","en");track.addCue(new VTTCue(0,10,"Caption <b>text</b>"));track.mode="showing"')
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-subtitles")?.textContent==="Caption text"', timeout=3)
        pip = self.pip_target()
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-subtitles").children.length'), 0)
        self.click_control('pip-captions')
        self.assertTrue(evaluate(pip, 'document.querySelector("#pip-subtitles").hidden'))
        self.click_control('pip-captions')
        self.assertFalse(evaluate(pip, 'document.querySelector("#pip-subtitles").hidden'))

    def test_09_keyboard_controls_master_and_escape_closes(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        pip = self.pip_target()
        evaluate(pip, 'document.body.tabIndex=-1;document.body.focus()')
        def key(name, code):
            result = rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': name, 'windowsVirtualKeyCode': code}}])[0]
            if name == 'Escape' and not result['ok']:
                # Closing PiP may destroy its CDP socket before the key ACK.
                # Accept only that transport timeout, and verify the exact effect.
                self.assertIn('CDP timeout: Input.dispatchKeyEvent', result.get('error', ''))
                wait_for(self.page, '!documentPictureInPicture.window')
                self.assertFalse(any(target['id'] == pip['id'] for target in fetch(f'http://127.0.0.1:{PORT}/json/list')))
            else:
                self.assertTrue(result['ok'], result)
        key(' ', 32)
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        key('ArrowRight', 39)
        self.assertGreater(evaluate(self.page, 'originalNode.currentTime'), 4)
        key('ArrowLeft', 37)
        self.assertEqual(evaluate(self.page, 'originalNode.currentTime'), 0)
        key('m', 77)
        self.assertTrue(evaluate(self.page, 'originalNode.muted'))
        key('Escape', 27)
        wait_for(self.page, '!documentPictureInPicture.window')

    def action_state(self):
        worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and t['url'] == f'chrome-extension://{self.extension_id}/background.js')
        expression = f'''(async () => {{
          const tab=(await chrome.tabs.query({{}})).find(t=>t.url==={json.dumps(URL)});
          return {{badge:await chrome.action.getBadgeText({{tabId:tab.id}}),title:await chrome.action.getTitle({{tabId:tab.id}})}};
        }})()'''
        return evaluate(worker, expression)

    def test_10_no_video_has_explicit_badge_error(self):
        evaluate(self.page, 'originalNode.remove()')
        self.activate()
        deadline = time.monotonic()+3
        state = self.action_state()
        while state['badge'] != '!' and time.monotonic() < deadline:
            time.sleep(0.1)
            state = self.action_state()
        self.assertEqual(state['badge'], '!')
        self.assertIn('нет готового HTML5-видео', state['title'])
        self.assertFalse(evaluate(self.page, 'Boolean(documentPictureInPicture.window)'))
        print('REAL_NO_VIDEO', json.dumps(state, ensure_ascii=False))

    def test_11_toggle_releases_tracks_and_can_reopen(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        evaluate(self.page, 'window.savedTrack=documentPictureInPicture.window.document.querySelector("#pip-video").srcObject.getVideoTracks()[0]')
        self.activate()
        wait_for(self.page, '!documentPictureInPicture.window')
        self.assertEqual(evaluate(self.page, 'savedTrack.readyState'), 'ended')
        self.assertTrue(evaluate(self.page, '!originalNode.paused && originalNode.parentNode===originalParent'))
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')

    def test_12_source_change_closes_stale_mirror(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        evaluate(self.page, 'originalNode.src="flower.mp4?changed=1"')
        wait_for(self.page, '!documentPictureInPicture.window')

    def test_13_opening_does_not_autoplay_paused_source(self):
        evaluate(self.page, 'originalNode.pause()')
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))

    def test_14_dynamically_created_video_is_found(self):
        evaluate(self.page, 'const replacement=originalNode.cloneNode();originalNode.remove();window.originalNode=replacement;document.body.append(originalNode)')
        wait_for(self.page, 'originalNode.readyState>=2')
        evaluate(self.page, 'originalNode.play()', True)
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))

    def test_15_site_pip_disable_is_respected(self):
        evaluate(self.page, 'originalNode.disablePictureInPicture=true')
        self.activate()
        deadline = time.monotonic()+3
        state = self.action_state()
        while state['badge'] != '!' and time.monotonic() < deadline:
            time.sleep(0.1)
            state = self.action_state()
        self.assertEqual(state['badge'], '!')
        self.assertIn('Сайт запретил', state['title'])
        self.assertFalse(evaluate(self.page, 'Boolean(documentPictureInPicture.window || document.pictureInPictureElement)'))

    def test_16_media_source_blob_pipeline_is_not_reloaded(self):
        supported = evaluate(self.page, 'MediaSource.isTypeSupported(\'video/webm;codecs="vp8,vorbis"\')')
        self.assertTrue(supported, 'Installed Chrome lacks fixture MSE codec support')
        evaluate(self.page, '''(async () => {
          const bytes=await (await fetch('flower.webm')).arrayBuffer();
          const media=new MediaSource();
          window.mediaSource=media;
          window.originalBlob=URL.createObjectURL(media);
          originalNode.src=originalBlob;
          await new Promise((resolve,reject)=>{
            media.addEventListener('sourceopen',()=>{
              try {
                const buffer=media.addSourceBuffer('video/webm;codecs="vp8,vorbis"');
                buffer.addEventListener('error',()=>reject(new Error('MSE fixture append failed')),{once:true});
                buffer.addEventListener('updateend',()=>{media.endOfStream();resolve();},{once:true});
                buffer.appendBuffer(bytes);
              } catch(error) {reject(error);}
            },{once:true});
          });
        })()''', True)
        wait_for(self.page, 'originalNode.readyState>=2')
        evaluate(self.page, 'originalNode.play()', True)
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        state = evaluate(self.page, '({sameBlob:originalNode.currentSrc===originalBlob,sameNode:document.querySelector("#main")===originalNode,previewURL:documentPictureInPicture.window.document.querySelector("#pip-video").currentSrc})')
        self.assertTrue(state['sameBlob'] and state['sameNode'], state)
        self.assertEqual(state['previewURL'], '')
        self.click_control('pip-play')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        print('REAL_MSE', json.dumps(state))

    def test_17_video_click_toggles_source_without_rewinding(self):
        self.activate()
        wait_for(self.page, 'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
        self.click_control('pip-video')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        position = evaluate(self.page, 'originalNode.currentTime')
        self.assertGreater(position, 0)
        self.click_control('pip-video')
        wait_for(self.page, '!originalNode.paused')
        self.assertTrue(evaluate(self.page, 'originalNode.parentNode===originalParent'))
        print('REAL_VIDEO_CLICK', position)

    def test_18_symbol_controls_follow_source_state(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        pip = self.pip_target()
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-play").textContent'), '⏸')
        evaluate(self.page, 'originalNode.pause();originalNode.muted=true')
        wait_for(pip, 'document.querySelector("#pip-play").textContent==="▶" && document.querySelector("#pip-mute").textContent==="🔇"')
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-play").getAttribute("aria-label")'), 'Воспроизвести')
        self.assertTrue(evaluate(pip, '["pip-back","pip-forward","pip-mute","pip-return","pip-close"].every(id=>Boolean(document.getElementById(id).title))'))
        self.click_control('pip-mute')
        wait_for(pip, 'document.querySelector("#pip-mute").textContent==="🔊"')

    def test_19_preset_speed_list_preserves_existing_exact_rate(self):
        evaluate(self.page, 'originalNode.playbackRate=1.234')
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-rate"))')
        pip = self.pip_target()
        rates = evaluate(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>Number(o.value))')
        expected = [0.5, 1, 1.10, 1.15, 1.25, 1.5, 2]
        self.assertTrue(all(rate in rates for rate in expected), rates)
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-rate").value'), '1.234')
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 1.234)
        evaluate(pip, 'const r=document.querySelector("#pip-rate");r.value="1.1";r.dispatchEvent(new Event("change",{bubbles:true}))')
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 1.1)

    def test_20_exact_manual_speed_validates_without_play_toggle(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-rate"))')
        pip = self.pip_target()
        self.assertTrue(evaluate(pip, 'Boolean(document.querySelector("#pip-rate-custom"))'), 'Exact rate input is missing')
        evaluate(self.page, 'originalNode.pause()')
        if evaluate(pip, 'Boolean(document.querySelector("#pip-menu-toggle"))'):
            self.click_control('pip-menu-toggle')
        evaluate(pip, 'document.querySelector("#pip-rate-custom").value="";document.querySelector("#pip-rate-custom").focus()')
        results = rpc(pip['webSocketDebuggerUrl'], [
            {'method': 'Input.insertText', 'params': {'text': '1,234'}},
            {'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': 'Enter', 'text': '\r', 'windowsVirtualKeyCode': 13}},
            {'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyUp', 'key': 'Enter', 'windowsVirtualKeyCode': 13}},
        ])
        self.assertTrue(all(item['ok'] for item in results), results)
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 1.234)
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-rate").value'), '1.234')
        self.assertTrue(evaluate(self.page, 'originalNode.paused'))
        for invalid in ['', '0', '4.1', 'Infinity', '0x1', 'abc']:
            evaluate(pip, f'document.querySelector("#pip-rate-custom").value={json.dumps(invalid)};document.querySelector("#pip-rate-form").requestSubmit()')
            self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 1.234)
            self.assertTrue(evaluate(pip, 'Boolean(document.querySelector("#pip-status").textContent)'))
        evaluate(pip, 'document.querySelector("#pip-rate-custom").value="0.25";document.querySelector("#pip-rate-form").requestSubmit()')
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 0.25)
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-status").textContent'), '')

    def test_21_options_save_validate_restore_and_reset_preferences(self):
        manifest = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))
        self.assertIn('options_ui', manifest, 'Settings page is missing')
        self.assertIn('storage', manifest['permissions'])
        url = f'chrome-extension://{self.extension_id}/options.html'
        target_id = rpc(self.browser, [{'method': 'Target.createTarget', 'params': {'url': url}}])[0]['result']['targetId']
        options = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id'] == target_id)
        try:
            wait_for(options, 'document.querySelector("#prefs-form")?.dataset.ready==="true"')
            evaluate(options, 'document.querySelector("#speed-mode").value="step";document.querySelector("#speed-step").value="0.1";document.querySelector("#custom-rates").value="1.234; 1,777";document.querySelector("#auto-hide").checked=false;document.querySelector("#prefs-form").requestSubmit()')
            wait_for(options, 'document.querySelector("#prefs-status").textContent==="Сохранено"')
            saved = evaluate(options, 'chrome.storage.local.get("pipSettings")')['pipSettings']
            self.assertEqual(saved['speedStep'], 0.1)
            self.assertEqual(saved['customRates'], [1.234, 1.777])
            self.assertFalse(saved['autoHide'])
            evaluate(options, 'document.querySelector("#custom-rates").value="1.234; bad";document.querySelector("#prefs-form").requestSubmit()')
            wait_for(options, 'document.querySelector("#prefs-status").textContent.startsWith("Ошибка:")')
            self.assertEqual(evaluate(options, 'chrome.storage.local.get("pipSettings")')['pipSettings'], saved)
            rpc(options['webSocketDebuggerUrl'], [{'method': 'Page.reload'}])
            wait_for(options, 'document.querySelector("#prefs-form")?.dataset.ready==="true"')
            self.assertEqual(evaluate(options, 'document.querySelector("#speed-step").value'), '0.1')
            self.assertFalse(evaluate(options, 'document.querySelector("#auto-hide").checked'))
            self.activate()
            wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-rate"))')
            pip = self.pip_target()
            wait_for(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>o.value).includes("1.777")')
            rates = evaluate(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>Number(o.value))')
            self.assertIn(1.234, rates)
            self.assertIn(1.2, rates)
            self.assertLess(len(rates), len(range(25, 401, 5)))
            evaluate(options, 'document.querySelector("#prefs-reset").click()')
            wait_for(options, 'document.querySelector("#prefs-status").textContent==="Настройки сброшены"')
            self.assertEqual(evaluate(options, 'chrome.storage.local.get("pipSettings")')['pipSettings'], {'speedMode': 'presets', 'speedStep': 0.05, 'customRates': [], 'autoHide': False, 'showSeekButtons': True})
            wait_for(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>o.value).includes("1.15")')
        finally:
            rpc(self.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': target_id}}])

    def test_22_overlay_layout_fills_window_and_fits_compact_width(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        evaluate(self.page, 'originalNode.pause()')
        pip = self.pip_target()
        window_id = rpc(self.browser, [{'method': 'Browser.getWindowForTarget', 'params': {'targetId': pip['id']}}])[0]['result']['windowId']
        for width, height in [(620, 350), (320, 220)]:
            # Document PiP ignores Emulation metrics; resize its owned window.
            results = rpc(self.browser, [{'method': 'Browser.setWindowBounds', 'params': {'windowId': window_id, 'bounds': {'width': width, 'height': height}}}])
            self.assertTrue(results[0]['ok'], results)
            wait_for(pip, f'innerWidth <= {width} && innerWidth >= {width-32}')
            layout = evaluate(pip, '''(() => {
              const rect=id=>{const r=document.getElementById(id).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
              const r=rect('pip-video'),time=rect('pip-time');
              return {video:r,width:innerWidth,height:innerHeight,timeCenter:time.x+time.w/2,
                overflow:document.body.scrollWidth>innerWidth,
                menu:!!document.querySelector('#pip-menu-toggle'),
                background:getComputedStyle(document.querySelector('#pip-play')).backgroundColor,
                controls:['pip-play','pip-back','pip-forward','pip-mute','pip-rate','pip-captions','pip-menu-toggle','pip-return','pip-close'].map(id=>document.getElementById(id)?{id,...rect(id)}:{id,missing:true})};
            })()''')
            self.assertEqual(layout['video']['y'], 0, layout)
            self.assertEqual(layout['video']['h'], layout['height'], layout)
            self.assertEqual(layout['video']['w'], layout['width'], layout)
            self.assertFalse(layout['overflow'], layout)
            self.assertTrue(layout['menu'], layout)
            self.assertEqual(layout['background'], 'rgba(0, 0, 0, 0)')
            self.assertAlmostEqual(layout['timeCenter'], layout['width']/2, delta=2)
            for control in layout['controls']:
                self.assertFalse(control.get('missing'), control)
                self.assertGreaterEqual(control['x'], 0, control)
                self.assertLessEqual(control['x']+control['w'], layout['width'], control)
                self.assertGreaterEqual(control['y'], 0, control)
                self.assertLessEqual(control['y']+control['h'], layout['height'], control)
            import base64
            image = rpc(pip['webSocketDebuggerUrl'], [{'method': 'Page.captureScreenshot', 'params': {'format': 'png', 'captureBeyondViewport': False}}])[0]
            self.assertTrue(image['ok'], image)
            folder = ROOT/'reports/screenshots'
            folder.mkdir(parents=True, exist_ok=True)
            (folder/f'pip-v1.2-{layout["width"]}x{layout["height"]}.png').write_bytes(base64.b64decode(image['result']['data']))
        self.click_control('pip-menu-toggle')
        self.assertTrue(evaluate(pip, '!document.querySelector("#pip-menu").hidden'))
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-menu-toggle").getAttribute("aria-expanded")'), 'true')
        self.click_control('pip-menu-toggle')
        self.assertTrue(evaluate(pip, 'document.querySelector("#pip-menu").hidden'))

    def test_23_menu_escape_outside_click_and_options_button(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-menu"))')
        evaluate(self.page, 'originalNode.pause()')
        pip = self.pip_target()
        self.click_control('pip-menu-toggle')
        evaluate(pip, 'document.querySelector("#pip-rate-custom").focus()')
        rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': 'Escape', 'windowsVirtualKeyCode': 27}}])
        self.assertTrue(evaluate(pip, 'document.querySelector("#pip-menu").hidden'), 'Escape must dismiss the open menu')
        self.assertTrue(evaluate(self.page, 'Boolean(documentPictureInPicture.window)'))
        self.click_control('pip-menu-toggle')
        self.click_control('pip-mute')
        self.assertTrue(evaluate(pip, 'document.querySelector("#pip-menu").hidden'))
        self.assertTrue(evaluate(self.page, 'originalNode.paused && originalNode.muted'))
        self.click_control('pip-menu-toggle')
        self.click_control('pip-options')
        options_url = f'chrome-extension://{self.extension_id}/options.html'
        deadline = time.monotonic() + 5
        options = None
        while time.monotonic() < deadline:
            options = next((t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['url'] == options_url), None)
            if options:
                break
            time.sleep(0.15)
        self.assertIsNotNone(options, 'Settings button did not open the actual options page')
        try:
            wait_for(options, 'document.querySelector("#prefs-form")?.dataset.ready==="true"')
            self.assertTrue(evaluate(self.page, 'originalNode.paused && originalNode.parentNode===originalParent'))
        finally:
            rpc(self.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': options['id']}}])

    def test_24_opt_in_auto_hide_wakes_and_respects_pause_focus_menu(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        pip = self.pip_target()
        worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and t['url'] == f'chrome-extension://{self.extension_id}/background.js')
        before = evaluate(worker, 'chrome.storage.local.get("pipSettings")').get('pipSettings', {'speedStep':0.05,'customRates':[],'autoHide':False})
        try:
            evaluate(worker, 'chrome.storage.local.set({pipSettings:{speedStep:0.05,customRates:[],autoHide:true}})')
            wait_for(pip, 'document.body.classList.contains("pip-ui-hidden")', timeout=7)
            wait_for(pip, 'getComputedStyle(document.querySelector("#pip-controls")).opacity==="0"')
            rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchMouseEvent', 'params': {'type': 'mouseMoved', 'x': 160, 'y': 100}}])
            wait_for(pip, '!document.body.classList.contains("pip-ui-hidden")')
            wait_for(pip, 'document.body.classList.contains("pip-ui-hidden")', timeout=7)
            self.click_control('pip-video')
            wait_for(self.page, 'originalNode.paused')
            wait_for(pip, '!document.body.classList.contains("pip-ui-hidden")')
            time.sleep(3.2)
            self.assertFalse(evaluate(pip, 'document.body.classList.contains("pip-ui-hidden")'))
            evaluate(self.page, 'originalNode.play()', True)
            self.click_control('pip-menu-toggle')
            time.sleep(3.2)
            self.assertFalse(evaluate(pip, 'document.body.classList.contains("pip-ui-hidden")'))
            self.click_control('pip-menu-toggle')
            evaluate(pip, 'document.querySelector("#pip-video").focus()')
            rpc(pip['webSocketDebuggerUrl'], [{'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': 'Tab', 'windowsVirtualKeyCode': 9}}])
            self.assertTrue(evaluate(pip, 'Boolean(document.activeElement.closest("#pip-header,#pip-controls"))'))
            time.sleep(3.2)
            self.assertFalse(evaluate(pip, 'document.body.classList.contains("pip-ui-hidden")'))
        finally:
            evaluate(worker, f'chrome.storage.local.set({{pipSettings:{json.dumps(before)}}})')

    def test_25_space_on_video_and_button_toggles_exactly_once(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        pip = self.pip_target()
        evaluate(self.page, 'window.transitions=[];originalNode.addEventListener("play",()=>transitions.push("play"));originalNode.addEventListener("pause",()=>transitions.push("pause"))')
        def space(control):
            evaluate(pip, f'document.getElementById({json.dumps(control)}).focus()')
            results = rpc(pip['webSocketDebuggerUrl'], [
                {'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyDown', 'key': ' ', 'text': ' ', 'windowsVirtualKeyCode': 32}},
                {'method': 'Input.dispatchKeyEvent', 'params': {'type': 'keyUp', 'key': ' ', 'windowsVirtualKeyCode': 32}},
            ])
            self.assertTrue(all(item['ok'] for item in results), results)
        space('pip-video')
        wait_for(self.page, 'originalNode.paused')
        space('pip-play')
        wait_for(self.page, '!originalNode.paused')
        space('pip-play')
        wait_for(self.page, 'originalNode.paused')
        space('pip-video')
        wait_for(self.page, '!originalNode.paused')
        self.assertEqual(evaluate(self.page, 'transitions'), ['pause', 'play', 'pause', 'play'])

    def test_26_corrupt_stored_preferences_are_bounded(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-rate"))')
        pip = self.pip_target()
        worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and t['url'] == f'chrome-extension://{self.extension_id}/background.js')
        try:
            evaluate(worker, 'chrome.storage.local.set({pipSettings:{speedStep:0,customRates:[0.1,5,"1.5",1.234,1.234],autoHide:"true"}})')
            wait_for(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>o.value).includes("1.234")')
            rates = evaluate(pip, 'Array.from(document.querySelector("#pip-rate").options,o=>Number(o.value))')
            self.assertIn(1.05, rates)
            self.assertNotIn(0.1, rates)
            self.assertNotIn(5, rates)
            self.assertEqual(rates.count(1.234), 1)
            self.assertEqual(evaluate(pip, 'document.body.dataset.autoHide'), 'false')
        finally:
            evaluate(worker, 'chrome.storage.local.set({pipSettings:{speedStep:0.05,customRates:[],autoHide:false}})')

    def test_27_preferences_survive_owned_browser_restart(self):
        import warnings
        import urllib.error
        from browser_lab import start, RUNTIME
        state = json.loads((RUNTIME/'chrome.json').read_text(encoding='utf-8'))
        self.assertTrue(any(arg.startswith('--user-data-dir=') and 'yandex-pip-lab' in arg for arg in state['args']), 'Do not restart unowned browsers')
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        worker = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type'] == 'service_worker' and t['url'] == f'chrome-extension://{self.extension_id}/background.js')
        saved = {'speedStep': 0.1, 'customRates': [1.234], 'autoHide': False}
        evaluate(worker, f'chrome.storage.local.set({{pipSettings:{json.dumps(saved)}}})')
        self.assertEqual(evaluate(worker, 'chrome.storage.local.get("pipSettings")')['pipSettings'], saved)
        rpc(self.browser, [{'method': 'Browser.close'}])
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            try:
                fetch(f'http://127.0.0.1:{PORT}/json/version')
            except (urllib.error.URLError, ConnectionError):
                break
            time.sleep(0.1)
        else:
            self.fail('Owned browser did not shut down')
        with warnings.catch_warnings(record=True) as launch_warnings:
            warnings.simplefilter('always', ResourceWarning)
            version = start('chrome')
        cls = type(self)
        cls.browser = version['webSocketDebuggerUrl']
        extensions = rpc(cls.browser, [{'method': 'Extensions.getExtensions'}])[0]
        self.assertTrue(extensions['ok'], extensions)
        if not any(ext['id'] == self.extension_id for ext in extensions['result']['extensions']):
            loaded = rpc(cls.browser, [{'method': 'Extensions.loadUnpacked', 'params': {'path': str(ROOT/'extension'), 'enableInIncognito': False}}])[0]
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['id'], self.extension_id)
        page_id = rpc(cls.browser, [{'method': 'Target.createTarget', 'params': {'url': URL}}])[0]['result']['targetId']
        cls.page = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id'] == page_id)
        wait_for(cls.page, 'document.querySelector("#main")?.readyState>=2')
        option_id = rpc(cls.browser, [{'method': 'Target.createTarget', 'params': {'url': f'chrome-extension://{self.extension_id}/options.html'}}])[0]['result']['targetId']
        options = next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id'] == option_id)
        try:
            wait_for(options, 'document.querySelector("#prefs-form")?.dataset.ready==="true"')
            self.assertEqual(evaluate(options, 'chrome.storage.local.get("pipSettings")')['pipSettings'], saved)
            self.assertEqual(evaluate(options, 'document.querySelector("#speed-step").value'), '0.1')
            self.assertEqual(evaluate(options, 'document.querySelector("#custom-rates").value'), '1.234')
            evaluate(options, 'document.querySelector("#prefs-reset").click()')
            wait_for(options, 'document.querySelector("#prefs-status").textContent==="Настройки сброшены"')
            print('REAL_RESTART_PERSISTENCE', json.dumps(saved))
            self.assertEqual([str(item.message) for item in launch_warnings if item.category is ResourceWarning], [])
        finally:
            rpc(cls.browser, [{'method': 'Target.closeTarget', 'params': {'targetId': option_id}}])

    def test_28_control_smoke_has_no_runtime_or_console_errors(self):
        import subprocess
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        pip = self.pip_target()
        expression = '''new Promise(resolve => {
          document.querySelector('#pip-menu-toggle').click();
          const input=document.querySelector('#pip-rate-custom');input.value='1.234';
          document.querySelector('#pip-rate-form').requestSubmit();
          const volume=document.querySelector('#pip-volume');volume.value='0.42';volume.dispatchEvent(new Event('input',{bubbles:true}));
          document.querySelector('#pip-captions').click();document.querySelector('#pip-captions').click();
          document.querySelector('#pip-menu-toggle').click();
          setTimeout(resolve,200);
        })'''
        payload = {'ws': pip['webSocketDebuggerUrl'], 'collectEvents': True, 'commands': [
            {'method': 'Runtime.enable'}, {'method': 'Log.enable'},
            {'method': 'Runtime.evaluate', 'params': {'expression': expression, 'awaitPromise': True, 'returnByValue': True, 'userGesture': True}},
        ]}
        run = subprocess.run(['node', str(ROOT/'tools/cdp.mjs')], input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=30, check=True)
        observed = json.loads(run.stdout)
        self.assertTrue(all(item['ok'] for item in observed['results']), observed)
        self.assertNotIn('exceptionDetails', observed['results'][-1]['result'])
        errors = [event for event in observed['events'] if event.get('method') == 'Runtime.exceptionThrown' or (event.get('method') == 'Log.entryAdded' and event['params']['entry']['level'] == 'error') or (event.get('method') == 'Runtime.consoleAPICalled' and event['params']['type'] == 'error')]
        self.assertEqual(errors, [])
        self.assertEqual(evaluate(pip, 'document.querySelector("#pip-status").textContent'), '')
        self.assertEqual(evaluate(self.page, 'originalNode.playbackRate'), 1.234)
        (ROOT/'reports/console-events-v1.2.json').write_text(json.dumps(observed, indent=2), encoding='utf-8')
        print('REAL_CONSOLE_ERRORS', len(errors))

    def test_29_close_releases_capture_and_storage_listener_with_pending_hide(self):
        import subprocess
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video"))')
        payload = {'ws':self.page['webSocketDebuggerUrl'],'collectEvents':True,'commands':[{'method':'Runtime.enable'}]}
        run = subprocess.run(['node',str(ROOT/'tools/cdp.mjs')],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,timeout=30,check=True)
        contexts = [event['params']['context']['id'] for event in json.loads(run.stdout)['events'] if event.get('method')=='Runtime.executionContextCreated']
        def isolated(context, expression):
            item = rpc(self.page['webSocketDebuggerUrl'], [{'method':'Runtime.evaluate','params':{'contextId':context,'expression':expression,'returnByValue':True,'awaitPromise':True}}])[0]
            self.assertTrue(item['ok'],item)
            self.assertNotIn('exceptionDetails',item['result'])
            return item['result']['result'].get('value')
        context = next(context for context in contexts if isolated(context,'Boolean(globalThis.__independentPiPState)'))
        self.assertTrue(isolated(context,'chrome.storage.onChanged.hasListeners()'))
        isolated(context, 'chrome.storage.local.set({pipSettings:{speedStep:0.05,customRates:[],autoHide:true}})')
        wait_for(self.pip_target(), 'document.body.dataset.autoHide==="true"')
        isolated(context,'globalThis.__testCapture=globalThis.__independentPiPState.capture;globalThis.__independentPiPState.window.close()')
        wait_for(self.page, '!documentPictureInPicture.window')
        result = isolated(context, '({tracksEnded:__testCapture.getTracks().every(t=>t.readyState==="ended"),stateGone:!globalThis.__independentPiPState,listenersGone:!chrome.storage.onChanged.hasListeners()})')
        self.assertTrue(all(result.values()),result)
        isolated(context, 'chrome.storage.local.set({pipSettings:{speedStep:0.05,customRates:[],autoHide:false}})')
        self.assertTrue(evaluate(self.page, 'originalNode.parentNode===originalParent && !originalNode.paused'))
        print('REAL_UI_CLEANUP',json.dumps(result))

    def test_01_toolbar_opens_mirror_without_detaching_source(self):
        self.activate()
        wait_for(self.page, 'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState >= 2)')
        result = evaluate(self.page, '''(() => {
          const preview=documentPictureInPicture.window.document.querySelector('#pip-video');
          return {sameNode:originalNode===document.querySelector('#main'),sameParent:originalNode.parentNode===originalParent,sourceCount:document.querySelectorAll('video').length,playing:!originalNode.paused,muted:preview.muted,tracks:preview.srcObject.getTracks().map(t=>t.kind),sourceURL:originalNode.currentSrc,previewURL:preview.currentSrc,frames:preview.getVideoPlaybackQuality().totalVideoFrames};
        })()''')
        self.assertTrue(result['sameNode'], result)
        self.assertTrue(result['sameParent'], result)
        self.assertEqual(result['sourceCount'], 1, result)
        self.assertTrue(result['playing'], result)
        self.assertTrue(result['muted'], result)
        self.assertEqual(result['tracks'], ['video'], result)
        self.assertIn('flower.mp4', result['sourceURL'], result)
        self.assertEqual(result['previewURL'], '', result)
        self.assertGreater(result['frames'], 0, result)
        print('REAL_MIRROR', json.dumps(result))


if __name__ == '__main__':
    unittest.main(verbosity=2)
