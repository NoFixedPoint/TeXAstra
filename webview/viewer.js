/* The same scrolling view runs in VS Code and the local browser demo. */
const vscode=typeof acquireVsCodeApi==='function'?acquireVsCodeApi():null;
const $=id=>document.getElementById(id),pages=new Map(),pendingPages=new Map();
const inputTimes=new Map();
let frame=null,page=0,file='pages/page-001.tex',stale=true,after=0;
let latestRequest=0,latestClient=0,clientSerial=0,generation=0,requestSerial=0;
let pendingSelection=null,pendingHighlight=null,scrollScheduled=false,lastSyncRequest=null,documentCount=0;
let lastBackwardRequest=null;
let prefetchAfter=0,prefetchTimer=null;
let activeFrame=null,queuedFrame=null,lastVisualPaintAt=null;
window.frameDeliveryStats={received:0,replaced:0,painted:0,errors:0};
window.paintHistory=[];
if(vscode)document.body.classList.add('embedded');
function showError(message,title='Compile error'){
  const panel=$('diagnostics'),text=String(message||'');
  $('error').textContent=text;$('error-title').textContent=text?title:'Compile errors';
  panel.classList.toggle('has-error',!!text);
}
function send(message,inputAt=performance.now()){
  message.clientId=++clientSerial;message.sentAt=Date.now();message.requestId=message.requestId||`view-${++requestSerial}`;
  if(message.type==='edit'||message.type==='start'){
    inputTimes.set(message.clientId,inputAt);
    if(inputTimes.size>256)inputTimes.delete(inputTimes.keys().next().value);
  }
  if(message.type==='edit'||message.type==='start')latestClient=message.clientId;
  if(vscode){vscode.postMessage(message);return Promise.resolve();}
  return fetch('/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(message)});
}
function markStale(){
  stale=true;prefetchAfter=performance.now()+200;clearTimeout(prefetchTimer);
  document.body.classList.add('stale');for(const p of pages.values()){p.caret.style.display='none';p.highlight.style.display='none';}
}
async function loadSource(name,selection){
  if(vscode){vscode.postMessage({type:'navigate',...selection,generation,revisionId:latestRequest});return;}
  const response=await fetch('/source?file='+encodeURIComponent(name));if(!response.ok)return;
  const data=await response.json();file=data.file;$('file').value=file;$('source').value=data.source;
  if(selection){
    const lines=data.source.split('\n'),offset=(line,column)=>lines.slice(0,line).reduce((n,s)=>n+s.length+1,0)+column;
    $('source').focus();$('source').setSelectionRange(offset(selection.line,selection.column),offset(selection.endLine,selection.endColumn));
  }
}
function createPage(index,width,height){
  const element=document.createElement('div');element.className='paper outdated';element.id=index===0?'paper':`paper-${index+1}`;
  element.dataset.page=index;element.style.aspectRatio=`${width} / ${height}`;element.setAttribute('aria-label',`Page ${index+1}`);
  const image=document.createElement('img');image.className='page-image';image.alt=`Rendered page ${index+1}`;
  const layer=document.createElement('div');layer.className='text-layer';
  const caret=document.createElement('div');caret.className='caret';
  const highlight=document.createElement('div');highlight.className='highlight';
  const label=document.createElement('div');label.className='page-placeholder';label.textContent=`Page ${index+1}`;
  if(index===0){image.id='image';layer.id='text-layer';caret.id='caret';highlight.id='highlight';}
  element.append(image,layer,caret,highlight,label);$('pages').append(element);
  const item={element,image,layer,caret,highlight,label,width,height,frame:null,sequence:0,previous:[],displayWidth:0};
  let pointer=null;
  element.addEventListener('pointerdown',e=>{pointer=[e.clientX,e.clientY];});
  element.addEventListener('click',e=>{
    if(stale||!item.frame||item.frame.generation!==generation||!pointer||Math.hypot(e.clientX-pointer[0],e.clientY-pointer[1])>4)return;
    const bounds=element.getBoundingClientRect(),x=(e.clientX-bounds.left)/bounds.width*item.width,y=(e.clientY-bounds.top)/bounds.height*item.height;
    if(item.frame.sourceSync==='synctex'){
      lastBackwardRequest=`backward-${++requestSerial}`;
      send({type:'sync-backward',page:index,x,y,generation,requestId:lastBackwardRequest});return;
    }
    const hits=item.frame.regions.filter(r=>regionHit(r,x,y));
    hits.sort((a,b)=>regionArea(a)-regionArea(b));
    // A precise unmapped hit takes precedence over a neighboring glyph's
    // one-point click tolerance. Never redirect an unknown glyph to its neighbor.
    const unknown=(item.frame.unmappedRegions||[]).find(r=>x>=r.rect[0]&&x<=r.rect[2]&&y>=r.rect[1]&&y<=r.rect[3]);
    if(unknown){
      for(const other of pages.values()){other.caret.style.display='none';other.highlight.style.display='none';}
      $('location').textContent=mappingReason(unknown.reason);return;
    }
    // Thin rules need the same click tolerance as text at normal zoom.
    const hit=hits[0];
    if(hit){showRegion({...hit,page:index},false);loadSource(hit.file,hit);}
  });
  pages.set(index,item);return item;
}
function regionArea(r){
  if(!r.quad)return (r.rect[2]-r.rect[0])*(r.rect[3]-r.rect[1]);
  const q=r.quad;return Math.abs((q[2]-q[0])*(q[7]-q[1])-(q[3]-q[1])*(q[6]-q[0]));
}
function regionHit(r,x,y){
  if(x<r.rect[0]-1||x>r.rect[2]+1||y<r.rect[1]-1||y>r.rect[3]+1)return false;
  if(!r.quad)return true;
  const q=r.quad;let positive=false,negative=false,near=false;
  for(let i=0;i<8;i+=2){
    const j=(i+2)%8,dx=q[j]-q[i],dy=q[j+1]-q[i+1],cross=dx*(y-q[i+1])-dy*(x-q[i]);
    positive ||= cross>0;negative ||= cross<0;
    const t=Math.max(0,Math.min(1,((x-q[i])*dx+(y-q[i+1])*dy)/(dx*dx+dy*dy||1)));
    near ||= Math.hypot(x-q[i]-t*dx,y-q[i+1]-t*dy)<=1;
  }
  return near||!(positive&&negative);
}
function mappingReason(reason){
  return ({'external-content':'This content comes from an imported PDF and has no TeX source location.',
    'missing-origin':'The compiler did not retain a source location for this generated content.',
    'untagged-content':'This output has no source marker; its source location is unknown.',
    'glyph-count-mismatch':'This output differs from its source marker. Navigation is unavailable here.',
    'unclosed-source-scope':'This output has an incomplete source marker. Navigation is unavailable here.',
    'unknown-source':'The source location for this output is no longer available.'})[reason]||'No verified source location is available here.';
}
function setLayout(message){
  for(let index=0;index<message.pageCount;index++){
    const [w,h]=message.pageSizes?.[index]||[message.width,message.height],item=pages.get(index)||createPage(index,w,h);
    item.width=w;item.height=h;item.element.style.aspectRatio=`${w} / ${h}`;
  }
  for(const [index,item] of pages)if(index>=message.pageCount){item.element.remove();pages.delete(index);}
  documentCount=message.pageCount;page=Math.min(page,documentCount-1);$('page').max=documentCount;$('page-count').textContent=`/ ${documentCount}`;
}
function requestPage(index){
  const item=pages.get(index);
  if(stale||!item||item.frame?.generation===generation||[...pendingPages.values()].includes(index))return;
  const requestId=`page-${++requestSerial}`;pendingPages.set(requestId,index);send({type:'page',page:index,generation,requestId});
}
function scheduleVisible(){
  if(scrollScheduled)return;scrollScheduled=true;
  requestAnimationFrame(()=>{
    scrollScheduled=false;if(!pages.size)return;
    const viewport=$('scroll').getBoundingClientRect(),center=(viewport.top+viewport.bottom)/2;
    let closest=page,distance=Infinity;const wanted=[];
    for(const [index,item] of pages){
      const r=item.element.getBoundingClientRect(),delta=r.top>center?r.top-center:r.bottom<center?center-r.bottom:0;
      if(delta<distance){closest=index;distance=delta;}
      if(r.bottom>=viewport.top-viewport.height&&r.top<=viewport.bottom+viewport.height)wanted.push(index);
    }
    page=closest;frame=pages.get(page)?.frame||frame;$('page').value=page+1;
    if(vscode)vscode.postMessage({type:'viewport',page,generation});
    wanted.sort((a,b)=>Math.abs(a-page)-Math.abs(b-page));
    const defer=performance.now()<prefetchAfter;
    if(defer){clearTimeout(prefetchTimer);prefetchTimer=setTimeout(scheduleVisible,prefetchAfter-performance.now());}
    // A page query can replay TeX. Keep speculative neighbors out of the edit
    // queue while typing; explicit navigation and the current page stay immediate.
    for(const index of wanted){if(pendingPages.size>=2)break;if(!defer||index===page)requestPage(index);}
    for(const [index,item] of pages)if(Math.abs(index-page)>4&&item.frame&&index!==pendingHighlight?.page){
      item.image.removeAttribute('src');item.layer.replaceChildren();item.previous=[];item.frame=null;
      item.label.style.display='block';item.element.classList.add('outdated');
    }
  });
}
function showRegion(region,scroll=true){
  const item=pages.get(region.page);if(!item)return;
  if(!item.frame||item.frame.generation!==generation){pendingHighlight=region;requestPage(region.page);if(scroll)navigate(region.page);return;}
  for(const other of pages.values()){other.caret.style.display='none';other.highlight.style.display='none';}
  const [x0,y0,x1,y1]=region.rect;
  for(const el of [item.highlight,item.caret]){
    el.style.left=x0/item.width*100+'%';el.style.top=y0/item.height*100+'%';el.style.width=Math.max(x1-x0,1)/item.width*100+'%';
    el.style.height=Math.max(y1-y0,3)/item.height*100+'%';el.style.display='block';
  }
  $('location').textContent=`${region.file}:${region.line+1}:${region.column+1} · ${region.kind||'token'}`;
  if(scroll){
    const r=item.element.getBoundingClientRect(),v=$('scroll').getBoundingClientRect(),y=r.top+y0/item.height*r.height;
    if(y<v.top+25||y>v.bottom-25)$('scroll').scrollTop+=y-v.top-v.height/2;
  }
  pendingHighlight=null;scheduleVisible();
}
function containsSource(r,l){return r.file===l.file&&l.line>=r.line&&l.line<=r.endLine&&(l.line>r.line||l.column>=r.column)&&(l.line<r.endLine||l.column<r.endColumn);}
function forward(location){
  if(stale){pendingSelection=location;return;}
  for(const [index,item] of [...pages].sort((a,b)=>Math.abs(a[0]-page)-Math.abs(b[0]-page)))if(item.frame?.generation===generation){
    const matches=item.frame.regions.filter(r=>containsSource(r,location)).sort((a,b)=>(a.end-a.start)-(b.end-b.start));
    if(matches.length){showRegion({...matches[0],page:index});return;}
  }
  // VS Code selections carry type:'forward'. Copy only the source position so
  // that envelope cannot overwrite the backend's sync-forward request type.
  lastSyncRequest=`sync-${++requestSerial}`;send({type:'sync-forward',file:location.file,line:location.line,column:location.column,page,generation,requestId:lastSyncRequest});
}
function finishFrame(entry,outcome){
  if(entry.message.purpose==='page'&&outcome!=='painted')pendingPages.delete(entry.message.requestId);
  if(vscode&&entry.message.deliveryId!==undefined)vscode.postMessage({type:'frame-ack',deliveryId:entry.message.deliveryId,outcome});
  entry.resolve();
}
async function runFrame(entry){
  activeFrame=entry;
  let outcome='discarded';
  try{
    entry.message.viewerQueueMs=performance.now()-entry.received;
    outcome=await receiveMessage(entry.message)||outcome;
  }catch(error){window.frameDeliveryStats.errors++;showError('Document update failed: '+error,'Rendering error');outcome='error';}
  finally{
    finishFrame(entry,outcome);activeFrame=null;
    if(queuedFrame){const next=queuedFrame;queuedFrame=null;runFrame(next);}
  }
}
function receive(message){
  // Status/navigation must remain immediate while a frame decodes or awaits
  // presentation. Finish active work to make progress even during nonstop edits.
  if(message.type!=='frame')return receiveMessage(message);
  const received=performance.now();
  if(message.hostDispatchAt!==undefined)message.webviewDeliveryMs=Date.now()-message.hostDispatchAt;
  window.frameDeliveryStats.received++;
  return new Promise(resolve=>{
    const entry={message,received,resolve};
    if(!activeFrame){runFrame(entry);return;}
    if(queuedFrame){
      if(message.generation<queuedFrame.message.generation||
        (message.generation===queuedFrame.message.generation&&message.purpose==='page'&&queuedFrame.message.purpose!=='page')){
        window.frameDeliveryStats.replaced++;finishFrame(entry,'replaced');return;
      }
      window.frameDeliveryStats.replaced++;finishFrame(queuedFrame,'replaced');
    }
    queuedFrame=entry;
  });
}
async function receiveMessage(message){
  const receivedAt=performance.now();
  if(message.type==='forward'){forward(message);return;}
  if(message.type==='status'){
    latestRequest=Math.max(latestRequest,message.revision||0);latestClient=Math.max(latestClient,message.clientId||0);markStale();pendingPages.clear();
    $('status').textContent=message.state==='error'?'Compile error · previous document is stale':'Updating document…';
    if(message.state==='error')showError(message.error||'Compilation failed. No error details were provided.');return;
  }
  if(message.type==='discard'||message.type==='query-error'){
    pendingPages.delete(message.requestId);if(message.type==='query-error')showError(message.error||'Unable to load the requested page.','Rendering error');return;
  }
  if(message.type==='sync'){
    if(message.direction==='backward'){
      if(!stale&&message.generation===generation&&message.requestId===lastBackwardRequest){
        if(message.location){showRegion(message.location,false);loadSource(message.location.file,message.location);}
        else $('location').textContent='No source line is available at this position.';
      }return;
    }
    if(!stale&&message.generation===generation&&message.requestId===lastSyncRequest){
      if(message.location)showRegion(message.location);else $('location').textContent='No rendered token is mapped at this source position.';
    }return;
  }
  if(message.type!=='frame')return;
  const query=message.purpose==='page';if(query&&!pendingPages.has(message.requestId))return;pendingPages.delete(message.requestId);
  if(message.generation<generation)return;
  if(message.generation>generation){generation=message.generation;pendingPages.clear();for(const p of pages.values())p.element.classList.add('outdated');}
  latestRequest=Math.max(latestRequest,message.revisionId||0);
  if(message.regionRows){
    message.regions=message.regionRows.map(row=>Object.fromEntries(message.regionFields.map((key,i)=>[key,row[i]])));
    message.characters=message.characterRows.map(([text,rect])=>({text,rect}));delete message.regionRows;delete message.characterRows;delete message.regionFields;
  }
  if(!query||message.pageCount!==documentCount)setLayout(message);
  const item=pages.get(message.page);if(!item)return;
  const decodeAt=performance.now();
  const own=++item.sequence,image=new Image();image.src=message.image;await image.decode();if(own!==item.sequence||message.generation!==generation)return;
  const decodedAt=performance.now();
  item.frame=message;item.image.src=image.src;item.label.style.display='none';item.element.classList.remove('outdated');
  const width=item.element.clientWidth,existing=Array.from(item.layer.children),fragment=document.createDocumentFragment();
  for(let i=0;i<message.characters.length;i++){
    const ch=message.characters[i],old=item.previous[i],span=existing[i]||document.createElement('span');if(!old||old.text!==ch.text)span.textContent=ch.text;
    if(!old||item.displayWidth!==width||ch.rect.some((n,j)=>n!==old.rect[j])){
      const [x0,y0,x1,y1]=ch.rect;span.style.left=x0/message.width*100+'%';span.style.top=y0/message.height*100+'%';
      span.style.width=(x1-x0)/message.width*100+'%';span.style.height=(y1-y0)/message.height*100+'%';span.style.fontSize=(y1-y0)/message.width*width+'px';
    }if(!existing[i])fragment.append(span);
  }
  for(let i=message.characters.length;i<existing.length;i++)existing[i].remove();
  item.layer.append(fragment);item.previous=message.characters;item.displayWidth=width;if(message.page===page||!frame)frame=message;
  stale=message.isStale||message.revisionId<latestRequest||message.clientId<latestClient;document.body.classList.toggle('stale',stale);
  if(!query){
    const compiler=({pdflatex:'PDFLaTeX',xelatex:'XeLaTeX'})[message.compiler];
    $('status').textContent=stale?'Updating · showing an earlier revision':message.provisional?'Document · updating references and layout':compiler?`Document ready · ${compiler}`:'Document ready';
    if(!stale)showError('');
  }
  const installedAt=performance.now();
  await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
  const paintedAt=performance.now();
  const paintStale=stale||message.isStale||message.revisionId<latestRequest||message.clientId<latestClient||message.generation!==generation||own!==item.sequence;
  // Slow edits can consume the entire input-time quiet interval. Start a new
  // interval at the fresh paint so neighbor replay cannot delay the next key.
  if(!query&&message.purpose==='edit'&&!paintStale)prefetchAfter=Math.max(prefetchAfter,paintedAt+200);
  const inputAt=inputTimes.get(message.clientId);
  const frameAgeMs=message.sentAt?(inputAt!==undefined?paintedAt-inputAt:Date.now()-message.sentAt):null;
  const visibleMs=paintStale?null:frameAgeMs;
  if(!query)$('timing').textContent=`${Math.round(message.pipelineMs)} ms pipeline${visibleMs?` · ${visibleMs} ms to display`:''}`;
  const stages=Object.fromEntries(['compileMs','prepareMs','checkpointMs','sourceUpdateMs','compilerStagesMs','snapshot','mapMs','renderMs','renderStagesMs','resourceRefreshMs','fontRefreshMs','fontResourceBytes','queueMs','requestToPayloadMs','resumedFrom','outputMode','compilationMode','cacheReused'].filter(k=>message[k]!==undefined).map(k=>[k,message[k]]));
  const browserStagesMs={prepare:decodeAt-receivedAt,decode:decodedAt-decodeAt,install:installedAt-decodedAt,paintWait:paintedAt-installedAt};
  const viewerQueueMs=message.viewerQueueMs||0;
  const deliveryMs=visibleMs===null||message.requestToPayloadMs===undefined?null:visibleMs-(paintedAt-receivedAt)-viewerQueueMs-message.requestToPayloadMs;
  const transport=Object.fromEntries(['deliveryId','hostReceivedAt','hostDispatchAt','hostStagesMs','webviewDeliveryMs','payloadBytes','imageEncodedBytes','nonImageBytes','replacedFrames'].filter(k=>message[k]!==undefined).map(k=>[k,message[k]]));
  const measured={type:'paint',revision:message.revisionId,clientId:message.clientId,page:message.page+1,generation:message.generation,purpose:message.purpose,phase:message.phase||'preview',pipelineMs:message.pipelineMs,visibleMs,frameAgeMs,revisionLag:Math.max(0,latestRequest-message.revisionId),updateIntervalMs:lastVisualPaintAt===null?null:paintedAt-lastVisualPaintAt,stale:paintStale,at:Date.now(),browserStagesMs,viewerQueueMs,deliveryMs,...transport,...stages};
  window.frameDeliveryStats.painted++;
  if(!query){lastVisualPaintAt=paintedAt;window.lastPaint=measured;window.paintHistory.push(measured);if(window.paintHistory.length>256)window.paintHistory.shift();if(vscode)vscode.postMessage(measured);else fetch('/paint',{method:'POST',body:JSON.stringify(measured)});}
  if(pendingHighlight?.page===message.page&&!stale)showRegion(pendingHighlight);
  if(pendingSelection&&!stale){const location=pendingSelection;pendingSelection=null;forward(location);}scheduleVisible();
  return paintStale?'painted-stale':'painted';
}
function navigate(target){
  const index=Math.max(0,Math.min(documentCount-1,target)),item=pages.get(index);if(!item)return;
  const r=item.element.getBoundingClientRect(),v=$('scroll').getBoundingClientRect();$('scroll').scrollTop+=r.top-v.top;
  page=index;$('page').value=page+1;requestPage(page);scheduleVisible();
}
$('source').addEventListener('input',()=>{const inputAt=performance.now(),lines=$('source').value.slice(0,$('source').selectionStart).split('\n');pendingSelection={file,line:lines.length-1,column:lines.at(-1).length};markStale();send({type:'edit',file,source:$('source').value,page},inputAt);});
$('source').addEventListener('click',()=>{const lines=$('source').value.slice(0,$('source').selectionStart).split('\n');forward({file,line:lines.length-1,column:lines.at(-1).length});});
$('scroll').addEventListener('scroll',scheduleVisible,{passive:true});window.addEventListener('resize',()=>{
  for(const item of pages.values())if(item.frame){
    const width=item.element.clientWidth;
    for(let i=0;i<item.layer.children.length;i++){
      const r=item.previous[i].rect;item.layer.children[i].style.fontSize=(r[3]-r[1])/item.width*width+'px';
    }item.displayWidth=width;
  }scheduleVisible();
});
$('previous').onclick=()=>navigate(page-1);$('next').onclick=()=>navigate(page+1);$('page').onchange=()=>navigate(Number($('page').value)-1);$('load').onclick=()=>loadSource($('file').value);
window.previewState=()=>({page,generation,stale,count:documentCount,loaded:[...pages].filter(([i,p])=>p.frame?.generation===generation).map(([i])=>i),pending:[...pendingPages.values()]});
if(vscode){window.addEventListener('message',event=>receive(event.data));vscode.postMessage({type:'ready'});}
else (async()=>{
  const bootstrap=await(await fetch('/bootstrap')).json();after=bootstrap.event;file=bootstrap.sourceFile||file;await loadSource(file);send({type:'start',page:0});
  // Match VS Code's event delivery: decoding/painting an earlier payload must
  // not delay newer revisions or statuses. receive guards generation/sequence.
  while(true){try{const events=await(await fetch('/events?after='+after)).json();for(const event of events){after=event.event;receive(event).catch(error=>{showError('Document update failed: '+error,'Rendering error');});}if(!events.length)await new Promise(resolve=>setTimeout(resolve,25));}
    catch(error){showError('Document connection interrupted: '+error,'Document connection error');await new Promise(resolve=>setTimeout(resolve,500));}}
})();
