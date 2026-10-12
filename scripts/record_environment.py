from pathlib import Path
import argparse,hashlib,json,platform,subprocess
from importlib.metadata import version,PackageNotFoundError
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output',default='environment.json')
args=parser.parse_args()
def command(argv):
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    return p.stdout.strip()
report={'platform':platform.platform(),'python':platform.python_version(),
        'nativeLuaLaTeX':command(['lualatex','--version']).splitlines()[0],
        'wslLuaLaTeX':command(['wsl','-d','Ubuntu-22.04','--','lualatex','--version']).splitlines()[0],
        'wslXeLaTeX':command(['wsl','-d','Ubuntu-22.04','--','xelatex','--version']).splitlines()[0],
        'cpu':command(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json']),
        'memoryBytes':command(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory']),
        'sourceSha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['texastra','webview','extension','native'] for p in sorted((ROOT/folder).glob('*')) if p.is_file()}}
report['native']={'node':command(['node','--version']),
                  'compiler':command(['wsl','-d','Ubuntu-22.04','--exec','g++','--version']).splitlines()[0],
                  'mupdf':'1.26.12',
                  'runtimeSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'native/runtime').glob('*')) if p.is_file() and not p.name.endswith('.new') and not p.name.startswith('libmupdfcpp')}}
report['pythonPackages']={}
for name in ['PyMuPDF','Pillow','zlib-ng']:
    try:report['pythonPackages'][name]=version(name)
    except PackageNotFoundError:report['pythonPackages'][name]=None
(ROOT/'results'/args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Recorded environment and implementation hashes')
