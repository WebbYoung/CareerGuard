import {createGuideRobot} from './robot-model.js';

// 首页的同一形象入口；完整引导仅在已登录工作台运行。
const assistant=document.createElement('div');assistant.className='robot-assistant';
const host=document.createElement('div');host.className='robot-model';
const link=document.createElement('a');link.className='robot-launcher';link.href='/app#guide';link.setAttribute('aria-label','让小安带我开始使用职安');link.title='进入工作台，让小安带你了解职安';
const tag=document.createElement('span');tag.className='robot-name';tag.textContent='小安 · 带你开始';assistant.append(host,link,tag);document.body.append(assistant);
const reduced=matchMedia('(prefers-reduced-motion: reduce)'),model=createGuideRobot(host,{reducedMotion:reduced.matches});
function dock(){const w=innerWidth<700?92:112,h=innerWidth<700?122:146;assistant.style.width=w+'px';assistant.style.height=h+'px';assistant.style.transform=`translate3d(${Math.max(8,innerWidth-w-16)}px,${Math.max(12,innerHeight-h-38)}px,0)`;model.resize();}
function sync(){const off=document.querySelector('#visual-effects-mode')?.value==='off';model.setReducedMotion(reduced.matches||off);model.setActive(!document.hidden&&!off);}
window.addEventListener('resize',dock,{passive:true});document.addEventListener('visibilitychange',sync);reduced.addEventListener('change',sync);
document.addEventListener('change',e=>{if(e.target.id==='visual-effects-mode')sync();});window.addEventListener('pagehide',()=>model.setActive(false));window.addEventListener('pageshow',sync);dock();sync();
