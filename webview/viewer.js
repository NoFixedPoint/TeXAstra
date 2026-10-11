/* Same view runs in a browser and in a VS Code webview. */
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
const $=id=>document.getElementById(id);
let frame=null, page=0, file='pages/page-001.tex', stale=true, sequence=0, after=0;
let editStarted=0, pendingSelection=null;
let latestRequest=0;
let clientSerial=0, latestClient=0;
let previousCharacters=[],previousWidth=0;
window.paintHistory=[];
if(vscode)document.body.classList.add('embedded');
function send(message){
  message.clientId=++clientSerial;latestClient=message.clientId;message.sentAt=Date.now();
  if(vscode){vscode.postMessage(message);return Promise.resolve();}
  return fetch('/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(message)});
}
function markStale(){stale=true;document.body.classList.add('stale');$('caret').style.display='none';$('highlight').style.display='none';}
async function loadSource(name,selection){
  if(vscode){vscode.postMessage({type:'navigate',...selection});return;}
  const response=await fetch('/source?file='+encodeURIComponent(name));
  if(!response.ok)return;
  const data=await response.json();file=data.file;$('file').value=file;$('source').value=data.source;
  if(selection){
    const lines=data.source.split('\n');
    const start=lines.slice(0,selection.line).reduce((n,l)=>n+l.length+1,0)+selection.column;
    const end=lines.slice(0,selection.endLine).reduce((n,l)=>n+l.length+1,0)+selection.endColumn;
    $('source').focus();$('source').setSelectionRange(start,end);
  }
}
function showRegion(region){
  if(!frame)return;
  const [x0,y0,x1,y1]=region.rect;
  for(const name of ['highlight','caret']){
    const el=$(name);el.style.left=(x0/frame.width*100)+'%';el.style.top=(y0/frame.height*100)+'%';
    el.style.width=(Math.max(x1-x0,1)/frame.width*100)+'%';el.style.height=(Math.max(y1-y0,3)/frame.height*100)+'%';el.style.display='block';
  }
  $('location').textContent=`${region.file}:${region.line+1}:${region.column+1}  ${region.kind}  ${region.text}`;
}
function forward(location){
  if(stale||!frame)return;
  const matches=frame.regions.filter(r=>r.file===location.file&&r.line===location.line&&r.column<=location.column&&r.endColumn>location.column);
  if(matches.length)showRegion(matches[0]);
  else{
    const match=/^pages\/page-(\d+)\.tex$/.exec(location.file);
    if(match&&Number(match[1])-1!==page){pendingSelection=location;navigate(Number(match[1])-1);}
  }
}
async function receive(message){
  if(message.type==='forward'){if(stale)pendingSelection=message;else forward(message);return;}
  if(message.type==='status'){
    latestRequest=Math.max(latestRequest,message.revision||0);
    latestClient=Math.max(latestClient,message.clientId||0);
    markStale();$('status').textContent=message.state==='error'?'Compile error · previous preview is stale':'Typesetting · previous preview is stale';
    if(message.error)$('error').textContent=message.error;
    return;
  }
  if(message.type!=='frame')return;
  if(message.regionRows){
    message.regions=message.regionRows.map(row=>Object.fromEntries(message.regionFields.map((key,i)=>[key,row[i]])));
    message.characters=message.characterRows.map(([text,rect])=>({text,rect}));
    delete message.regionRows;delete message.characterRows;delete message.regionFields;
  }
  const own=++sequence;const image=new Image();image.src=message.image;await image.decode();
  if(own!==sequence)return;
  frame=message;page=message.page;$('page').value=page+1;
  $('image').src=image.src;
  const layer=$('text-layer'),displayWidth=$('paper').clientWidth;
  const fragment=document.createDocumentFragment();
  const existing=Array.from(layer.children);
  for(let i=0;i<message.characters.length;i++){
    const ch=message.characters[i],old=previousCharacters[i],span=existing[i]||document.createElement('span');
    if(!old||old.text!==ch.text)span.textContent=ch.text;
    if(!old||previousWidth!==displayWidth||ch.rect.some((n,j)=>n!==old.rect[j])){
      const [x0,y0,x1,y1]=ch.rect;
      span.style.left=x0/message.width*100+'%';span.style.top=y0/message.height*100+'%';
      span.style.width=(x1-x0)/message.width*100+'%';span.style.height=(y1-y0)/message.height*100+'%';
      span.style.fontSize=((y1-y0)/message.width*displayWidth)+'px';
    }
    if(!existing[i])fragment.append(span);
  }
  for(let i=message.characters.length;i<existing.length;i++)existing[i].remove();
  layer.append(fragment);previousCharacters=message.characters;previousWidth=displayWidth;
  stale=message.isStale||message.revisionId<latestRequest||message.clientId<latestClient;document.body.classList.toggle('stale',stale);
  $('status').textContent=stale?'Typing · showing an earlier revision':message.provisional?'Provisional preview · references may need convergence':'Preview ready';
  $('error').textContent=message.warnings?.length?JSON.stringify(message.warnings.slice(0,20),null,2):'';
  await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
  const visibleMs=message.sentAt&&!stale?Date.now()-message.sentAt:null;
  $('timing').textContent=`${Math.round(message.pipelineMs)} ms pipeline${visibleMs?` · ${Math.round(visibleMs)} ms to display`:''}`;
  const stages=Object.fromEntries(['engineMs','prepareMs','compileMs','mapMs','roundtripMs','renderMs','requestToPayloadMs','resumedFrom','outputMode','pageBytes','resourceRefresh'].filter(k=>message[k]!==undefined).map(k=>[k,message[k]]));
  const measured={type:'paint',revision:message.revisionId,clientId:message.clientId,page:page+1,pipelineMs:message.pipelineMs,visibleMs,stale,at:Date.now(),...stages};
  window.lastPaint=measured;
  window.paintHistory.push(measured);
  if(vscode)vscode.postMessage(measured);
  else fetch('/paint',{method:'POST',body:JSON.stringify(measured)});
  if(!stale)editStarted=0;
  if(pendingSelection&&!stale){const location=pendingSelection;pendingSelection=null;forward(location);}
}
let pointer=null;
$('paper').addEventListener('pointerdown',e=>{pointer=[e.clientX,e.clientY];});
$('paper').addEventListener('click',e=>{
  if(stale||!frame||!pointer||Math.hypot(e.clientX-pointer[0],e.clientY-pointer[1])>4)return;
  const bounds=$('paper').getBoundingClientRect(),x=(e.clientX-bounds.left)/bounds.width*frame.width,y=(e.clientY-bounds.top)/bounds.height*frame.height;
  const hits=frame.regions.filter(r=>x>=r.rect[0]-1&&x<=r.rect[2]+1&&y>=r.rect[1]-1&&y<=r.rect[3]+1);
  hits.sort((a,b)=>(a.rect[2]-a.rect[0])*(a.rect[3]-a.rect[1])-(b.rect[2]-b.rect[0])*(b.rect[3]-b.rect[1]));
  if(hits[0]){showRegion(hits[0]);loadSource(hits[0].file,hits[0]);}
});
$('source').addEventListener('input',()=>{
  const lines=$('source').value.slice(0,$('source').selectionStart).split('\n');
  pendingSelection={file,line:lines.length-1,column:lines.at(-1).length};
  editStarted=performance.now();markStale();send({type:'edit',file,source:$('source').value,page});
});
$('source').addEventListener('click',()=>{
  const before=$('source').value.slice(0,$('source').selectionStart),lines=before.split('\n');
  forward({file,line:lines.length-1,column:lines.at(-1).length});
});
function navigate(target){page=Math.max(0,target);$('page').value=page+1;editStarted=performance.now();markStale();send({type:'page',page});}
$('previous').onclick=()=>navigate(page-1);$('next').onclick=()=>navigate(page+1);$('page').onchange=()=>navigate(Number($('page').value)-1);
$('load').onclick=()=>loadSource($('file').value);
if(vscode){window.addEventListener('message',event=>receive(event.data));vscode.postMessage({type:'ready'});}
else{
  (async()=>{
    after=(await(await fetch('/bootstrap')).json()).event;
    await loadSource(file);send({type:'start',page:0});
    while(true){
      try{
        const events=await(await fetch('/events?after='+after)).json();
        for(const event of events){after=event.event;await receive(event);}
        if(!events.length)await new Promise(resolve=>setTimeout(resolve,25));
      }catch(error){$('error').textContent='Preview connection interrupted: '+error;await new Promise(resolve=>setTimeout(resolve,500));}
    }
  })();
}
