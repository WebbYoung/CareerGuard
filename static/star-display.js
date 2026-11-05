/* 纯显示规划：不修改技能、前置关系或考核进度。导航线与真实依赖明确分开。 */
window.StarDisplay={
  nodeBox(point,width,height,delta,baseZoom){return {x:point.x-width/(2*baseZoom),y:point.y-(height/2-delta)/baseZoom,width:width/baseZoom,height:height/baseZoom};},
  fitView(boxes,width,height,padding=28){
    if(!boxes.length)return {zoom:1,cx:0,cy:0};
    const left=Math.min(...boxes.map(b=>b.x)),top=Math.min(...boxes.map(b=>b.y)),right=Math.max(...boxes.map(b=>b.x+b.width)),bottom=Math.max(...boxes.map(b=>b.y+b.height));
    return {zoom:Math.min(1.2,Math.max(1,width-padding*2)/Math.max(1,right-left),Math.max(1,height-padding*2)/Math.max(1,bottom-top)),cx:(left+right)/2,cy:(top+bottom)/2};
  },
  nextExpanded(current,index,effectiveOpen){const next=new Set(current);effectiveOpen?next.delete(index):next.add(index);return [...next];},
  clampCluster(point,children,width,height,zoom){
    const dx=[0,...children.map(p=>p.x)],dy=[0,...children.map(p=>p.y)];
    return {...point,x:Math.max(85/zoom-Math.min(...dx),Math.min(width-90/zoom-Math.max(...dx),point.x)),y:Math.max(45/zoom-Math.min(...dy),Math.min(height-100/zoom-Math.max(...dy),point.y))};
  },
  freeGrid(point,others,zoom){return this.freeCluster(point,[],others,zoom);},
  freeCluster(point,children,others,zoom){
    const G=window.StarGraph,clear=p=>[p,...children.map(q=>({x:p.x+q.x,y:p.y+q.y}))].every(member=>member.x>=85/zoom&&member.y>=45/zoom&&others.every(q=>!G.overlaps(member,q,zoom)));
    if(clear(point))return {...point};
    for(let ring=1;ring<40;ring++){
      const offsets=[];for(let dx=-ring;dx<=ring;dx++)for(let dy=-ring;dy<=ring;dy++)if(Math.max(Math.abs(dx),Math.abs(dy))===ring)offsets.push({dx,dy});
      offsets.sort((a,b)=>Math.abs(a.dx)+Math.abs(a.dy)-Math.abs(b.dx)-Math.abs(b.dy)||Math.abs(a.dx)-Math.abs(b.dx)||b.dy-a.dy||a.dx-b.dx);
      for(const {dx,dy} of offsets){const p={...point,x:point.x+dx*164/zoom,y:point.y+dy*146/zoom};if(clear(p))return p;}
    }
    return {...point,x:Math.max(85/zoom,...others.map(p=>p.x+164/zoom))-Math.min(0,...children.map(p=>p.x)),y:Math.max(45/zoom,point.y)-Math.min(0,...children.map(p=>p.y))};
  },
  orderedLayout(graph,display,base,zoom,overrides=new Map()){
    const G=window.StarGraph,career=base.focus;if(!career)return G.separate(base,zoom,overrides);
    const actualZoom=zoom;zoom=Math.min(base.gridZoom||zoom,zoom);
    const required=G.required(graph,career),byId=new Map(graph.nodes.map(n=>[n.id,n])),depths=new Map();
    function depth(id){if(depths.has(id))return depths.get(id);const n=byId.get(id),value=n.prerequisites.length?1+Math.max(...n.prerequisites.map(depth)):0;depths.set(id,value);return value;}
    const buckets=G.stages.map((stage,index)=>({stage,index,nodes:graph.nodes.filter(n=>required.has(n.id)&&n.stage===stage).sort((a,b)=>depth(a.id)-depth(b.id)||a.name.localeCompare(b.name,'zh-CN')||a.id.localeCompare(b.id))})).filter(b=>b.nodes.length);
    buckets.forEach(b=>{b.cols=b.nodes.length>=3?2:1;b.width=b.cols*164;});
    const total=buckets.reduce((sum,b)=>sum+b.width,0)+Math.max(0,buckets.length-1)*64;
    const left=Math.max(120/zoom,950-total/(2*zoom)),top=Math.max(250/zoom,850-100/zoom),points=new Map(),order=new Map(),sections=[];
    const maxRows=Math.max(1,...buckets.map(b=>Math.ceil(b.nodes.length/b.cols)));
    const cx=left+total/(2*zoom);points.set('student',{kind:'student',x:cx,y:top-160/zoom});
    points.set(career.id,{kind:'career',x:cx,y:top+((maxRows+1)*144+30)/zoom});
    let offset=0;
    for(const bucket of buckets){
      const groupId='@stage:'+bucket.index,defaultGroup={x:left+(offset+bucket.width/2)/zoom,y:top},manualGroup=overrides.get(groupId),shift={x:manualGroup?manualGroup.x-defaultGroup.x:0,y:manualGroup?manualGroup.y-defaultGroup.y:0};
      if(display.groups.some(g=>g.id===groupId))points.set(groupId,{kind:'group',...defaultGroup});
      const section={index:bucket.index,groupId,cols:bucket.cols,left:left+offset/zoom,top,width:bucket.width/zoom,rows:Math.ceil(bucket.nodes.length/bucket.cols)};sections.push(section);
      bucket.nodes.forEach((n,index)=>{order.set(n.id,index+1);if(display.skillIds.has(n.id))points.set(n.id,{kind:'skill',x:left+(offset+82+(index%bucket.cols)*164)/zoom+shift.x,y:top+(Math.floor(index/bucket.cols)+1)*144/zoom+shift.y});});
      offset+=bucket.width+64;
    }
    const placed=[],final=new Map();
    const entries=[...points].sort(([a],[b])=>Number(overrides.has(b))-Number(overrides.has(a)));
    for(const [id,p] of entries){const actual=this.freeGrid({...p,...overrides.get(id)},placed,actualZoom);placed.push(actual);final.set(id,actual);}
    return {...base,points:final,order,sections,gridZoom:zoom,cx,cy:top+55/zoom,width:Math.max(1900,...placed.map(p=>p.x+120/zoom)),height:Math.max(1700,...placed.map(p=>p.y+120/zoom))};
  },
  plan(graph,{focus=null,selected=null,full=false,expanded=[]}={}){
    const G=window.StarGraph,career=graph.careers.find(c=>c.id===focus),skillIds=new Set(),groups=[],edges=[];
    const link=(from,to,navigation=false)=>edges.push({from,to,navigation});
    if(!career){graph.careers.forEach(c=>link('student',c.id,true));return {skillIds,groups,edges};}
    const required=G.required(graph,career),nodes=graph.nodes.filter(n=>required.has(n.id)),chosen=nodes.find(n=>n.id===selected);
    if(full){
      nodes.forEach(n=>{skillIds.add(n.id);if(!n.prerequisites.length)link('student',n.id,true);n.prerequisites.forEach(id=>link(id,n.id));});
      const parents=new Set(nodes.flatMap(n=>n.prerequisites));nodes.filter(n=>!parents.has(n.id)).forEach(n=>link(n.id,career.id,true));
      return {skillIds,groups,edges};
    }
    const open=new Set(expanded);
    if(chosen){
      open.add(G.stages.indexOf(chosen.stage));skillIds.add(chosen.id);
      chosen.prerequisites.forEach(id=>{skillIds.add(id);link(id,chosen.id);});
      nodes.filter(n=>n.prerequisites.includes(chosen.id)).forEach(n=>{skillIds.add(n.id);link(chosen.id,n.id);});
      if(!chosen.prerequisites.length)link('student',chosen.id,true);
      if(!nodes.some(n=>n.prerequisites.includes(chosen.id)))link(chosen.id,career.id,true);
    }
    G.stages.forEach((stage,index)=>{
      const members=nodes.filter(n=>n.stage===stage);if(!members.length)return;
      if(open.has(index))members.forEach(n=>skillIds.add(n.id));
      groups.push({id:'@stage:'+index,stage,index,count:members.length,expanded:open.has(index),hiddenCount:0});
    });
    groups.forEach(g=>g.hiddenCount=nodes.filter(n=>n.stage===g.stage&&!skillIds.has(n.id)).length);
    if(!chosen){let previous='student';groups.forEach(group=>{link(previous,group.id,true);previous=group.id;});link(previous,career.id,true);}
    return {skillIds,groups,edges};
  }
};
