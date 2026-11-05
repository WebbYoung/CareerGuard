import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../static/tree-canvas.js',import.meta.url),'utf8');
function setup(options={}){
 const handlers={},selected=[],classes=new Set();let clears=0;
 const viewport={scrollLeft:100,scrollTop:90,scrollWidth:1000,scrollHeight:800,clientWidth:400,clientHeight:300,
 classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},addEventListener:(k,f)=>handlers[k]=f,
 setPointerCapture(){},releasePointerCapture(){},hasPointerCapture:()=>true};
 const context={window:{}};vm.createContext(context);vm.runInContext(source,context);
 const api=context.window.TreeCanvas.attach(viewport,{onSelect:id=>selected.push(id),onClear:()=>clears++,...options});
 const target=id=>({closest:selector=>selector==='[data-skill-id]'&&id?{dataset:{skillId:id}}:null});
 function fire(type,{x=100,y=100,id=null,pointerId=1,...extra}={}){let stopped=false;handlers[type]?.({button:0,isPrimary:true,pointerId,clientX:x,clientY:y,detail:1,target:target(id),preventDefault(){stopped=true;},stopImmediatePropagation(){stopped=true;},...extra});return stopped;}
 return {viewport,selected,classes,api,fire,get clears(){return clears;}};
}
test('鼠标拖动只移动画布，抬起后不选择节点或关闭详情',()=>{const s=setup();s.fire('pointerdown');s.fire('pointermove',{x:40,y:60});assert.equal(s.viewport.scrollLeft,160);assert.equal(s.viewport.scrollTop,130);s.fire('pointerup',{x:40,y:60});assert.ok(s.fire('click',{id:'n1'}));assert.deepEqual(s.selected,[]);assert.equal(s.clears,0);assert.ok(!s.classes.has('dragging'));});
test('轻触节点切换选择，轻触空白关闭，微小抖动仍可点击',()=>{const s=setup();s.fire('pointerdown',{id:'n1'});s.fire('pointermove',{id:'n1',x:103});s.fire('pointerup',{id:'n1',x:103});s.fire('click',{id:'n1'});s.fire('pointerdown',{id:'n2'});s.fire('pointerup',{id:'n2'});s.fire('click',{id:'n2'});s.fire('pointerdown');s.fire('pointerup');s.fire('click');assert.deepEqual(s.selected,['n1','n2']);assert.equal(s.clears,1);});
test('单指拖动有边界，拖回起点仍抑制点击，下一次点击恢复',()=>{const s=setup();s.fire('pointerdown',{pointerType:'touch'});s.fire('pointermove',{x:-5000,y:-5000});assert.equal(s.viewport.scrollLeft,600);assert.equal(s.viewport.scrollTop,500);s.fire('pointermove',{x:100,y:100});s.fire('pointerup');s.fire('click',{id:'n1'});assert.deepEqual(s.selected,[]);s.fire('pointerdown');s.fire('pointermove',{x:5000,y:5000});assert.equal(s.viewport.scrollLeft,0);assert.equal(s.viewport.scrollTop,0);s.fire('pointerup');s.fire('pointerdown',{id:'n2'});s.fire('pointerup',{id:'n2'});s.fire('click',{id:'n2'});assert.deepEqual(s.selected,['n2']);});
test('取消手势后不残留拖动，键盘点击可正常选中',()=>{const s=setup();s.fire('pointerdown');s.fire('pointermove',{x:40});s.fire('pointercancel');assert.ok(!s.classes.has('dragging'));s.fire('click',{id:'n1',detail:0});assert.deepEqual(s.selected,['n1']);});
test('第二根手指中断平移，复位取消进行中的手势',()=>{const s=setup();s.fire('pointerdown',{pointerType:'touch'});s.fire('pointerdown',{pointerId:2,isPrimary:false,pointerType:'touch'});s.fire('pointermove',{x:20});assert.equal(s.viewport.scrollLeft,100);s.fire('pointerup',{pointerId:2});s.fire('pointerup');s.fire('pointerdown');s.fire('pointermove',{x:30});s.api.cancel();assert.ok(!s.classes.has('dragging'));s.fire('pointermove',{x:0});assert.equal(s.viewport.scrollLeft,170);});

test('指针捕获将点击目标改为画布时，仍选择按下的节点',()=>{const s=setup();s.fire('pointerdown',{id:'n1'});s.fire('pointerup');s.fire('lostpointercapture');s.fire('click');assert.deepEqual(s.selected,['n1']);assert.equal(s.clears,0);});

test('拖动节点只通知节点坐标变化，不平移画布且不误点',()=>{const moves=[],ends=[];const s=setup({onNodeDragMove:(id,dx,dy)=>moves.push([id,dx,dy]),onNodeDragEnd:(id,cancelled)=>ends.push([id,cancelled])});s.fire('pointerdown',{id:'n1'});s.fire('pointermove',{x:150,y:130,id:'n1'});s.fire('pointerup',{x:150,y:130});s.fire('click');assert.equal(s.viewport.scrollLeft,100);assert.deepEqual(moves,[['n1',50,30]]);assert.deepEqual(ends,[['n1',false]]);assert.equal(s.clears,0);});
test('滚轮缩放传递鼠标锚点并阻止页面滚动',()=>{const events=[];const s=setup({onZoom:event=>events.push(event)});assert.ok(s.fire('wheel',{x:150,y:180,deltaY:-100,deltaMode:0}));assert.equal(events[0].clientX,150);assert.equal(events[0].deltaY,-100);});
