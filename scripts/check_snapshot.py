from pathlib import Path
import json,sys,time,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prototype.snapshot import SnapshotEngine
from prototype.engine import ROOT

report={'candidate':'LuaTeX POSIX input-boundary checkpoints','updates':[]}
def brief(result):return {k:v for k,v in result.items() if k not in {'image','regions','characters','warnings'}}
with SnapshotEngine() as engine:
    print('session',engine.directory,flush=True)
    result=engine.start();report['startup']=brief(result);print('startup',brief(result),flush=True)
    if result['ok']:
        for page in [99,49,0]:
            file=f'pages/page-{page+1:03d}.tex'
            source=(ROOT/'corpus'/file).read_text(encoding='utf-8')
            for edit in range(3):
                modified=source.replace('word: alpha.','word: omega.' if edit%2==0 else 'word: alpha.')
                result=engine.update(file,modified,page)
                report['updates'].append(dict(case=f'text-{page+1}',**brief(result)))
                print('update',brief(result),flush=True)
                if not result['ok']:break
            if not result['ok']:break
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/snapshot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
