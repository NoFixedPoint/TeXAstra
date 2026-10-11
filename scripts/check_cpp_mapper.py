"""Differentially check the C++ mapper against the established Python reference."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from prototype.instrument import Instrumenter
def linux(path):return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:] if os.name=='nt' else str(path)
prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime');args=parser.parse_args()
p=subprocess.Popen(prefix+[linux(args.runtime.resolve()/'bakoma-backend'),'--instrument'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
mapper=Instrumenter();count=0
cases=[(f.relative_to(ROOT/'corpus').as_posix(),f.read_text(encoding='utf-8')) for f in sorted((ROOT/'corpus/pages').glob('*.tex'))]
cases.extend([
    ('cases/unicode.tex','ABC 😀 é e\u0301 中文\n$x+\\frac{a}{b_2}$'),
    ('cases/macros.tex',r'\unknown[opt]{raw} \section*{A} $\sqrt[3]{x}+\left(\pair{z}\right)$ % comment'+'\n'),
    ('cases/crlf.tex','first\r\n中文 $x$\r\nlast'),
    ('pages/page-050.tex',cases[49][1].replace('alpha.','omega.')),
])
try:
    for file,source in cases:
        expected=mapper.instrument(source,file)
        p.stdin.write(json.dumps(dict(file=file,source=source))+'\n');p.stdin.flush()
        actual=json.loads(p.stdout.readline())
        if actual['source']!=expected:
            import difflib
            print(''.join(difflib.unified_diff(expected.splitlines(True),actual['source'].splitlines(True))))
            raise AssertionError('Instrumented source differs: '+file)
        spans={str(k):v for k,v in mapper.spans.items() if v['file']==file}
        assert actual['spans']==spans,('Source spans differ',file)
        count+=1
finally:
    p.stdin.close();p.wait(timeout=10)
assert p.returncode==0
(ROOT/'results/cpp-mapper.json').write_text(json.dumps({'checks':count,'ok':True},indent=2))
print('Passed',count,'source and Unicode mapping comparisons')
