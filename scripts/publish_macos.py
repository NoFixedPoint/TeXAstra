"""Replace macOS assets only after a pinned native validation run succeeds."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from collect_compatible_release import rebind
from package_sources import sha256, verify_sources

ROOT = Path(__file__).resolve().parents[1]


def gh(*args):
    return subprocess.check_output(['gh', *args], cwd=ROOT, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run = json.loads(gh('run', 'view', args.run, '--json', 'status,conclusion,headSha,workflowName'))
    assert run['status'] == 'completed' and run['conclusion'] == 'success', run
    assert run['headSha'] == args.commit and run['workflowName'] == 'macOS distribution', run
    version = json.loads((ROOT/'package.json').read_text())['version']
    tag = 'v'+version
    before = json.loads(gh('release', 'view', tag, '--json', 'assets,body,url'))
    old = {item['name']: item for item in before['assets']}
    sums = {name: item['digest'].removeprefix('sha256:') for name, item in old.items()
            if name.endswith(('.vsix', '.zip'))}
    (ROOT/'.work').mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='publish-macos-', dir=ROOT/'.work'))
    output = work/'ready'
    output.mkdir()
    report = {'version': version, 'run': args.run, 'commit': args.commit, 'packages': []}
    for arch in ('arm64', 'x64'):
        target = 'darwin-'+arch
        folder = work/target
        gh('run', 'download', args.run, '--name', 'texastra-'+target, '--dir', str(folder))
        vsix = folder/('texastra-macos-'+arch+'.vsix')
        tested = json.loads((folder/'validation'/f'release-packages-{target}.json').read_text())
        setup = json.loads((folder/'validation/macos-setup-native.json').read_text())
        assert tested['version'] == version
        assert tested['packages'][0]['sha256'] == sha256(vsix)
        assert setup['native'] and setup['platform'] == 'darwin' and setup['ok']
        for engine in ('lualatex', 'pdflatex'):
            assert any(engine+' compiles' in check for check in setup['checks'])
        metadata = verify_sources(vsix)
        assert metadata['target'] == target and metadata['version'] == version
        with zipfile.ZipFile(vsix) as package:
            for name in ('extension/extension.js', 'extension/macos-tex.js', 'README.md'):
                key = 'extension/'+name
                if name == 'README.md':
                    key = next(n for n in package.namelist() if n.lower() == 'extension/readme.md')
                expected = subprocess.check_output(['git', 'show', args.commit+':'+name], cwd=ROOT)
                assert package.read(key) == expected, name
        source = output/f'texastra-{target}-sources.zip'
        shutil.copyfile(folder/metadata['file'], source)
        published = output/vsix.name
        item = rebind(vsix, published, source)
        item['automaticSetup'] = setup
        report['packages'].append(item)
        for file in (published, source):
            assert file.name in old, 'Only replace existing macOS assets'
            sums[file.name] = sha256(file)
        (output/f'SHA256SUMS-{target}').write_text(''.join(
            sums[file.name]+'  '+file.name+'\n' for file in (published, source)), encoding='utf-8')
    (output/'SHA256SUMS').write_text(''.join(sums[name]+'  '+name+'\n' for name in sorted(sums)), encoding='utf-8')
    files = sorted(output.iterdir())
    if not args.dry_run:
        gh('release', 'upload', tag, *(str(file) for file in files), '--clobber')
        gh('release', 'edit', tag, '--notes-file', str(ROOT/'.github/release-notes.md'))
        after = json.loads(gh('release', 'view', tag, '--json', 'assets,body,url'))
        actual = {item['name']: item for item in after['assets']}
        assert actual.keys() == old.keys(), 'Unexpected release asset names'
        for name, item in actual.items():
            file = output/name
            expected = 'sha256:'+sha256(file) if file.is_file() else old[name]['digest']
            assert item['state'] == 'uploaded' and item['digest'] == expected, name
        assert after['body'].replace('\r\n', '\n') == (ROOT/'.github/release-notes.md').read_text()
        report.update(url=after['url'], allAssetDigestsVerified=True,
                      unchangedWindowsAndWslAssets=True,
                      assets=[{key: item[key] for key in ('name', 'digest', 'size')} for item in after['assets']])
    report['dryRun'] = args.dry_run
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/macos-publication.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
