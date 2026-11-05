'use strict';
// 独立装饰层：不读取表单值、不保存材料、不请求外部资源。
(() => {
  const C=window.CareerFXCore;
  if(!C||window.CareerEffects)return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),fine=matchMedia('(hover: hover) and (pointer: fine)');
  const body=document.body,root=document.documentElement;
  const layer=document.createElement('div');layer.className='fx-cosmos';layer.setAttribute('aria-hidden','true');
  ['blue','violet','cyan'].forEach(color=>{const n=document.createElement('i');n.className='fx-aurora '+color;layer.append(n);});
  const canvas=document.createElement('canvas');canvas.className='fx-canvas';layer.append(canvas);body.prepend(layer);
  const ctx=canvas.getContext('2d',{alpha:true});
  let mode='full',width=1,height=1,config,points=[],meteors=[],bursts=[],loop,nextShower=0,resizeFrame=0,alive=true;
  const pointer={x:-1000,y:-1000};
  const cards=new Set(),cardSelectors='.overview-hero,.overview-continue,.overview-feature,.cinema-feature,.cinema-growth,.panel,.metric,.week-card,.entry-card,.auth-story,.demo-panel,.star-panel,.star-map-shell,.star-hud,.star-config';
  const atlas='/static/assets/glass-icons.png',names=['shield','grid','file','alert','lock','tree','route','list','arrow','upload','check','trash','spark','download','user','mic'];
  const centerX=[190,480,772,1065],centerY=[180,473,767,1057];
  const svgNS='http://www.w3.org/2000/svg';
  // 用亮度生成alpha，使黑底图集成为透明玻璃图标，避免方形底块。
  const defsRoot=document.createElementNS(svgNS,'svg');defsRoot.classList.add('fx-icon-defs');defsRoot.setAttribute('aria-hidden','true');
  const defs=document.createElementNS(svgNS,'defs'),filter=document.createElementNS(svgNS,'filter'),matrix=document.createElementNS(svgNS,'feColorMatrix');
  filter.id='fx-icon-alpha';filter.setAttribute('filterUnits','userSpaceOnUse');filter.setAttribute('x','0');filter.setAttribute('y','0');filter.setAttribute('width','280');filter.setAttribute('height','280');filter.setAttribute('color-interpolation-filters','sRGB');matrix.setAttribute('type','matrix');matrix.setAttribute('values','1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  1 1 1 0 -0.03');filter.append(matrix);defs.append(filter);defsRoot.append(defs);body.prepend(defsRoot);
  function paintIcon(svg,name){
    if(svg.dataset.fxIcon||!names.includes(name))return;
    const index=names.indexOf(name),img=document.createElementNS(svgNS,'image');
    img.setAttribute('href',atlas);img.setAttribute('x',String(140-centerX[index%4]));img.setAttribute('y',String(140-centerY[Math.floor(index/4)]));img.setAttribute('width','1254');img.setAttribute('height','1254');
    img.setAttribute('filter','url(#fx-icon-alpha)');svg.replaceChildren(img);svg.setAttribute('viewBox','0 0 280 280');svg.setAttribute('aria-hidden','true');svg.dataset.fxIcon=name;svg.classList.add('fx-glass-icon');
  }
  function newIcon(name){const svg=document.createElementNS(svgNS,'svg');paintIcon(svg,name);return svg;}
  function upgradeIcons(scope){
    const svgs=[...(scope.matches?.('svg')?[scope]:[]),...scope.querySelectorAll('svg')];
    svgs.forEach(svg=>{
      if(svg.closest('.sprite,.fx-icon-defs,#tree-scene')||svg.dataset.fxIcon)return;
      const href=svg.querySelector('use')?.getAttribute('href');
      let name=href?.replace('#i-','');
      if(!name&&svg.closest('.site-mark,.brand-mark'))name='shield';
      if(names.includes(name))paintIcon(svg,name);
    });
    scope.querySelectorAll('.site-brand>img[src="/static/mark.svg"]').forEach(img=>img.replaceWith(newIcon('shield')));
    const glyphSelector='.star-orb,.star-detail-symbol,.star-career-item>span:first-child,.model-logo,.camera-tool-icon,.camera-placeholder>span,.voice-orb,.avatar,.top-avatar,.icon-button:not([data-action=close-dialog])';
    [...(scope.matches?.(glyphSelector)?[scope]:[]),...scope.querySelectorAll(glyphSelector)].forEach(el=>{
      if(el.dataset.fxIcon)return;
      let name='spark';
      const glyphName={'⌘':'grid','⬡':'tree','▥':'list','✦':'spark','◇':'shield','☁':'upload','✓':'check','▯':'file','⌁':'route'}[el.textContent.trim()];
      const node=el.closest('.star-node');
      if(node)name=node.classList.contains('student')?'shield':node.classList.contains('group')?'tree':node.classList.contains('completed')?'check':node.classList.contains('career')?(glyphName||'route'):'file';
      else if(el.classList.contains('model-logo'))name=el.classList.contains('llm-logo')?'spark':'file';
      else if(el.matches('.camera-tool-icon,.camera-placeholder>span,.avatar,.top-avatar'))name='user';
      else if(el.classList.contains('voice-orb'))name='mic';
      else if(glyphName)name=glyphName;
      el.replaceChildren(newIcon(name));el.dataset.fxIcon=name;
    });
  }
  const visibleObserver='IntersectionObserver'in window?new IntersectionObserver(entries=>entries.forEach(e=>e.target.classList.toggle('fx-visible',e.isIntersecting)),{rootMargin:'80px'}):null;
  function decorate(scope){
    upgradeIcons(scope);
    const matches=[...(scope.matches?.(cardSelectors)?[scope]:[]),...scope.querySelectorAll(cardSelectors)];
    matches.forEach(card=>{
      if(card.dataset.fxCard)return;
      card.dataset.fxCard='true';card.classList.add('fx-card');cards.add(card);
      const edge=document.createElement('span');edge.className='fx-edge';edge.setAttribute('aria-hidden','true');card.append(edge);
      const spot=document.createElement('span');spot.className='fx-spot';spot.setAttribute('aria-hidden','true');
      const light=document.createElement('span');light.className='fx-spot-light';spot.append(light);card.append(spot);
      if(visibleObserver)visibleObserver.observe(card);else card.classList.add('fx-visible');
      let frame=0,lastPoint;
      const canTilt=card.matches('.overview-feature,.cinema-feature,.metric,.entry-card');
      card.addEventListener('pointermove',event=>{
        if(mode==='off'||reduced.matches||!fine.matches||event.pointerType!=='mouse'||document.hidden)return;
        lastPoint={x:event.clientX,y:event.clientY};if(frame)return;
        frame=requestAnimationFrame(()=>{
          frame=0;if(!lastPoint||reduced.matches||document.hidden||mode==='off')return;
          const rect=card.getBoundingClientRect(),x=lastPoint.x-rect.left,y=lastPoint.y-rect.top;
          light.style.transform=`translate3d(${x-140}px,${y-140}px,0)`;
          if(canTilt&&mode==='full'&&!body.classList.contains('motion-keyboard')){
            const rx=Math.max(-3,Math.min(3,(.5-y/rect.height)*6)),ry=Math.max(-3,Math.min(3,(x/rect.width-.5)*6));
            card.style.transform=`perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-2px)`;
          }
        });
      });
      const reset=()=>{cancelAnimationFrame(frame);frame=0;lastPoint=null;card.style.transform='';light.style.transform='';};
      card.addEventListener('pointerleave',reset);card.addEventListener('focusout',reset);card.fxReset=reset;
    });
  }
  function syncPause(){
    body.classList.toggle('fx-paused',!alive||document.hidden||reduced.matches||mode==='off');
    loop?.setActive(alive&&!document.hidden&&config.fps>0);
    if(document.hidden||reduced.matches||mode==='off')cards.forEach(card=>card.fxReset?.());
  }
  function render(dt,stamp){
    if(!ctx)return;
    ctx.clearRect(0,0,width,height);
    if(mode==='off')return;
    const time=stamp/1000;
    C.stepField(points,dt,width,height);
    ctx.lineWidth=.65;
    const distance=mode==='lite'?95:150;
    C.nearLinks(points,distance,config.links).forEach(([a,b,d])=>{
      const p=points[a],q=points[b];ctx.beginPath();ctx.strokeStyle=`rgba(107,160,246,${(1-d)*.24})`;ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();
    });
    points.forEach(p=>{
      const alpha=.32+(Math.sin(time*1.2+p.phase)+1)*.25;
      ctx.beginPath();ctx.fillStyle=`hsla(${p.hue},90%,82%,${alpha})`;ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();
      const dx=pointer.x-p.x,dy=pointer.y-p.y,d=Math.hypot(dx,dy);
      if(mode==='full'&&d<145){ctx.beginPath();ctx.strokeStyle=`rgba(144,212,255,${(1-d/145)*.4})`;ctx.moveTo(p.x,p.y);ctx.lineTo(pointer.x,pointer.y);ctx.stroke();}
    });
    if(config.meteors&&stamp>=nextShower){
      const count=Math.min(mode==='full'?3:1,config.meteors-meteors.length);
      for(let i=0;i<count;i++)meteors.push(C.makeMeteor(width,height));
      nextShower=stamp+(mode==='full'?850:2300);
    }
    meteors=C.advanceMeteors(meteors,dt,width,height);
    meteors.forEach(m=>{
      const fade=Math.max(0,Math.min(1,m.age*4,(m.life-m.age)*3));
      const tailX=m.x+m.length*.85,tailY=m.y-m.length*.53,g=ctx.createLinearGradient(m.x,m.y,tailX,tailY);
      g.addColorStop(0,`rgba(230,246,255,${fade})`);g.addColorStop(.15,`hsla(${m.hue},95%,75%,${fade*.8})`);g.addColorStop(1,`hsla(${m.hue},95%,70%,0)`);
      ctx.beginPath();ctx.strokeStyle=g;ctx.lineWidth=1.8;ctx.moveTo(m.x,m.y);ctx.lineTo(tailX,tailY);ctx.stroke();
      ctx.beginPath();ctx.fillStyle=`rgba(232,248,255,${fade})`;ctx.arc(m.x,m.y,1.7,0,Math.PI*2);ctx.fill();
    });
    bursts=bursts.filter(b=>{
      b.age+=dt;if(b.age>.65)return false;
      const t=b.age;ctx.beginPath();ctx.fillStyle=`rgba(162,216,255,${1-t/.65})`;ctx.arc(b.x+b.vx*t,b.y+b.vy*t+50*t*t,1.3,0,Math.PI*2);ctx.fill();return true;
    });
  }
  function configure(){
    cards.forEach(card=>card.fxReset?.());
    document.querySelectorAll('[data-tilt]').forEach(el=>{el.style.transform='';});
    loop?.dispose();width=Math.max(1,innerWidth);height=Math.max(1,innerHeight);config=C.budget(width,mode,reduced.matches);
    const scale=Math.min(devicePixelRatio||1,config.dpr,Math.sqrt(2000000/(width*height)));
    canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);ctx?.setTransform(scale,0,0,scale,0,0);
    points=C.createField(width,height,config.particles);meteors=[];bursts=[];nextShower=0;
    if(config.meteors){const seed=C.makeMeteor(width,height);seed.x=width*.76;seed.y=height*.15;seed.age=.25;meteors.push(seed);}
    body.dataset.fxMode=mode;layer.hidden=mode==='off';
    if(ctx){render(0,performance.now());loop=C.createLoop({request:requestAnimationFrame,cancel:cancelAnimationFrame,draw:render,interval:config.fps?1000/config.fps:1000});}
    syncPause();
  }
  const label=document.createElement('label');label.className='fx-toolbar';label.append(document.createTextNode('特效 '));
  const select=document.createElement('select');select.id='visual-effects-mode';select.setAttribute('aria-label','视觉特效强度');
  [['full','全开'],['lite','轻量'],['off','关闭']].forEach(([value,title])=>{const o=document.createElement('option');o.value=value;o.textContent=title;select.append(o);});
  label.append(select);(document.querySelector('.top-actions,.site-nav,.admin-top')||body).append(label);
  select.addEventListener('change',()=>{mode=select.value;configure();});
  const onMove=e=>{if(e.pointerType==='mouse'){pointer.x=e.clientX;pointer.y=e.clientY;}};
  const onClick=e=>{
    if(mode==='off'||reduced.matches||document.hidden||e.target.closest('input,textarea,select,.fx-toolbar'))return;
    const button=e.target.closest('.button,.pill,.nav-item,.overview-feature');
    if(button&&!button.disabled){
      button.classList.add('fx-press');const r=button.getBoundingClientRect(),ripple=document.createElement('span');ripple.className='fx-ripple';ripple.setAttribute('aria-hidden','true');ripple.style.left=`${e.clientX-r.left}px`;ripple.style.top=`${e.clientY-r.top}px`;button.append(ripple);
      ripple.addEventListener('animationend',()=>ripple.remove(),{once:true});setTimeout(()=>ripple.remove(),900);
    }
    if(mode==='full'&&bursts.length<60)for(let i=0;i<10;i++){const a=Math.random()*Math.PI*2,s=25+Math.random()*70;bursts.push({x:e.clientX,y:e.clientY,vx:Math.cos(a)*s,vy:Math.sin(a)*s,age:0});}
  };
  const onResize=()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(configure);};
  document.addEventListener('pointermove',onMove,{passive:true});document.addEventListener('pointerdown',onClick,{passive:true});
  document.addEventListener('pointerleave',()=>{pointer.x=pointer.y=-1000;});
  document.addEventListener('keydown',()=>cards.forEach(card=>card.fxReset?.()),{passive:true});
  window.addEventListener('viewchange',()=>{pointer.x=pointer.y=-1000;bursts=[];cards.forEach(card=>card.fxReset?.());});
  document.addEventListener('visibilitychange',syncPause);window.addEventListener('resize',onResize,{passive:true});reduced.addEventListener('change',configure);
  const mutation=new MutationObserver(records=>{
    for(const record of records)for(const item of record.addedNodes)if(item.nodeType===1&&!item.closest?.('.fx-cosmos'))decorate(item);
    for(const card of cards)if(!card.isConnected){visibleObserver?.unobserve(card);card.fxReset?.();cards.delete(card);}
  });
  decorate(document);mutation.observe(body,{childList:true,subtree:true});configure();
  // pagehide暂停但不销毁，保证浏览器后退缓存恢复后仍可继续。
  window.addEventListener('pagehide',()=>{alive=false;loop?.setActive(false);body.classList.add('fx-paused');cards.forEach(card=>card.fxReset?.());});
  window.addEventListener('pageshow',()=>{alive=true;syncPause();});
  window.CareerEffects={setMode(next){if(['full','lite','off'].includes(next)){mode=next;select.value=next;configure();}},get mode(){return mode;}};
})();
