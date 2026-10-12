"""Record real source edits in the shared browser viewer and export a GIF."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-mode', choices=['native', 'wsl'], default='wsl')
    parser.add_argument('--output', type=Path, default=ROOT/'assets/demo.gif')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT/'.work').mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='recording-', dir=ROOT/'.work'))
    project = work/'project'
    shutil.copytree(ROOT/'examples/demo', project)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    log = (work/'server.log').open('w', encoding='utf-8')
    server = subprocess.Popen(['node', str(ROOT/'native/demo.js'), '--project', str(project),
                               '--main', 'main.tex', '--runtime-mode', args.runtime_mode,
                               '--port', str(port)], cwd=ROOT, stdout=log, stderr=log)
    checks = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1200, 'height': 820},
                                          record_video_dir=str(work/'video'),
                                          record_video_size={'width': 1200, 'height': 820})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for attempt in range(50):
                try:
                    page.goto(url)
                    break
                except Exception:
                    if attempt == 49:
                        raise
                    time.sleep(.1)
            page.wait_for_function('window.lastPaint && !stale && frame.pageCount===1', timeout=120000)
            recording_start = page.evaluate('performance.now()')/1000
            page.wait_for_timeout(1200)

            def edit(old, new, label):
                source = page.locator('#source')
                source.evaluate('''(e,old)=>{
                    const start=e.value.indexOf(old);
                    if(start<0)throw Error('Demo text missing');
                    e.focus();e.setSelectionRange(start,start+old.length);
                    const line=e.value.slice(0,start).split('\\n').length;
                    e.scrollTop=Math.max(0,(line-7)*parseFloat(getComputedStyle(e).lineHeight));
                }''', old)
                page.wait_for_timeout(700)
                page.keyboard.type(new, delay=90)
                page.wait_for_function('window.lastPaint && !stale && lastPaint.clientId===latestClient', timeout=60000)
                checks.append({'edit': label, 'source': new, 'rendered': True})
                page.screenshot(path=str(work/(label+'.png')))
                page.wait_for_timeout(1700)

            edit('The result is clear.', 'The result is beautiful.', 'text')
            edit('{Source};', '{Ideas};', 'tikz')
            edit('width=0.70', 'width=0.95', 'figure')
            edit('TeXAstra & 95', 'TeXAstra & 99', 'table')
            assert not errors, errors
            page.wait_for_timeout(1000)
            video = page.video.path()
            context.close()
            browser.close()
        # Preserve the real elapsed edit/compile time; trim only initial startup.
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-ss', str(recording_start), '-i', str(video),
                        '-filter_complex', 'fps=10,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3',
                        '-loop', '0', str(args.output)], check=True)
        (work/'checks.json').write_text(json.dumps(checks, indent=2)+'\n')
        print(json.dumps({'gif': str(args.output), 'bytes': args.output.stat().st_size,
                          'capture': str(work), 'checks': checks}, indent=2))
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(url+'/action', data=b'{"type":"close"}',
                headers={'Content-Type': 'application/json'}), timeout=5).close()
        except Exception:
            pass
        server.terminate()
        server.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    main()
