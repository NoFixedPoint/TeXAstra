"""Test-only JSON client; production uses the Node/VS Code launchers directly."""
import json,os,queue,subprocess,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def linux(path):
    path=path.resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:] if os.name=='nt' else str(path)
class Client:
    def __init__(self,project=ROOT/'corpus',runtime=None,main='main.tex',preview_mode='auto',compiler='lualatex',sync=True,environment=None,tex_bin=None):
        prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
        mode=['env','BAKO_CHECKPOINT_MODE='+os.environ['BAKO_CHECKPOINT_MODE']] if 'BAKO_CHECKPOINT_MODE' in os.environ else []
        if environment:
            mode = ['env']+mode[1:] if mode else ['env']
            mode += [key+'='+value for key,value in environment.items()]
        executable=(runtime or ROOT/'native/runtime')/'bakoma-backend'
        self.process=subprocess.Popen(prefix+mode+[linux(executable),'--project',linux(project),'--assets',linux(ROOT/'prototype'),'--main',main,'--preview-mode',preview_mode,'--compiler',compiler]+(['--sync'] if sync else [])+(['--tex-bin',str(tex_bin)] if tex_bin else []),stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
        self.responses=queue.Queue()
        def read():
            for line in self.process.stdout:self.responses.put(json.loads(line))
            self.responses.put({'ok':False,'error':'Native process ended'})
        threading.Thread(target=read,daemon=True).start()
    def request(self,**message):
        self.process.stdin.write(json.dumps(message,ensure_ascii=False)+'\n');self.process.stdin.flush()
        return self.responses.get(timeout=120)
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"type":"close"}\n');self.process.stdin.close();self.process.wait(timeout=15)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
