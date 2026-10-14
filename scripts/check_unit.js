const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'..');
for(const name of ['.work','results'])fs.mkdirSync(path.join(root,name),{recursive:true});
for(const [script,...args] of [['check_configuration.js'],['check_macos_setup.js'],['check_project.js'],['check_extension_live.js'],
  ['check_extension_live.js','--pdflatex'],['check_extension_live.js','--managed-tex'],['check_extension_save.js'],['check_frame_delivery.js']]){
  const result=spawnSync(process.execPath,[path.join(__dirname,script),...args],{cwd:root,stdio:'inherit'});
  if(result.status!==0)process.exit(result.status||1);
}
