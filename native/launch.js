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
  if(!selected||!names.includes(selected))throw new Error(`WSL distribution '${selected||configured}' is unavailable. Installed: ${names.join(', ')||'none'}. Install a WSL distribution with TeX Live or set bakoma.wslDistribution.`);
  if(hosts.length&&hosts[0]!==selected)throw new Error(`This WSL path belongs to ${hosts[0]}, but ${selected} is selected. Set bakoma.wslDistribution to ${hosts[0]}.`);
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
  if(!['win32','linux'].includes(process.platform))throw new Error('The preview runtime requires Linux x86-64 or Windows with WSL. Native macOS is not supported.');
  const executable=path.join(options.runtime||path.join(root,'native/runtime'),'bakoma-backend');
  for(const file of [executable,path.join(path.dirname(executable),'bakoma-luahbtex')])
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
function launch(root,project,checkpoint=process.env.BAKO_CHECKPOINT_MODE||'fork',options={}){
  if(checkpoint!=='fork')throw new Error('Internal snapshots were removed; use fork checkpoints.');
  const chosen=command(root,project,options);
  const args=[...chosen.prefix,...chosen.args,'--project',linuxPath(project,chosen.distribution),'--assets',linuxPath(path.join(root,'prototype'),chosen.distribution),'--checkpoint',checkpoint,
    '--main',options.main||'main.tex','--preview-mode',options.mode||'auto','--compiler',options.compiler||'lualatex'];
  const child=spawn(chosen.program,args,{windowsHide:true});
  child.bakomaEnvironment={platform:process.platform,wslDistribution:chosen.distribution};
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
      try{resolve({...JSON.parse(stdout),host:{platform:process.platform,wslDistribution:chosen.distribution}});}
      catch{reject(new Error(`Cannot run the preview runtime (exit ${code}). Check Linux x86-64 and its shared-library requirements. ${stderr||stdout}`));}
    });
  });
}
module.exports={launch,linuxPath,environment,wslNames,selectWsl};
