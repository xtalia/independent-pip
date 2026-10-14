"""Launch only owned isolated browsers; never attach to user profiles."""
import argparse
import errno
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import os

ROOT = Path(__file__).resolve().parents[1]
# Native Windows subprocesses may inherit the system TMPDIR instead of Hermes
# scratch. Keep this isolated lab explicitly inside the managed scratch tree.
SCRATCH = (Path(os.environ['LOCALAPPDATA']) / 'hermes/cache/scratch') if os.name == 'nt' else Path(os.environ['TMPDIR'])
RUNTIME = SCRATCH / 'yandex-pip-lab'
BINARIES = {'yandex': 'C:/Program Files/Yandex/YandexBrowser/Application/browser.exe', 'chrome': 'C:/Program Files/Google/Chrome/Application/chrome.exe'}
PORTS = {'yandex': 9232, 'chrome': 9233}
# Preserve launch handles during an owning verification process. Browser lifecycle
# is controlled through loopback CDP; its PID/profile are also recorded on disk.
OWNED_PROCESSES = []


def fetch(url):
    with urllib.request.urlopen(url, timeout=4) as r:
        return json.load(r)


def rpc(ws, commands):
    result = subprocess.run(['node', str(ROOT / 'tools/cdp.mjs')], input=json.dumps({'ws': ws, 'commands': commands}), text=True, encoding='utf-8', capture_output=True, timeout=60, check=True)
    data = json.loads(result.stdout)
    if data.get('error'):
        raise RuntimeError(data['error'])
    return data['results']


def _profile_argument(arguments):
    return next((arg.split('=', 1)[1] for arg in arguments if arg.startswith('--user-data-dir=')), None)


def _same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _validate_owned(kind, version, state):
    port = PORTS[kind]
    endpoint = version.get('webSocketDebuggerUrl')
    if not endpoint or endpoint != state.get('webSocketDebuggerUrl'):
        raise RuntimeError(f'{kind} CDP endpoint ownership mismatch')
    expected_profile = RUNTIME / f'{kind}-profile'
    if not _same_path(str(expected_profile), str(_profile_argument(state.get('args', [])))):
        raise RuntimeError(f'{kind} managed profile ownership mismatch')
    try:
        response = rpc(endpoint, [{'method': 'Browser.getBrowserCommandLine'}])[0]
        live_args = response['result']['arguments'] if response.get('ok') else None
    except Exception as exc:
        raise RuntimeError(f'{kind} live browser ownership check failed: {exc}') from exc
    if not isinstance(live_args, list):
        raise RuntimeError(f'{kind} live browser ownership check failed')
    required = ('--enable-automation', f'--remote-debugging-port={port}', '--remote-debugging-address=127.0.0.1')
    if (not all(arg in live_args for arg in required)
            or not _same_path(str(expected_profile), str(_profile_argument(live_args)))):
        raise RuntimeError(f'{kind} live browser ownership mismatch')
    return version


def ensure_owned(kind):
    """Fail closed unless CDP still identifies the exact managed browser."""
    state_file = RUNTIME / f'{kind}.json'
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'{kind} ownership state is missing or invalid') from exc
    try:
        version = fetch(f'http://127.0.0.1:{PORTS[kind]}/json/version')
    except Exception as exc:
        raise RuntimeError(f'{kind} owned browser is unavailable') from exc
    return _validate_owned(kind, version, state)


def start(kind):
    port = PORTS[kind]
    try:
        fetch(f'http://127.0.0.1:{port}/json/version')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'{kind} debug port {port} is already occupied; refusing to attach') from exc
    except urllib.error.URLError as exc:
        if getattr(exc.reason, 'errno', None) != errno.ECONNREFUSED:
            raise RuntimeError(f'{kind} debug port {port} is already occupied; refusing to attach') from exc
    else:
        raise RuntimeError(f'{kind} debug port {port} is already occupied; refusing to attach')
    profile = RUNTIME / f'{kind}-profile'
    profile.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log = (RUNTIME / f'{kind}.log').open('ab')
    args = [BINARIES[kind], '--headless=new', '--enable-automation', f'--user-data-dir={profile}', f'--remote-debugging-port={port}', '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--window-size=1200,800', '--screen-info={1920x1080}', '--enable-unsafe-extension-debugging', 'about:blank']
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    OWNED_PROCESSES.append(process)
    log.close()
    for _ in range(50):
        try:
            version = fetch(f'http://127.0.0.1:{port}/json/version')
            state = {'pid': process.pid, 'args': args, 'port': port, 'webSocketDebuggerUrl': version.get('webSocketDebuggerUrl')}
            _validate_owned(kind, version, state)
            (RUNTIME / f'{kind}.json').write_text(json.dumps(state), encoding='utf-8')
            return version
        except urllib.error.URLError:
            if process.poll() is not None:
                raise RuntimeError(f'{kind} exited: {process.returncode}')
            time.sleep(0.2)
    raise RuntimeError(f'{kind} did not expose an owned CDP browser')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=BINARIES)
    args = parser.parse_args()
    print(json.dumps(start(args.kind), indent=2))
    print(json.dumps(fetch(f'http://127.0.0.1:{PORTS[args.kind]}/json/list'), indent=2))


if __name__ == '__main__':
    main()
