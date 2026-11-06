import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../static/recruitment-bridge.js',import.meta.url),'utf8');
const prepare=source.slice(source.indexOf('function prepare('),source.indexOf('  async function initMail('));
function setup(){
  const fields=new Map();const get=id=>{if(!fields.has(id))fields.set(id,{value:'old',checked:true,hidden:false,replaceChildren(){this.cleared=true;}});return fields.get(id);};
  const context={platform:{interviewEpoch:2,interview:{id:4}},document:{querySelector:get},window:{CameraAssist:{stop(){}}},stopVoice(){},show(view){context.view=view;},toast(){}};
  vm.createContext(context);vm.runInContext(prepare,context);return {context,get};
}
test('一键岗位面试填入岗位并关闭旧媒体、清除旧对话，AI授权必须重新勾选',()=>{
  const {context,get}=setup();context.prepare({application_id:8,occupation:'后端开发',jd:'Python',job:{id:2}});
  assert.equal(context.platform.applicationId,8);assert.equal(context.platform.interview,null);assert.equal(context.platform.interviewEpoch,3);
  assert.equal(get('#interview-occupation').value,'后端开发');assert.equal(get('#interview-jd').value,'Python');assert.equal(get('#interview-consent').checked,false);
  assert.equal(get('#interview-messages').cleared,true);assert.equal(get('#interview-application-note').hidden,false);assert.equal(context.view,'interview');
});
test('个人练习不共享企业履历；非法application id不能准备表单',()=>{
  const {context,get}=setup();context.prepare({application_id:null,occupation:'开发',jd:'岗位要求'});
  assert.equal(get('#interview-application-note').hidden,true);assert.equal(context.platform.applicationId,null);
  context.prepare({application_id:'8',occupation:'错误',jd:'错误'});assert.equal(get('#interview-occupation').value,'开发');
});
