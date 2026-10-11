const vscode=require('vscode');
const fs=require('fs');
const path=require('path');
const readline=require('readline');
const {contains,resolveMain}=require('./project');
function activate(context){
  let panel,backend,project,currentFrame,suppressSelection,visiblePage=0,serial=0,latestMutation=0,output=vscode.window.createOutputChannel('BaKoMa prototype');
  const stop=()=>{if(backend){backend.stdin.end('{"type":"close"}\n');backend=null;}currentFrame=null;};
  const send=message=>{if(backend&&!backend.killed){
    const clientId=++serial;
    if(message.type==='start'||message.type==='edit'){
      latestMutation=clientId;currentFrame=null;
      panel?.webview.postMessage({type:'status',state:'building',clientId});
    }
    backend.stdin.write(JSON.stringify({...message,clientId,sentAt:message.sentAt??Date.now()})+'\n');
  }};
  context.subscriptions.push(output,vscode.commands.registerCommand('bakoma.openPreview',async()=>{
    if(!vscode.workspace.isTrusted)return;
    if(panel){panel.reveal(vscode.ViewColumn.Beside);return;}
    const active=vscode.window.activeTextEditor?.document;
    const folder=(active&&vscode.workspace.getWorkspaceFolder(active.uri))||vscode.workspace.workspaceFolders?.[0];
    let config=vscode.workspace.getConfiguration('bakoma',active?.uri||folder?.uri);
    const read=file=>vscode.workspace.textDocuments.find(doc=>doc.uri.fsPath===file)?.getText()||fs.readFileSync(file,'utf8');
    let root;
    try{root=resolveMain({configured:config.get('mainFile',''),workspace:folder?.uri.fsPath,active:active?.uri.scheme==='file'?active.uri.fsPath:null,read});}
    catch(error){vscode.window.showErrorMessage(String(error));return;}
    if(!root){
      const chosen=await vscode.window.showOpenDialog({title:'Choose the main LaTeX document',canSelectMany:false,filters:{LaTeX:['tex']},defaultUri:folder?.uri});
      if(!chosen?.length)return;
      root=chosen[0].fsPath;
      config=vscode.workspace.getConfiguration('bakoma',chosen[0]);
    }
    project=path.dirname(root);
    // Opening our preview always starts our compiler, independently of the
    // editor's previous XeLaTeX/pdfLaTeX settings or existing output files.
    const options={main:path.basename(root),mode:'auto',compiler:'lualatex'};
    visiblePage=0;serial=0;latestMutation=0;currentFrame=null;
    output.appendLine(`Opening ${root} in the live compiler; resources and generated files stay in the user cache.`);
    panel=vscode.window.createWebviewPanel('bakomaPreview','BaKoMa · prototype',vscode.ViewColumn.Beside,{enableScripts:true,retainContextWhenHidden:true,localResourceRoots:[vscode.Uri.joinPath(context.extensionUri,'webview')]});
    const web=panel.webview;
    let html=fs.readFileSync(path.join(context.extensionPath,'webview/index.html'),'utf8');
    for(const asset of ['viewer.css','viewer.js'])html=html.replace(asset,web.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'webview',asset)).toString());
    const nonce=require('crypto').randomBytes(16).toString('hex');
    html=html.replace('<script src=',`<script nonce="${nonce}" src=`);
    html=html.replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src ${web.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">`);
    try{
      backend=require('../native/launch').launch(context.extensionPath,project,'fork',options);
    }catch(error){output.appendLine(String(error));vscode.window.showErrorMessage(String(error));panel.dispose();panel=null;return;}
    backend.stderr.on('data',chunk=>output.append(chunk.toString()));
    backend.on('error',error=>{output.appendLine(String(error));web.postMessage({type:'status',state:'error',error:String(error)});});
    backend.on('exit',code=>{if(code)web.postMessage({type:'status',state:'error',error:`Backend exited (${code}). See Output → BaKoMa prototype.`});});
    readline.createInterface({input:backend.stdout}).on('line',line=>{
      try{const message=JSON.parse(line);if(message.error)output.appendLine(String(message.error));if(message.type==='frame'){
        if(message.clientId<latestMutation)message.isStale=true;
        if(!message.isStale&&(!currentFrame||message.generation>=currentFrame.generation))currentFrame=message;
      }else if(message.state)currentFrame=null;web.postMessage(message);}catch(error){output.appendLine(String(error));}
    });
    web.onDidReceiveMessage(async message=>{
      if(message.type==='ready'){
        const overlays={};
        for(const doc of vscode.workspace.textDocuments){
          const relative=path.relative(project,doc.uri.fsPath).replaceAll('\\','/');
          if(doc.isDirty&&doc.uri.scheme==='file'&&contains(project,doc.uri.fsPath))overlays[relative]=doc.getText();
        }
        send({type:'start',page:0,overlays});
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
      }else if(message.type==='paint'){output.appendLine(JSON.stringify(message));}
      else if(message.type==='viewport'){visiblePage=message.page;}
      else if(message.type==='page'||message.type==='sync-forward'){send(message);}
    });
    panel.onDidDispose(()=>{stop();panel=null;});web.html=html;
  }),vscode.workspace.onDidChangeTextDocument(event=>{
    const sentAt=Date.now();
    if(!panel||!event.contentChanges.length)return;
    const relative=path.relative(project,event.document.uri.fsPath).replaceAll('\\','/');
    if(event.document.uri.scheme!=='file'||!contains(project,event.document.uri.fsPath)||! /\.(tex|sty|cls|bib|bst|bbx|cbx|lbx|ist|csv|dat|txt|lua)$/i.test(relative))return;
    currentFrame=null;
    send({type:'edit',file:relative,source:event.document.getText(),page:visiblePage,sentAt});
  }),vscode.window.onDidChangeTextEditorSelection(event=>{
    if(!panel)return;
    const relative=path.relative(project,event.textEditor.document.uri.fsPath).replaceAll('\\','/');
    const position=event.selections[0]?.active;if(!position)return;
    if(suppressSelection&&suppressSelection.file===event.textEditor.document.uri.fsPath){suppressSelection=null;return;}
    panel.webview.postMessage({type:'forward',file:relative,line:position.line,column:position.character});
  }),{dispose:stop});
}
exports.activate=activate;
