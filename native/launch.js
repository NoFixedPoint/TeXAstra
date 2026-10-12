/* Shared launcher for VS Code and the standalone demo. No Python edit path. */
const fs=require('fs');
const path=require('path');
const {spawn,spawnSync}=require('child_process');
function wslNames(bytes){
  const text=Buffer.isBuffer(bytes)?bytes.toString(bytes.includes(0)?'utf16le':'utf8'):String(bytes||'');
  return text.replace(/^\uFEFF/,'').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
}
function selectWsl(names,configured='',paths=[]){
  const hosts=[...new Set(paths.map(value=>/^[/\\]{2}wsl(?:\.localhost|\$)[/\\]([^/\\]+)/i.exec(value)?.[1]).filter(Boolean))];
  if(hosts.length>1)throw new Error('The runtime and project must be accessible from the same WSL distribution.');
  const selected=configured||hosts[0]||(names.includes('Ubuntu-22.04')?'Ubuntu-22.04':names[0]);
  if(!selected||!names.includes(selected))throw new Error(`WSL distribution '${selected||configured}' is unavailable. Installed: ${names.join(', ')||'none'}. Install a WSL distribution with TeX Live or set texastra.wslDistribution.`);
  if(hosts.length&&hosts[0]!==selected)throw new Error(`This WSL path belongs to ${hosts[0]}, but ${selected} is selected. Set texastra.wslDistribution to ${hosts[0]}.`);
  return selected;
}
function linuxPath(value,distribution='Ubuntu-22.04'){
  const full=path.resolve(value).replaceAll('\\','/');
  if(process.platform!=='win32')return full;
  const drive=/^([A-Za-z]):\/(.*)$/.exec(full);
  if(drive)return `/mnt/${drive[1].toLowerCase()}/${drive[2]}`;
  const unc=/^\/\/wsl(?:\.localhost|\$)\/([^/]+)\/(.*)$/i.exec(full);
  if(unc&&unc[1]===distribution)return '/'+unc[2];
  throw new Error(`The C++ backend requires a local drive or a WSL path in ${distribution}.`);
}
function command(root,project,options={}){
  if(!['win32','linux'].includes(process.platform))throw new Error('The document runtime requires Linux x86-64 or native Windows x64. Native macOS is not supported.');
  if(options.runtimeMode&&!['native','wsl'].includes(options.runtimeMode))throw new Error('runtimeMode must be native or wsl.');
  if(process.platform==='win32'&&options.runtimeMode!=='wsl'){
    if(process.arch!=='x64')throw new Error('The native Windows runtime currently requires an x64 extension host.');
    const executable=path.join(options.runtime||path.join(root,'native/runtime/windows-x64'),'texastra-backend.exe');
    if(!fs.existsSync(executable))throw new Error(`Native Windows runtime is missing: ${executable}. Install the Windows VSIX or build scripts/build_windows_engine.py and scripts/build_windows_cpp.py.`);
    return {program:executable,prefix:[],args:options.texBinDirectory?['--tex-bin',options.texBinDirectory]:[],distribution:null,nativeWindows:true};
  }
  const executable=path.join(options.runtime||path.join(root,'native/runtime'),'texastra-backend');
  for(const file of [executable,path.join(path.dirname(executable),'texastra-luahbtex')])
    if(!fs.existsSync(file))throw new Error(`Bundled runtime file is missing: ${file}. Reinstall the extension, or rebuild the runtime from source.`);
  let distribution=null;
  if(process.platform==='win32'){
    const listed=spawnSync('wsl',['--list','--quiet'],{windowsHide:true,timeout:5000});
    if(listed.error||listed.status!==0)throw new Error('Cannot list WSL distributions. Install/enable WSL and a Linux distribution with TeX Live. '+(listed.error?.message||wslNames(listed.stderr).join(' ')));
    distribution=selectWsl(wslNames(listed.stdout),options.wslDistribution,[root,project||root,executable]);
  }
  const args=[];
  if(options.texBinDirectory)args.push('--tex-bin',options.texBinDirectory);
  return {program:distribution?'wsl':executable,
    prefix:distribution?['-d',distribution,'--exec',linuxPath(executable,distribution)]:[],args,distribution};
}
function launch(root,project,checkpoint=process.env.BAKO_CHECKPOINT_MODE||'auto',options={}){
  const chosen=command(root,project,options);
  const selected=chosen.nativeWindows?'windows':'fork';
  if(checkpoint==='auto')checkpoint=selected;
  if(checkpoint!==selected)throw new Error(`The selected runtime requires ${selected} checkpoints.`);
  const convert=value=>chosen.nativeWindows?path.resolve(value):linuxPath(value,chosen.distribution);
  const args=[...chosen.prefix,...chosen.args,'--project',convert(project),'--assets',convert(path.join(root,'texastra')),'--checkpoint',checkpoint,
    '--main',options.main||'main.tex','--preview-mode',options.mode||'auto','--compiler',options.compiler||'lualatex'];
  const child=spawn(chosen.program,args,{windowsHide:true});
  child.texastraEnvironment={platform:process.platform,wslDistribution:chosen.distribution,runtime:chosen.nativeWindows?'native':'linux'};
  return child;
}
function environment(root,options={}){
  const chosen=command(root,null,options);
  return new Promise((resolve,reject)=>{
    const child=spawn(chosen.program,[...chosen.prefix,...chosen.args,'--environment'],{windowsHide:true});
    let stdout='',stderr='';
    child.stdout.on('data',data=>stdout+=data);child.stderr.on('data',data=>stderr+=data);
    child.on('error',reject);
    child.on('close',code=>{
      try{resolve({...JSON.parse(stdout),host:{platform:process.platform,wslDistribution:chosen.distribution,runtime:chosen.nativeWindows?'native':'linux'}});}
      catch{reject(new Error(`Cannot run the selected document runtime (exit ${code}). ${stderr||stdout}`));}
    });
  });
}
module.exports={launch,linuxPath,environment,wslNames,selectWsl,command};
