"""Check source pairing, archive deduplication, and unchanged runtime payloads."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from package_sources import prepare_sources, verify_sources
from collect_compatible_release import combine_sources, rebind


class SourcePackagingTests(unittest.TestCase):
    def test_platform_packages_preserve_runtime_and_notices(self):
        for target in ('wsl', 'linux-x64', 'win32-x64', 'darwin-arm64', 'darwin-x64'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                stage = root/'stage'
                runtime = stage/'native/runtime'
                if target == 'win32-x64':
                    runtime /= 'windows-x64'
                materials = runtime/'sources'
                materials.mkdir(parents=True)
                payload = b'unchanged executable bytes'
                (runtime/'backend').write_bytes(payload)
                (materials/'GPL-3.0.txt').write_text('license notice')
                (materials/'upstream.tar.xz').write_bytes(b'complete upstream archive')
                (runtime/'upstream.tar.xz').write_bytes(b'complete upstream archive')
                (stage/'package.json').write_text(json.dumps({'version': '1.2.3'}))
                (stage/'build.py').write_text('# matching build recipe\n')
                metadata = prepare_sources(stage, runtime, root, '1.2.3', target)
                self.assertEqual((runtime/'backend').read_bytes(), payload)
                self.assertEqual((materials/'GPL-3.0.txt').read_text(), 'license notice')
                self.assertFalse(list(runtime.rglob('*.tar.xz')))
                self.assertIn(metadata['url'], (stage/'SOURCE.md').read_text())
                with zipfile.ZipFile(root/metadata['file']) as sources:
                    self.assertEqual(sources.testzip(), None)
                    self.assertEqual(sources.read('upstream/upstream.tar.xz'), b'complete upstream archive')
                    self.assertEqual(sources.read('texastra/build.py'), (stage/'build.py').read_bytes())
                    self.assertFalse(any('native/runtime' in name for name in sources.namelist()))
                vsix = root/'test.vsix'
                with zipfile.ZipFile(vsix, 'w') as archive:
                    for path in stage.rglob('*'):
                        if path.is_file():
                            archive.write(path, 'extension/'+path.relative_to(stage).as_posix())
                self.assertEqual(verify_sources(vsix), metadata)
                combined = root/'texastra-sources.zip'
                combine_sources([(target, vsix)], combined)
                rebound = root/'release.vsix'
                collected = rebind(vsix, rebound, combined, target+'/')
                self.assertTrue(collected['onlySourceReferencesChanged'])
                self.assertEqual(verify_sources(rebound)['prefix'], target+'/')
                with zipfile.ZipFile(rebound) as archive:
                    self.assertEqual(archive.read('extension/'+(runtime/'backend').relative_to(stage).as_posix()), payload)
                with zipfile.ZipFile(combined) as archive:
                    self.assertEqual(archive.read(target+'/upstream/upstream.tar.xz'), b'complete upstream archive')
                # A collector must never silently pair a rebuilt source kit with
                # binaries that refer to the previous source kit's checksum.
                (root/metadata['file']).write_bytes(b'replaced source kit')
                with self.assertRaisesRegex(RuntimeError, 'Missing or modified'):
                    verify_sources(vsix)
                (root/metadata['file']).unlink()
                with self.assertRaisesRegex(RuntimeError, 'Missing or modified'):
                    verify_sources(vsix)

    def test_root_archives_cannot_be_dropped_without_matching_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root/'stage/native/runtime'
            (runtime/'sources').mkdir(parents=True)
            original = runtime/'engine.tar.xz'
            original.write_bytes(b'original source')
            for replacement in (None, b'different source'):
                if replacement is not None:
                    (runtime/'sources/engine.tar.xz').write_bytes(replacement)
                with self.assertRaisesRegex(RuntimeError, 'Missing or mismatched'):
                    prepare_sources(root/'stage', runtime, root, '1.2.3', 'wsl')
                self.assertEqual(original.read_bytes(), b'original source')


if __name__ == '__main__':
    unittest.main()
