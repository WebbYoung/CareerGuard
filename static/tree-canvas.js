/* 单指/鼠标共享手势：浏览器原生滚动负责裁剪和绘制，不逐帧重建节点。 */
window.TreeCanvas={
  attach(viewport,{onSelect,onClear,onNodeDragMove,onNodeDragEnd,onZoom}){
    let gesture=null,suppressClick=false,blocked=false;const pointers=new Set();
    function cancel(){
      const id=gesture?.id,interrupted=gesture;gesture=null;viewport.classList.remove('dragging');viewport.classList.remove('dragging-node');
      if(interrupted?.nodeDrag){onNodeDragEnd?.(interrupted.node,true);}
      if(id!==undefined&&viewport.hasPointerCapture(id))viewport.releasePointerCapture(id);
    }
    viewport.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;
      pointers.add(event.pointerId);
      if(pointers.size>1||!event.isPrimary){blocked=true;suppressClick=true;cancel();return;}
      if(blocked)return;
      suppressClick=false;hasPointerClick=false;
      gesture={id:event.pointerId,x:event.clientX,y:event.clientY,left:viewport.scrollLeft,top:viewport.scrollTop,dragged:false};
      // 在按下时捕获，滑到画布外仍能正确结束；click 用指针起点判断节点。
      gesture.node=event.target.closest('[data-skill-id]')?.dataset.skillId||null;
      viewport.setPointerCapture(event.pointerId);
    });
    viewport.addEventListener('pointermove',event=>{
      if(!gesture||gesture.id!==event.pointerId||blocked)return;
      const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
      if(!gesture.dragged&&Math.hypot(dx,dy)<6)return;
      gesture.dragged=true;suppressClick=true;event.preventDefault();
      if(gesture.node&&onNodeDragMove){gesture.nodeDrag=true;viewport.classList.add('dragging-node');onNodeDragMove(gesture.node,dx,dy);return;}
      viewport.classList.add('dragging');
      viewport.scrollLeft=Math.max(0,Math.min(viewport.scrollWidth-viewport.clientWidth,gesture.left-dx));
      viewport.scrollTop=Math.max(0,Math.min(viewport.scrollHeight-viewport.clientHeight,gesture.top-dy));
    });
    // 捕获导致 click 的目标可能变成画布，记录起点节点供随后 click 使用。
    let clickedNode=null,hasPointerClick=false;
    function end(event,cancelled=false){
      if(gesture?.id===event.pointerId){
        const moved=Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>=6;
        suppressClick=suppressClick||moved||cancelled;
        clickedNode=gesture.node;hasPointerClick=!cancelled;
        if(gesture.nodeDrag){gesture.nodeDrag=false;onNodeDragEnd?.(gesture.node,cancelled);}
        cancel();
      }
      pointers.delete(event.pointerId);if(!pointers.size)blocked=false;
    }
    viewport.addEventListener('pointerup',event=>end(event));
    viewport.addEventListener('pointercancel',event=>end(event,true));
    viewport.addEventListener('lostpointercapture',()=>{if(gesture){suppressClick=true;cancel();}pointers.clear();blocked=false;});
    viewport.addEventListener('click',event=>{
      if(event.detail!==0&&suppressClick){event.preventDefault();event.stopImmediatePropagation();hasPointerClick=false;return;}
      const id=event.detail!==0&&hasPointerClick?clickedNode:event.target.closest('[data-skill-id]')?.dataset.skillId;
      hasPointerClick=false;if(id)onSelect(id);else onClear();
    },true);
    viewport.addEventListener('wheel',event=>{if(!onZoom||!Number.isFinite(event.deltaY))return;event.preventDefault();onZoom({deltaY:event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?viewport.clientHeight:1),clientX:event.clientX,clientY:event.clientY});},{passive:false});
    viewport.addEventListener('keydown',event=>{if(event.key==='Escape'){onClear();viewport.focus();}});
    return {cancel(){suppressClick=true;hasPointerClick=false;cancel();pointers.clear();blocked=false;}};
  }
};
