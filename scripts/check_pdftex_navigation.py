"""Character navigation must work without the optional external SyncTeX tool."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from cpp_client import Client, ROOT, linux


def main():
    if os.name == 'nt':
        subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--exec', 'python3',
                        linux(Path(__file__))], check=True)
        return
    with tempfile.TemporaryDirectory(prefix='pdftex-navigation-') as folder:
        project = Path(folder)/'project'
        tools = Path(folder)/'bin'
        project.mkdir()
        tools.mkdir()
        for name in ['kpsewhich', 'pdflatex', 'lualatex', 'bibtex', 'biber', 'makeindex']:
            executable = shutil.which(name)
            if executable:
                (tools/name).symlink_to(Path(executable).resolve())
        source = '\\documentclass{article}\n\\begin{document}\nZebra Zebra\n\\end{document}\n'
        (project/'main.tex').write_text(source)
        offset = source.rindex('Zebra')+2
        with Client(project, compiler='pdflatex', preview_mode='full', tex_bin=tools) as client:
            frame = client.request(type='start', page=0)
            assert frame.get('sourceSync') == 'token-and-macro-origin', frame.get('error')
            response = client.request(type='sync-forward', file='main.tex', line=2, column=8, page=0)
            assert response.get('ok') and response.get('location'), response
            location = response['location']
            assert location['start'] == offset and location['end'] == offset+1, location
            rect = location['rect']
            reverse = client.request(type='sync-backward', page=0,
                                     x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2)
            assert reverse.get('ok') and reverse.get('location', {}).get('start') == offset, reverse
    report = {'ok': True, 'checks': ['forward character sync without synctex',
                                    'reverse character sync without synctex']}
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/pdftex-navigation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
