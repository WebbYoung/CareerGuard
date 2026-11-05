import {createGuideRobot} from './robot-model.js';

// 机器人只介绍界面，不执行分析、上传、考试或媒体权限请求。
const core=window.CareerGuideCore;
if(core){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const make=(tag,cls,text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
  const assistant=make('div','robot-assistant'),modelHost=make('div','robot-model');
  const launcher=make('button','robot-launcher');launcher.type='button';launcher.disabled=true;launcher.setAttribute('aria-label','让小安带我了解职安');launcher.title='重新查看新手引导';
  const name=make('span','robot-name','小安 · 点击引导');assistant.append(modelHost,launcher,name);document.body.append(assistant);
  const model=createGuideRobot(modelHost,{reducedMotion:reduced.matches});
  const overlay=make('div','robot-tour-backdrop'),highlight=make('div','robot-tour-highlight'),bubble=make('section','robot-bubble');
  overlay.hidden=highlight.hidden=bubble.hidden=true;
  highlight.setAttribute('aria-hidden','true');bubble.setAttribute('role','dialog');bubble.setAttribute('aria-modal','true');bubble.setAttribute('aria-labelledby','robot-guide-title');bubble.setAttribute('aria-describedby','robot-guide-body');
  const progress=make('p','robot-guide-progress'),title=make('h2','robot-guide-title'),description=make('p','robot-guide-body'),message=make('p','robot-guide-message');
  title.id='robot-guide-title';description.id='robot-guide-body';message.setAttribute('role','status');message.setAttribute('aria-live','polite');
  const controls=make('div','robot-guide-controls'),previous=make('button','robot-guide-prev','上一步'),skip=make('button','robot-guide-skip','跳过引导'),next=make('button','robot-guide-next','我明白了');
  [previous,skip,next].forEach(b=>b.type='button');controls.append(previous,skip,next);bubble.append(progress,title,description,message,controls);document.body.append(overlay,highlight,bubble);
  let active=false,index=0,busy=false,initialized=false,oldOverflow='',oldFocus=null,target=null,frame=0,aim=null;
  const gate=core.createGate();
  const inerted=new Map();
  const request=(data,keepalive=false)=>window.api('/onboarding',data?{method:'POST',data,keepalive}:{});
  const clamp=(n,a,b)=>Math.max(a,Math.min(n,b));
  function syncMotion(){
    const off=document.querySelector('#visual-effects-mode')?.value==='off';
    model.setReducedMotion(reduced.matches||off);model.setActive(!document.hidden&&!off);
  }
  function setBusy(value){busy=value;previous.disabled=next.disabled=value;next.setAttribute('aria-busy',String(value));}
  function moveHost(x,y,width,height){
    assistant.style.width=width+'px';assistant.style.height=height+'px';assistant.style.transform=`translate3d(${x}px,${y}px,0)`;model.resize();
  }
  function dock(){
    if(active)return;
    const w=innerWidth<700?92:112,h=innerWidth<700?122:146;
    let y=innerHeight-h-38;
    const camera=document.querySelector('#camera-mini');
    if(camera&&!camera.hidden&&camera.getBoundingClientRect().width&&camera.closest('.view')?.hidden===false)y=Math.min(y,camera.getBoundingClientRect().top-h-12);
    moveHost(Math.max(8,innerWidth-w-16),Math.max(12,y),w,h);model.setPointing(false);
  }
  function position(){
    frame=0;if(!active||!target?.isConnected)return;
    const rect=target.getBoundingClientRect();
    const first=core.place(rect,{width:innerWidth,height:innerHeight});
    bubble.style.width=first.bubble.width+'px';
    const layout=core.place(rect,{width:innerWidth,height:innerHeight},{bubbleHeight:bubble.offsetHeight||218});
    bubble.style.transform=`translate3d(${layout.bubble.x}px,${layout.bubble.y}px,0)`;
    bubble.style.maxHeight=(innerHeight-24)+'px';
    const r=layout.highlight;highlight.style.transform=`translate3d(${r.x}px,${r.y}px,0)`;highlight.style.width=r.width+'px';highlight.style.height=r.height+'px';
    moveHost(layout.robot.x,layout.robot.y,layout.robot.width,layout.robot.height);aim=layout.aim;model.setPointing(true);model.pointAt(aim.x,aim.y);
  }
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(active?position:()=>{frame=0;dock();});};
  assistant.addEventListener('transitionend',e=>{if(active&&e.propertyName==='transform'&&aim)model.pointAt(aim.x,aim.y);});
  function showStep(){
    const step=core.STEPS[index];if(!step)return;
    window.show(step.view);
    target=document.querySelector(step.target)||document.querySelector('#view-'+step.view+' .page-heading');
    progress.textContent=`小安的使用指南 · ${index+1} / ${core.STEPS.length}`;title.textContent=step.title;description.textContent=step.body;message.textContent='';previous.hidden=index===0;
    if(target){target.scrollIntoView({block:innerWidth<700?'start':'center',behavior:'instant'});position();}
    else {message.textContent='这个区域暂未就绪，可以跳过这一步。';target=document.querySelector('#main');position();}
    next.focus({preventScroll:true});schedule();
  }
  function maskBackground(){
    for(const el of document.body.children){
      if(el===assistant||el===overlay||el===highlight||el===bubble||el.tagName==='SCRIPT'||el.tagName==='SVG'||el.classList.contains('fx-cosmos'))continue;
      inerted.set(el,el.inert);el.inert=true;
    }
  }
  function open(step,token){
    if(!gate.enter(token))return;
    active=true;index=clamp(step,0,core.STEPS.length-1);oldFocus=document.activeElement;oldOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    assistant.classList.add('is-guiding');launcher.hidden=name.hidden=true;overlay.hidden=highlight.hidden=bubble.hidden=false;maskBackground();setBusy(false);showStep();
  }
  function close(){
    if(!active)return;gate.close();active=false;target=null;aim=null;cancelAnimationFrame(frame);frame=0;
    overlay.hidden=highlight.hidden=bubble.hidden=true;assistant.classList.remove('is-guiding');launcher.hidden=name.hidden=false;document.body.style.overflow=oldOverflow;
    inerted.forEach((value,el)=>{if(el.isConnected)el.inert=value;});inerted.clear();model.setPointing(false);setBusy(false);dock();
    const focus=oldFocus?.isConnected&&oldFocus!==document.body?oldFocus:launcher;focus.focus?.({preventScroll:true});
  }
  async function begin(){
    if(active||launcher.disabled)return;
    const token=gate.begin();
    launcher.disabled=true;
    try{const result=await request({action:'start',step:0});open(result.step,token);}
    catch{if(typeof window.toast==='function')window.toast('暂时无法开启引导，请稍后重试。',true);}
    finally{launcher.disabled=false;}
  }
  async function advance(direction){
    if(busy||!active)return;
    const token=gate.version,wanted=index+direction,done=wanted>=core.STEPS.length;setBusy(true);message.textContent='';
    try{
      await request({action:done?'complete':'progress',step:done?index:wanted});
      if(token!==gate.version||!active)return;
      if(done){close();if(typeof window.toast==='function')window.toast('使用指南已完成。接下来，按你的节奏开始。');}
      else{index=wanted;setBusy(false);showStep();}
    }catch{if(token===gate.version&&active){message.textContent='进度暂未保存，请再试一次；也可以跳过引导。';setBusy(false);schedule();}}
  }
  async function skipGuide(){
    if(!active)return;
    const step=index;close();launcher.disabled=true;
    try{await request({action:'skip',step},true);}
    catch{if(typeof window.toast==='function')window.toast('引导已关闭，进度暂未保存。',true);}
    finally{launcher.disabled=false;}
  }
  launcher.addEventListener('click',begin);previous.addEventListener('click',()=>advance(-1));next.addEventListener('click',()=>advance(1));skip.addEventListener('click',skipGuide);
  document.addEventListener('keydown',e=>{
    if(!active)return;
    if(e.key==='Escape'){e.preventDefault();skipGuide();}
    if(e.key==='Tab'){
      const buttons=[previous,skip,next].filter(b=>!b.hidden&&!b.disabled);
      const current=buttons.indexOf(document.activeElement);e.preventDefault();buttons[(current+(e.shiftKey?-1:1)+buttons.length)%buttons.length]?.focus();
    }
  });
  window.addEventListener('resize',schedule,{passive:true});window.addEventListener('scroll',()=>{if(active)schedule();},{passive:true});
  window.addEventListener('viewchange',()=>{if(!active)schedule();});document.addEventListener('visibilitychange',syncMotion);reduced.addEventListener('change',()=>{syncMotion();schedule();});
  document.addEventListener('change',e=>{if(e.target.id==='visual-effects-mode')syncMotion();});
  window.addEventListener('pagehide',()=>model.setActive(false));window.addEventListener('pageshow',syncMotion);
  async function initialize(){
    if(initialized)return;initialized=true;launcher.disabled=false;dock();syncMotion();const token=gate.version;
    if(location.hash==='#guide'){history.replaceState(null,'',location.pathname+location.search);begin();return;}
    try{const status=await request();if(status.auto_start&&!active)open(status.step,token);}
    catch{/* 机器人与手动入口保持可见，接口恢复后可重试。 */}
  }
  if(window.careerPlatformReady)initialize();else window.addEventListener('platform-loaded',initialize,{once:true});
  dock();syncMotion();
}
