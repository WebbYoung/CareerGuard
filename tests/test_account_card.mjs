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
