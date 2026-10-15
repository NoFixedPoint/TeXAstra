const assert=require('assert'),path=require('path'),Module=require('module');
const original=Module._load,calls=[];
Module._load=function(name,parent,...rest){
  if(parent?.filename===path.resolve(__dirname,'../native/launch.js')){
    if(name==='fs')return {existsSync:()=>true};
    if(name==='child_process')return {
      spawn:(program,args,options)=>{calls.push({program,args,options});return {};},
      spawnSync:()=>({status:0,stdout:Buffer.from('Ubuntu-22.04\n')})
    };
  }
  return original.call(this,name,parent,...rest);
};
const {launch}=require('../native/launch');
Module._load=original;
const root=path.resolve(__dirname,'..');
for(const runtimeMode of ['native','wsl']){
  for(const enabled of [undefined,true,false]){
    launch(root,root,'auto',{runtimeMode,autoInstallPackages:enabled});
    const {args,options}=calls.at(-1);
    assert.equal(args[args.indexOf('--auto-install-packages')+1],String(enabled!==false));
    assert.equal(options.windowsHide,true);
  }
}
console.log({packageLaunchChecks:calls.length,ok:true});
