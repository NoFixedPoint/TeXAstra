/* Test host: the real extension + backend + viewer, with VS Code APIs mocked.
 * Only the HTTP bridge and editor event source are substituted. */
const fs=require('fs'),path=require('path'),http=require('http'),Module=require('module');
const options=Object.fromEntries(Array.from({length:(process.argv.length-2)/2},(_,i)=>process.argv.slice(2+i*2,4+i*2)));
const root=path.resolve(options['--extension']||path.join(__dirname,'..'));
const project=path.resolve(options['--project']),main=options['--main'],port=Number(options['--port']);
let command,change,save,diskChange,receiver,dispose,backend,lastEdit,events=[],stream;
const requests=[];
const diagnostics=[];
const workspaceRelative=path.relative(fs.realpathSync(path.resolve(__dirname,'../.work')),fs.realpathSync(path.join(project,main)));
const allowSave=options['--allow-save']==='yes'&&workspaceRelative!==''&&!workspaceRelative.startsWith('..')&&!path.isAbsolute(workspaceRelative);
const document={uri:{scheme:'file',fsPath:path.join(project,main)},isDirty:false,version:1,
  source:fs.readFileSync(path.join(project,main),'utf8').replace(/\r\n?/g,'\n'),getText(){return this.source;}};
const web={cspSource:'self',asWebviewUri:u=>'/'+path.basename(u.fsPath),onDidReceiveMessage:f=>{receiver=f;},
  postMessage:m=>{if(stream)stream.write('data: '+JSON.stringify(m)+'\n\n');else events.push(m);}};
const panel={webview:web,onDidDispose:f=>{dispose=f;},reveal(){},dispose(){dispose?.();}};
const config={mainFile:main,runtimeMode:'wsl'};
const vscode={Uri:{file:fsPath=>({fsPath}),joinPath:(base,...parts)=>({fsPath:path.join(base.fsPath,...parts)})},ViewColumn:{Beside:2},
  RelativePattern:class {},commands:{registerCommand:(name,f)=>{if(name==='texastra.openDocument')command=f;}},
  workspace:{isTrusted:true,textDocuments:[document],workspaceFolders:[{uri:{fsPath:project}}],
    getWorkspaceFolder:()=>({uri:{fsPath:project}}),getConfiguration:()=>({get:(name,fallback)=>config[name]??fallback}),
    onDidChangeTextDocument:f=>{change=f;},onDidSaveTextDocument:f=>{save=f;},createFileSystemWatcher:()=>({onDidCreate(){},onDidChange:f=>{diskChange=f;},onDidDelete(){},dispose(){}})},
  window:{activeTextEditor:{document},createOutputChannel:()=>({append(){},appendLine(line){
    try{const item=JSON.parse(line);if(['paint','frame-transport','frame-delivery'].includes(item.type))diagnostics.push(item);}catch{}
  }}),createWebviewPanel:()=>panel,
    onDidChangeTextEditorSelection(){},showErrorMessage:m=>{throw Error(m);}}};
const original=Module._load;
Module._load=function(name,parent,...rest){
  if(name==='vscode')return vscode;
  // Benchmark the caller's already-provisioned TeX environment, without first-use UI.
  if(name==='./macos-tex')return {createMacTexSetup:()=>({dispose(){},withProgress:async(_vscode,_output,options)=>options})};
  const value=original.call(this,name,parent,...rest);
  if(name==='../native/launch')return {...value,launch:(...args)=>{
    backend=value.launch(...args);const write=backend.stdin.write.bind(backend.stdin);
    backend.stdin.write=(data,...args)=>{const request=JSON.parse(data);requests.push({type:request.type,clientId:request.clientId,sentAt:request.sentAt});if(request.type==='edit')lastEdit={clientId:request.clientId,sentAt:request.sentAt,bytes:Buffer.byteLength(data),delta:!('source' in request)};return write(data,...args);};
    return backend;
  }};
  return value;
};
function output(res,data){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(data));}
(async()=>{
  require(path.join(root,'extension/extension')).activate({subscriptions:[],extensionPath:root,extensionUri:{fsPath:root}});
  await command();
  const server=http.createServer(async(req,res)=>{
    try{
      if(req.headers.host!==`127.0.0.1:${port}`){res.writeHead(403);res.end();return;}
      if(req.method==='GET'){
        if(req.url==='/requests'){output(res,requests);return;}
        if(req.url==='/diagnostics'){output(res,diagnostics);return;}
        if(req.url==='/events'){
          stream=res;res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store'});res.write(': ready\n\n');
          for(const event of events)res.write('data: '+JSON.stringify(event)+'\n\n');events=[];
          req.on('close',()=>{if(stream===res)stream=null;});return;
        }
        if(req.url==='/'){
          res.setHeader('Content-Type','text/html');res.end(web.html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/,''));return;
        }
        if(['/viewer.js','/viewer.css'].includes(req.url)){
          res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':'text/css');res.end(fs.readFileSync(path.join(root,'webview',req.url.slice(1))));return;
        }
      }
      if(req.method==='POST'){
        const chunks=[];for await(const chunk of req)chunks.push(chunk);
        const data=JSON.parse(Buffer.concat(chunks));
        if(req.url==='/action'){await receiver(data);output(res,{});return;}
        if(req.url==='/edit'){
          for(const c of [...data.changes].sort((a,b)=>b.rangeOffset-a.rangeOffset))
            document.source=document.source.slice(0,c.rangeOffset)+c.text+document.source.slice(c.rangeOffset+c.rangeLength);
          document.version++;document.isDirty=true;change({document,contentChanges:data.changes});output(res,lastEdit);return;
        }
        if(req.url==='/save'){
          if(!allowSave)throw Error('Save tests require --allow-save yes and a project copy under .work');
          const savedAt=Date.now(),requestCount=requests.length;
          fs.writeFileSync(document.uri.fsPath,document.source);document.isDirty=false;
          save?.(document);diskChange(document.uri);output(res,{savedAt,requestCount});return;
        }
        if(req.url==='/close'){dispose?.();output(res,{});stream?.end();server.close();return;}
      }
      res.writeHead(404);res.end();
    }catch(error){res.writeHead(500);res.end(String(error));}
  });
  server.listen(port,'127.0.0.1',()=>console.log('ready'));
})().catch(error=>{console.error(error);backend?.stdin.end('{"type":"close"}\n');process.exitCode=1;});
