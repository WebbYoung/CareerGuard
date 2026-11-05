/* 纯显示规划：不修改技能、前置关系或考核进度。导航线与真实依赖明确分开。 */
window.StarDisplay={
  nextExpanded(current,index,effectiveOpen){const next=new Set(current);effectiveOpen?next.delete(index):next.add(index);return [...next];},
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
