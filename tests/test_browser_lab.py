"""Ownership checks must never accept arbitrary loopback CDP browsers."""
import errno
import http.client
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock

sys_path_root = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(sys_path_root / 'tools'))
import browser_lab


class BrowserOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)
        self.profile = self.runtime / 'chrome-profile'
        self.profile.mkdir()
        self.state_file = self.runtime / 'chrome.json'
        self.port = browser_lab.PORTS['chrome']
        self.endpoint = 'ws://127.0.0.1:9233/devtools/browser/managed'
        self.version = {'webSocketDebuggerUrl': self.endpoint, 'Browser': 'Chrome/test'}
        self.args = [
            '--enable-automation',
            f'--user-data-dir={self.profile}',
            f'--remote-debugging-port={self.port}',
            '--remote-debugging-address=127.0.0.1',
        ]
        self.state_file.write_text(json.dumps({
            'pid': 123, 'args': self.args, 'port': self.port,
            'webSocketDebuggerUrl': self.endpoint,
        }), encoding='utf-8')
        self.runtime_patch = mock.patch.object(browser_lab, 'RUNTIME', self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def test_preoccupied_port_is_refused_even_with_stale_state_file(self):
        with mock.patch.object(browser_lab, 'fetch', return_value=self.version):
            with self.assertRaisesRegex(RuntimeError, 'already occupied'):
                browser_lab.start('chrome')

    def test_http_response_from_preoccupied_port_is_not_treated_as_free(self):
        occupied = urllib.error.HTTPError('http://127.0.0.1:9233/json/version', 404, 'not found', {}, None)
        self.addCleanup(occupied.close)
        with mock.patch.object(browser_lab, 'fetch', side_effect=occupied), mock.patch.object(browser_lab.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'already occupied'):
                browser_lab.start('chrome')
        popen.assert_not_called()

    def test_owned_check_rejects_foreign_endpoint_even_if_profile_args_match(self):
        foreign = dict(self.version, webSocketDebuggerUrl='ws://127.0.0.1:9233/devtools/browser/foreign')
        with mock.patch.object(browser_lab, 'fetch', return_value=foreign), mock.patch.object(
            browser_lab, 'rpc', return_value=[{'ok': True, 'result': {'arguments': self.args}}]
        ):
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                browser_lab.ensure_owned('chrome')

    def test_owned_check_rejects_live_profile_or_debug_argument_mismatch(self):
        wrong_args = ['--enable-automation', '--user-data-dir=C:/unrelated', '--remote-debugging-port=9233', '--remote-debugging-address=127.0.0.1']
        with mock.patch.object(browser_lab, 'fetch', return_value=self.version), mock.patch.object(
            browser_lab, 'rpc', return_value=[{'ok': True, 'result': {'arguments': wrong_args}}]
        ):
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                browser_lab.ensure_owned('chrome')

    def test_missing_state_fails_closed(self):
        self.state_file.unlink()
        with mock.patch.object(browser_lab, 'fetch', return_value=self.version):
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                browser_lab.ensure_owned('chrome')

    def test_owned_check_accepts_exact_saved_endpoint_and_live_arguments(self):
        with mock.patch.object(browser_lab, 'fetch', return_value=self.version), mock.patch.object(
            browser_lab, 'rpc', return_value=[{'ok': True, 'result': {'arguments': self.args}}]
        ) as cdp:
            self.assertEqual(browser_lab.ensure_owned('chrome'), self.version)
        cdp.assert_called_once_with(self.endpoint, [{'method': 'Browser.getBrowserCommandLine'}])

    def test_non_refused_url_errors_are_treated_as_occupied(self):
        failures = (
            http.client.RemoteDisconnected('peer closed connection'),
            ConnectionResetError(errno.ECONNRESET, 'connection reset'),
            TimeoutError(errno.ETIMEDOUT, 'connection timed out'),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(browser_lab, 'fetch', side_effect=urllib.error.URLError(failure)), mock.patch.object(
                    browser_lab.subprocess, 'Popen'
                ) as popen:
                    with self.assertRaisesRegex(RuntimeError, 'already occupied'):
                        browser_lab.start('chrome')
                popen.assert_not_called()

    def test_start_launches_automation_and_persists_verified_endpoint(self):
        process = mock.Mock(pid=456)
        refused = ConnectionRefusedError(errno.ECONNREFUSED, 'connection refused')
        fetch = mock.Mock(side_effect=[urllib.error.URLError(refused), self.version])
        popen = mock.Mock(return_value=process)

        def live_command_line(endpoint, commands):
            return [{'ok': True, 'result': {'arguments': popen.call_args.args[0][1:]}}]

        with mock.patch.object(browser_lab, 'fetch', fetch), mock.patch.object(browser_lab.subprocess, 'Popen', popen), mock.patch.object(
            browser_lab, 'rpc', side_effect=live_command_line
        ):
            self.assertEqual(browser_lab.start('chrome'), self.version)

        launched = popen.call_args.args[0]
        self.assertIn('--enable-automation', launched)
        state = json.loads(self.state_file.read_text(encoding='utf-8'))
        self.assertEqual(state['webSocketDebuggerUrl'], self.endpoint)
        self.assertEqual(state['args'], launched)


if __name__ == '__main__':
    unittest.main(verbosity=2)
