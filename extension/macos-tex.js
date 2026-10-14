/* First-use macOS TeX setup. Uses VS Code's Node runtime and macOS system tools. */
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');
const {spawn}=require('child_process');
const {pipeline}=require('stream/promises');
const REPOSITORY='https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2021/tlnet-final';
const INSTALLER_SHA256='bc9285e51bf3eec8e928fce78dd146e9418d20b2c3048148cfb28d95f76c4cb5';
const PACKAGES=['pgf','booktabs','geometry','luaotfload','luatex','luahbtex','latex-bin','synctex'];
const REQUIRED=['kpsewhich','tlmgr','lualatex','pdflatex','luahbtex','pdftex','fmtutil-sys'];
const cancelled=()=>Object.assign(new Error('TeX setup cancelled. Run TeXAstra: Open Document to retry.'),{name:'AbortError'});
async function sha256(file){
  const hash=crypto.createHash('sha256');
  await pipeline(fs.createReadStream(file),hash);
  return hash.digest('hex');
}
function run(program,args,{cwd,env,signal,log=()=>{}}={}){
  if(signal?.aborted)return Promise.reject(cancelled());
  return new Promise((resolve,reject)=>{
    // A separate process group lets Cancel stop perl and its downloader children.
    const grouped=process.platform!=='win32';
    const child=spawn(program,args,{cwd,env,detached:grouped,windowsHide:true,stdio:['ignore','pipe','pipe']});
    let stdout='',tail='';
    const abort=()=>{
      try{if(grouped&&child.pid)process.kill(-child.pid,'SIGKILL');else child.kill('SIGKILL');}catch{/* Already exited. */}
    };
    signal?.addEventListener('abort',abort,{once:true});
    child.stdout.on('data',data=>{stdout=(stdout+data).slice(-65536);log(data.toString());});
    child.stderr.on('data',data=>{tail=(tail+data).slice(-4000);log(data.toString());});
    child.on('error',error=>{signal?.removeEventListener('abort',abort);reject(error);});
    child.on('close',code=>{
      signal?.removeEventListener('abort',abort);
      if(signal?.aborted)reject(cancelled());
      else if(code!==0)reject(new Error(`${path.basename(program)} failed (${code}). ${tail||stdout}`));
      else resolve(stdout.trim());
    });
  });
}
function profile(destination){
  if(/[\r\n]/.test(destination))throw new Error('The TeX installation path cannot contain a newline.');
  return ['selected_scheme scheme-basic','binary_universal-darwin 1',
    'TEXDIR '+destination,...Object.entries({TEXMFCONFIG:'texmf-config',TEXMFVAR:'texmf-var',
      TEXMFHOME:'texmf-home',TEXMFLOCAL:'texmf-local',TEXMFSYSCONFIG:'texmf-config',TEXMFSYSVAR:'texmf-var'})
      .map(([key,value])=>key+' '+path.join(destination,value)),
    'instopt_adjustpath 0','tlpdbopt_install_docfiles 0','tlpdbopt_install_srcfiles 0'].join('\n')+'\n';
}
async function install({extensionPath,destination,work,signal,log,report,execute=run}){
  const options={cwd:work,signal,log};
  // Do not inherit TEXMF overrides from a user's separate MacTeX installation.
  const env=Object.fromEntries(Object.entries(process.env).filter(([name])=>!/^TEX|^LUAINPUTS$|^LUA_PATH$|^LUA_CPATH$/.test(name)));
  env.PATH='/usr/bin:/bin:/usr/sbin:/sbin';
  options.env=env;
  report('Downloading TeX Live 2021 installer…');
  const archive=path.join(work,'install-tl-unx.tar.gz');
  await execute('/usr/bin/curl',['--fail','--location','--proto','=https','--proto-redir','=https',
    '--retry','2','--connect-timeout','30','--max-time','300','--output',archive,REPOSITORY+'/install-tl-unx.tar.gz'],options);
  if(await sha256(archive)!==INSTALLER_SHA256)throw new Error('Historical TeX installer checksum mismatch. Please retry later.');
  await execute('/usr/bin/tar',['-xzf',archive,'-C',work],options);
  const extracted=(await fs.promises.readdir(work)).find(name=>/^install-tl-/.test(name)&&name!=='install-tl-unx.tar.gz');
  if(!extracted)throw new Error('The TeX installer archive is missing install-tl.');
  const profileFile=path.join(work,'macos.profile');
  await fs.promises.writeFile(profileFile,profile(destination));
  report('Installing TeX Live 2021 (this can take several minutes)…');
  await execute('/usr/bin/perl',[path.join(work,extracted,'install-tl'),'-profile',profileFile,'-repository',REPOSITORY],options);
  const binary=path.join(destination,'bin/universal-darwin');
  env.PATH=binary+path.delimiter+env.PATH;
  report('Installing document packages and fonts…');
  await execute(path.join(binary,'tlmgr'),['install',...PACKAGES],options);
  for(const [source,target] of [['texastra-luahbtex','luahbtex'],['texastra-pdftex','pdftex']]){
    const file=path.join(binary,target);
    // Replace the isolated distribution's binary, never follow a symlink out of it.
    await fs.promises.rm(file,{force:true});
    await fs.promises.copyFile(path.join(extensionPath,'native/runtime',source),file);
    await fs.promises.chmod(file,0o755);
  }
  env.TEXMFCNF=await execute(path.join(binary,'kpsewhich'),['--var-value=TEXMFCNF'],options);
  report('Preparing matching LuaLaTeX and PDFLaTeX formats…');
  for(const engine of ['luahbtex','pdftex'])await execute(path.join(binary,'fmtutil-sys'),['--byengine',engine],options);
  for(const [engine,version] of [['lualatex','1.14.0'],['pdflatex','1.40.22']]){
    const actual=await execute(path.join(binary,engine),['--version'],options);
    if(!actual.includes(version))throw new Error(`The installed ${engine} does not match the bundled engine (${version}).`);
    const format=await execute(path.join(binary,'kpsewhich'),['--format=fmt',engine+'.fmt'],options);
    if(!format)throw new Error(`The ${engine} format was not generated.`);
  }
  return binary;
}
async function usable(directory,key){
  try{
    const marker=JSON.parse(await fs.promises.readFile(path.join(directory,'ready.json'),'utf8'));
    if(marker.key!==key)return false;
    await Promise.all(REQUIRED.map(file=>fs.promises.access(path.join(directory,'texlive/bin/universal-darwin',file),fs.constants.X_OK)));
    return true;
  }catch{return false;}
}
function createMacTexSetup({platform=process.platform,extensionPath,storagePath,installTree=install}){
  let pending,controller;
  async function ensure(options={},ui={}){
    if(platform!=='darwin'||options.texBinDirectory)return options;
    if(!pending)pending=prepare(ui).finally(()=>{pending=null;});
    return {...options,texBinDirectory:await pending};
  }
  async function prepare(ui){
    if(!storagePath)throw new Error('VS Code did not provide persistent storage for TeX setup.');
    const hashes=await Promise.all(['texastra-luahbtex','texastra-pdftex'].map(name=>sha256(path.join(extensionPath,'native/runtime',name))));
    const key=crypto.createHash('sha256').update(['setup-v1',...hashes].join(':')).digest('hex');
    const prefix='texlive-2021-'+key.slice(0,16)+'-';
    await fs.promises.mkdir(storagePath,{recursive:true});
    for(const name of await fs.promises.readdir(storagePath)){
      if(name.startsWith(prefix)&&await usable(path.join(storagePath,name),key))
        return path.join(storagePath,name,'texlive/bin/universal-darwin');
    }
    return ui.progress(async(report,signal)=>{
      // Each attempt has its own final path: TeX profiles contain absolute paths.
      // Even two VS Code windows or a terminated host cannot share a partial tree.
      const directory=await fs.promises.mkdtemp(path.join(storagePath,prefix));
      const work=path.join(directory,'installer');
      const destination=path.join(directory,'texlive');
      let complete=false;
      try{
        await fs.promises.mkdir(work);
        await installTree({extensionPath,destination,work,signal,report,log:ui.log});
        if(signal.aborted)throw cancelled();
        await fs.promises.writeFile(path.join(directory,'ready.json'),JSON.stringify({key})+'\n');
        if(!await usable(directory,key))throw new Error('The TeX installation is incomplete. Please retry.');
        complete=true;
        ui.log?.(`TeX Live ready: ${path.join(destination,'bin/universal-darwin')}\n`);
        return path.join(destination,'bin/universal-darwin');
      }finally{
        await fs.promises.rm(complete?work:directory,{recursive:true,force:true});
      }
    });
  }
  return {ensure,async withProgress(vscode,output,options){
    return ensure(options,{log:text=>output.append(text),progress:task=>vscode.window.withProgress({
      location:vscode.ProgressLocation.Notification,title:'TeXAstra: Setting up TeX Live',cancellable:true,
    },async(progress,token)=>{
      controller=new AbortController();
      const subscription=token.onCancellationRequested(()=>controller?.abort());
      if(token.isCancellationRequested)controller.abort();
      try{return await task(message=>progress.report({message}),controller.signal);}
      finally{subscription.dispose();controller=null;}
    })});
  },dispose(){controller?.abort();}};
}
module.exports={createMacTexSetup,install,profile,run,sha256,REPOSITORY,INSTALLER_SHA256,REQUIRED};
