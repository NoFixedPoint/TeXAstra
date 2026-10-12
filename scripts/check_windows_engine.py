"""Exercise real retained LuaHBTeX checkpoints on native Windows."""
import json
import msvcrt
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def environment():
    env = os.environ.copy()
    for name in ('TEXMFCNF', 'TEXMFROOT'):
        env[name] = subprocess.check_output(['kpsewhich', '--var-value=' + name], text=True).strip()
    return env


def main():
    runtime = ROOT / 'native/runtime/windows-x64'
    fixture = ROOT / '.work/native-engine-case'
    fixture.mkdir(parents=True, exist_ok=True)
    env = environment()
    env.update(BAKO_PAGE_STREAM='1', BAKO_FONT_STREAM='1', BAKO_SOURCE_MARKERS='1',
               BAKO_LIVE_DOCUMENT='1', BAKO_ENGINE_MODULE=(runtime / 'texastra-engine.dll').as_posix())
    for name in ('snapshot.lua', 'inputs.lua', 'provenance.lua', 'page_stream.lua'):
        shutil.copyfile(ROOT / 'texastra' / name, fixture / name)
    original = r'''\documentclass{article}
\begin{document}
First page $x^2$.
\newpage
Second page $\frac{a}{b}$.
\newpage
Third page retained.
\end{document}
'''
    (fixture / 'paper.tex').write_text(original, encoding='utf-8', newline='\n')
    (fixture / 'bako-sources.tsv').write_text('1\t' + (fixture / 'paper.tex').as_posix() + '\n')
    (fixture / 'bako-driver.tex').write_text(
        "\\directlua{dofile('inputs.lua')}%\n"
        "\\AtBeginDocument{\\directlua{dofile('provenance.lua');dofile('snapshot.lua');bako_live_begin()}}%\n"
        "\\AtEndDocument{\\directlua{bako_live_end()}}%\n"
        "\\input{paper.tex}\n")
    for name in ('completed.json', 'failed.json'):
        (fixture / name).unlink(missing_ok=True)
    command_read, command_write = os.pipe()
    event_read, event_write = os.pipe()
    os.set_inheritable(command_read, True)
    os.set_inheritable(event_write, True)
    env['BAKO_COMMAND_HANDLE'] = str(msvcrt.get_osfhandle(command_read))
    env['BAKO_EVENT_HANDLE'] = str(msvcrt.get_osfhandle(event_write))
    report = json.loads(subprocess.check_output([str(runtime / 'texastra-backend.exe'), '--environment'], encoding='utf-8'))
    format_path = Path(report['format'])
    log = (fixture / 'engine-output.log').open('wb')
    process = subprocess.Popen([str(runtime / 'texastra-backend.exe'), '--compiler-worker', '--fmt=' + format_path.as_posix(),
                                '--progname=lualatex', '--shell-escape', '--interaction=nonstopmode',
                                '--halt-on-error', '--recorder', '--jobname=main', 'bako-driver.tex'],
                               cwd=fixture, env=env, stdout=log, stderr=subprocess.STDOUT, close_fds=False)
    os.close(command_read)
    os.close(event_write)
    frames = queue.Queue()

    def receive():
        def exact(size):
            data = b''
            while len(data) < size:
                chunk = os.read(event_read, size - len(data))
                if not chunk:
                    raise EOFError('Native compiler closed its event pipe')
                data += chunk
            return data
        try:
            while True:
                line = b''
                while not line.endswith(b'\n'):
                    line += exact(1)
                meta_size, data_size = map(int, line.split())
                frames.put((json.loads(exact(meta_size)), exact(data_size)))
        except Exception as error:
            frames.put(error)
    reader = threading.Thread(target=receive, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 60
        while not (fixture / 'completed.json').exists():
            if process.poll() is not None or (fixture / 'failed.json').exists() or time.monotonic() > deadline:
                raise RuntimeError((fixture / 'engine-output.log').read_text(errors='replace')[-5000:])
            time.sleep(.02)
        checkpoints = sorted(fixture.glob('cp-*.meta'))
        print('Native engine compiled; checkpoints:', [p.name for p in checkpoints], flush=True)
        assert len(checkpoints) >= 3
        # Resume from page two after changing only text not yet consumed there.
        changed = original.replace('Second page', 'Edited page')
        (fixture / 'paper.tex').write_text(changed, encoding='utf-8', newline='\n')
        (fixture / 'completed.json').unlink(missing_ok=True)
        os.write(command_write, b'restore 2 2\n')
        result = frames.get(timeout=30)
        if isinstance(result, Exception):
            raise result
        metadata, drawing = result
        assert metadata['snapshot']['mode'] == 'windows'
        assert metadata['snapshot']['pid'] == process.pid
        assert drawing and metadata['pages'][0]['page'] == 1
        print(json.dumps({'ok': True, 'compilerPid': process.pid, 'metadata': metadata,
                          'pageBytes': len(drawing)}, indent=2), flush=True)
    finally:
        process.terminate()
        process.wait(timeout=5)
        os.close(command_write)
        reader.join(timeout=5)
        os.close(event_read)
        log.close()


if __name__ == '__main__':
    main()
