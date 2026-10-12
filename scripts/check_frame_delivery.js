const assert=require('assert'),fs=require('fs'),path=require('path');
const {createFrameDelivery}=require('../extension/frame-delivery');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const checks=[];
function check(name,condition){assert(condition,name);checks.push(name);console.log(name);}
const frame=(id,purpose='edit',generation=id)=>({type:'frame',clientId:id,revisionId:id,generation,purpose,requestId:`request-${id}`});
(async()=>{
  const sent=[],logs=[];
  const delivery=createFrameDelivery(m=>{sent.push(m);return true;},line=>logs.push(line));
  delivery.enqueue(frame(1));await tick();
  for(let i=2;i<=100;i++)delivery.enqueue(frame(i));
  await tick();
  check('hidden or slow viewer holds one in-flight payload',sent.length===1);
  delivery.acknowledge({deliveryId:999});await tick();
  check('unrelated acknowledgement cannot release a payload',sent.length===1);
  delivery.acknowledge({deliveryId:sent[0].deliveryId,outcome:'painted-stale'});await tick();
  check('active stale paint makes progress then newest completed revision follows',sent.length===2&&sent[1].clientId===100);
  check('replaced frame count and monotonic queue timing are reported',sent[1].replacedFrames===98&&sent[1].hostStagesMs.queue>=0);
  delivery.enqueue(frame(101,'page',100));delivery.enqueue(frame(102,'edit',101));await tick();
  check('replaced page requests are explicitly released',sent.some(m=>m.type==='discard'&&m.requestId==='request-101'));
  delivery.enqueue(frame(103,'page',101));await tick();
  check('page query cannot replace pending edit of the same generation',sent.some(m=>m.type==='discard'&&m.requestId==='request-103'));
  delivery.acknowledge({deliveryId:sent.find(m=>m.clientId===100).deliveryId,outcome:'error'});await tick();
  check('decode error acknowledgement releases the next frame',sent.at(-1).clientId===102);
  check('acknowledgement timing is recorded without payload contents',logs.some(line=>JSON.parse(line).hostRoundTripMs>=0));
  const oldId=sent.at(-1).deliveryId;
  delivery.enqueue(frame(103));delivery.reset();delivery.enqueue(frame(104));await tick();
  check('reloaded viewer resumes without an acknowledgement from its old document',sent.at(-1).clientId===104&&sent.at(-1).deliveryId>oldId);
  const reloadedCount=sent.length;
  delivery.enqueue(frame(105));delivery.acknowledge({deliveryId:oldId});await tick();
  check('old document acknowledgement cannot release new document work',sent.length===reloadedCount);
  delivery.enqueue(frame(104));delivery.dispose();
  const count=sent.length;delivery.acknowledge({deliveryId:sent.at(-1).deliveryId});delivery.enqueue(frame(105));await tick();
  check('disposing drops pending work and ignores late acknowledgements',sent.length===count);
  for(const rejection of [false,new Error('closed webview')]){
    const attempts=[];
    const failing=createFrameDelivery(m=>{attempts.push(m);return attempts.length===1?(rejection===false?false:Promise.reject(rejection)):true;},()=>{});
    failing.enqueue(frame(1));failing.enqueue(frame(2));await tick();
    check(`postMessage ${rejection===false?'false':'rejection'} releases pending work`,attempts.length===2&&attempts[1].clientId===2);
    failing.dispose();
  }
  let posted=false;const closed=createFrameDelivery(()=>{posted=true;},()=>{});
  closed.enqueue(frame(1));closed.dispose();await tick();
  check('disposal before deferred post prevents delivery to an old panel',!posted);
  fs.writeFileSync(path.join(__dirname,'../results/frame-delivery.json'),JSON.stringify({ok:true,checks},null,2)+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
