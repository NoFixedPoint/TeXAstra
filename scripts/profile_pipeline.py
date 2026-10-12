"""Direct compiler/render timing loop, without browser scheduling or convergence."""
import argparse,gc,json,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from texastra.snapshot import SnapshotEngine
from texastra.engine import ROOT

parser=argparse.ArgumentParser()
parser.add_argument('--output',default='pipeline-profile.json')
parser.add_argument('--repeats',type=int,default=6)
args=parser.parse_args()
samples=[]
gc_start={};gc_pauses=[]
def gc_timing(phase,info):
    generation=info['generation']
    if phase=='start':gc_start[generation]=time.perf_counter()
    else:gc_pauses.append((time.perf_counter()-gc_start[generation])*1000)
gc.callbacks.append(gc_timing)
with SnapshotEngine(output='stream') as engine:
    assert engine.start()['ok']
    for page in [100,50,1]:
        file=f'pages/page-{page:03d}.tex'
        original=(ROOT/'corpus'/file).read_text(encoding='utf-8')
        for i in range(args.repeats):
            gc_pauses.clear()
            source=original.replace('word: alpha.','word: omega.') if i%2==0 else original
            result=engine.update(file,source,page-1)
            assert result['ok'],result
            sample={k:v for k,v in result.items() if k.endswith('Ms')}
            sample['gcMs']=sum(gc_pauses)
            sample['page']=page;samples.append(sample)
            print(json.dumps(sample),flush=True)
gc.callbacks.remove(gc_timing)
report={'samples':samples,'means':{}}
for key,value in samples[0].items():
    if isinstance(value,dict):report['means'][key]={k:statistics.mean(s[key][k] for s in samples) for k in value}
    elif key.endswith('Ms'):report['means'][key]=statistics.mean(s[key] for s in samples)
(ROOT/'results'/args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report['means'],indent=2))
