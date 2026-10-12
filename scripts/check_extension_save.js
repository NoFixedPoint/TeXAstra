/* Save notifications must preserve the compiler state already updated by edits. */
const assert=require('assert/strict'),fs=require('fs'),path=require('path'),Module=require('module');
const {EventEmitter}=require('events'),{PassThrough}=require('stream');
const root=path.resolve(__dirname,'..'),project=fs.mkdtempSync(path.join(root,'.work/save-events-'));
const main=path.join(project,'paper.tex');
const document={uri:{scheme:'file',fsPath:main},version:1,isDirty:false,
  text:'\\documentclass{article}\n\\begin{document}Original.\\end{document}\n',getText(){return this.text;}};
fs.writeFileSync(main,document.text);
let command,change,save,receive,dispose,onChange,onCreate,onDelete;
const sent=[],messages=[],checks=[];
const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
child.stdin.on('data',data=>{for(const line of data.toString().trim().split('\n'))sent.push(JSON.parse(line));});
const web={cspSource:'test',asWebviewUri:u=>u.fsPath,postMessage:m=>messages.push(m),onDidReceiveMessage:f=>{receive=f;}};
const panel={webview:web,onDidDispose:f=>{dispose=f;},reveal(){},dispose(){dispose?.();}};
const vscode={Uri:{file:fsPath=>({fsPath}),joinPath:(base,...parts)=>({fsPath:path.join(base.fsPath,...parts)})},ViewColumn:{Beside:2},
  RelativePattern:class {},commands:{registerCommand:(name,f)=>{if(name==='texastra.openDocument')command=f;}},
  workspace:{isTrusted:true,textDocuments:[document],workspaceFolders:[{uri:{fsPath:project}}],
    getWorkspaceFolder:()=>({uri:{fsPath:project}}),getConfiguration:()=>({get:(key,fallback)=>key==='mainFile'?'paper.tex':fallback}),
    onDidChangeTextDocument:f=>{change=f;},onDidSaveTextDocument:f=>{save=f;},
    createFileSystemWatcher:()=>({onDidChange:f=>{onChange=f;},onDidCreate:f=>{onCreate=f;},onDidDelete:f=>{onDelete=f;},dispose(){}})},
  window:{activeTextEditor:{document},createOutputChannel:()=>({append(){},appendLine(){}}),
    createWebviewPanel:()=>panel,onDidChangeTextEditorSelection(){},showErrorMessage:m=>{throw Error(m);}}};
const original=Module._load;
Module._load=function(name,parent,...rest){if(name==='vscode')return vscode;if(name==='../native/launch')return {launch:()=>child};return original.call(this,name,parent,...rest);};
const settle=()=>new Promise(resolve=>setTimeout(resolve,300));
function check(name,condition){checks.push({name,ok:!!condition});console.log(name,!!condition);assert(condition,name);}
function edit(){document.text=document.text.replace('Original.','Original.x');document.version++;document.isDirty=true;
  change({document,contentChanges:[{rangeOffset:document.text.indexOf('Original.')+9,rangeLength:0,text:'x'}]});}
function writeSave(){fs.writeFileSync(main,document.text);document.isDirty=false;save?.(document);}
(async()=>{
  try{
    require('../extension/extension').activate({subscriptions:[],extensionPath:root,extensionUri:{fsPath:root}});
    await command();await receive({type:'ready'});
    let count=sent.length;
    writeSave();onChange(document.uri);await settle();
    check('saving unchanged initial source sends no rebuild',sent.length===count);
    edit();const before=sent.length,states=messages.length;
    writeSave();onChange(document.uri);await settle();
    check('saving an already submitted edit sends no rebuild',sent.length===before);
    check('save preserves the current preview state',messages.length===states);
    edit();check('first edit after saving retains its delta base',!Object.hasOwn(sent.at(-1),'source'));
    writeSave();onChange(document.uri);edit();count=sent.length;await settle();
    check('typing after Save before watcher delivery sends no rebuild',sent.length===count);
    onChange(document.uri);await settle();
    check('delayed duplicate save notifications send no rebuild',sent.length===count);
    fs.writeFileSync(main,document.text);document.isDirty=false;
    onChange(document.uri);await settle();save?.(document);
    check('watcher arriving before save callback sends no rebuild',sent.length===count);
    fs.unlinkSync(main);onDelete(document.uri);fs.writeFileSync(main,document.text);onCreate(document.uri);onChange(document.uri);
    await settle();check('atomic-save delete/create events send no rebuild',sent.length===count);
    // Another extension commonly rewrites the document PDF on every save.
    for(const name of ['paper.pdf','main.pdf']){
      const uri={fsPath:path.join(project,name)};fs.writeFileSync(uri.fsPath,'PDF output');onCreate(uri);onChange(uri);
    }
    await settle();check('generated document PDFs do not trigger reloads',sent.length===count);
    // A saved snapshot remains known after closing its editor buffer.
    document.isClosed=true;vscode.workspace.textDocuments=[];onChange(document.uri);await settle();
    check('late save notification after editor closes sends no rebuild',sent.length===count);
    document.isClosed=false;vscode.workspace.textDocuments=[document];
    edit();count=sent.length;
    fs.writeFileSync(main,'External edit.');onChange(document.uri);await settle();
    check('different external source content still reloads',sent.length===count+1&&sent.at(-1).type==='reload');
    check('external reload preserves unsaved editor text',sent.at(-1).overlays['paper.tex']===document.text);
    // A no-op source notification must never swallow a real figure update.
    count=sent.length;writeSave();onChange(document.uri);
    const figure={fsPath:path.join(project,'figure.pdf')};fs.writeFileSync(figure.fsPath,'Changed figure');onChange(figure);
    await settle();check('figure PDF updates mixed with Save still reload',sent.length===count+1&&sent.at(-1).type==='reload');
    count=sent.length;fs.unlinkSync(main);onDelete(document.uri);await settle();
    check('actual source deletion still reloads',sent.length===count+1&&sent.at(-1).type==='reload');
    count=sent.length;const added={fsPath:path.join(project,'new.tex')};fs.writeFileSync(added.fsPath,'New input');onCreate(added);await settle();
    check('new input files still reload',sent.length===count+1&&sent.at(-1).type==='reload');
    fs.writeFileSync(main,document.text);edit();writeSave();count=sent.length;
    child.stdout.write(JSON.stringify({type:'status',state:'error',error:'Rejected source update'})+'\n');
    await new Promise(resolve=>setImmediate(resolve));onChange(document.uri);await settle();
    check('backend errors invalidate save suppression',sent.length===count+1&&sent.at(-1).type==='reload');
    const bibliography={uri:{scheme:'file',fsPath:path.join(project,'refs.bib')},version:1,isDirty:true,text:'@book{x,title={Saved}}',getText(){return this.text;}};
    vscode.workspace.textDocuments.push(bibliography);
    change({document:bibliography,contentChanges:[{rangeOffset:0,rangeLength:0,text:bibliography.text}]});
    count=sent.length;fs.writeFileSync(bibliography.uri.fsPath,bibliography.text);bibliography.isDirty=false;save?.(bibliography);onCreate(bibliography.uri);await settle();
    check('already submitted bibliography Save avoids a second rebuild',sent.length===count);
    fs.writeFileSync(figure.fsPath,'Later figure');onChange(figure);dispose();await settle();
    check('closing preview cancels pending reloads',sent.length===count+1&&sent.at(-1).type==='close');
  }finally{
    dispose?.();Module._load=original;
    fs.writeFileSync(path.join(root,'results/extension-save.json'),JSON.stringify({checks},null,2)+'\n');
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
