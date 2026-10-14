const vscode=require('vscode');
const fs=require('fs');
const path=require('path');
const readline=require('readline');
const crypto=require('crypto');
const {performance}=require('perf_hooks');
const {configuration}=require('./configuration');
const {createFrameDelivery}=require('./frame-delivery');
const {createMacTexSetup}=require('./macos-tex');
const {contains,resolveMain,resolveProject,supportedFile,resolveCompiler}=require('./project');
function activate(context){
  const texSetup=createMacTexSetup({extensionPath:context.extensionPath,storagePath:context.globalStorageUri?.fsPath});
  context.subscriptions.push(texSetup);
  let panel,backend,project,currentFrame,suppressSelection,visiblePage=0,serial=0,latestMutation=0,output=vscode.window.createOutputChannel('TeXAstra');
  let watcher,reloadTimer,frameDelivery,ready=false,selectedOptions={};
  const editBases=new Map();
  const submittedBuffers=new Map(),savedContents=new Map();
  const fileKey=file=>process.platform==='win32'?path.resolve(file).toLowerCase():path.resolve(file);
  const fingerprint=text=>crypto.createHash('sha256').update(text.replace(/^\uFEFF/,'')).digest('hex');
  const rememberBuffers=overlays=>{
    submittedBuffers.clear();savedContents.clear();
    for(const doc of vscode.workspace.textDocuments){
      if(doc.uri.scheme!=='file'||!supportedFile(project,doc.uri.fsPath))continue;
      const relative=path.relative(project,doc.uri.fsPath).replaceAll('\\','/');
      if(!doc.isDirty||Object.hasOwn(overlays,relative))submittedBuffers.set(fileKey(doc.uri.fsPath),{document:doc,version:doc.version});
    }
  };
  const alreadySubmitted=async file=>{
    const key=fileKey(file);
    if(!savedContents.has(key)&&!submittedBuffers.has(key))return false;
    try{
      const disk=fingerprint(await fs.promises.readFile(file,'utf8'));
      if(disk===savedContents.get(key))return true;
      const known=submittedBuffers.get(key),doc=known?.document;
      // Checking bytes also handles watcher-before-save ordering and atomic
      // saves. An open document alone is not proof that an external edit is known.
      if(doc&&!doc.isClosed&&doc.version===known.version&&disk===fingerprint(doc.getText())){
        savedContents.set(key,disk);return true;
      }
    }catch{/* Missing or unreadable inputs must still invalidate the document. */}
    return false;
  };
  const distributionOptions=config=>Object.fromEntries(['runtimeMode','wslDistribution','texBinDirectory'].map(name=>[name,config.get(name,'')]).filter(([,value])=>value));
  context.subscriptions.push(vscode.commands.registerCommand('texastra.showEnvironment',async()=>{
    if(!vscode.workspace.isTrusted)return;
    try{
      const config=configuration(vscode.workspace,vscode.window.activeTextEditor?.document.uri);
      const options=panel?selectedOptions:await texSetup.withProgress(vscode,output,distributionOptions(config));
      const report=await require('../native/launch').environment(context.extensionPath,options);
      const document=await vscode.workspace.openTextDocument({language:'json',content:JSON.stringify(report,null,2)});
      await vscode.window.showTextDocument(document,{preview:false});
    }catch(error){output.appendLine(String(error));vscode.window.showErrorMessage(String(error));}
  }));
  const stop=()=>{ready=false;frameDelivery?.dispose();frameDelivery=null;editBases.clear();submittedBuffers.clear();savedContents.clear();clearTimeout(reloadTimer);watcher?.dispose();watcher=null;if(backend){backend.stdin.end('{"type":"close"}\n');backend=null;}currentFrame=null;};
  const dirtyBuffers=()=>Object.fromEntries(vscode.workspace.textDocuments
    .filter(doc=>doc.isDirty&&doc.uri.scheme==='file'&&contains(project,doc.uri.fsPath))
    .map(doc=>[path.relative(project,doc.uri.fsPath).replaceAll('\\','/'),doc.getText()]));
  const send=message=>{if(backend&&!backend.killed){
    if(message.type==='start'||message.type==='reload'){editBases.clear();rememberBuffers(message.overlays||{});}
    const clientId=++serial;
    if(message.type==='start'||message.type==='edit'||message.type==='reload'){
      latestMutation=clientId;currentFrame=null;
      panel?.webview.postMessage({type:'status',state:'building',clientId});
    }
    backend.stdin.write(JSON.stringify({...message,clientId,sentAt:message.sentAt??Date.now()})+'\n');
  }};
  context.subscriptions.push(output,vscode.commands.registerCommand('texastra.openDocument',async()=>{
    if(!vscode.workspace.isTrusted)return;
    if(panel){panel.reveal(vscode.ViewColumn.Beside);return;}
    const active=vscode.window.activeTextEditor?.document;
    const folder=(active&&vscode.workspace.getWorkspaceFolder(active.uri))||vscode.workspace.workspaceFolders?.[0];
    let config=configuration(vscode.workspace,active?.uri||folder?.uri);
    const read=file=>vscode.workspace.textDocuments.find(doc=>doc.uri.fsPath===file)?.getText()||fs.readFileSync(file,'utf8');
    let root;
    try{root=resolveMain({configured:config.get('mainFile',''),workspace:folder?.uri.fsPath,active:active?.uri.scheme==='file'?active.uri.fsPath:null,read});}
    catch(error){vscode.window.showErrorMessage(String(error));return;}
    if(!root){
      const chosen=await vscode.window.showOpenDialog({title:'Choose the main LaTeX document',canSelectMany:false,filters:{LaTeX:['tex']},defaultUri:folder?.uri});
      if(!chosen?.length)return;
      root=chosen[0].fsPath;
      config=configuration(vscode.workspace,chosen[0]);
    }
    const rootFolder=vscode.workspace.getWorkspaceFolder(vscode.Uri.file(root));
    config=configuration(vscode.workspace,vscode.Uri.file(root));
    let resolvedProject;
    try{resolvedProject=resolveProject({main:root,workspace:rootFolder?.uri.fsPath,configured:config.get('projectRoot','')});}
    catch(error){vscode.window.showErrorMessage(String(error));return;}
    let compilerLog='';
    try{
      const descriptor=fs.openSync(root.replace(/\.tex$/i,'.log'),'r');
      try{const buffer=Buffer.alloc(1024);compilerLog=buffer.toString('utf8',0,fs.readSync(descriptor,buffer,0,buffer.length,0));}
      finally{fs.closeSync(descriptor);}
    }catch{/* A document without a previous build uses its setting or magic comment. */}
    const compiler=resolveCompiler(config.get('compiler','auto'),read(root),compilerLog);
    let preparedOptions;
    try{preparedOptions=await texSetup.withProgress(vscode,output,distributionOptions(config));}
    catch(error){
      output.appendLine(String(error));
      if(error.name!=='AbortError')vscode.window.showErrorMessage(`TeX setup failed. Run TeXAstra: Open Document to retry. ${error} See Output → TeXAstra.`);
      return;
    }
    // Another invocation may have opened the preview while setup was running.
    if(panel){panel.reveal(vscode.ViewColumn.Beside);return;}
    if(!vscode.workspace.isTrusted)return;
    project=resolvedProject;
    selectedOptions=preparedOptions;
    const options={main:path.relative(project,root).replaceAll('\\','/'),mode:compiler==='lualatex'?'auto':'full',compiler,...selectedOptions};
    visiblePage=0;serial=0;latestMutation=0;currentFrame=null;
    output.appendLine(`Opening ${root} with ${compiler} and project root ${project}; resources and generated files stay in the user cache.`);
    panel=vscode.window.createWebviewPanel('texastraDocument','TeXAstra',vscode.ViewColumn.Beside,{enableScripts:true,retainContextWhenHidden:true,localResourceRoots:[vscode.Uri.joinPath(context.extensionUri,'webview')]});
    const web=panel.webview;
    const delivery=createFrameDelivery(message=>web.postMessage(message),line=>output.appendLine(line));
    frameDelivery=delivery;
    let html=fs.readFileSync(path.join(context.extensionPath,'webview/index.html'),'utf8');
    for(const asset of ['viewer.css','viewer.js'])html=html.replace(asset,web.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'webview',asset)).toString());
    const nonce=require('crypto').randomBytes(16).toString('hex');
    html=html.replace('<script src=',`<script nonce="${nonce}" src=`);
    html=html.replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src ${web.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">`);
    try{
      backend=require('../native/launch').launch(context.extensionPath,project,'auto',options);
    }catch(error){output.appendLine(String(error));vscode.window.showErrorMessage(String(error));panel.dispose();panel=null;return;}
    let runtimeError='';
    backend.stderr.on('data',chunk=>{runtimeError=(runtimeError+chunk.toString()).slice(-4000);output.append(chunk.toString());});
    backend.on('error',error=>{output.appendLine(String(error));web.postMessage({type:'status',state:'error',error:String(error)});});
    backend.on('exit',code=>{if(code)web.postMessage({type:'status',state:'error',error:`Backend exited (${code}). ${runtimeError} See Output → TeXAstra.`});});
    watcher=vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(project,'**/*'));
    const watchedBackend=backend,pendingDisk=new Map();let diskSequence=0;
    // These are output PDFs already excluded from the compiler's input mirror.
    const outputPdfs=new Set([root.replace(/\.tex$/i,'.pdf'),path.join(path.dirname(root),'main.pdf')].map(fileKey));
    const diskChanged=uri=>{
      if(!ready||!supportedFile(project,uri.fsPath)||outputPdfs.has(fileKey(uri.fsPath)))return;
      pendingDisk.set(fileKey(uri.fsPath),uri.fsPath);const sequence=++diskSequence;
      clearTimeout(reloadTimer);
      reloadTimer=setTimeout(async()=>{
        const known=await Promise.all([...pendingDisk.values()].map(alreadySubmitted));
        if(!ready||backend!==watchedBackend||sequence!==diskSequence)return;
        pendingDisk.clear();
        if(known.some(value=>!value))send({type:'reload',page:visiblePage,overlays:dirtyBuffers()});
      },200);
    };
    watcher.onDidCreate(diskChanged);watcher.onDidChange(diskChanged);watcher.onDidDelete(diskChanged);
    readline.createInterface({input:backend.stdout}).on('line',line=>{
      if(backend!==watchedBackend)return;
      const received=performance.now(),hostReceivedAt=Date.now();
      try{const message=JSON.parse(line),parseMs=performance.now()-received;if(message.type==='environment'){
        output.appendLine(JSON.stringify({...message.report,host:backend?.texastraEnvironment},null,2));return;
      }if(message.type==='frame-transport'){output.appendLine(JSON.stringify(message));return;
      }if(message.error){editBases.clear();submittedBuffers.clear();savedContents.clear();output.appendLine(String(message.error));}if(message.type==='frame'){
        if(message.environmentReport)output.appendLine(`Build environment report: ${message.environmentReport}`);
        if(message.clientId<latestMutation)message.isStale=true;
        if(!message.isStale&&(!currentFrame||message.generation>=currentFrame.generation))currentFrame=message;
        const imageEncodedBytes=message.image?.length||0;
        message.payloadBytes=Buffer.byteLength(line);message.imageEncodedBytes=imageEncodedBytes;
        message.nonImageBytes=message.payloadBytes-imageEncodedBytes;
        message.hostReceivedAt=hostReceivedAt;message.hostStagesMs={parse:parseMs};
        delivery.enqueue(message,performance.now());return;
      }else if(message.state)currentFrame=null;web.postMessage(message);}catch(error){output.appendLine(String(error));}
    });
    web.onDidReceiveMessage(async message=>{
      if(frameDelivery!==delivery)return;
      if(message.type==='ready'){
        delivery.reset();
        ready=true;
        send({type:'start',page:0,overlays:dirtyBuffers()});
      }else if(message.type==='navigate'){
        if(!currentFrame||currentFrame.isStale||message.generation!==currentFrame.generation||message.revisionId!==currentFrame.revisionId)return;
        const file=path.resolve(project,message.file);
        const relative=path.relative(project,file);
        if(!contains(project,file))return;
        const doc=await vscode.workspace.openTextDocument(file);
        const editor=await vscode.window.showTextDocument(doc,{viewColumn:vscode.ViewColumn.One,preserveFocus:false});
        const selection=new vscode.Selection(message.line,message.column,message.endLine,message.endColumn);
        suppressSelection={file,line:message.line,column:message.column};
        editor.selection=selection;editor.revealRange(selection,vscode.TextEditorRevealType.InCenterIfOutsideViewport);
      }else if(message.type==='frame-ack'){delivery.acknowledge(message);}
      else if(message.type==='paint'){output.appendLine(JSON.stringify(message));}
      else if(message.type==='viewport'){visiblePage=message.page;}
      else if(message.type==='page'||message.type==='sync-forward'||message.type==='sync-backward'){send(message);}
    });
    panel.onDidDispose(()=>{stop();panel=null;});web.html=html;
  }),vscode.workspace.onDidChangeTextDocument(event=>{
    const sentAt=Date.now();
    if(!panel||!event.contentChanges.length)return;
    const relative=path.relative(project,event.document.uri.fsPath).replaceAll('\\','/');
    if(event.document.uri.scheme!=='file'||!contains(project,event.document.uri.fsPath)||! /\.(tex|sty|cls|bib|bst|bbx|cbx|lbx|ist|csv|dat|txt|lua)$/i.test(relative))return;
    currentFrame=null;
    const doc=event.document,base=editBases.get(relative),version=doc.version;
    const changes=event.contentChanges.map(({rangeOffset,rangeLength,text})=>({rangeOffset,rangeLength,text}));
    const canPatch=base&&base.document===doc&&version===base.version+1&&changes.every(c=>
      Number.isInteger(c.rangeOffset)&&Number.isInteger(c.rangeLength)&&c.rangeOffset>=0&&c.rangeLength>=0&&c.rangeOffset+c.rangeLength<=base.length);
    let message,length;
    if(canPatch){
      length=base.length+changes.reduce((n,c)=>n+c.text.length-c.rangeLength,0);
      message={changes,baseVersion:base.version,baseLength:base.length};
    }else{
      const source=doc.getText();length=source.length;message={source};
    }
    editBases.set(relative,{document:doc,version,length});
    send({type:'edit',file:relative,...message,sourceVersion:version,page:visiblePage,sentAt});
    submittedBuffers.set(fileKey(doc.uri.fsPath),{document:doc,version});
  }),vscode.workspace.onDidSaveTextDocument(doc=>{
    if(!ready||doc.uri.scheme!=='file')return;
    const key=fileKey(doc.uri.fsPath),known=submittedBuffers.get(key);
    if(known?.document===doc&&known.version===doc.version)savedContents.set(key,fingerprint(doc.getText()));
  }),vscode.window.onDidChangeTextEditorSelection(event=>{
    if(!panel)return;
    const relative=path.relative(project,event.textEditor.document.uri.fsPath).replaceAll('\\','/');
    const position=event.selections[0]?.active;if(!position)return;
    if(suppressSelection&&suppressSelection.file===event.textEditor.document.uri.fsPath){suppressSelection=null;return;}
    panel.webview.postMessage({type:'forward',file:relative,line:position.line,column:position.character});
  }),{dispose:stop});
}
exports.activate=activate;
