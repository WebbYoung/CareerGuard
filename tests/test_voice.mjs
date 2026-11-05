// 使用语音API替身检验实际前端状态机，不声称验证实体麦克风或浏览器云端ASR。
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../static/platform.js',import.meta.url),'utf8').replace('initPlatform().catch(e=>toast(e.message,true));','');
function setup(){
  const elements=new Map(),timers=[],cleared=[];
  function $(id){if(!elements.has(id))elements.set(id,{checked:false,value:'',textContent:'',classList:{add(){},remove(){}}});return elements.get(id);}
  class Recognition{start(){} abort(){this.aborted=true;} stop(){this.stopped=true;}}
  const context={console,titles:{},state:{view:'interview'},window:{SpeechRecognition:Recognition,speechSynthesis:{cancel(){}}},
    $,text:(id,value)=>{$(id).textContent=value;},
    setTimeout:(fn,ms)=>{const id=timers.length;timers.push({fn,ms});return id;},clearTimeout:id=>cleared.push(id),
    document:{},SpeechSynthesisUtterance:class{},api:async()=>({}),toast(){},show(){}};
  vm.createContext(context);vm.runInContext(source,context);
  vm.runInContext('platform.user={id:1}; platform.interview={id:1};',context);
  return {context,$,timers,cleared,read:code=>vm.runInContext(code,context)};
}
test('持续识别不会延长三分钟硬截止',()=>{
  const s=setup();s.$('#voice-consent').checked=true;s.$('#voice-auto').checked=true;
  s.context.listen();const rec=s.read('platform.recognition');
  assert.equal(s.timers.filter(t=>t.ms===180000).length,1);
  rec.onresult({resultIndex:0,results:[Object.assign([{transcript:'合成回答'}],{isFinal:true})]});
  rec.onresult({resultIndex:0,results:[Object.assign([{transcript:'继续回答'}],{isFinal:true})]});
  assert.equal(s.timers.filter(t=>t.ms===180000).length,1);
  s.timers.find(t=>t.ms===180000).fn();assert.equal(rec.stopped,true);
});
test('停止语音时撤销识别并释放两类计时器',()=>{
  const s=setup();s.$('#voice-consent').checked=true;s.context.listen();
  const rec=s.read('platform.recognition');s.context.stopVoice();
  assert.equal(rec.aborted,true);assert.equal(s.read('platform.recognition'),null);assert.equal(s.read('platform.listening'),false);
  assert.ok(s.cleared.includes(0));
});
test('离开面试页面后迟到追问不会渲染或朗读',async()=>{
  const s=setup();s.$('#interview-consent').checked=true;s.$('#interview-answer').value='合成回答';
  let finish;const pending=new Promise(resolve=>finish=resolve);s.context.api=()=>pending;
  let spoken=0;s.context.speakQuestion=()=>spoken++;
  const turn=s.context.sendAnswer();s.read("platform.interviewEpoch++;state.view='profile';");
  finish({id:1,question:'后续问题',history:[]});await turn;assert.equal(spoken,0);
});
