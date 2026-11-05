'use strict';
// 几何画面辅助独立于面试评分、AI文本和个人材料存储。
window.CameraAssist=(()=>{
  const cam={stream:null,monitor:null,epoch:0,timer:null,live:false,starting:false,controller:null,last:null,failures:0,ready:false,lastNoticeKey:'',lastNoticeAt:-Infinity};
  const el=id=>document.getElementById(id);
  function message(value,kind=''){
    const n=el('camera-status');if(!n)return;if(n.textContent!==value)n.textContent=value;n.className='camera-status'+(kind?' '+kind:'');
    const mini=el('camera-mini');if(!mini)return;
    const status=kind==='error'?'error':kind==='adjust'?'warn':cam.live?(cam.ready?'ok':'watch'):'off';
    mini.dataset.state=status;el('camera-mini-status').textContent={off:cam.starting?'连接中':'未开启',ok:'稳定',watch:'观察中',warn:'请调整',error:'请检查'}[status];
  }
  function controls(){if(!el('camera-start'))return;el('camera-start').disabled=cam.starting||cam.live;el('camera-stop').disabled=el('camera-mini').hidden;el('camera-sensitivity').disabled=cam.starting||cam.live;el('camera-calibrate').disabled=!cam.live||cam.last?.face_count!==1;}
  function release(stream){stream?.getTracks().forEach(track=>track.stop());}
  async function discard(monitor){if(!monitor)return;try{await api('/vision/'+monitor.id,{method:'DELETE',headers:{'X-Vision-Token':monitor.token}});}catch{}}
  function stop(reason='摄像头已关闭'){
    cam.epoch++;cam.controller?.abort();cam.controller=null;clearTimeout(cam.timer);cam.timer=null;
    cam.lastNoticeKey='';cam.lastNoticeAt=-Infinity;
    const monitor=cam.monitor;cam.monitor=null;cam.live=false;cam.starting=false;cam.ready=false;cam.last=null;
    release(cam.stream);cam.stream=null;
    const video=el('camera-preview');if(video){video.pause();video.srcObject=null;video.setAttribute('aria-hidden','true');}
    el('camera-stage')?.classList.remove('active');if(el('camera-placeholder'))el('camera-placeholder').hidden=false;
    if(el('camera-mini'))el('camera-mini').hidden=true;
    if(el('camera-calibration'))el('camera-calibration').textContent='校准可修正摄像头安装角度带来的偏差。';
    message(reason);controls();void discard(monitor);
  }
  function draw(result){
    // 不展示关键点、包围框或角度数值，画面只保留本人镜头。
    const noticeKey=result.alerts.join('|'),now=performance.now();
    if(noticeKey&&noticeKey!==cam.lastNoticeKey&&now-cam.lastNoticeAt>5000){toast('画面提醒：'+result.hints[0]);cam.lastNoticeAt=now;}
    cam.lastNoticeKey=noticeKey;
    message(result.status==='adjust'?'请调整画面姿态':result.status==='observing'?'正在观察画面变化':'画面姿态稳定',result.status==='adjust'?'adjust':'');
    el('camera-calibration').textContent=result.calibrated?'已按当前正面位置校准。':'建议先正对镜头，点击下方校准。';
  }
  async function start(){
    signed();if(!el('camera-consent').checked){message('请先同意摄像头画面分析说明。','error');return;}
    if(!navigator.mediaDevices?.getUserMedia){message('当前浏览器无法访问摄像头，请使用支持摄像头的浏览器，并通过 HTTPS 访问。','error');return;}
    stop('正在准备画面分析…');const epoch=cam.epoch;cam.starting=true;el('camera-mini').hidden=false;controls();
    let stream=null,monitor=null;
    try{
      monitor=await api('/vision/session',{method:'POST',data:{consent:true,sensitivity:el('camera-sensitivity').value}});
      if(epoch!==cam.epoch){void discard(monitor);return;}
      cam.monitor=monitor;
      stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},facingMode:'user'},audio:false});
      if(epoch!==cam.epoch){release(stream);void discard(monitor);return;}
      cam.stream=stream;const video=el('camera-preview');video.srcObject=stream;await video.play();
      if(epoch!==cam.epoch){release(stream);return;}
      video.setAttribute('aria-hidden','false');
      el('camera-stage').style.aspectRatio=video.videoWidth+'/'+video.videoHeight;
      el('camera-stage').classList.add('active');el('camera-placeholder').hidden=true;
      cam.live=true;cam.starting=false;cam.failures=0;controls();message('正在分析画面…');
      stream.getVideoTracks().forEach(track=>track.addEventListener('ended',()=>{if(epoch===cam.epoch)stop('摄像头连接已结束。');}));
      void pump(epoch);
    }catch(error){
      release(stream);if(epoch!==cam.epoch)return;stop();
      const reasons={NotAllowedError:'未获摄像头授权，可在浏览器站点设置中允许后重新开启。',NotFoundError:'未检测到摄像头，请连接设备后重试。',NotReadableError:'摄像头被其他应用占用或无法读取。',OverconstrainedError:'摄像头不支持当前采集设置。'};
      message(reasons[error.name]||error.message||'无法启动摄像头。','error');
    }
  }
  async function pump(epoch){
    if(epoch!==cam.epoch||!cam.live)return;
    const started=performance.now(),video=el('camera-preview');
    if(!video.videoWidth||video.readyState<2){cam.timer=setTimeout(()=>pump(epoch),300);return;}
    try{
      const canvas=document.createElement('canvas');const scale=Math.min(640/video.videoWidth,480/video.videoHeight,1);
      canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.7));
      if(epoch!==cam.epoch||!cam.live)return;if(!blob)throw Error('无法读取摄像头帧。');
      cam.controller=new AbortController();const monitor=cam.monitor;
      const result=await api('/vision/'+monitor.id+'/frame',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg','X-Vision-Token':monitor.token},signal:cam.controller.signal});
      if(epoch!==cam.epoch||!cam.live)return;
      cam.last=result;cam.ready=result.status==='ok';cam.failures=0;draw(result);controls();
    }catch(error){
      if(epoch!==cam.epoch||error.name==='AbortError')return;
      cam.failures++;message(error.message||'画面分析暂未完成，请稍后重试。','error');
      if(cam.failures>=3){stop('连续未能完成画面分析，摄像头已关闭，请重新开启。');return;}
    }
    if(epoch===cam.epoch&&cam.live)cam.timer=setTimeout(()=>pump(epoch),cam.failures?1200:Math.max(220,400-(performance.now()-started)));
  }
  async function calibrate(){if(!cam.monitor)return;try{const result=await api('/vision/'+cam.monitor.id+'/calibrate',{method:'POST',headers:{'X-Vision-Token':cam.monitor.token}});el('camera-calibration').textContent=result.message;toast(result.message);}catch(error){message(error.message,'error');}}
  function positionWindow(left,top){
    const mini=el('camera-mini'),rect=mini.getBoundingClientRect();
    const x=Math.max(8,Math.min(left,window.innerWidth-rect.width-8));
    const y=Math.max(8,Math.min(top,window.innerHeight-rect.height-8));
    Object.assign(mini.style,{left:'0',top:'0',right:'auto',bottom:'auto',transform:`translate3d(${x}px,${y}px,0)`});
  }
  function bindWindow(){
    const mini=el('camera-mini'),grip=el('camera-grip');let drag=null;
    grip.addEventListener('pointerdown',e=>{if(e.button!==0)return;const rect=mini.getBoundingClientRect();drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:rect.left,top:rect.top};grip.setPointerCapture(e.pointerId);e.preventDefault();});
    grip.addEventListener('pointermove',e=>{if(drag&&drag.id===e.pointerId)positionWindow(drag.left+e.clientX-drag.x,drag.top+e.clientY-drag.y);});
    ['pointerup','pointercancel','lostpointercapture'].forEach(name=>grip.addEventListener(name,()=>{drag=null;}));
    const reset=()=>{for(const key of ['left','top','right','bottom','transform'])mini.style.removeProperty(key);};
    grip.addEventListener('dblclick',reset);
    grip.addEventListener('keydown',e=>{if(e.key==='Home'){e.preventDefault();reset();return;}const d={ArrowLeft:[-10,0],ArrowRight:[10,0],ArrowUp:[0,-10],ArrowDown:[0,10]}[e.key];if(d){e.preventDefault();const r=mini.getBoundingClientRect();positionWindow(r.left+d[0],r.top+d[1]);}});
    window.addEventListener('resize',()=>{if(mini.hidden)return;const r=mini.getBoundingClientRect();positionWindow(r.left,r.top);});
  }
  async function checkModel(){try{const value=await api('/vision/status');el('camera-model').textContent=value.ready?'镜头分析已就绪':'模型待配置';el('camera-model').className='badge '+(value.ready?'green':'neutral');}catch{el('camera-model').textContent='模型状态暂不可用';}}
  async function init(){
    const section=el('view-interview');if(!section||el('camera-preview'))return;
    const response=await fetch('/static/camera.html',{cache:'no-store',credentials:'same-origin'});if(!response.ok)return;
    const template=document.createElement('template');template.innerHTML=await response.text();section.insertBefore(template.content,section.querySelector('.interview-layout'));
    el('camera-start').addEventListener('click',()=>start().catch(e=>message(e.message,'error')));
    el('camera-stop').addEventListener('click',()=>stop());el('camera-calibrate').addEventListener('click',calibrate);
    el('camera-consent').addEventListener('change',()=>{if(!el('camera-consent').checked)stop('已撤回摄像头画面分析同意。');});
    bindWindow();
    window.addEventListener('viewchange',e=>{if(e.detail!=='interview')stop();else{el('camera-mini').hidden=false;controls();void checkModel();}});
    window.addEventListener('platform-clear',()=>stop());window.addEventListener('pagehide',()=>stop());
    document.addEventListener('visibilitychange',()=>{if(document.hidden)stop('页面已离开前台，摄像头已关闭。');});
    if(state.view==='interview'){el('camera-mini').hidden=false;controls();void checkModel();}
  }
  window.addEventListener('platform-ready',()=>init().catch(()=>{}),{once:true});
  if(el('view-interview'))void init();
  return {start,stop,calibrate,get active(){return cam.live;},get ready(){return cam.ready;}};
})();
