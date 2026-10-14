/* Portable lifecycle checks; --native also downloads TeX and compiles on macOS. */
const assert=require('assert/strict'),fs=require('fs'),path=require('path');
const {createMacTexSetup,install,profile,run,sha256,REQUIRED}=require('../extension/macos-tex');
const root=path.resolve(__dirname,'..');
fs.mkdirSync(path.join(root,'.work'),{recursive:true});
const sandbox=fs.mkdtempSync(path.join(root,'.work/macos-setup-'));
const extensionPath=path.join(sandbox,'extension with spaces'),storagePath=path.join(sandbox,'Application Support','storage');
const runtime=path.join(extensionPath,'native/runtime');
fs.mkdirSync(runtime,{recursive:true});
for(const name of ['texastra-luahbtex','texastra-pdftex'])fs.writeFileSync(path.join(runtime,name),name);
let installs=0,progress=0,fail=false,incomplete=false,gate;
const attempts=[],checks=[];
const check=(name,value)=>{assert(value,name);checks.push(name);console.log(name);};
async function fakeInstall({destination,signal}){
  installs++;attempts.push(destination);
  fs.mkdirSync(path.join(destination,'bin/universal-darwin'),{recursive:true});
  if(gate)await gate;
  if(fail)throw Error('network unavailable');
  if(signal.aborted)throw Object.assign(Error('cancelled'),{name:'AbortError'});
  for(const name of REQUIRED)if(!incomplete||name!=='pdflatex')
    fs.writeFileSync(path.join(destination,'bin/universal-darwin',name),'test',{mode:0o755});
}
const make=(extra={})=>createMacTexSetup({platform:'darwin',extensionPath,storagePath,installTree:fakeInstall,...extra});
let abort;
const ui={log(){},progress:async task=>{progress++;abort=new AbortController();return task(()=>{},abort.signal);}};
(async()=>{
  for(const platform of ['win32','linux']){
    const options={runtimeMode:'wsl'};
    assert.equal(await make({platform}).ensure(options),options);
  }
  const explicit={texBinDirectory:'/existing MacTeX/bin'};
  assert.equal(await make().ensure(explicit),explicit);
  check('non-macOS and explicit TeX settings never trigger setup',installs===0&&progress===0);
  const setup=make();
  const [first,second]=await Promise.all([setup.ensure({},ui),setup.ensure({runtimeMode:'native'},ui)]);
  check('concurrent callers share one complete installation',installs===1&&first.texBinDirectory===second.texBinDirectory&&second.runtimeMode==='native');
  const cached=await make().ensure({},ui);
  check('a fresh extension activation reuses persistent TeX without downloads',cached.texBinDirectory===first.texBinDirectory&&installs===1&&progress===1);
  fs.writeFileSync(path.join(runtime,'texastra-pdftex'),'updated engine');
  const updated=await make().ensure({},ui);
  check('engine updates prepare matching formats in a separate tree',installs===2&&updated.texBinDirectory!==first.texBinDirectory&&fs.existsSync(first.texBinDirectory));
  fs.unlinkSync(path.join(updated.texBinDirectory,'pdflatex'));
  fail=true;
  const retry=make();
  await assert.rejects(retry.ensure({},ui),/network unavailable/);
  check('broken cached installations are rejected and failed attempts cleaned',!fs.existsSync(path.dirname(attempts.at(-1))));
  fail=false;
  await retry.ensure({},ui);
  check('retry succeeds after a download failure',installs===4);
  const cancelSetup=make({storagePath:path.join(sandbox,'cancel')});
  let release;gate=new Promise(resolve=>{release=resolve;});
  const waiting=cancelSetup.ensure({},ui);
  while(attempts.length<5)await new Promise(resolve=>setImmediate(resolve));
  abort.abort();release();gate=null;
  await assert.rejects(waiting,{name:'AbortError'});
  check('cancellation never marks a partial installation ready',!fs.existsSync(path.dirname(attempts.at(-1))));
  await cancelSetup.ensure({},ui);
  check('cancelled setup can be retried',installs===6);
  incomplete=true;
  await assert.rejects(make({storagePath:path.join(sandbox,'incomplete')}).ensure({},ui),/incomplete/);
  check('missing required binaries prevent completion',!fs.existsSync(path.dirname(attempts.at(-1))));
  incomplete=false;
  const text=profile(path.join(sandbox,'a directory with spaces'));
  check('profile isolates TeX user/system trees and preserves paths with spaces',text.includes('instopt_adjustpath 0')&&text.includes('TEXMFHOME '+path.join(sandbox,'a directory with spaces','texmf-home')));
  assert.throws(()=>profile('bad\npath'),/newline/);
  const work=path.join(sandbox,'checksum');fs.mkdirSync(work);
  let commands=0;
  await assert.rejects(install({extensionPath,destination:path.join(sandbox,'unused'),work,report(){},execute:async(program,args)=>{
    commands++;assert.equal(program,'/usr/bin/curl');assert(args.includes('=https'));
    fs.writeFileSync(path.join(work,'install-tl-unx.tar.gz'),'untrusted download');
  }}),/checksum mismatch/);
  check('checksum mismatch blocks extraction and installer execution',commands===1);
  fs.writeFileSync(path.join(work,'hash.txt'),'abc');
  check('download verification computes SHA-256',await sha256(path.join(work,'hash.txt'))==='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  const controller=new AbortController();
  const running=run(process.execPath,['-e','setInterval(()=>{},1000)'],{signal:controller.signal});
  controller.abort();await assert.rejects(running,{name:'AbortError'});
  check('Cancel terminates an active setup process',true);
  await assert.rejects(run(process.execPath,['-e','process.stderr.write("failure detail");process.exit(7)']),/failure detail/);
  check('subprocess failures preserve useful diagnostics',true);
  if(process.argv.includes('--native')){
    assert.equal(process.platform,'darwin','--native requires macOS');
    const nativeStorage=path.join(sandbox,'native Application Support');
    const nativeSetup=createMacTexSetup({extensionPath:root,storagePath:nativeStorage});
    const options=await nativeSetup.ensure({}, {log:text=>process.stdout.write(text),progress:task=>task(message=>console.log(message),new AbortController().signal)});
    const bin=options.texBinDirectory;
    const project=path.join(sandbox,'compile');fs.mkdirSync(project);
    fs.writeFileSync(path.join(project,'main.tex'),'\\documentclass{article}\n\\usepackage{tikz,booktabs,geometry}\n\\begin{document}Automatic setup. \\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}\\end{document}\n');
    const env={...process.env,PATH:bin+path.delimiter+process.env.PATH};
    env.TEXMFCNF=await run(path.join(bin,'kpsewhich'),['--var-value=TEXMFCNF'],{env});
    for(const engine of ['lualatex','pdflatex']){
      await run(path.join(bin,engine),['-interaction=nonstopmode','-halt-on-error','main.tex'],{cwd:project,env});
      check(`${engine} compiles using the automatic macOS installation`,fs.statSync(path.join(project,'main.pdf')).size>0);
      fs.unlinkSync(path.join(project,'main.pdf'));
    }
    assert.deepEqual(await createMacTexSetup({extensionPath:root,storagePath:nativeStorage}).ensure({}),options);
    check('native macOS installation is reused without setup',true);
  }
  fs.mkdirSync(path.join(root,'results'),{recursive:true});
  fs.writeFileSync(path.join(root,`results/macos-setup${process.argv.includes('--native')?'-native':''}.json`),JSON.stringify({ok:true,platform:process.platform,native:process.argv.includes('--native'),checks},null,2)+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
