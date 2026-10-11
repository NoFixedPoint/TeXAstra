"""Test-only JSON client; production uses the Node/VS Code launchers directly."""
import json,os,queue,subprocess,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def linux(path):return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:] if os.name=='nt' else str(path)
class Client:
    def __init__(self,project=ROOT/'corpus'):
        prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
        self.process=subprocess.Popen(prefix+[linux(ROOT/'native/runtime/bakoma-backend'),'--project',linux(project),'--assets',linux(ROOT/'prototype'),'--sync'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
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
