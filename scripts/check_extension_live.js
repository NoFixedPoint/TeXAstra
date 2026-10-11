/* Exercise the VS Code command with legacy settings and an unsaved buffer. */
const assert=require('assert'),fs=require('fs'),path=require('path'),Module=require('module');
const {EventEmitter}=require('events'),{PassThrough}=require('stream');
const root=path.resolve(__dirname,'..'),project=path.join(root,'.work/extension-project'),main='paper/paper.tex';
fs.mkdirSync(path.join(project,'paper'),{recursive:true});
fs.writeFileSync(path.join(project,main),'\\documentclass{article}\n\\begin{document}Example.\\end{document}\n');
const document={uri:{scheme:'file',fsPath:path.join(project,main)},isDirty:true,getText:()=>fs.readFileSync(path.join(project,main),'utf8')+'% unsaved\n'};
const sibling={uri:{scheme:'file',fsPath:path.join(project,'shared/body.tex')},isDirty:true,getText:()=> 'Unsaved sibling.'};
const editor={document};let command,environmentCommand,environmentArgs,environmentDocument,receiver,change,launchArgs,disposed,webMessages=[],outputLines=[];
const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
let input='';child.stdin.on('data',c=>input+=c);
const web={cspSource:'test',asWebviewUri:u=>u.fsPath,postMessage:m=>{webMessages.push(m);},onDidReceiveMessage:f=>{receiver=f;}};
const panel={webview:web,onDidDispose:f=>{disposed=f;},reveal(){},dispose(){disposed?.();}};
let diskChange,diskCreate,diskDelete,watchDisposed=false,watchPattern;
const watcher={onDidChange:f=>{diskChange=f;},onDidCreate:f=>{diskCreate=f;},onDidDelete:f=>{diskDelete=f;},dispose:()=>{watchDisposed=true;}};
const config={checkpointMode:'internal',mainFile:main,engine:'native',previewMode:'full',latexCompiler:'xelatex',wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'};
const vscode={
  Uri:{file:fsPath=>({fsPath}),joinPath:(base,...s)=>({fsPath:path.join(base.fsPath,...s)})},ViewColumn:{Beside:2,One:1},
  RelativePattern:class {constructor(base,pattern){this.base=base;this.pattern=pattern;}},
  commands:{registerCommand:(name,f)=>{if(name==='bakoma.showEnvironment')environmentCommand=f;else command=f;}},
  workspace:{isTrusted:true,textDocuments:[document,sibling],workspaceFolders:[{uri:{fsPath:project}}],
    getWorkspaceFolder:()=>({uri:{fsPath:project}}),getConfiguration:()=>({get:(k,d)=>config[k]??d}),
    onDidChangeTextDocument:f=>{change=f;},createFileSystemWatcher:p=>{watchPattern=p;return watcher;},openTextDocument:async options=>{environmentDocument=options;return options;}},
  window:{activeTextEditor:editor,createOutputChannel:()=>({append(){},appendLine:s=>outputLines.push(s)}),
    createWebviewPanel:()=>panel,onDidChangeTextEditorSelection:()=>{},showTextDocument:async()=>{},showErrorMessage:m=>{throw Error(m);}}
};
const original=Module._load;
Module._load=function(request,parent,...rest){
  if(request==='vscode')return vscode;
  if(request==='../native/launch')return {launch:(...args)=>{launchArgs=args;return child;},environment:async(...args)=>{environmentArgs=args;return {ok:true,binDirectory:'/selected/bin'};}};
  return original.call(this,request,parent,...rest);
};
(async()=>{
  require('../extension/extension').activate({subscriptions:[],extensionPath:root,extensionUri:{fsPath:root}});
  await command();await receiver({type:'ready'});
  assert.deepStrictEqual(launchArgs.slice(1),[project,'fork',{main,mode:'auto',compiler:'lualatex',wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'}]);
  await environmentCommand();assert.deepStrictEqual(environmentArgs,[root,{wslDistribution:'Test Linux',texBinDirectory:'/selected/bin'}]);
  assert.equal(environmentDocument.language,'json');assert.equal(JSON.parse(environmentDocument.content).binDirectory,'/selected/bin');
  child.stdout.write(JSON.stringify({type:'environment',report:{ok:true,binDirectory:'/selected/bin'}})+'\n');
  await new Promise(r=>setImmediate(r));assert(outputLines.some(line=>line.includes('/selected/bin')));
  let sent=input.trim().split('\n').map(JSON.parse);
  assert.equal(sent[0].overlays[main],document.getText());
  assert.equal(sent[0].overlays['shared/body.tex'],sibling.getText());
  assert(web.html.includes('id="pages"'));
  const now=Date.now,getText=document.getText;let clock=1000;
  Date.now=()=>clock;document.getText=()=>{clock+=50;return getText();};
  try{change({document,contentChanges:[{text:'x'}]});}
  finally{Date.now=now;document.getText=getText;}
  sent=input.trim().split('\n').map(JSON.parse);assert.equal(sent[1].type,'edit');assert.equal(sent[1].source,document.getText());
  assert.equal(sent[1].sentAt,1000,'Latency begins before reading the editor buffer');
  assert.equal(webMessages.at(-1).state,'building');
  child.stdout.write(JSON.stringify({type:'frame',clientId:1,generation:1,revisionId:1,isStale:false})+'\n');
  await new Promise(r=>setImmediate(r));assert.equal(webMessages.at(-1).isStale,true);
  child.stdout.write(JSON.stringify({type:'status',state:'error',error:'Incomplete \\iffalse'})+'\n');
  await new Promise(r=>setImmediate(r));assert(outputLines.includes('Incomplete \\iffalse'));
  assert.equal(webMessages.at(-1).state,'error');
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
  const result={checks:22,ok:true};fs.writeFileSync(path.join(root,'results/extension-live.json'),JSON.stringify(result,null,2)+'\n');console.log(result);
})().catch(e=>{Module._load=original;console.error(e);process.exitCode=1;});
