"""v1.2 behavior tests, using real extension and media (no UI mocks)."""
import json
import unittest
import test_extension as base
from test_extension import evaluate, wait_for, fetch, rpc, PORT, ROOT

class V12Tests(base.ExtensionTests):
    def setUp(self):
        super().setUp()
        worker=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type']=='service_worker' and self.extension_id in t['url'])
        evaluate(worker,'chrome.storage.local.remove("pipSettings")')

# Do not repeat inherited regression tests in this module's suite.
for name in dir(base.ExtensionTests):
    if name.startswith('test_'):
        setattr(V12Tests,name,None)

def test_default_speed_presets(self):
    self.activate()
    wait_for(self.page,'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-rate"))')
    pip=self.pip_target()
    rates=evaluate(pip,'Array.from(document.querySelector("#pip-rate").options,o=>Number(o.value))')
    self.assertEqual(rates,[0.5,1,1.10,1.15,1.25,1.5,2])
    self.assertEqual(evaluate(self.page,'originalNode.playbackRate'),1)
V12Tests.test_30_default_speed_presets=test_default_speed_presets

def test_speed_mode_options_and_migration(self):
    url=f'chrome-extension://{self.extension_id}/options.html'
    tid=rpc(self.browser,[{'method':'Target.createTarget','params':{'url':url}}])[0]['result']['targetId']
    options=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==tid)
    try:
        wait_for(options,'document.querySelector("#prefs-form")?.dataset.ready==="true"')
        self.assertTrue(evaluate(options,'Boolean(document.querySelector("#speed-mode"))'),'Speed list mode option is missing')
        self.assertEqual(evaluate(options,'document.querySelector("#speed-mode").value'),'presets')
        evaluate(options,'document.querySelector("#speed-mode").value="step";document.querySelector("#speed-step").value="0.1";document.querySelector("#prefs-form").requestSubmit()')
        wait_for(options,'document.querySelector("#prefs-status").textContent==="Сохранено"')
        self.assertEqual(evaluate(options,'chrome.storage.local.get("pipSettings")')['pipSettings']['speedMode'],'step')
        self.assertEqual(evaluate(options,'IndependentPiPSettings.normalize({speedStep:0.1,customRates:[1.234]}).speedMode'),'step')
        self.assertEqual(evaluate(options,'IndependentPiPSettings.normalize({speedStep:0.05,customRates:[]}).speedMode'),'presets')
        evaluate(options,'document.querySelector("#prefs-reset").click()')
        wait_for(options,'document.querySelector("#prefs-status").textContent==="Настройки сброшены"')
        self.assertEqual(evaluate(options,'document.querySelector("#speed-mode").value'),'presets')
    finally:
        rpc(self.browser,[{'method':'Target.closeTarget','params':{'targetId':tid}}])
V12Tests.test_31_speed_mode_options_and_migration=test_speed_mode_options_and_migration

def test_seek_visibility_live_and_persistent(self):
    self.activate()
    wait_for(self.page,'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-back"))')
    pip=self.pip_target()
    self.assertFalse(evaluate(pip,'document.querySelector("#pip-back").hidden'))
    tid=rpc(self.browser,[{'method':'Target.createTarget','params':{'url':f'chrome-extension://{self.extension_id}/options.html'}}])[0]['result']['targetId']
    options=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['id']==tid)
    try:
        wait_for(options,'document.querySelector("#prefs-form")?.dataset.ready==="true"')
        self.assertTrue(evaluate(options,'Boolean(document.querySelector("#show-seek-buttons"))'),'Seek visibility setting missing')
        evaluate(options,'document.querySelector("#show-seek-buttons").checked=false;document.querySelector("#prefs-form").requestSubmit()')
        wait_for(options,'document.querySelector("#prefs-status").textContent==="Сохранено"')
        wait_for(pip,'document.querySelector("#pip-back").hidden && document.querySelector("#pip-forward").hidden')
        self.assertTrue(evaluate(pip,'document.querySelector("#pip-seek").getBoundingClientRect().width>0'))
        rpc(options['webSocketDebuggerUrl'],[{'method':'Page.reload'}])
        wait_for(options,'document.querySelector("#prefs-form")?.dataset.ready==="true"')
        self.assertFalse(evaluate(options,'document.querySelector("#show-seek-buttons").checked'))
        evaluate(options,'document.querySelector("#prefs-reset").click()')
        wait_for(pip,'!document.querySelector("#pip-back").hidden && !document.querySelector("#pip-forward").hidden')
    finally:
        rpc(self.browser,[{'method':'Target.closeTarget','params':{'targetId':tid}}])
