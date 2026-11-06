import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../static/effects.js',import.meta.url),'utf8');
const upgrade=source.slice(source.indexOf('function upgradeIcons('),source.indexOf('  const visibleObserver'));

test('头像装饰保留用户头像和昵称首字，不替换为通用玻璃图标',()=>{
  let replacements=0;
  const el={dataset:{},textContent:'逐',classList:{contains:name=>name==='account-nav-avatar'},matches:selector=>selector!=='svg',querySelectorAll:()=>[],closest:()=>null,replaceChildren(){replacements++;}};
  const context={newIcon:()=>({})};vm.createContext(context);vm.runInContext(upgrade,context);
  context.upgradeIcons(el);
  assert.equal(replacements,0);
  assert.equal(el.dataset.fxIcon,undefined);
});

test('资料组件脚本晚于平台就绪时仍加载昵称，不必先打开个人中心',async()=>{
  const elements=new Map();let requests=0;
  const el=()=>({textContent:'',classList:{add(){},toggle(){}},append(){},replaceChildren(){},setAttribute(){},querySelectorAll:()=>[],addEventListener(){}});
  const get=selector=>{if(!elements.has(selector))elements.set(selector,el());return elements.get(selector);};
  const context={platform:{user:{id:1,username:'synthetic'}},window:{careerPlatformReady:true,addEventListener(){},api:async()=>{requests++;return {nickname:'探索者',city:'',bio:'',created:'2026-11-06',has_avatar:false};}},document:{querySelector:get,createElement:el,body:{append(){}}}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(new URL('../static/account-card.js',import.meta.url),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests,1);assert.equal(get('#account-top').textContent,'探索者');
});
