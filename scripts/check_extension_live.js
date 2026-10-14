/* Exercise the VS Code command with legacy settings and an unsaved buffer. */
const assert=require('assert'),fs=require('fs'),path=require('path'),Module=require('module');
const {EventEmitter}=require('events'),{PassThrough}=require('stream');
const root=path.resolve(__dirname,'..'),project=path.join(root,'.work/extension-project'),main='paper/paper.tex';
const pdfMode=process.argv.includes('--pdflatex');
const managed=process.argv.includes('--managed-tex');
let setupError,releaseSetup,setupCalls=0,launchCalls=0;
const setupGate=new Promise(resolve=>{releaseSetup=resolve;});
fs.mkdirSync(path.join(project,'paper'),{recursive:true});
const log=path.join(project,'paper/paper.log');
if(pdfMode)fs.writeFileSync(log,'This is pdfTeX, Version 3.141592653 (TeX Live)\n');
else if(fs.existsSync(log))fs.unlinkSync(log);
fs.writeFileSync(path.join(project,main),'\\documentclass{article}\n\\begin{document}Example.\\end{document}\n');
const document={uri:{scheme:'file',fsPath:path.join(project,main)},isDirty:true,getText:()=>fs.readFileSync(path.join(project,main),'utf8')+'% unsaved\n'};
const sibling={uri:{scheme:'file',fsPath:path.join(project,'shared/body.tex')},isDirty:true,getText:()=> 'Unsaved sibling.'};
const editor={document};let command,environmentCommand,environmentArgs,environmentDocument,receiver,change,selectionChange,launchArgs,disposed,webMessages=[],outputLines=[];
const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
let input='';child.stdin.on('data',c=>input+=c);
const web={cspSource:'test',asWebviewUri:u=>u.fsPath,postMessage:m=>{webMessages.push(m);},onDidReceiveMessage:f=>{receiver=f;}};
const panel={webview:web,onDidDispose:f=>{disposed=f;},reveal(){},dispose(){disposed?.();}};
let diskChange,diskCreate,diskDelete,watchDisposed=false,watchPattern;
const watcher={onDidChange:f=>{diskChange=f;},onDidCreate:f=>{diskCreate=f;},onDidDelete:f=>{diskDelete=f;},dispose:()=>{watchDisposed=true;}};
const config={checkpointMode:'internal',mainFile:main,engine:'native',previewMode:'full',latexCompiler:'xelatex',wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'};
if(managed)delete config.texBinDirectory;
const defaults=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).contributes.configuration.properties;
const vscode={
  Uri:{file:fsPath=>({fsPath}),joinPath:(base,...s)=>({fsPath:path.join(base.fsPath,...s)})},ViewColumn:{Beside:2,One:1},
  RelativePattern:class {constructor(base,pattern){this.base=base;this.pattern=pattern;}},
  commands:{registerCommand:(name,f)=>{if(name==='texastra.showEnvironment')environmentCommand=f;else command=f;}},
  workspace:{isTrusted:true,textDocuments:[document,sibling],workspaceFolders:[{uri:{fsPath:project}}],
    getWorkspaceFolder:()=>({uri:{fsPath:project}}),getConfiguration:()=>({get:(k,d)=>config[k]??defaults['texastra.'+k]?.default??d}),
    onDidChangeTextDocument:f=>{change=f;},onDidSaveTextDocument(){},createFileSystemWatcher:p=>{watchPattern=p;return watcher;},openTextDocument:async options=>{environmentDocument=options;return options;}},
  window:{activeTextEditor:editor,createOutputChannel:()=>({append(){},appendLine:s=>outputLines.push(s)}),
    createWebviewPanel:()=>panel,onDidChangeTextEditorSelection:f=>{selectionChange=f;},showTextDocument:async()=>{},showErrorMessage:m=>{throw Error(m);}}
};
const original=Module._load;
Module._load=function(request,parent,...rest){
  if(request==='vscode')return vscode;
  if(managed&&request==='./macos-tex')return {createMacTexSetup:()=>({dispose(){},withProgress:async(_vscode,_output,options)=>{
    setupCalls++;if(setupError)throw setupError;await setupGate;return {...options,texBinDirectory:'/selected/bin'};
  }})};
  if(request==='../native/launch')return {launch:(...args)=>{launchCalls++;launchArgs=args;return child;},environment:async(...args)=>{environmentArgs=args;return {ok:true,binDirectory:'/selected/bin'};}};
  return original.call(this,request,parent,...rest);
};
(async()=>{
  require('../extension/extension').activate({subscriptions:[],extensionPath:root,extensionUri:{fsPath:root}});
  if(managed){
    vscode.workspace.isTrusted=false;await command();await environmentCommand();
    assert.equal(setupCalls,0,'Untrusted workspaces never start setup');
    vscode.workspace.isTrusted=true;
    setupError=Error('download failed');await assert.rejects(command(),/TeX setup failed/);
    assert.equal(launchCalls,0,'Setup failures do not launch the backend');
    setupError=Object.assign(Error('cancelled'),{name:'AbortError'});await command();
    assert.equal(launchCalls,0,'Cancelling setup does not open a preview');
    setupError=null;
    const opening=command(),duplicate=command();
    assert.equal(launchCalls,0,'The backend waits until TeX setup finishes');
    releaseSetup();await Promise.all([opening,duplicate]);
    assert.equal(launchCalls,1,'Repeated Open Document during setup opens only one preview');
  }
  await command();await receiver({type:'ready'});
  assert.deepStrictEqual(launchArgs.slice(1),[project,'auto',{main,mode:pdfMode?'full':'auto',compiler:pdfMode?'pdflatex':'lualatex',runtimeMode:'wsl',wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'}]);
  await environmentCommand();assert.deepStrictEqual(environmentArgs,[root,{runtimeMode:'wsl',wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'}]);
  assert.equal(environmentDocument.language,'json');assert.equal(JSON.parse(environmentDocument.content).binDirectory,'/selected/bin');
  child.stdout.write(JSON.stringify({type:'environment',report:{ok:true,binDirectory:'/selected/bin'}})+'\n');
  await new Promise(r=>setImmediate(r));assert(outputLines.some(line=>line.includes('/selected/bin')));
  let sent=input.trim().split('\n').map(JSON.parse);
  assert.equal(sent[0].overlays[main],document.getText());
  assert.equal(sent[0].overlays['shared/body.tex'],sibling.getText());
  assert(web.html.includes('id="pages"'));
  selectionChange({textEditor:{document:sibling},selections:[{active:{line:120,character:3}}]});
  assert.deepStrictEqual(webMessages.at(-1),{type:'forward',file:'shared/body.tex',line:120,column:3});
  const now=Date.now,getText=document.getText;let clock=1000;
  Date.now=()=>clock;document.getText=()=>{clock+=50;return getText();};
  try{change({document,contentChanges:[{text:'x'}]});}
  finally{Date.now=now;document.getText=getText;}
  sent=input.trim().split('\n').map(JSON.parse);assert.equal(sent[1].type,'edit');assert.equal(sent[1].source,document.getText());
  assert.equal(sent[1].sentAt,1000,'Latency begins before reading the editor buffer');
  assert.equal(webMessages.at(-1).state,'building');
  document.version=2;
  change({document,contentChanges:[{rangeOffset:0,rangeLength:0,text:'x'}]});
  assert.equal(JSON.parse(input.trim().split('\n').at(-1)).source,document.getText(),'First versioned event establishes the complete buffer');
  const baseLength=document.getText().length;
  document.version=3;document.getText=()=>{throw Error('Delta edits must not read the whole buffer');};
  change({document,contentChanges:[{rangeOffset:5,rangeLength:1,text:'xyz'},{rangeOffset:1,rangeLength:0,text:'😀'}]});
  const delta=JSON.parse(input.trim().split('\n').at(-1));
  assert(!('source' in delta));assert.equal(delta.baseVersion,2);assert.equal(delta.sourceVersion,3);
  assert.equal(delta.baseLength,baseLength);assert.equal(delta.changes.length,2);
  document.getText=getText;document.version=5;
  change({document,contentChanges:[{rangeOffset:0,rangeLength:0,text:'x'}]});
  assert.equal(JSON.parse(input.trim().split('\n').at(-1)).source,document.getText(),'Skipped versions resynchronize with the full buffer');
  child.stdout.write(JSON.stringify({type:'frame',clientId:1,generation:1,revisionId:1,isStale:false})+'\n');
  await new Promise(r=>setImmediate(r));assert.equal(webMessages.at(-1).isStale,true);
  // A slow/hidden webview must not accumulate full PNG messages while typing.
  for(let i=0;i<20;i++)child.stdout.write(JSON.stringify({type:'frame',purpose:'edit',clientId:100+i,generation:100+i,revisionId:100+i,isStale:false})+'\n');
  await new Promise(r=>setImmediate(r));
  assert.equal(webMessages.filter(m=>m.type==='frame').length,1,'Only one frame may cross the bridge before the viewer acknowledges it');
  const firstDelivery=webMessages.find(m=>m.type==='frame').deliveryId;
  await receiver({type:'frame-ack',deliveryId:firstDelivery,outcome:'painted'});
  const newest=webMessages.filter(m=>m.type==='frame').at(-1);
  assert.equal(newest.clientId,119,'The next delivery is the newest completed frame');
  await receiver({type:'frame-ack',deliveryId:firstDelivery});
  assert.equal(webMessages.filter(m=>m.type==='frame').length,2,'Duplicate acknowledgements do not release a different frame');
  await receiver({type:'frame-ack',deliveryId:newest.deliveryId,outcome:'painted'});
  child.stdout.write(JSON.stringify({type:'status',state:'error',error:'Incomplete \\iffalse'})+'\n');
  await new Promise(r=>setImmediate(r));assert(outputLines.includes('Incomplete \\iffalse'));
  assert.equal(webMessages.at(-1).state,'error');
  await receiver({type:'sync-forward',file:'shared/body.tex',line:120,column:3,generation:1,requestId:'sync-late'});
  const lookup=JSON.parse(input.trim().split('\n').at(-1));
  assert.equal(lookup.type,'sync-forward');assert.equal(lookup.file,'shared/body.tex');assert.equal(lookup.requestId,'sync-late');
  child.stdout.write(JSON.stringify({type:'sync',generation:1,requestId:'sync-late',location:{page:99}})+'\n');
  await new Promise(r=>setImmediate(r));assert.equal(webMessages.at(-1).location.page,99);
  const backward={type:'sync-backward',page:1,x:40,y:100,generation:1,requestId:'reverse'};
  await receiver(backward);
  const reverseSent=JSON.parse(input.trim().split('\n').at(-1));
  for(const [key,value] of Object.entries(backward))assert.equal(reverseSent[key],value);
  for(const suffix of ['bib','ist','bbx','cbx','lbx']){
    const file=`references.${suffix}`,source=`unsaved ${suffix}`;
    change({document:{uri:{scheme:'file',fsPath:path.join(project,file)},getText:()=>source},contentChanges:[{text:source}]});
    const latest=JSON.parse(input.trim().split('\n').at(-1));
    assert.equal(latest.type,'edit');assert.equal(latest.file,file);assert.equal(latest.source,source);
  }
  assert.equal(watchPattern.base,project);
  let count=input.trim().split('\n').length;
  diskChange({fsPath:path.join(project,'figure.png')});diskCreate({fsPath:path.join(project,'new.tex')});diskDelete({fsPath:path.join(project,'old.bib')});
  await new Promise(r=>setTimeout(r,250));
  sent=input.trim().split('\n').map(JSON.parse);assert.equal(sent.length,count+1);
  assert.equal(sent.at(-1).type,'reload');assert.equal(sent.at(-1).overlays[main],document.getText());
  document.isDirty=false;sibling.isDirty=false;
  diskChange(document.uri);await new Promise(r=>setTimeout(r,250));
  assert.deepEqual(JSON.parse(input.trim().split('\n').at(-1)).overlays,{});
  count=input.trim().split('\n').length;
  diskChange({fsPath:path.join(project,'main.log')});diskChange({fsPath:path.join(project,'../outside.tex')});
  await new Promise(r=>setTimeout(r,250));assert.equal(input.trim().split('\n').length,count);
  diskChange(document.uri);disposed();await new Promise(r=>setTimeout(r,250));
  assert(watchDisposed);assert.equal(JSON.parse(input.trim().split('\n').at(-1)).type,'close');
  Module._load=original;
  if(pdfMode)fs.unlinkSync(log);
  const result={checks:managed?43:38,ok:true};fs.writeFileSync(path.join(root,`results/extension-${managed?'managed-tex':pdfMode?'pdflatex':'live'}.json`),JSON.stringify(result,null,2)+'\n');console.log(result);
})().catch(e=>{Module._load=original;console.error(e);process.exitCode=1;});
