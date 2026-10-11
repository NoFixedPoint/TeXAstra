"""Build the Linux C++ backend; Windows invokes the existing WSL toolchain.

Pinned MuPDF headers and the matching native library are cached locally. Python
is a build tool here, not part of the C++ backend's edit/render loop.
"""
import hashlib,json,os,shutil,subprocess,tarfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'.work/cpp-build'
RUNTIME=ROOT/'native/runtime'

def fetch(url,path,sha=None):
    if not path.exists():
        print('Downloading',url,flush=True)
        with urllib.request.urlopen(url,timeout=120) as source:path.write_bytes(source.read())
    if sha and hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise RuntimeError('Download checksum mismatch: '+str(path))
    return path

def install(data,path):
    if path.exists() and path.read_bytes()==data:return
    temporary=path.with_name(path.name+'.new');temporary.write_bytes(data);os.replace(temporary,path)

def main():
    BUILD.mkdir(parents=True,exist_ok=True);RUNTIME.mkdir(parents=True,exist_ok=True)
    header=fetch('https://cdn.jsdelivr.net/gh/nlohmann/json@v3.12.0/single_include/nlohmann/json.hpp',BUILD/'json.hpp','aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63')
    wheel=fetch('https://files.pythonhosted.org/packages/2a/6b/3de1714d734ff949be1e90a22375d0598d3540b22ae73eb85c2d7d1f36a9/pymupdf-1.26.7-cp310-abi3-manylinux_2_28_x86_64.whl',BUILD/'pymupdf.whl','69dfc78f206a96e5b3ac22741263ebab945fdf51f0dbe7c5757c3511b23d9d72')
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if '/libmupdf.so' in name:
                install(archive.read(name),RUNTIME/Path(name).name)
    source=fetch('https://codeload.github.com/ArtifexSoftware/mupdf/tar.gz/refs/tags/1.26.12',BUILD/'mupdf-1.26.12.tar.gz','e6247e1c6216ca8ec5863848a082ce121773074dfc2f34b0b7c7a4de4ff5172e')
    with tarfile.open(source) as archive:
        for item in archive.getmembers():
            parts=Path(item.name).parts
            if len(parts)>1 and (parts[1]=='include' or parts[1]=='COPYING') and item.isfile():
                target=BUILD/Path(*parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(item).read())
    shutil.copyfile(BUILD/'COPYING',RUNTIME/'MuPDF-COPYING')
    # Linux library and LuaTeX checkpoint requirements are explicit for now.
    def linux(path):
        if os.name!='nt':return str(path)
        return subprocess.check_output(['wsl','-d','Ubuntu-22.04','--exec','wslpath','-a',path.as_posix()],text=True).strip()
    prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
    libs=sorted(RUNTIME.glob('libmupdf.so*'))
    if len(libs)!=1:raise RuntimeError('Expected one pinned MuPDF library')
    command=prefix+['g++','-std=c++17','-O2','-g','-pthread','-Wall','-Wextra',
        '-I'+linux(BUILD),'-I'+linux(BUILD/'include'),linux(ROOT/'native/main.cpp'),
        linux(libs[0]),'-lz','-ldeflate','-Wl,-rpath,$ORIGIN','-o',linux(RUNTIME/'bakoma-backend.new')]
    subprocess.run(command,check=True)
    try:os.replace(RUNTIME/'bakoma-backend.new',RUNTIME/'bakoma-backend')
    except PermissionError:raise SystemExit('Close running C++ previews, then rebuild. Windows is holding the existing executable open; it has not been overwritten.')
    subprocess.run(prefix+['gcc','-O2','-fPIC','-shared',linux(ROOT/'prototype/snapshot.c'),'-o',linux(RUNTIME/'bako_snapshot.so.new')],check=True)
    os.replace(RUNTIME/'bako_snapshot.so.new',RUNTIME/'bako_snapshot.so')
    subprocess.run(prefix+['g++','-std=c++17','-O2','-g','-fPIC','-shared','-fno-builtin','-fno-stack-protector','-Wl,-z,now',linux(ROOT/'native/internal_snapshot.cpp'),'-o',linux(RUNTIME/'bako_internal.so.new')],check=True)
    os.replace(RUNTIME/'bako_internal.so.new',RUNTIME/'bako_internal.so')
    print('Built',RUNTIME/'bakoma-backend',flush=True)

if __name__=='__main__':main()
