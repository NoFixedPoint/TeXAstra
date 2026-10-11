const vscode=require('vscode');
const fs=require('fs');
const path=require('path');
const {spawn}=require('child_process');
const readline=require('readline');
function activate(context){
  let panel,backend,project,currentFrame,visiblePage=0,serial=0,output=vscode.window.createOutputChannel('BaKoMa prototype');
  const stop=()=>{if(backend){backend.stdin.end('{"type":"close"}\n');backend=null;}currentFrame=null;};
  const send=message=>{if(backend&&!backend.killed)backend.stdin.write(JSON.stringify({...message,clientId:++serial,sentAt:Date.now()})+'\n');};
  context.subscriptions.push(output,vscode.commands.registerCommand('bakoma.openPreview',async()=>{
    if(!vscode.workspace.isTrusted)return;
    if(panel){panel.reveal(vscode.ViewColumn.Beside);return;}
    const folder=vscode.workspace.workspaceFolders?.[0];if(!folder)return;
    const config=vscode.workspace.getConfiguration('bakoma');
    const root=path.resolve(folder.uri.fsPath,config.get('mainFile'));
    if(!fs.existsSync(root)){vscode.window.showErrorMessage(`Root document does not exist: ${root}`);return;}
    project=path.dirname(root);
    panel=vscode.window.createWebviewPanel('bakomaPreview','BaKoMa · prototype',vscode.ViewColumn.Beside,{enableScripts:true,retainContextWhenHidden:true,localResourceRoots:[vscode.Uri.joinPath(context.extensionUri,'webview')]});
    const web=panel.webview;
    let html=fs.readFileSync(path.join(context.extensionPath,'webview/index.html'),'utf8');
    for(const asset of ['viewer.css','viewer.js'])html=html.replace(asset,web.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'webview',asset)).toString());
    const nonce=require('crypto').randomBytes(16).toString('hex');
    html=html.replace('<script src=',`<script nonce="${nonce}" src=`);
    html=html.replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src ${web.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">`);
    backend=spawn(config.get('python'),['-u','-m','prototype.bridge','--project',project,'--engine',config.get('engine')],{cwd:context.extensionPath,windowsHide:true});
    backend.stderr.on('data',chunk=>output.append(chunk.toString()));
    backend.on('error',error=>{output.appendLine(String(error));web.postMessage({type:'status',state:'error',error:String(error)});});
    readline.createInterface({input:backend.stdout}).on('line',line=>{
      try{const message=JSON.parse(line);if(message.type==='frame'){message.isStale=message.isStale||message.clientId<serial;currentFrame=message;visiblePage=message.page;}else if(message.state)currentFrame=null;web.postMessage(message);}catch(error){output.appendLine(String(error));}
    });
    web.onDidReceiveMessage(async message=>{
      if(message.type==='ready'){
        send({type:'start',page:0});
        for(const doc of vscode.workspace.textDocuments){
          const relative=path.relative(project,doc.uri.fsPath).replaceAll('\\','/');
          if(doc.isDirty&&!relative.startsWith('../')&&!path.isAbsolute(relative))send({type:'edit',file:relative,source:doc.getText(),page:0});
        }
      }else if(message.type==='navigate'){
        if(!currentFrame||currentFrame.isStale)return;
        const file=path.resolve(project,message.file);
        const relative=path.relative(project,file);
        if(relative.startsWith('..')||path.isAbsolute(relative))return;
        const doc=await vscode.workspace.openTextDocument(file);
        const editor=await vscode.window.showTextDocument(doc,{viewColumn:vscode.ViewColumn.One,preserveFocus:false});
        const selection=new vscode.Selection(message.line,message.column,message.endLine,message.endColumn);
        editor.selection=selection;editor.revealRange(selection,vscode.TextEditorRevealType.InCenterIfOutsideViewport);
      }else if(message.type==='paint'){output.appendLine(JSON.stringify(message));}
      else if(message.type==='page'){currentFrame=null;send(message);}
    });
    panel.onDidDispose(()=>{stop();panel=null;});web.html=html;
  }),vscode.workspace.onDidChangeTextDocument(event=>{
    if(!panel||!event.contentChanges.length)return;
    const relative=path.relative(project,event.document.uri.fsPath).replaceAll('\\','/');
    if(relative.startsWith('../')||path.isAbsolute(relative)||!relative.endsWith('.tex'))return;
    currentFrame=null;
    send({type:'edit',file:relative,source:event.document.getText(),page:visiblePage});
  }),vscode.window.onDidChangeTextEditorSelection(event=>{
    if(!panel)return;
    const relative=path.relative(project,event.textEditor.document.uri.fsPath).replaceAll('\\','/');
    const position=event.selections[0]?.active;if(!position)return;
    panel.webview.postMessage({type:'forward',file:relative,line:position.line,column:position.character});
  }),{dispose:stop});
}
exports.activate=activate;
