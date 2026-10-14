"""Run real-browser checks and retain machine-readable execution output."""
import contextlib
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))
import test_extension
import test_v12
from browser_lab import ensure_owned, fetch, rpc, RUNTIME


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'id': test.id(), 'status': 'passed'})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.records.append({'id': test.id(), 'status': 'failed', 'error': self._exc_info_to_string(error, test)})

    def addError(self, test, error):
        super().addError(test, error)
        self.records.append({'id': test.id(), 'status': 'error', 'error': self._exc_info_to_string(error, test)})


def main():
    ensure_owned('chrome')
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    syntax = []
    for file in sorted((ROOT / 'extension').glob('*.js')):
        result = subprocess.run(['node', '--check', str(file)], text=True, encoding='utf-8', capture_output=True)
        syntax.append({'file': file.name, 'returncode': result.returncode, 'output': result.stdout + result.stderr})
    manifest = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))
    assert manifest['permissions'] == ['activeTab', 'scripting', 'storage']
    assert 'host_permissions' not in manifest and 'content_scripts' not in manifest
    patterns = {'external_network': r'\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(', 'dynamic_execution': r'\beval\s*\(|new\s+Function\s*\(', 'unsafe_html': r'\binnerHTML\s*=', 'secret_literal': r'(?i)(?:password|api_key|secret)\s*[:=]\s*[\"\'][^\"\']{6,}'}
    findings = []
    for file in sorted((ROOT / 'extension').glob('*.js')):
        text = file.read_text(encoding='utf-8')
        for name, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                findings.append({'file': file.name, 'rule': name, 'offset': match.start()})
    output = io.StringIO()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(test_extension.ExtensionTests), unittest.defaultTestLoader.loadTestsFromTestCase(test_v12.V12Tests)])
    expected_count = suite.countTestCases()
    with contextlib.redirect_stdout(output):
        result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordedResult).run(suite)
    log = output.getvalue()
    (reports / 'test-run.log').write_text(log, encoding='utf-8')
    browser = fetch('http://127.0.0.1:9233/json/version')
    installed = rpc(browser['webSocketDebuggerUrl'], [{'method': 'Extensions.getExtensions'}])[0]
    state = json.loads((RUNTIME / 'chrome.json').read_text(encoding='utf-8'))
    code_hashes = {str(file.relative_to(ROOT / 'extension')).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted((ROOT / 'extension').rglob('*')) if file.is_file()}
    success = result.wasSuccessful() and result.testsRun == expected_count and len(result.records) == expected_count and not findings and all(item['returncode'] == 0 for item in syntax)
    report = {'generated_at': datetime.datetime.now().astimezone().isoformat(), 'passed': success, 'browser': browser['Browser'], 'headless': '--headless=new' in state['args'], 'expected_test_count': expected_count, 'tests_run': result.testsRun, 'tests': result.records, 'syntax_checks': syntax, 'static_security_findings': findings, 'manifest_permissions': manifest['permissions'], 'installed_extensions_readback': installed, 'tested_code_sha256': code_hashes, 'manual_unverified': ['Visible Windows physical-mouse dragging / visual smoothness and topmost over other applications (native windows.update separately verified in hidden headed Chrome)', 'Global OS shortcut assignment', 'Real DRM services', 'Site-specific custom captions and all production video sites', 'Full native Yandex browser.dll decompilation and compositor trace'], 'independent_review': 'This execution report covers browser tests and local static checks only; independent pre-commit review is recorded separately.'}
    (reports / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(log)
    print(json.dumps({'passed': success, 'tests_run': result.testsRun, 'expected': expected_count, 'static_findings': findings, 'report': str(reports / 'verification.json')}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
