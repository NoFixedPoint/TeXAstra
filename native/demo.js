/* Loopback browser adapter. Source mapping, compilation and rendering are C++. */
const fs=require('fs'),path=require('path'),http=require('http'),readline=require('readline');
const {launch}=require('./launch');
const {spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
let port=8765,project=path.join(root,'corpus'),engine='cpp',checkpoint=process.env.BAKO_CHECKPOINT_MODE||'auto';
const options={};
for(let i=2;i<process.argv.length;i++){
  if(process.argv[i]==='--port')port=Number(process.argv[++i]);
  else if(process.argv[i]==='--project')project=path.resolve(process.argv[++i]);
  else if(process.argv[i]==='--engine')engine=process.argv[++i];
  else if(process.argv[i]==='--checkpoint')checkpoint=process.argv[++i];
  else if(process.argv[i]==='--main')options.main=process.argv[++i];
  else if(process.argv[i]==='--runtime')options.runtime=path.resolve(process.argv[++i]);
  else if(process.argv[i]==='--runtime-mode')options.runtimeMode=process.argv[++i];
  else if(process.argv[i]==='--tex-bin')options.texBinDirectory=process.argv[++i];
  else if(process.argv[i]==='--wsl-distribution')options.wslDistribution=process.argv[++i];
  else throw new Error('Unknown argument '+process.argv[i]);
}
if(!['cpp','stream'].includes(engine))throw new Error('Use cpp or stream for the comparison');
const backend=engine==='cpp'?launch(root,project,checkpoint,options):spawn(process.env.BAKOMA_PYTHON||'python',['-u','-m','prototype.bridge','--project',project,'--engine','stream'],{cwd:root,windowsHide:true});
const messages=[],waiting=new Set(),overlays=new Map();
let event=0,revision=0,closed=false;
function output(res,status,data,kind='application/json'){
  if(res.destroyed)return;
  const bytes=Buffer.isBuffer(data)?data:Buffer.from(JSON.stringify(data));
  res.writeHead(status,{'Content-Type':kind,'Content-Length':bytes.length,'Cache-Control':'no-store'});res.end(bytes);
}
function events(){for(const pending of waiting){const data=messages.filter(m=>m.event>pending.after);if(data.length){clearTimeout(pending.timer);waiting.delete(pending);output(pending.res,200,data);}}}
readline.createInterface({input:backend.stdout}).on('line',line=>{
  try{const message=JSON.parse(line);message.event=++event;messages.push(message);if(messages.length>32)messages.shift();events();}
  catch(error){process.stderr.write('Backend protocol error: '+error+'\n');}
});
backend.stderr.on('data',chunk=>process.stderr.write(chunk));
backend.on('error',error=>process.stderr.write(String(error)+'\n'));
backend.on('exit',code=>{closed=true;if(code)process.stderr.write(`C++ backend exited (${code})\n`);});
function sourcePath(file){const full=path.resolve(project,file),relative=path.relative(project,full);if(relative.startsWith('..')||path.isAbsolute(relative))throw new Error('Source path escapes project');return full;}
const server=http.createServer(async(req,res)=>{
  try{
    const allowed=[`127.0.0.1:${port}`,`localhost:${port}`];
    if(!allowed.includes(req.headers.host))return output(res,403,{});
    if(req.headers.origin&&!allowed.map(host=>'http://'+host).includes(req.headers.origin))return output(res,403,{});
    const url=new URL(req.url,'http://localhost');
    if(req.method==='GET'){
      if(url.pathname==='/bootstrap')return output(res,200,{event,sourceFile:options.main||'pages/page-001.tex'});
      if(url.pathname==='/events'){
        const after=Number(url.searchParams.get('after')||0),data=messages.filter(m=>m.event>after);
        if(data.length)return output(res,200,data);
        const pending={res,after};pending.timer=setTimeout(()=>{waiting.delete(pending);output(res,200,[]);},15000);waiting.add(pending);
        res.on('close',()=>{waiting.delete(pending);clearTimeout(pending.timer);});return;
      }
      if(url.pathname==='/source'){
        const file=url.searchParams.get('file')||'pages/page-001.tex';
        return output(res,200,{file,source:overlays.has(file)?overlays.get(file):fs.readFileSync(sourcePath(file),'utf8').replace(/\r\n?/g,'\n')});
      }
      const files={'/':['index.html','text/html'],'/viewer.js':['viewer.js','text/javascript'],'/viewer.css':['viewer.css','text/css']};
      if(files[url.pathname]){const [name,type]=files[url.pathname];return output(res,200,fs.readFileSync(path.join(root,'webview',name)),type);}
    }
    if(req.method==='POST'){
      let size=0;const chunks=[];
      for await(const chunk of req){size+=chunk.length;if(size>2000000)return output(res,413,{});chunks.push(chunk);}
      const data=JSON.parse(Buffer.concat(chunks).toString());
      if(url.pathname==='/paint')return output(res,200,{ok:true});
      if(url.pathname==='/action'){
        if(closed)return output(res,503,{error:'Backend is closed'});
        if(data.type==='edit'){sourcePath(data.file);data.source=data.source.replace(/\r\n?/g,'\n');overlays.set(data.file,data.source);}
        backend.stdin.write(JSON.stringify(data)+'\n');if(data.type==='close')backend.stdin.end();
        return output(res,200,{revision:++revision});
      }
    }
    output(res,404,{});
  }catch(error){output(res,400,{error:String(error)});}
});
function close(){if(!closed){backend.stdin.end('{"type":"close"}\n');closed=true;}server.close();}
process.on('SIGINT',close);process.on('SIGTERM',close);
server.listen(port,'127.0.0.1',()=>console.log(`Prototype: http://127.0.0.1:${port} (${engine}${engine==='cpp'?'/'+checkpoint:''})`));
