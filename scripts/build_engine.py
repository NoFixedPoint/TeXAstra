"""Build the pinned LuaHBTeX token-origin patch on Linux (or Ubuntu-22.04 WSL)."""
import argparse,hashlib,os,platform,shutil,subprocess,sys,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='https://archive.ubuntu.com/ubuntu/pool/main/t/texlive-bin/'
ARCHIVES={
 'texlive-bin_2021.20210626.59705.orig.tar.xz':'d9f08f7c6c1d87b3bf664ef3adaed1518b772aaad803aac5fe16f753a897be78',
 'texlive-bin_2021.20210626.59705-1ubuntu0.3.debian.tar.xz':'5f7c6849e9d6016c7d8932ae1a0dd37fcd91df942d90c01ee11e42f54b71616a',
}
FLAGS=['--disable-native-texlive-build','--disable-all-pkgs','--enable-web2c','--enable-luahbtex',
 '--disable-luatex','--disable-luajittex','--disable-luajithbtex','--disable-pdftex','--disable-xetex',
 '--disable-tex','--disable-etex','--disable-ptex','--disable-eptex','--disable-uptex','--disable-euptex',
 '--disable-aleph','--disable-omega','--disable-mp','--disable-mf','--disable-mfluajit',
 '--with-system-harfbuzz','--with-system-zlib','--with-system-libpng','--disable-x','--disable-shared']
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
 parser.add_argument('--source-only',action='store_true')
 args=parser.parse_args()
 if os.name=='nt':
  def linux(p):return subprocess.check_output(['wsl','-d','Ubuntu-22.04','--exec','wslpath','-a',str(p.resolve())],text=True).strip()
  subprocess.run(['wsl','-d','Ubuntu-22.04','--exec','python3',linux(Path(__file__)),'--runtime',linux(args.runtime)]+(['--source-only'] if args.source_only else []),check=True);return
 mac=sys.platform=='darwin'
 cache=Path.home()/('.cache/texastra-engine-'+platform.machine() if mac else '.cache/texastra-engine');source=cache/'source';build=cache/'build'
 cache.mkdir(parents=True,exist_ok=True);build.mkdir(exist_ok=True)
 for name,digest in ARCHIVES.items():
  path=cache/name
  if not path.exists():urllib.request.urlretrieve(URL+name,path)
  assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
 upstream='\n'.join(ARCHIVES.values())
 if not (source/'.bako-upstream').exists() or (source/'.bako-upstream').read_text()!=upstream:
  source.mkdir(exist_ok=True)
  with tarfile.open(cache/next(iter(ARCHIVES))) as archive:
   for item in archive.getmembers():
    parts=Path(item.name).parts[1:]
    if not parts:continue
    target=source/Path(*parts)
    if not target.resolve().is_relative_to(source.resolve()):raise RuntimeError('Archive path escapes source')
    if item.isfile():
     target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(item).read());target.chmod(item.mode)
    elif item.isdir():target.mkdir(parents=True,exist_ok=True)
    elif item.issym():
     target.parent.mkdir(parents=True,exist_ok=True)
     if target.exists() or target.is_symlink():target.unlink()
     target.symlink_to(item.linkname)
  with tarfile.open(cache/list(ARCHIVES)[1]) as archive:
   # Keep the distro's security fixes, in its declared order.
   series=archive.extractfile('debian/patches/series').read().decode().splitlines()
   for name in series:
    if name.startswith('CVE-'):
     subprocess.run(['patch','-p1','--batch'],cwd=source,input=archive.extractfile('debian/patches/'+name).read(),check=True)
  (source/'.bako-upstream').write_text(upstream)
 if mac:
  # Ubuntu's repack omits dependency trees. Restore the matching upstream
  # revision, as in the native Windows build, and link those libraries statically.
  dependency=cache/'upstream-r59705.tar.gz'
  if not dependency.exists():urllib.request.urlretrieve('https://codeload.github.com/TeX-Live/texlive-source/tar.gz/7652969578ab227a3ae1774f0530f175e4a5abe2',dependency)
  digest='d759b7f1ec7f70bd48d0c2479046b7dab87c41f9a0d2d642e6d5900b73ab2856'
  if hashlib.sha256(dependency.read_bytes()).hexdigest()!=digest:raise RuntimeError('Upstream dependency source checksum mismatch')
  if not (source/'.bako-bundled-libraries').exists():
   existing={p.name for p in (source/'libs').iterdir()}
   with tarfile.open(dependency) as archive:
    for item in archive:
     parts=Path(item.name).parts[1:]
     if len(parts)<2 or parts[0]!='libs' or parts[1] in existing:continue
     target=source.joinpath(*parts)
     if not target.resolve().is_relative_to(source.resolve()):raise RuntimeError('Archive path escapes source')
     if item.isdir():target.mkdir(parents=True,exist_ok=True)
     elif item.isfile():
      target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(item).read());target.chmod(item.mode)
     elif item.issym():
      target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(item.linkname)
   (source/'.bako-bundled-libraries').write_text(digest)
 if mac:
  # Apple now defines TARGET_OS_MAC through SDK headers; this old conditional
  # means classic Mac OS, whose fp.h is absent from modern macOS.
  png=source/'libs/libpng/libpng-src/pngpriv.h'
  text=png.read_text()
  if '!defined(__APPLE__)' not in text:text=text.replace('defined(TARGET_OS_MAC)', '(defined(TARGET_OS_MAC) && !defined(__APPLE__))')
  if png.read_text()!=text:png.write_text(text)
 sys.path.insert(0,str(ROOT/'engine'))
 from patch import apply
 apply(source)
 if args.source_only:return
 flags=[f for f in FLAGS if not (mac and f.startswith('--with-system-'))]
 if mac:flags+=['--without-x','--with-system-zlib','--disable-pmp','--disable-upmp','--disable-mflua','--disable-web-progs']
 signature='\n'.join(flags)+('\n'+os.environ.get('MACOSX_DEPLOYMENT_TARGET','') if mac else '')
 if not (build/'.bako-configure').exists() or (build/'.bako-configure').read_text()!=signature:
  if mac and (build/'.bako-configure').exists():
   # Nested autoconf projects otherwise retain stale options from cached builds.
   if build.resolve().parent!=cache.resolve():raise RuntimeError('Unexpected engine build directory')
   shutil.rmtree(build);build.mkdir()
  with (build/'configure.log').open('w') as log:subprocess.run([str(source/'configure'),*flags],cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
  (build/'.bako-configure').write_text(signature)
 print('Building LuaHBTeX; log:',build/'build.log',flush=True)
 with (build/'build.log').open('w') as log:
  jobs='-j'+str(min(os.cpu_count() or 2,12))
  libraries=['HARFBUZZ_INCLUDES=-I'+str(source/'libs/harfbuzz/harfbuzz-src/src')+' -I'+str(build/'libs/harfbuzz'),
             'HARFBUZZ_LIBS='+str(build/'libs/harfbuzz/libharfbuzz.a'),
             'GRAPHITE2_INCLUDES=-I'+str(source/'libs/graphite2/graphite2-src/include'),
             'GRAPHITE2_LIBS='+str(build/'libs/graphite2/libgraphite2.a'),
             'ZZIPLIB_LIBS='+str(build/'libs/zziplib/libzzip.a'),
             'luahbtex_LDFLAGS=-Wl,-export_dynamic'] if mac else []
  subdirs=['CONF_SUBDIRS=libpng zziplib graphite2 harfbuzz lua53 pplib','MAKE_SUBDIRS=libpng zziplib graphite2 harfbuzz lua53 pplib'] if mac else []
  for command in [['make','all-local'],['make','-C','texk/kpathsea',jobs],['make','-C','texk/ptexenc',jobs],
                  ['make','-C','libs',jobs,*subdirs],['make','-C','texk','all-local'],
                  ['make','-C','texk/web2c',jobs,'luahbtex',*([] if mac else ['ZZIPLIB_LIBS=-lzzip'])]]:
   subprocess.run(command+libraries,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
 runtime=args.runtime.resolve();runtime.mkdir(parents=True,exist_ok=True)
 temporary=runtime/'texastra-luahbtex.new';shutil.copyfile(build/'texk/web2c/luahbtex',temporary)
 subprocess.run(['strip',*(['-S'] if mac else []),str(temporary)],check=True);temporary.chmod(0o755);os.replace(temporary,runtime/'texastra-luahbtex')
 # Ship complete upstream source plus distro patches and our own build recipe.
 for name in ARCHIVES:shutil.copyfile(cache/name,runtime/name)
 if mac:
  (runtime/'sources').mkdir(exist_ok=True)
  shutil.copyfile(dependency,runtime/'sources'/dependency.name)
 shutil.copyfile(ROOT/'licenses/GPL-2.0.txt',runtime/'LuaHBTeX-COPYING')
 print('Built',runtime/'texastra-luahbtex',flush=True)
if __name__=='__main__':main()
