/* 有预算的视觉核心；无DOM、网络或用户数据依赖，浏览器/Node共用。 */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.CareerFXCore=api;
})(typeof window==='undefined'?this:window,function(){
  'use strict';
  function budget(width,mode='full',reduced=false){
    const small=width<700,lite=mode==='lite',off=mode==='off';
    return {particles:off?0:reduced?24:small?(lite?18:38):(lite?38:92),links:off?0:small?16:lite?32:90,
      meteors:off||reduced?0:small?2:lite?2:8,fps:off||reduced?0:small?24:lite?20:30,dpr:lite?1:1.5};
  }
  function createField(width,height,count,random=Math.random){
    return Array.from({length:count},()=>({x:random()*width,y:random()*height,vx:(random()-.5)*15,vy:(random()-.5)*11,r:.6+random()*1.6,phase:random()*Math.PI*2,hue:random()>.5?192:244}));
  }
  function stepField(points,dt,width,height){
    const delta=Math.max(0,Math.min(.05,dt));
    points.forEach(p=>{p.x=(p.x+p.vx*delta+width)%width;p.y=(p.y+p.vy*delta+height)%height;});
  }
  function nearLinks(points,distance,limit){
    if(limit<=0)return [];
    const out=[],max=distance*distance;
    for(let a=0;a<points.length;a++)for(let b=a+1;b<points.length;b++){
      const dx=points[a].x-points[b].x,dy=points[a].y-points[b].y;
      if(dx*dx+dy*dy<max){out.push([a,b,Math.sqrt(dx*dx+dy*dy)/distance]);if(out.length>=limit)return out;}
    }
    return out;
  }
  function makeMeteor(width,height,random=Math.random){
    const speed=300+random()*250;
    return {x:width*(.2+random()*1.1),y:-30-random()*height*.22,vx:-speed,vy:speed*.62,length:90+random()*180,age:0,life:1.1+random()*1.5,hue:random()>.55?195:245};
  }
  function advanceMeteors(meteors,dt,width,height){
    return meteors.filter(m=>{m.age+=dt;m.x+=m.vx*dt;m.y+=m.vy*dt;return m.age<m.life&&m.x>-m.length&&m.y<height+m.length;});
  }
  function createLoop({request,cancel,draw,interval=33}){
    let active=false,dead=false,id=null,last=null,epoch=0;
    const schedule=()=>{
      if(!active||dead||id!==null)return;
      const generation=epoch;
      id=request(stamp=>{
        if(generation!==epoch||!active||dead)return;
        id=null;
        if(last===null||stamp-last>=interval){const dt=last===null?0:Math.min(.05,(stamp-last)/1000);last=stamp;draw(dt,stamp);}
        schedule();
      });
    };
    return {setActive(next){
      if(dead||active===Boolean(next))return;
      active=Boolean(next);epoch++;last=null;
      if(id!==null){cancel(id);id=null;}
      if(active)schedule();
    },dispose(){active=false;dead=true;epoch++;if(id!==null)cancel(id);id=null;last=null;}};
  }
  return {budget,createField,stepField,nearLinks,makeMeteor,advanceMeteors,createLoop};
});
