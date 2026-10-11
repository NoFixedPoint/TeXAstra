from pathlib import Path
import hashlib,json,platform,subprocess
ROOT=Path(__file__).resolve().parents[1]
def command(argv):
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    return p.stdout.strip()
report={'platform':platform.platform(),'python':platform.python_version(),
        'nativeLuaLaTeX':command(['lualatex','--version']).splitlines()[0],
        'wslLuaLaTeX':command(['wsl','-d','Ubuntu-22.04','--','lualatex','--version']).splitlines()[0],
        'wslXeLaTeX':command(['wsl','-d','Ubuntu-22.04','--','xelatex','--version']).splitlines()[0],
        'cpu':command(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json']),
        'memoryBytes':command(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory']),
        'sourceSha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['prototype','webview','extension'] for p in sorted((ROOT/folder).glob('*')) if p.is_file()}}
(ROOT/'results/environment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Recorded environment and implementation hashes')
