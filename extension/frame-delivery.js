/* Backpressure for full preview payloads. Control messages and source edits
 * never wait for a paint. Hidden webviews retain at most one pending payload. */
const {performance}=require('perf_hooks');
function createFrameDelivery(post,log){
  let active=null,pending=null,serial=0,closed=false,replaced=0;
  const discard=message=>{
    replaced++;
    if(message.purpose==='page')post({type:'discard',requestId:message.requestId});
  };
  const dispatch=entry=>{
    if(closed)return;
    const {message,received}=entry,started=performance.now();
    const deliveryId=++serial;
    active={deliveryId,started,clientId:message.clientId,revision:message.revisionId,generation:message.generation};
    const payload={...message,deliveryId,hostDispatchAt:Date.now(),
      hostStagesMs:{...message.hostStagesMs,queue:started-received},replacedFrames:replaced};
    // postMessage's result means accepted for delivery, not decoded or painted.
    Promise.resolve().then(()=>closed||active?.deliveryId!==deliveryId?false:post(payload)).then(accepted=>{
      if(accepted===false)finish({deliveryId,outcome:'not-delivered'});
    },error=>{log(String(error));finish({deliveryId,outcome:'delivery-error'});});
  };
  const finish=ack=>{
    if(closed||!active||ack.deliveryId!==active.deliveryId)return;
    log(JSON.stringify({type:'frame-delivery',...active,started:undefined,
      hostRoundTripMs:performance.now()-active.started,outcome:ack.outcome,replacedFrames:replaced}));
    active=null;
    if(pending){const next=pending;pending=null;dispatch(next);}
  };
  return {
    enqueue(message,received=performance.now()){
      if(closed)return;
      const entry={message,received};
      if(!active){dispatch(entry);return;}
      if(pending){
        // A late old page query cannot displace a newer edit. Same-generation
        // page requests also yield to the mutation that establishes the layout.
        if(message.generation<pending.message.generation||
          (message.generation===pending.message.generation&&message.purpose==='page'&&pending.message.purpose!=='page')){
          discard(message);return;
        }
        discard(pending.message);
      }
      pending=entry;
    },
    acknowledge:finish,
    // A reloaded webview cannot acknowledge its previous document's payload.
    // Keep IDs increasing so a late acknowledgement cannot release new work.
    reset(){active=null;pending=null;replaced=0;},
    dispose(){closed=true;active=null;pending=null;}
  };
}
module.exports={createFrameDelivery};
