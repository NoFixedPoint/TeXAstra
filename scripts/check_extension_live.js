/* Exercise the VS Code command with legacy settings and an unsaved buffer. */
const assert=require('assert'),fs=require('fs'),path=require('path'),Module=require('module');
const {EventEmitter}=require('events'),{PassThrough}=require('stream');
const root=path.resolve(__dirname,'..'),project=path.join(root,'.work/scroll-case');
const document={uri:{scheme:'file',fsPath:path.join(project,'paper.tex')},isDirty:true,getText:()=>fs.readFileSync(path.join(project,'paper.tex'),'utf8')+'% unsaved\n'};
const editor={document};let command,receiver,change,launchArgs,disposed,webMessages=[];
const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
let input='';child.stdin.on('data',c=>input+=c);
const web={cspSource:'test',asWebviewUri:u=>u.fsPath,postMessage:m=>{webMessages.push(m);},onDidReceiveMessage:f=>{receiver=f;}};
const panel={webview:web,onDidDispose:f=>{disposed=f;},reveal(){},dispose(){disposed?.();}};
const config={mainFile:'paper.tex',engine:'native',previewMode:'full',latexCompiler:'xelatex'};
const vscode={
  Uri:{joinPath:(base,...s)=>({fsPath:path.join(base.fsPath,...s)})},ViewColumn:{Beside:2,One:1},
  commands:{registerCommand:(name,f)=>{command=f;}},
  workspace:{isTrusted:true,textDocuments:[document],workspaceFolders:[{uri:{fsPath:project}}],
    getWorkspaceFolder:()=>({uri:{fsPath:project}}),getConfiguration:()=>({get:(k,d)=>config[k]??d}),
    onDidChangeTextDocument:f=>{change=f;}},
  window:{activeTextEditor:editor,createOutputChannel:()=>({append(){},appendLine(){}}),
    createWebviewPanel:()=>panel,onDidChangeTextEditorSelection:()=>{},showErrorMessage:m=>{throw Error(m);}}
};
const original=Module._load;
Module._load=function(request,parent,...rest){
  if(request==='vscode')return vscode;
  if(request==='../native/launch')return {launch:(...args)=>{launchArgs=args;return child;}};
  return original.call(this,request,parent,...rest);
};
(async()=>{
  require('../extension/extension').activate({subscriptions:[],extensionPath:root,extensionUri:{fsPath:root}});
  await command();await receiver({type:'ready'});
  assert.deepStrictEqual(launchArgs.slice(1),[project,'fork',{main:'paper.tex',mode:'auto',compiler:'lualatex'}]);
  let sent=input.trim().split('\n').map(JSON.parse);
  assert.equal(sent[0].overlays['paper.tex'],document.getText());
  assert(web.html.includes('id="pages"'));
  change({document,contentChanges:[{text:'x'}]});
  sent=input.trim().split('\n').map(JSON.parse);assert.equal(sent[1].type,'edit');assert.equal(sent[1].source,document.getText());
  assert.equal(webMessages.at(-1).state,'building');
  child.stdout.write(JSON.stringify({type:'frame',clientId:1,generation:1,revisionId:1,isStale:false})+'\n');
  await new Promise(r=>setImmediate(r));assert.equal(webMessages.at(-1).isStale,true);
  disposed();Module._load=original;
  const result={checks:5,ok:true};fs.writeFileSync(path.join(root,'results/extension-live.json'),JSON.stringify(result,null,2)+'\n');console.log(result);
})().catch(e=>{Module._load=original;console.error(e);process.exitCode=1;});
