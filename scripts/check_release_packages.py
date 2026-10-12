"""Compile and edit the demo using the runtimes extracted from release VSIX files."""
import argparse
import sys
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import fitz
from cpp_client import Client, ROOT


def pixels(frame):
    assert frame.get('ok'), frame.get('error')
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['darwin-arm64', 'darwin-x64'])
    args = parser.parse_args()
    version = json.loads((ROOT/'package.json').read_text())['version']
    (ROOT/'.work').mkdir(exist_ok=True)
    (ROOT/'results').mkdir(exist_ok=True)
    report = {'version': version, 'packages': []}
    packages = [(args.target, f'texastra-{version}-{args.target}.vsix')] if args.target else [
        ('wsl', f'texastra-{version}.vsix'), ('windows-x64', f'texastra-{version}-win32-x64.vsix')]
    for platform, filename in packages:
        artifact = ROOT/'artifacts'/filename
        with tempfile.TemporaryDirectory(prefix='release check ', dir=ROOT/'.work') as folder:
            location = Path(folder)
            with zipfile.ZipFile(artifact) as archive:
                assert archive.testzip() is None
                archive.extractall(location)
                if sys.platform != 'win32':
                    for item in archive.infolist():
                        if item.external_attr >> 16 & 0o111:
                            (location/item.filename).chmod(0o755)
            extension = location/'extension'
            manifest = json.loads((extension/'package.json').read_text())
            assert manifest['version'] == version
            mode = manifest['contributes']['configuration']['properties']['texastra.runtimeMode']['default']
            assert mode == ('native' if platform != 'wsl' else 'wsl')
            runtime = extension/'native/runtime'
            if platform == 'windows-x64':
                runtime /= 'windows-x64'
                os.environ['BAKO_CHECKPOINT_MODE'] = 'windows'
            else:
                os.environ.pop('BAKO_CHECKPOINT_MODE', None)
            assert (runtime/'sources/AGPL-3.0.txt').stat().st_size > 30000
            assert (runtime/'sources/pymupdf-1.26.7.tar.gz').is_file()
            project = location/'project'
            shutil.copytree(ROOT/'examples/demo', project)
            source = (project/'main.tex').read_text(encoding='utf-8')
            checks = []
            with Client(project, runtime=runtime, assets=extension/'texastra') as live:
                initial = live.request(type='start', page=0)
                assert initial.get('ok') and initial['pageCount'] == 1, initial.get('error')
                previous = pixels(initial)
                for label, before, after in [
                    ('text', 'The result is clear.', 'The result is beautiful.'),
                    ('tikz', '{Source};', '{Ideas};'),
                    ('figure', 'width=0.70', 'width=0.95'),
                    ('table', 'TeXAstra & 95', 'TeXAstra & 99'),
                ]:
                    assert before in source
                    source = source.replace(before, after)
                    actual = live.request(type='edit', file='main.tex', source=source, page=0)
                    rendered = pixels(actual)
                    assert rendered != previous, label+' did not change the rendered page'
                    assert actual['regionRows'], label+' has no source mapping'
                    with Client(project, runtime=runtime, assets=extension/'texastra') as fresh:
                        expected = fresh.request(type='start', page=0, overlays={'main.tex': source})
                        assert rendered == pixels(expected), label+' differs from a full compile'
                    previous = rendered
                    checks.append({'edit': label, 'matchesFullBuild': True})
                    print(platform, label, 'matches complete compile', flush=True)
            report['packages'].append({'platform': platform,
                'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'checks': checks})
    (ROOT/('results/release-packages-'+args.target+'.json' if args.target else 'results/release-packages.json')).write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
