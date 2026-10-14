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
from package_sources import verify_sources


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
        source_archive = verify_sources(artifact)
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
            with zipfile.ZipFile(artifact.parent/source_archive['file']) as sources:
                assert sources.testzip() is None
                prefix = source_archive.get('prefix', '')
                assert prefix+'upstream/pymupdf-1.26.7.tar.gz' in sources.namelist()
                assert prefix+'texastra/engine/patch.py' in sources.namelist()
            project = location/'project'
            shutil.copytree(ROOT/'examples/demo', project)
            # The CV crash was caused by indexing an unrelated legacy-encoded
            # draft before compiling the valid UTF-8 root. Exercise that exact
            # project shape with the backend extracted from each release VSIX.
            legacy = b'% Unrelated legacy draft\n\xff\n'
            (project/'unrelated-legacy.tex').write_bytes(legacy)
            original_files = {p.relative_to(project): p.read_bytes()
                              for p in project.rglob('*') if p.is_file()}
            source = (project/'main.tex').read_text(encoding='utf-8')
            checks = []
            with Client(project, runtime=runtime, assets=extension/'texastra') as live:
                initial = live.request(type='start', page=0)
                assert initial.get('ok') and initial['pageCount'] == 1, initial.get('error')
                assert initial['regionRows'], 'UTF-8 root has no source mapping'
                checks.append({'unrelatedLegacyEncoding': True, 'rootSourceMapped': True})
                print(platform, 'unrelated legacy-encoded TeX file does not block preview', flush=True)
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
            assert original_files == {p.relative_to(project): p.read_bytes()
                                      for p in project.rglob('*') if p.is_file()}
            checks.append({'projectFilesUnchanged': True})
            if platform.startswith('darwin-'):
                from check_posix_runtime import check
                checks.append(check(runtime, extension/'texastra'))
                assert (runtime/'texastra-pdftex').is_file(), 'Missing bundled pdfTeX'
                assert (runtime/'pdfTeX-COPYING').is_file(), 'Missing pdfTeX license'
                pdftex = json.loads((runtime/'pdftex-build.json').read_text())
                assert pdftex['engineSha256'] == hashlib.sha256((runtime/'texastra-pdftex').read_bytes()).hexdigest()
                with zipfile.ZipFile(artifact.parent/source_archive['file']) as sources:
                    assert 'texastra/engine/pdftex_state.c' in sources.namelist()
                    assert 'upstream/pdfTeX-COPYING' in sources.namelist()
                checks.append(check(runtime, extension/'texastra', 'pdflatex'))
            report['packages'].append({'platform': platform,
                'sourceArchive': source_archive, 'sizeBytes': artifact.stat().st_size,
                'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'checks': checks})
    (ROOT/('results/release-packages-'+args.target+'.json' if args.target else 'results/release-packages.json')).write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
