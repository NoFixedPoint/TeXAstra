/* Shared launcher for VS Code and the standalone demo. No Python edit path. */
const fs=require('fs');
const path=require('path');
const {spawn}=require('child_process');
function linuxPath(value){
  const full=path.resolve(value).replaceAll('\\','/');
  if(process.platform!=='win32')return full;
  const drive=/^([A-Za-z]):\/(.*)$/.exec(full);
  if(drive)return `/mnt/${drive[1].toLowerCase()}/${drive[2]}`;
  const unc=/^\/\/wsl(?:\.localhost|\$)\/Ubuntu-22\.04\/(.*)$/i.exec(full);
  if(unc)return '/'+unc[1];
  throw new Error('The C++ backend currently requires a local drive or Ubuntu-22.04 WSL path.');
}
function launch(root,project,checkpoint=process.env.BAKO_CHECKPOINT_MODE||'fork',options={}){
  const executable=path.join(options.runtime||path.join(root,'native/runtime'),'bakoma-backend');
  if(!fs.existsSync(executable))throw new Error('Build the C++ backend first: python scripts/build_cpp.py');
  if(checkpoint!=='fork')throw new Error('Internal snapshots were removed; use fork checkpoints.');
  const args=['--project',linuxPath(project),'--assets',linuxPath(path.join(root,'prototype')),'--checkpoint',checkpoint,
    '--main',options.main||'main.tex','--preview-mode',options.mode||'auto','--compiler',options.compiler||'lualatex'];
  return process.platform==='win32'
    ?spawn('wsl',['-d','Ubuntu-22.04','--exec',linuxPath(executable),...args],{windowsHide:true})
    :spawn(executable,args);
}
module.exports={launch,linuxPath};
