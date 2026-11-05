import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../static/camera.js',import.meta.url),'utf8');
function setup(){
  const elements=new Map(),calls=[],notices=[];let acquired=0,stopped=0;
  const stream={getTracks:()=>[{stop(){stopped++;}}],getVideoTracks:()=>[{addEventListener(){}}]};
  const get=id=>{
    if(id==='view-interview')return null;
    if(!elements.has(id))elements.set(id,{value:'standard',checked:true,hidden:false,disabled:false,textContent:'',className:'',style:{},dataset:{},classList:{add(){},remove(){}},
      setAttribute(){},append(){},replaceChildren(){},pause(){},async play(){},videoWidth:640,videoHeight:480,readyState:2,srcObject:null,getContext:()=>({clearRect(){}})});
    return elements.get(id);
  };
  const context={window:{addEventListener(){}},document:{getElementById:get,createElement:()=>({getContext:()=>({drawImage(){}}),toBlob:fn=>fn({size:123})})},
    navigator:{mediaDevices:{getUserMedia:async()=>{acquired++;return stream;}}},node:()=>({}),signed(){},toast:message=>notices.push(message),
    state:{view:'interview'},performance,AbortController,clearTimeout,setTimeout:()=>1,
    api:async(path)=>{calls.push(path);if(path.endsWith('/frame'))return new Promise(()=>{});return {id:'local-monitor',token:'test-token'};}};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,cam:context.window.CameraAssist,get,stream,calls,notices,counts:()=>({acquired,stopped})};
}
test('未同意摄像头处理时不请求设备',async()=>{
  const s=setup();s.get('camera-consent').checked=false;await s.cam.start();assert.equal(s.counts().acquired,0);assert.equal(s.calls.length,0);
});
test('权限请求尚未完成时关闭，随后得到的媒体轨道仍会释放',async()=>{
  const s=setup();let resolve;
  s.context.navigator.mediaDevices.getUserMedia=()=>new Promise(r=>resolve=r);
  const starting=s.cam.start();await new Promise(setImmediate);assert.ok(resolve);
  s.cam.stop();resolve(s.stream);await starting;
  assert.ok(s.counts().stopped>=1);assert.equal(s.cam.active,false);assert.equal(s.get('camera-preview').srcObject,null);
});
test('模型未就绪不打开摄像头',async()=>{
  const s=setup();s.context.api=async()=>{throw Error('本机视觉模型未配置完整。');};await s.cam.start();
  assert.equal(s.counts().acquired,0);assert.match(s.get('camera-status').textContent,/模型/);assert.equal(s.get('camera-start').disabled,false);
});
test('关闭正在分析的摄像头会立即停止轨道并清空预览',async()=>{
  const s=setup();await s.cam.start();assert.equal(s.cam.active,true);assert.equal(s.get('camera-mini').hidden,false);s.cam.stop();
  assert.equal(s.cam.active,false);assert.equal(s.get('camera-preview').srcObject,null);assert.ok(s.counts().stopped>=1);
  assert.equal(s.get('camera-mini').hidden,true);
});

test('持续动作提醒会显示在面试页面提示层',async()=>{
  const s=setup(),request=s.context.api;
  s.context.api=path=>path.endsWith('/frame')?Promise.resolve({status:'adjust',alerts:['hand_motion'],hints:['可尝试减少重复动作。'],face_count:1,face_box:null,hands:[],angles:{yaw:0,pitch:0,roll:0},calibrated:false}):request(path);
  await s.cam.start();await new Promise(setImmediate);
  assert.equal(s.notices.length,1);assert.match(s.notices[0],/画面提醒/);assert.equal(s.get('camera-mini').dataset.state,'warn');s.cam.stop();
});
