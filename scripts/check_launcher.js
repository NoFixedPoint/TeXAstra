/* WSL selection and protocol launch, without requiring additional installed VMs. */
const assert=require('assert'),path=require('path'),fs=require('fs');
const {wslNames,selectWsl,linuxPath,environment}=require('../native/launch');
let checks=0;
function check(actual,expected){assert.deepStrictEqual(actual,expected);checks++;}
check(wslNames(Buffer.from('\uFEFFUbuntu-22.04\r\nDebian\r\n','utf16le')),['Ubuntu-22.04','Debian']);
check(wslNames(Buffer.from('Debian\n')),['Debian']);
check(selectWsl(['Debian','Ubuntu-22.04']),'Ubuntu-22.04');
check(selectWsl(['Debian']),'Debian');
check(selectWsl(['Debian','Ubuntu-22.04'],'Debian'),'Debian');
check(selectWsl(['Debian','Ubuntu-22.04'],'',['\\\\wsl.localhost\\Debian\\home\\paper']),'Debian');
for(const call of [()=>selectWsl([]),()=>selectWsl(['Debian'],'Missing'),()=>selectWsl(['Debian','Ubuntu'],'Ubuntu',['\\\\wsl$\\Debian\\home']),()=>selectWsl(['Debian','Ubuntu'],'',['\\\\wsl$\\Debian\\home','\\\\wsl$\\Ubuntu\\home'])]){
  assert.throws(call);checks++;
}
if(process.platform==='win32'){
  check(linuxPath('D:\\paper folder\\main.tex','Debian'),'/mnt/d/paper folder/main.tex');
  check(linuxPath('\\\\wsl.localhost\\Debian\\home\\paper.tex','Debian'),'/home/paper.tex');
  assert.throws(()=>linuxPath('\\\\wsl.localhost\\Ubuntu\\home\\paper.tex','Debian'));checks++;
}
(async()=>{
  const root=path.resolve(__dirname,'..');
  const report=await environment(root,{runtimeMode:'wsl',texBinDirectory:'/usr/bin'});
  check(report.ok,true);check(report.binDirectory,'/usr/bin');
  check(report.host.platform,process.platform);
  if(process.platform==='win32'){
    const native=await environment(root);
    check(native.ok,true);check(native.platform,'win32-x64');
    check(native.host.runtime,'native');check(native.host.wslDistribution,null);
    assert(!native.binDirectory.startsWith('/'));checks++;
  }
  const failed=await environment(root,{runtimeMode:'wsl',texBinDirectory:'/texastra-missing-installation'});
  check(failed.ok,false);assert(failed.error.includes('kpsewhich'));checks++;
  const result={checks,ok:true};fs.writeFileSync(path.join(root,'results/launcher.json'),JSON.stringify(result,null,2)+'\n');console.log(result);
})().catch(error=>{console.error(error);process.exitCode=1;});
