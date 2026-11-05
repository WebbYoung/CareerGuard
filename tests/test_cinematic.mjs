import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../static/cinematic.js',import.meta.url),'utf8');
function setup(hash,ready=false){
  const listeners={},opened=[];
  const window={careerPlatformReady:ready,matchMedia:()=>({matches:true,addEventListener(){}}),addEventListener:(event,fn)=>listeners[event]=fn};
  const document={querySelectorAll:()=>[],addEventListener(){},body:{classList:{add(){},remove(){}}}};
  const context={window,document,location:{hash},show:view=>opened.push(view)};
  vm.runInNewContext(source,context);
  return {listeners,opened,context};
}
test('首页直达入口等待平台加载后打开目标功能，不抢先调用未初始化视图',()=>{
  const s=setup('#interview');assert.deepEqual(s.opened,[]);
  assert.equal(typeof s.listeners['platform-loaded'],'function');
  s.listeners['platform-loaded']();assert.deepEqual(s.opened,['interview']);
});
test('只接受明确的前台页面，未知hash及管理员目标不会导航',()=>{
  for(const hash of ['#admin','#<script>','#__proto__','#constructor','']){
    const s=setup(hash);s.listeners['platform-loaded']();assert.deepEqual(s.opened,[]);
  }
});
test('平台加载完成后才响应hash切换，隐私入口导航正常',()=>{
  const s=setup('#tree');s.listeners.hashchange?.();assert.deepEqual(s.opened,[]);
  s.listeners['platform-loaded']();s.context.location.hash='#privacy';s.listeners.hashchange();
  assert.deepEqual(s.opened,['tree','privacy']);
});
test('视觉脚本迟到、平台已就绪时也能打开首页直达入口',()=>{
  const s=setup('#interview',true);assert.deepEqual(s.opened,['interview']);
  s.context.location.hash='#tree';s.listeners.hashchange();assert.deepEqual(s.opened,['interview','tree']);
});
