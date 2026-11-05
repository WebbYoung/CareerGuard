import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),Guide=require('../static/guide-core.js');
test('十步覆盖真实前台入口且目标选择器固定，不拼接用户内容',()=>{
  assert.equal(Guide.STEPS.length,10);
  assert.deepEqual(Guide.STEPS.map(s=>s.view),['overview','materials','risk','privacy','career','tree','exam','interview','jobs','profile']);
  assert.ok(Guide.STEPS.every(s=>typeof s.target==='string'&&s.title&&s.body));
});
test('桌面与手机、靠近各边角的目标都保证机器人和气泡在视口内',()=>{
  for(const [width,height] of [[1440,1024],[390,844],[320,568],[844,390]]){
    for(const target of [{left:0,top:0,right:70,bottom:45},{left:width-70,top:height-40,right:width,bottom:height},{left:20,top:height/2-80,right:width-20,bottom:height/2+80}]){
      const layout=Guide.place(target,{width,height});
      for(const r of [layout.robot,layout.bubble])assert.ok(r.x>=0&&r.y>=0&&r.x+r.width<=width+.1&&r.y+r.height<=height+.1,JSON.stringify({width,height,r}));
      assert.ok(layout.aim.x>=0&&layout.aim.x<=width&&layout.aim.y>=0&&layout.aim.y<=height);
    }
  }
});
test('有空间时气泡与目标分开，机器人在气泡旁边',()=>{
  const target={left:500,top:250,right:800,bottom:350},r=Guide.place(target,{width:1440,height:1024});
  assert.ok(r.bubble.y>=target.bottom||r.bubble.y+r.bubble.height<=target.top||r.bubble.x>=target.right||r.bubble.x+r.bubble.width<=target.left);
  assert.ok(r.robot.x>=r.bubble.x+r.bubble.width);
});
test('自动GET与手动POST乱序返回时只进入一次，关闭后不会保留重复模态锁',()=>{
  const gate=Guide.createGate(),automatic=gate.version,manual=gate.begin();
  assert.equal(gate.enter(automatic),false);assert.equal(gate.enter(manual),true);
  assert.equal(gate.enter(manual),false);gate.close();assert.equal(gate.active,false);
  assert.equal(gate.enter(automatic),false);
});
test('关闭会使迟到的步骤保存和启动结果失效，新一轮仍能正常进入',()=>{
  const gate=Guide.createGate(),start=gate.begin();assert.equal(gate.enter(start),true);
  const pending=gate.version;gate.close();assert.notEqual(gate.version,pending);
  assert.equal(gate.enter(start),false);assert.equal(gate.enter(gate.begin()),true);
});