V12Tests.test_32_seek_visibility_live_and_persistent=test_seek_visibility_live_and_persistent

def test_volume_hover_horizontal_vertical_and_keyboard(self):
    self.activate()
    wait_for(self.page,'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-mute"))')
    pip=self.pip_target()
    self.assertTrue(evaluate(pip,'Boolean(document.querySelector("#pip-volume-popup"))'),'Hover volume popup is missing')
    wid=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']['windowId']
    for width,orientation in [(700,'horizontal'),(320,'vertical')]:
        rpc(self.browser,[{'method':'Browser.setWindowBounds','params':{'windowId':wid,'bounds':{'width':width,'height':350}}}])
        wait_for(pip,f'innerWidth<{width} && innerWidth>={width-32}')
        point=evaluate(pip,'(() => {const r=document.querySelector("#pip-mute").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
        rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mouseMoved',**point}}])
        wait_for(pip,'!document.querySelector("#pip-volume-popup").hidden')
        self.assertEqual(evaluate(pip,'document.querySelector("#pip-volume-popup").dataset.orientation'),orientation)
        self.assertTrue(evaluate(pip,'(() => {const r=document.querySelector("#pip-volume-popup").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()'))
        evaluate(self.page,'originalNode.volume=.3;originalNode.muted=true')
        wait_for(pip,'document.querySelector("#pip-volume").value==="0"')
        evaluate(pip,'document.querySelector("#pip-volume").value=".4";document.querySelector("#pip-volume").dispatchEvent(new Event("input",{bubbles:true}))')
        self.assertAlmostEqual(evaluate(self.page,'originalNode.volume'),.4)
        self.assertFalse(evaluate(self.page,'originalNode.muted'))
        evaluate(pip,'document.querySelector("#pip-volume").focus()')
        key='ArrowUp' if orientation=='vertical' else 'ArrowRight'
        rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchKeyEvent','params':{'type':'keyDown','key':key,'windowsVirtualKeyCode':38 if key=='ArrowUp' else 39}}])
        self.assertGreater(evaluate(self.page,'originalNode.volume'),.4)
        import base64
        shot=rpc(pip['webSocketDebuggerUrl'],[{'method':'Page.captureScreenshot','params':{'format':'png','captureBeyondViewport':False}}])[0]
        self.assertTrue(shot['ok'],shot)
        (ROOT/f'reports/screenshots/pip-v1.2-volume-{orientation}.png').write_bytes(base64.b64decode(shot['result']['data']))
        rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchKeyEvent','params':{'type':'keyDown','key':'Escape','windowsVirtualKeyCode':27}}])
        self.assertTrue(evaluate(pip,'document.querySelector("#pip-volume-popup").hidden'))
        self.assertTrue(evaluate(self.page,'Boolean(documentPictureInPicture.window)'))
V12Tests.test_33_volume_hover_horizontal_vertical_and_keyboard=test_volume_hover_horizontal_vertical_and_keyboard

def test_drag_moves_only_pip_without_play_toggle(self):
    self.activate()
    wait_for(self.page,'documentPictureInPicture.window?.document.querySelector("#pip-video")?.readyState>=2')
    pip=self.pip_target()
    self.assertEqual(evaluate(pip,'document.body.dataset.dragAvailable'),'true','Owned-window drag binding is missing')
    native=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']
    parent=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':self.page['id']}}])[0]['result']
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mousePressed','x':160,'y':100,'button':'left','buttons':1,'clickCount':1}}])
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mouseMoved','x':220,'y':140,'button':'left','buttons':1}}])
    def bounds():
        return rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']['bounds']
    import time
    deadline=time.monotonic()+5
    after=bounds()
    while after['left']==native['bounds']['left'] and time.monotonic()<deadline:
        time.sleep(.1);after=bounds()
    self.assertEqual(after['left'],native['bounds']['left']+60,after)
    self.assertEqual(after['top'],native['bounds']['top']+40,after)
    # After moving the window, the same physical screen point has old client coords.
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mouseReleased','x':160,'y':100,'button':'left','buttons':0,'clickCount':1}}])
    self.assertFalse(evaluate(self.page,'originalNode.paused'),'Release after drag toggled pause')
    current_parent=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':self.page['id']}}])[0]['result']
    self.assertEqual(current_parent,parent)
    self.click_control('pip-video')
    self.assertTrue(evaluate(self.page,'originalNode.paused'),'Ordinary click stopped toggling')
    print('REAL_DRAG',json.dumps({'before':native,'after':after,'parent_unchanged':current_parent==parent}))
V12Tests.test_34_drag_moves_only_pip_without_play_toggle=test_drag_moves_only_pip_without_play_toggle

def test_volume_pointer_leave_after_mouse_focus(self):
    self.activate()
    wait_for(self.page,'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-mute"))')
    pip=self.pip_target()
    self.click_control('pip-mute')
    wait_for(pip,'!document.querySelector("#pip-volume-popup").hidden')
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mouseMoved','x':200,'y':100}}])
    wait_for(pip,'document.querySelector("#pip-volume-popup").hidden',timeout=2)
V12Tests.test_35_volume_pointer_leave_after_mouse_focus=test_volume_pointer_leave_after_mouse_focus

def test_drag_safety_closed_binding_and_reopen(self):
    self.activate()
    wait_for(self.page,'documentPictureInPicture.window?.document.body.dataset.dragAvailable==="true"')
    pip=self.pip_target()
    worker=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type']=='service_worker' and self.extension_id in t['url'])
    native=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']
    checks=evaluate(worker,'''(async () => {
      const [key,binding]=Object.entries(await chrome.storage.session.get(null)).find(([key])=>key.startsWith('pipWindow:'));
      const sender={id:chrome.runtime.id,frameId:0,tab:await chrome.tabs.get(binding.sourceTabId)};
      const gesture=crypto.randomUUID();
      await handleDrag({type:'independent-pip:drag-start',nonce:binding.nonce,gesture},sender);
      const rejected=[];
      for(const patch of [{nonce:crypto.randomUUID()},{dx:Infinity},{dx:40000},{sequence:0}]) {
        try {await handleDrag({type:'independent-pip:drag-move',nonce:binding.nonce,gesture,sequence:1,dx:10,dy:10,...patch},sender);rejected.push(false)} catch {rejected.push(true)}
      }
      const active=(await chrome.storage.session.get(key))[key];
      await chrome.storage.session.set({[key]:{...active,windowId:binding.sourceWindowId}});
      try {await handleDrag({type:'independent-pip:drag-move',nonce:binding.nonce,gesture,sequence:1,dx:10,dy:10},sender);rejected.push(false)} catch {rejected.push(true)}
      await chrome.storage.session.set({[key]:active});
      return rejected;
    })()''')
    self.assertTrue(all(checks),checks)
    self.assertEqual(rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result'],native)
    evaluate(self.page,'documentPictureInPicture.window.close()')
    wait_for(worker,'chrome.storage.session.get(null).then(data=>Object.keys(data).every(key=>!key.startsWith("pipWindow:")))')
    self.activate()
    wait_for(self.page,'documentPictureInPicture.window?.document.body.dataset.dragAvailable==="true"')
    self.assertFalse(evaluate(self.page,'originalNode.paused'))
V12Tests.test_36_drag_safety_closed_binding_and_reopen=test_drag_safety_closed_binding_and_reopen

def test_drag_survives_actual_worker_restart(self):
    import subprocess,time
    self.activate()
    wait_for(self.page,'documentPictureInPicture.window?.document.body.dataset.dragAvailable==="true"')
    worker=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type']=='service_worker' and self.extension_id in t['url'])
    payload={'ws':self.page['webSocketDebuggerUrl'],'collectEvents':True,'commands':[{'method':'ServiceWorker.enable'},{'method':'Runtime.evaluate','params':{'expression':'new Promise(resolve=>setTimeout(resolve,250))','awaitPromise':True}}]}
    result=json.loads(subprocess.run(['node',str(ROOT/'tools/cdp.mjs')],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,check=True,timeout=30).stdout)
    self.assertTrue(all(item['ok'] for item in result['results']),result['results'])
    versions=[v for e in result['events'] if e.get('method')=='ServiceWorker.workerVersionUpdated' for v in e['params']['versions'] if v.get('scriptURL')==worker['url']]
    self.assertTrue(versions,'No extension worker version discovered')
    stopped=rpc(self.page['webSocketDebuggerUrl'],[{'method':'ServiceWorker.enable'},{'method':'ServiceWorker.stopWorker','params':{'versionId':versions[-1]['versionId']}}])[-1]
    self.assertTrue(stopped['ok'],stopped)
    deadline=time.monotonic()+5
    while any(t['id']==worker['id'] for t in fetch(f'http://127.0.0.1:{PORT}/json/list')) and time.monotonic()<deadline:
        time.sleep(.1)
    self.assertFalse(any(t['id']==worker['id'] for t in fetch(f'http://127.0.0.1:{PORT}/json/list')))
    pip=self.pip_target()
    before=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']['bounds']
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mousePressed','x':160,'y':100,'button':'left','buttons':1,'clickCount':1}},{'method':'Input.dispatchMouseEvent','params':{'type':'mouseMoved','x':190,'y':120,'button':'left','buttons':1}}])
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        after=rpc(self.browser,[{'method':'Browser.getWindowForTarget','params':{'targetId':pip['id']}}])[0]['result']['bounds']
        if after['left']==before['left']+30:break
        time.sleep(.1)
    self.assertEqual(after['left'],before['left']+30,after)
    self.assertEqual(after['top'],before['top']+20,after)
    rpc(pip['webSocketDebuggerUrl'],[{'method':'Input.dispatchMouseEvent','params':{'type':'mouseReleased','x':160,'y':100,'button':'left','clickCount':1}}])
    new_worker=next(t for t in fetch(f'http://127.0.0.1:{PORT}/json/list') if t['type']=='service_worker' and self.extension_id in t['url'])
    self.assertNotEqual(new_worker['id'],worker['id'])
    self.assertFalse(evaluate(self.page,'originalNode.paused'))
    print('REAL_WORKER_RESTART',json.dumps({'old':worker['id'],'new':new_worker['id'],'moved':True}))
V12Tests.test_37_drag_survives_actual_worker_restart=test_drag_survives_actual_worker_restart

def test_mute_restores_last_volume_after_zero_slider(self):
    self.activate()
    wait_for(self.page,'Boolean(documentPictureInPicture.window?.document.querySelector("#pip-volume"))')
    pip=self.pip_target()
    evaluate(self.page,'originalNode.volume=.38;originalNode.muted=false')
    wait_for(pip,'document.querySelector("#pip-volume").value==="0.38"')
    evaluate(pip,'document.querySelector("#pip-volume").value="0";document.querySelector("#pip-volume").dispatchEvent(new Event("input",{bubbles:true}))')
    self.click_control('pip-mute')
    self.assertFalse(evaluate(self.page,'originalNode.muted'))
    self.assertAlmostEqual(evaluate(self.page,'originalNode.volume'),.38)
V12Tests.test_38_mute_restores_last_volume_after_zero_slider=test_mute_restores_last_volume_after_zero_slider

if __name__=='__main__':
    unittest.main(verbosity=2)
