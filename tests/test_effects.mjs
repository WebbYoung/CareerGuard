import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const FX=require('../static/effects-core.js');
test('移动端及轻量模式削减预算，关闭与减少动态没有连续帧',()=>{
  const full=FX.budget(1440,'full',false),mobile=FX.budget(390,'full',false),lite=FX.budget(1440,'lite',false);
  assert.ok(full.particles>mobile.particles&&full.particles>lite.particles);
  assert.ok(full.meteors<=8&&full.links<=100&&full.particles<=100);
  assert.equal(FX.budget(1440,'off',false).fps,0);
  assert.equal(FX.budget(1440,'full',true).fps,0);
});
test('帧循环重复开启只调度一帧，暂停取消，迟到帧不能复活',()=>{
  const pending=new Map();let seq=0,draws=0;
  const loop=FX.createLoop({request:fn=>{pending.set(++seq,fn);return seq;},cancel:id=>pending.delete(id),draw:()=>draws++,interval:30});
  loop.setActive(true);loop.setActive(true);assert.equal(pending.size,1);
  const stale=[...pending.values()][0];loop.setActive(false);assert.equal(pending.size,0);
  stale(100);assert.equal(draws,0);assert.equal(pending.size,0);
  loop.setActive(true);assert.equal(pending.size,1);loop.dispose();assert.equal(pending.size,0);
});
test('帧循环按时间限帧，draw中暂停不会重新预约',()=>{
  let fn,draws=0,loop;
  loop=FX.createLoop({request:cb=>(fn=cb,1),cancel:()=>{},draw:()=>{if(++draws===2)loop.setActive(false);},interval:33});
  loop.setActive(true);fn(0);fn(10);assert.equal(draws,1);fn(40);assert.equal(draws,2);
  fn(80);assert.equal(draws,2);
});
test('粒子有界且超长暂停不会造成超大位移；连线不重复并遵守上限',()=>{
  const p=FX.createField(100,100,30,()=>0.5),before=p[0].x;
  p[0].vx=50;p[0].vy=-40;FX.stepField(p,100,100,100);assert.ok(Math.abs(p[0].x-before)<5);
  assert.ok(p.every(s=>s.x>=0&&s.x<=100&&s.y>=0&&s.y<=100));
  const links=FX.nearLinks(p,200,15);assert.equal(links.length,15);assert.deepEqual(FX.nearLinks(p,200,0),[]);
  assert.equal(new Set(links.map(([a,b])=>a+':'+b)).size,links.length);assert.ok(links.every(([a,b])=>a<b));
});
test('过期流星被移除，不累计不可见对象',()=>{
  const meteor=FX.makeMeteor(1000,800,()=>0.5);
  const result=FX.advanceMeteors([meteor],meteor.life+1,1000,800);assert.equal(result.length,0);
});
