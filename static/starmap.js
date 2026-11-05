/* 星图视图：正式模式使用服务器考试进度；演示模式只修改本页内存。 */
window.StarMap=(()=>{
  const palette=['#87adf2','#b19cea','#74c8bd','#a6a1ee','#d1a1bb','#8ebbd3','#aecb93','#c6ad89','#92a5d7'];
  const glyphs=['⌘','⬡','▥','✦','◇','☁','✓','▯','⌁'];
  const S={mode:'live',graph:null,progress:[],focus:null,selected:null,zoom:1,layout:null,initialized:false,achievementTimer:null,pendingAchievements:[],positions:new Map(),drag:null,dragFrame:0,wheelFrame:0,wheelDelta:0,settleTimer:0};
  const get=id=>document.getElementById(id),el=(tag,cls='',value='')=>node(tag,cls,value);
  function setText(id,value){get(id).textContent=value;}
  function careerIndex(id){return Math.max(0,S.graph.careers.findIndex(c=>c.id===id));}
  function theme(id){const i=careerIndex(id);return {color:palette[i%palette.length],glyph:glyphs[i%glyphs.length]};}
  function view(){return S.graph?StarGraph.decorate(S.graph,S.progress):null;}
  function modeUI(){
    document.querySelectorAll('.star-mode-switch button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.star===S.mode)));
    get('star-demo-actions').hidden=S.mode!=='demo';setText('star-mode-tag',S.mode==='demo'?'演示星图 · 不写入个人进度':'AI 个人星图');
    setText('star-source',S.mode==='demo'?'九方向示例，个人星图由 AI 动态生成':'根据专业、岗位与能力差距动态生成');
    get('tree-workspace').hidden=false;
  }
  function load(value){
    platform.canvas?.cancel();S.mode='live';S.graph=value.tree;S.progress=[...value.progress];S.focus=null;S.selected=null;platform.tree=value;
    setText('tree-title',value.tree.title);setText('tree-state','完成节点考核后解锁后续技能，旧版自我记录不作为考核结果。');
    get('tree-config').open=false;modeUI();draw(true);
  }
  function switchMode(mode){
    platform.canvas?.cancel();if(mode==='demo'){
      S.mode='demo';S.graph=StarGraph.demo();S.progress=[];S.focus=null;S.selected=null;get('tree-config').open=false;modeUI();draw(true);
    }else if(platform.tree)load(platform.tree);
    else{S.mode='live';S.graph=null;S.progress=[];S.selected=null;S.focus=null;modeUI();drawEmpty();get('tree-config').open=true;}
  }
  function drawEmpty(){
    const scene=get('tree-scene'),space=get('tree-space');scene.replaceChildren();scene.style.cssText='';space.style.cssText='';
    const empty=el('div','star-empty');empty.append(el('span','','✧'),el('h2','','你的成长星图，由你定义'),el('p','','输入目标岗位和已有基础，让 AI 连接你的技能与职业方向。也可以先探索九方向演示。'));
    const b=el('button','','探索演示星图');b.type='button';b.addEventListener('click',()=>switchMode('demo'));empty.append(b);scene.append(empty);scene.style.height='620px';scene.style.width='100%';
    setText('tree-title','等待点亮的成长宇宙');setText('tree-progress','0 / 0');setText('star-level','LV.01');setText('star-level-name','学习者成长起点');setText('star-career-count','—');get('star-progress-fill').style.transform='scaleX(0)';setText('tree-zoom','—');setText('star-focus-label','职业总览');setText('tree-summary','先定义目标，再连接每一步成长。');renderDetail();
  }
  function updateHUD(g){
    const completed=g.nodes.filter(n=>n.status==='completed').length,total=g.nodes.length,level=1+Math.floor(completed/4);
    setText('tree-title',g.title);setText('tree-progress',completed+' / '+total+' 项');setText('star-level','LV.'+String(level).padStart(2,'0'));
    setText('star-level-name',completed===0?(g.learner_label||'学习者成长起点')+' · 探索者':completed<8?'基础积累 · 持续进阶':completed<18?'技能连接 · 实践成长':'项目进阶 · 职业探索');
    setText('star-career-count',g.careers.length);get('star-progress-fill').style.transform='scaleX('+(total?completed/total:0)+')';
    const c=g.careers.find(c=>c.id===S.focus);setText('star-focus-label',c?c.name+' · 技能路径':'职业总览');setText('tree-summary',c?'共享基础 → 方向探索 → 专业能力 → 项目实战':'点击职业方向，展开共享技能与汇合路径。');
  }
  function layoutKey(){return S.mode+':'+(S.mode==='live'?platform.tree?.id:'sample')+':'+(S.focus||'overview');}
  function displayedIds(){return new Set([...S.layout.points].filter(([id,p])=>p.kind!=='skill'||S.focus||S.zoom>=.32).map(([id])=>id));}
  function fitZoom(){const vp=get('tree-scroll');return Math.max(.2,Math.min(.9,vp.clientWidth/1900*.98,vp.clientHeight/1700*.98));}
  function draw(fit=false){
    if(!S.graph){drawEmpty();return;}
    platform.canvas?.cancel();const g=view();S.layout=StarGraph.layout(g,S.focus);
    if(fit)S.zoom=S.focus?Math.max(.4,fitZoom()):fitZoom();
    S.layout=StarGraph.separate(S.layout,S.zoom,S.positions.get(layoutKey())||new Map(),displayedIds());
    const scene=get('tree-scene');scene.replaceChildren();scene.style.width=S.layout.width+'px';scene.style.height=S.layout.height+'px';
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width',S.layout.width);svg.setAttribute('height',S.layout.height);svg.setAttribute('aria-hidden','true');scene.append(svg);
    for(const [id,p] of S.layout.points){
      const n=g.nodes.find(n=>n.id===id),c=g.careers.find(c=>c.id===id);
      // 小屏总览只展示中心与职业星座；真实基础技能在聚焦视图完整展开。
      if(!S.focus&&n&&S.zoom<.32)continue;
      const kind=p.kind,b=el('button','star-node '+kind+(n?' '+n.status:c&&c.coverage===100?' completed':''));b.type='button';b.dataset.skillId=id;
      b.style.left=(p.x-56)+'px';b.style.top=(p.y-52.5)+'px';b.style.width='112px';
      const orb=el('span','star-orb',kind==='student'?'⌘':kind==='career'?theme(id).glyph:n.status==='completed'?'✓':n.status==='locked'?'⌑':StarGraph.stages.indexOf(n.stage)===3?'⬡':'✧');orb.setAttribute('aria-hidden','true');b.append(orb);
      const label=kind==='student'?(g.learner_label||'学习者成长起点'):n?n.name:c.name;b.append(el('span','star-node-label',label));
      b.append(el('span','star-node-meta',kind==='student'?'成长起点':c?'技能覆盖率 '+c.coverage+'%':n.shared_count>1?'共享于 '+n.shared_count+' 个方向':n.status==='locked'?'前置待完成':n.status==='completed'?'考核完成':'可以学习'));
      b.setAttribute('aria-label',label+(n?'，'+({locked:'未解锁',available:'可学习',completed:'已完成'}[n.status]):c?'，技能覆盖率'+c.coverage+'%':''));b.setAttribute('aria-pressed',String(S.selected===id));
      if(c)b.style.setProperty('--career-color',theme(id).color);scene.append(b);
    }
    applyZoom(fit);updateHUD(g);highlight();renderDetail();
  }
  function applyZoom(center=false){
    if(!S.graph)return;const scene=get('tree-scene'),space=get('tree-space');scene.style.width=S.layout.width+'px';scene.style.height=S.layout.height+'px';const svg=scene.querySelector('svg');if(svg){svg.setAttribute('width',S.layout.width);svg.setAttribute('height',S.layout.height);}scene.style.transform=`scale(${S.zoom})`;
    const viewport=get('tree-scroll'),pad=80;space.style.width=Math.max(viewport.clientWidth,S.layout.width*S.zoom)+pad*2+'px';space.style.height=Math.max(viewport.clientHeight,S.layout.height*S.zoom)+pad*2+'px';space.style.marginLeft='0';space.style.marginTop='0';scene.style.left=pad+Math.max(0,(viewport.clientWidth-S.layout.width*S.zoom)/2)+'px';scene.style.top=pad+Math.max(0,(viewport.clientHeight-S.layout.height*S.zoom)/2)+'px';
    const geometry=[...scene.querySelectorAll('.star-node')].map(b=>{const orb=b.querySelector('.star-orb');return {b,height:b.offsetHeight,delta:b.offsetHeight/2-orb.offsetTop-orb.offsetHeight/2,p:S.layout.points.get(b.dataset.skillId)};});
    geometry.forEach(({b,height,delta,p})=>{b.dataset.anchor=String(delta);b.dataset.layoutHeight=String(height);b.style.left=(p.x-56)+'px';b.style.transform=`scale(${1/S.zoom})`;b.style.top=(p.y-height/2+delta/S.zoom)+'px';});setText('tree-zoom',Math.round(S.zoom*100)+'%');drawEdges();
    if(center){const vp=get('tree-scroll');vp.scrollLeft=Math.max(0,scene.offsetLeft+S.layout.cx*S.zoom-vp.clientWidth/2);vp.scrollTop=Math.max(0,scene.offsetTop+S.layout.cy*S.zoom-vp.clientHeight/2);}
  }
  function pathFor(from,to,aggregate=false){
    const a=S.layout.points.get(from),b=S.layout.points.get(to);if(!a||!b)return '';
    const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);if(length<1)return '';
    const trim=Math.min(length*.22,28/S.zoom),sx=a.x+dx/length*trim,sy=a.y+dy/length*trim,ex=b.x-dx/length*trim,ey=b.y-dy/length*trim;
    const bend=aggregate?length*.07:length*.035;
    return `M${sx},${sy} Q${(sx+ex)/2-dy/length*bend},${(sy+ey)/2+dx/length*bend} ${ex},${ey}`;
  }
  function drawEdges(){
    const svg=get('tree-scene').querySelector('svg');if(!svg)return;svg.replaceChildren();const g=view(),ns='http://www.w3.org/2000/svg',make=tag=>document.createElementNS(ns,tag);
    const defs=make('defs'),marker=make('marker');marker.id='star-arrow';marker.setAttribute('viewBox','0 0 8 8');marker.setAttribute('refX','7');marker.setAttribute('refY','4');marker.setAttribute('markerWidth','6');marker.setAttribute('markerHeight','6');marker.setAttribute('orient','auto');const arrow=make('path');arrow.setAttribute('d','M1 1 L7 4 L1 7');arrow.setAttribute('fill','none');arrow.setAttribute('stroke','#6e83ac');marker.append(arrow);defs.append(marker);svg.append(defs);
    const orbits=make('g');orbits.setAttribute('class','star-orbits');for(const radius of S.focus?[250,350,470,580,640]:[260,640]){const c=make('circle');c.setAttribute('cx',950);c.setAttribute('cy',850);c.setAttribute('r',radius);orbits.append(c);}svg.append(orbits);
    let particles=0;const noMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
    function link(from,to,state,aggregate=false){
      const d=pathFor(from,to,aggregate);if(!d)return;
      const p=make('path');p.dataset.from=from;p.dataset.to=to;p.dataset.aggregate=String(aggregate);p.setAttribute('d',d);p.setAttribute('class','path-'+(aggregate?'overview':state));p.setAttribute('vector-effect','non-scaling-stroke');p.setAttribute('marker-end','url(#star-arrow)');svg.append(p);
      if(state==='completed'&&!aggregate&&!noMotion&&particles<6){const dot=make('circle');dot.setAttribute('r',2/S.zoom);dot.setAttribute('class','star-energy');const motion=make('animateMotion');motion.setAttribute('path',d);motion.setAttribute('dur',(3+particles*.3)+'s');motion.setAttribute('repeatCount','3');dot.append(motion);svg.append(dot);particles++;}
    }
    if(!S.focus){
      const foundation=g.nodes.filter(n=>S.layout.visible.has(n.id)&&S.zoom>=.32);
      foundation.forEach(n=>link('student',n.id,n.status==='completed'?'completed':'locked',true));
      for(const c of g.careers){const ids=StarGraph.required(g,c),sources=foundation.filter(n=>ids.has(n.id));(sources.length?sources.map(n=>n.id):['student']).forEach(id=>link(id,c.id,c.coverage===100?'completed':'locked',true));}
    }else{
      g.nodes.filter(n=>S.layout.visible.has(n.id)).forEach(n=>{const state=n.status==='completed'?'completed':n.status==='available'?'ready':'locked';if(!n.prerequisites.length)link('student',n.id,state);n.prerequisites.forEach(id=>link(id,n.id,state));});
      const c=g.careers.find(c=>c.id===S.focus),parents=new Set(g.nodes.filter(n=>S.layout.visible.has(n.id)).flatMap(n=>n.prerequisites));[...S.layout.visible].filter(id=>!parents.has(id)).forEach(id=>link(id,c.id,c.coverage===100?'completed':'locked'));
    }
    highlight();
  }
  function highlight(){
    document.querySelectorAll('#tree-scene .star-node').forEach(b=>{b.classList.toggle('selected',b.dataset.skillId===S.selected);b.setAttribute('aria-pressed',String(b.dataset.skillId===S.selected));});
    document.querySelectorAll('#tree-scene path[data-from]').forEach(p=>p.classList.toggle('emphasized',Boolean(S.selected)&&(p.dataset.from===S.selected||p.dataset.to===S.selected)));
  }
  function select(id){
    if(!S.graph)return;const career=S.graph.careers.find(c=>c.id===id);
    if(career&&S.focus!==id){S.focus=id;S.selected=id;draw(true);[...get('tree-scene').querySelectorAll('[data-skill-id]')].find(b=>b.dataset.skillId===id)?.focus({preventScroll:true});return;}
    if(id==='student'){overview();return;}
    const panelFocus=get('star-detail-body').contains(document.activeElement);S.selected=id;highlight();renderDetail();if(panelFocus){get('star-detail-body').tabIndex=-1;get('star-detail-body').focus({preventScroll:true});}
  }
  function clear(){S.selected=null;highlight();renderDetail();}
  function overview(){S.focus=null;S.selected=null;draw(true);}
  function addHeading(root,label,values){root.append(el('h3','',label));const ul=el('ul');values.forEach(value=>ul.append(el('li','',value)));root.append(ul);}
  function skillButtons(root,ids,g){const list=el('div','star-skill-list');ids.forEach(id=>{const n=g.nodes.find(n=>n.id===id);if(!n)return;const b=el('button','',`${n.status==='completed'?'✓':n.status==='available'?'✧':'○'} ${n.name}`);b.type='button';b.addEventListener('click',()=>select(id));list.append(b);});root.append(list);}
  function renderDetail(){
    const root=get('star-detail-body');if(!root)return;root.replaceChildren();const g=view();
    if(!g){setText('star-panel-label','成长导航');root.append(el('div','star-detail-symbol','✦'),el('h2','','连接你的可能性'),el('p','','正式星图根据目标岗位、JD 和能力差距由 AI 动态生成。每一项共享技能，都会影响它连接的职业方向。'));addHeading(root,'成长方式',['先明确目标与基础','学习并完成实战任务','通过考核，点亮后续技能']);return;}
    const n=g.nodes.find(n=>n.id===S.selected),c=g.careers.find(c=>c.id===S.selected);
    if(n){
      setText('star-panel-label','技能档案');root.append(el('div','star-detail-symbol',n.status==='completed'?'✓':'✧'),el('h2','',n.name));const chips=el('div','star-chip-row');chips.append(el('span','star-chip '+n.status,{locked:'未解锁',available:'可学习',completed:'已完成'}[n.status]),el('span','star-chip',n.stage));if(n.shared_count>1)chips.append(el('span','star-chip','共享 '+n.shared_count+' 个方向'));root.append(chips,el('p','',n.description));
      root.append(el('h3','','前置要求'));if(n.prerequisites.length)skillButtons(root,n.prerequisites,g);else root.append(el('p','','无前置技能，可从这里开始。'));
      addHeading(root,'学习资源',n.resources||['课程资料：待补充']);root.append(el('h3','','实战任务'),el('p','',n.task));
      root.append(el('h3','','节点考核'),el('p','',S.mode==='demo'?'演示通过只改变当前示例进度，不生成真实考核成绩。':'至少 3 道不同题目，正确率达到 80% 且前置已完成，才点亮此技能。AI 题目仍需结合课程核对。'));
      let consent;
      if(S.mode==='live'){const label=el('label','check-line'),input=el('input');input.type='checkbox';input.id='star-node-consent';consent=input;label.append(input,document.createTextNode('同意发送此技能内容生成 AI 考核。'));root.append(label);}
      const action=button(S.mode==='demo'?(n.status==='completed'?'已在演示中点亮':'演示通过考核'):(n.status==='completed'?'再做一次巩固练习':'开始节点考核'),async()=>{if(S.mode==='demo'){completeDemo(n.id);return;}if(!consent.checked)throw Error('请先同意生成本次考核。');await startExam(n.id);},'primary');action.disabled=n.status==='locked'||(S.mode==='demo'&&n.status==='completed');root.append(action);
      root.append(el('p','star-subtle',n.status==='locked'?'完成前置技能后，本节点自动变为可学习。':'技能完成状态用于学习规划，不代表能力认证。'));
    }else if(c){
      setText('star-panel-label','目标职业');const symbol=el('div','star-detail-symbol',theme(c.id).glyph);symbol.style.color=theme(c.id).color;root.append(symbol,el('h2','',c.name),el('p','',c.description));
      const rate=el('div','star-coverage-number');rate.append(el('strong','',c.coverage+'%'),el('span','','技能覆盖率'));root.append(rate);const track=el('div','star-progress-track'),fill=el('i');fill.style.transform='scaleX('+c.coverage/100+')';track.append(fill);root.append(track,el('p','star-subtle',`${c.completed_count} / ${c.required_count} 项必备技能已完成 · 非招聘录用概率`));
      root.append(el('h3','','已掌握技能'));if(c.mastered.length)skillButtons(root,c.mastered,g);else root.append(el('p','','尚无考核完成记录。'));
      root.append(el('h3','','缺失技能'));if(c.missing.length)skillButtons(root,c.missing,g);else root.append(el('p','','此路径必备技能已全部完成。'));
      const next=c.missing.map(id=>g.nodes.find(n=>n.id===id)).filter(n=>n.status==='available');addHeading(root,'推荐下一步',next.length?next.slice(0,3).map(n=>'学习并考核：'+n.name):c.missing.length?['先完成上述前置技能。']:['整理项目成果，补充简历中的能力证据。']);addHeading(root,'建议项目',c.projects);root.append(el('p','star-subtle','覆盖率 = 已完成必备技能数 / 必备技能总数。包含前置技能；不衡量真实招聘结果。'));
    }else{
      setText('star-panel-label','职业导航');root.append(el('div','star-detail-symbol','✦'),el('h2','',S.focus?'继续连接你的技能':'每一条路径，都有交点'),el('p','',S.focus?'点击技能查看学习内容、前置要求与实战任务。':'从中央学生起点出发。基础能力被多个职业复用，点击职业展开依赖路径。'));
      root.append(el('h3','',g.careers.length+' 个职业方向'));const list=el('div','star-career-list');g.careers.forEach(c=>{const b=el('button','star-career-item');b.type='button';b.style.setProperty('--career-color',theme(c.id).color);const text=el('div');text.append(el('strong','',c.name),el('small','',`${c.completed_count} / ${c.required_count} 必备技能`));b.append(el('span','',theme(c.id).glyph),text,el('em','',c.coverage+'%'));b.setAttribute('aria-label',c.name+'，技能覆盖率'+c.coverage+'%');b.addEventListener('click',()=>select(c.id));list.append(b);});root.append(list,el('p','star-subtle','百分比为技能覆盖率，不代表录用概率。'));
    }
  }
  function unlockedBefore(){return new Set(view()?.careers.filter(c=>c.coverage===100).map(c=>c.id)||[]);}
  function celebrate(before){const now=view()?.careers.filter(c=>c.coverage===100&&!before.has(c.id))||[];if(!now.length)return;S.pendingAchievements.push(...now.map(c=>c.name));if(state.view==='tree')showAchievement();}
  function showAchievement(){if(!S.pendingAchievements.length)return;const box=get('star-achievement');box.replaceChildren(el('strong','','✧ 职业路径解锁'),el('p','',S.pendingAchievements.join(' · ')),el('p','','必备技能已完成。此成就不代表职业认证或录用。'));S.pendingAchievements=[];box.hidden=false;clearTimeout(S.achievementTimer);S.achievementTimer=setTimeout(()=>box.hidden=true,5200);}
  function sample(){if(S.mode!=='demo')return;const before=unlockedBefore();S.progress=['cs','code','git','net','db','http','dir_frontend','skill_frontend'];S.selected='career_frontend';S.focus='career_frontend';draw(true);celebrate(before);toast('已加载演示进度，完成前端项目即可展示职业解锁。');}
  function completeDemo(id){if(S.mode!=='demo')return;const n=view().nodes.find(n=>n.id===id);if(!n||n.status!=='available')return;const before=unlockedBefore();S.progress=[...new Set([...S.progress,id])];draw();celebrate(before);}
  async function startExam(id){
    if(S.mode!=='live'||!platform.tree)return;const n=view().nodes.find(n=>n.id===id);if(!n||n.status==='locked')throw Error('请先完成前置技能。');
    const tid=platform.tree.id;toast('AI 正在生成节点考核…');const exam=await api('/learning/exams',{method:'POST',data:{tree_id:tid,node_ids:[id],unlock:n.status!=='completed',consent:true}});
    if(S.mode==='live'&&platform.tree?.id===tid){renderExam(exam);show('exam');}
  }
  async function applyExam(result){
    if(!result.tree_id||platform.tree?.id!==result.tree_id)return;const before=unlockedBefore(),focus=S.focus,selected=S.selected;
    const data=await api('/learning/trees');const value=data.items.find(t=>t.id===result.tree_id);if(!value)return;
    platform.tree=value;if(S.mode==='live'){S.graph=value.tree;S.progress=value.progress;S.focus=focus;S.selected=selected;draw();celebrate(before);}
  }
  function setZoom(next,anchor=null){
    if(!S.graph||S.drag)return;
    const vp=get('tree-scroll'),scene=get('tree-scene'),rect=vp.getBoundingClientRect(),old=S.zoom;
    const sx=anchor?anchor.clientX-rect.left-vp.clientLeft:vp.clientWidth/2,sy=anchor?anchor.clientY-rect.top-vp.clientTop:vp.clientHeight/2;
    const wx=(vp.scrollLeft+sx-scene.offsetLeft)/old,wy=(vp.scrollTop+sy-scene.offsetTop)/old;
    S.zoom=Math.max(.2,Math.min(1.8,next));
    if(!S.focus&&((old<.32)!==(S.zoom<.32)))draw();else applyZoom();
    vp.scrollLeft=scene.offsetLeft+wx*S.zoom-sx;vp.scrollTop=scene.offsetTop+wy*S.zoom-sy;
    clearTimeout(S.settleTimer);S.settleTimer=setTimeout(()=>{
      if(!S.graph||S.drag)return;
      S.layout=StarGraph.separate(S.layout,S.zoom,S.positions.get(layoutKey())||new Map(),displayedIds());applyZoom();
    },150);
  }
  function zoom(delta){setZoom(S.zoom+delta);}
  function wheelZoom(event){
    if(!S.graph||S.drag)return;S.wheelDelta+=Math.max(-500,Math.min(500,event.deltaY));S.wheelAnchor=event;
    if(S.wheelFrame)return;
    S.wheelFrame=requestAnimationFrame(()=>{S.wheelFrame=0;const delta=S.wheelDelta;S.wheelDelta=0;setZoom(S.zoom*Math.exp(-delta*.0014),S.wheelAnchor);});
  }
  function updateDraggedNode(){
    if(!S.drag)return;const d=S.drag,p=S.layout.points.get(d.id);
    p.x=Math.max(85/S.zoom,Math.min(S.layout.width-90/S.zoom,d.x+d.dx/S.zoom));
    p.y=Math.max(45/S.zoom,Math.min(S.layout.height-100/S.zoom,d.y+d.dy/S.zoom));
    const b=[...get('tree-scene').querySelectorAll('[data-skill-id]')].find(b=>b.dataset.skillId===d.id);
    if(b){b.style.left=(p.x-56)+'px';b.style.top=(p.y-Number(b.dataset.layoutHeight)/2+Number(b.dataset.anchor)/S.zoom)+'px';}
    get('tree-scene').querySelectorAll('path[data-from]').forEach(path=>{if(path.dataset.from===d.id||path.dataset.to===d.id)path.setAttribute('d',pathFor(path.dataset.from,path.dataset.to,path.dataset.aggregate==='true'));});
  }
  function dragNode(id,dx,dy){
    if(!S.graph||!S.layout.points.has(id))return;
    if(!S.drag){const p=S.layout.points.get(id);S.drag={id,x:p.x,y:p.y,dx:0,dy:0};get('tree-scene').querySelectorAll('.star-energy').forEach(dot=>dot.remove());clearTimeout(S.settleTimer);}
    S.drag.dx=dx;S.drag.dy=dy;
    if(!S.dragFrame)S.dragFrame=requestAnimationFrame(()=>{S.dragFrame=0;updateDraggedNode();});
  }
  function endNodeDrag(id,cancelled=false){
    if(!S.drag||S.drag.id!==id)return;cancelAnimationFrame(S.dragFrame);S.dragFrame=0;updateDraggedNode();const d=S.drag;S.drag=null;
    if(cancelled){Object.assign(S.layout.points.get(id),{x:d.x,y:d.y});}
    else{
      const others=[...S.layout.points].filter(([other])=>other!==id&&displayedIds().has(other)).map(([,p])=>p);
      const p=StarGraph.freePosition(S.layout.points.get(id),others,S.zoom);S.layout.points.set(id,p);
      S.layout.width=Math.max(S.layout.width,p.x+90/S.zoom);S.layout.height=Math.max(S.layout.height,p.y+100/S.zoom);
      const saved=S.positions.get(layoutKey())||new Map();saved.set(id,{x:p.x,y:p.y});S.positions.set(layoutKey(),saved);
    }
    applyZoom();
  }
  function arrange(){if(!S.graph)return;S.positions.delete(layoutKey());draw(true);}
  function reset(){if(S.mode!=='demo')return;[...S.positions.keys()].filter(k=>k.startsWith('demo:')).forEach(k=>S.positions.delete(k));S.progress=[];S.focus=null;S.selected=null;S.pendingAchievements=[];get('star-achievement').hidden=true;draw(true);toast('演示已重置，个人学习记录未修改。');}
  function init(){
    if(S.initialized)return;S.initialized=true;modeUI();drawEmpty();
    document.querySelector('#view-tree').addEventListener('pointerdown',()=>document.body.classList.remove('star-keyboard'));
    document.querySelector('#view-tree').addEventListener('keydown',()=>document.body.classList.add('star-keyboard'));
    document.querySelector('#view-tree').addEventListener('click',event=>{const b=event.target.closest('[data-star]');if(!b)return;const actions={live:()=>switchMode('live'),demo:()=>switchMode('demo'),overview,clear,sample,reset,arrange,center:()=>draw(true),'zoom-in':()=>zoom(.1),'zoom-out':()=>zoom(-.1)};actions[b.dataset.star]?.();});
    get('tree-scroll').addEventListener('keydown',event=>{
      if(event.key==='Home'){event.preventDefault();draw(true);get('tree-scroll').focus({preventScroll:true});return;}if(event.key==='+'||event.key==='='){event.preventDefault();zoom(.1);return;}if(event.key==='-'){event.preventDefault();zoom(-.1);return;}
      const current=event.target.closest('[data-skill-id]');if(current&&event.altKey&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const dx=event.key==='ArrowLeft'?-32:event.key==='ArrowRight'?32:0,dy=event.key==='ArrowUp'?-32:event.key==='ArrowDown'?32:0;dragNode(current.dataset.skillId,dx,dy);endNodeDrag(current.dataset.skillId);return;}if(!current||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)||!S.layout)return;
      const pos=S.layout.points.get(current.dataset.skillId);const candidates=[...get('tree-scene').querySelectorAll('[data-skill-id]')].filter(b=>b!==current).map(b=>({b,p:S.layout.points.get(b.dataset.skillId)})).filter(({p})=>event.key==='ArrowLeft'?p.x<pos.x-1:event.key==='ArrowRight'?p.x>pos.x+1:event.key==='ArrowUp'?p.y<pos.y-1:p.y>pos.y+1).sort((a,b)=>Math.hypot(a.p.x-pos.x,a.p.y-pos.y)-Math.hypot(b.p.x-pos.x,b.p.y-pos.y));
      if(candidates.length){event.preventDefault();candidates[0].b.focus();}
    });
    let resizeFrame=0;window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(state.view==='tree'&&S.graph)draw(true);});});
    window.addEventListener('viewchange',event=>{document.body.classList.toggle('star-theme',event.detail==='tree');if(event.detail==='tree')showAchievement();else get('star-achievement').hidden=true;});
  }
  function clearAll(){platform.canvas?.cancel();cancelAnimationFrame(S.wheelFrame);cancelAnimationFrame(S.dragFrame);clearTimeout(S.settleTimer);S.wheelFrame=0;S.dragFrame=0;S.drag=null;S.positions.clear();S.graph=null;S.progress=[];S.focus=null;S.selected=null;S.mode='live';S.pendingAchievements=[];if(S.initialized){modeUI();drawEmpty();}}
  return {init,load,select,clear,overview,draw,renderDetail,applyExam,clearAll,dragNode,endNodeDrag,wheelZoom,get mode(){return S.mode;}};
})();
