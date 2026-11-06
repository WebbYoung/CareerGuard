(function(){
  'use strict';
  const labels={identity:'姓名与联系方式',goal:'求职意向',summary:'个人简介',education:'教育背景',experience:'工作 / 实习经历',projects:'项目经历',skills:'专业技能',achievements:'成果与证书'};
  function init(container){
    const root=container.matches?.('#view-resume')?container:container.querySelector('#view-resume');
    if(!root||root.dataset.initialized)return;root.dataset.initialized='true';
    const el=key=>root.querySelector('[data-rs="'+key+'"]');let active=null,busy=false,photoURL=null,dirty=false,epoch=0;
    const make=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
    function status(text){el('status').textContent=text;}
    async function request(path,options){const started=epoch;const result=await api(path,options);if(started!==epoch)throw new DOMException('个人资料已清空，旧结果已丢弃','AbortError');return result;}
    function lockControls(locked){root.querySelectorAll('button,select,input,textarea').forEach(control=>control.disabled=locked);}
    async function run(fn){if(busy)return;const started=epoch;busy=true;root.setAttribute('aria-busy','true');lockControls(true);try{await fn();}catch(error){if(started===epoch&&error.name!=='AbortError')status(error.message||'操作失败，请重试。');}finally{if(started===epoch){busy=false;root.removeAttribute('aria-busy');lockControls(false);}}}
    function clearAccountData(){
      epoch++;active=null;dirty=false;busy=false;
      if(photoURL){URL.revokeObjectURL(photoURL);photoURL=null;}
      el('photo').hidden=true;el('photo').removeAttribute('src');
      el('workspace').hidden=true;el('proposal').hidden=true;
      ['messages','fields','missing','proposal-fields','proposal-citations','proposal-warning'].forEach(key=>el(key).replaceChildren());
      root.querySelectorAll('form').forEach(form=>form.reset());
      el('message').value='';el('photo-file').value='';
      root.querySelectorAll('input[type=checkbox]').forEach(input=>input.checked=false);
      el('sessions').replaceChildren(new Option('选择一份简历',''));
      lockControls(false);
      root.removeAttribute('aria-busy');
      status('个人资料已清空。可以新建一份简历重新开始。');
    }
    async function list(){const data=await request('/resume/sessions');el('sessions').replaceChildren(new Option('选择一份简历',''));data.items.forEach(item=>el('sessions').append(new Option(item.title+' · '+item.updated,item.id)));if(active)el('sessions').value=active.id;}
    async function photo(){if(photoURL){URL.revokeObjectURL(photoURL);photoURL=null;}el('photo').hidden=true;el('photo').removeAttribute('src');if(!active?.has_portrait)return;const blob=await request('/resume/sessions/'+active.id+'/portrait',{download:true});photoURL=URL.createObjectURL(blob);el('photo').src=photoURL;el('photo').hidden=false;}
    function proposalPreview(value){
      const proposal=value.proposal;el('proposal').hidden=!proposal;if(!proposal)return;
      el('proposal-fields').replaceChildren();Object.entries(labels).forEach(([key,label])=>{
        if(!proposal.source_facts[key]&&!proposal.draft[key])return;
        const section=make('section',null,'rs-proposal-field');section.append(make('h4',label));
        const compare=make('div',null,'rs-compare'),before=make('div'),after=make('div');
        before.append(make('strong','原始事实'),make('p',proposal.source_facts[key]||'尚未提供'));
        after.append(make('strong','AI 建议表达'),make('p',proposal.draft[key]||'待补充'));compare.append(before,after);section.append(compare);
        if(proposal.evidence[key]?.length){const evidence=make('details');evidence.append(make('summary','查看事实依据'));proposal.evidence[key].forEach(q=>evidence.append(make('p',q)));section.append(evidence);}
        el('proposal-fields').append(section);
      });
      const flags=(proposal.unsupported_facts||[]).map(item=>item.label+'：'+item.reason);
      el('proposal-warning').textContent=[proposal.notice,...flags,...(proposal.followups||[]).map(x=>'待补充：'+x)].join('\n');
      el('proposal-citations').replaceChildren(make('h4','知识库参考 · '+(proposal.retrieval_mode==='vector'?'向量检索':'关键词降级检索')));
      if(!proposal.citations.length)el('proposal-citations').append(make('p','未检索到匹配资料；本次依据你提供的事实整理。'));
      proposal.citations.forEach(item=>{const d=make('details');d.append(make('summary',item.title||'知识库资料'),make('p',item.text||''));el('proposal-citations').append(d);});
    }
    function render(value){active=value;dirty=false;el('workspace').hidden=false;el('messages').replaceChildren();value.messages.forEach(m=>{const card=make('div',null,'rs-message '+m.role);card.append(make('strong',m.role==='user'?'你':'简历顾问'),make('div',m.content));el('messages').append(card);});el('messages').scrollTop=el('messages').scrollHeight;el('fields').replaceChildren();Object.entries(labels).forEach(([key,label])=>{const field=make('label',label),area=make('textarea');area.name=key;area.value=value.draft[key]||'';area.rows=['projects','experience'].includes(key)?5:3;area.maxLength={identity:1000,goal:1000,summary:2000,education:3000,experience:6000,projects:6000,skills:3000,achievements:3000}[key];area.addEventListener('input',()=>dirty=true);field.append(area);el('fields').append(field);});el('missing').textContent=value.missing_facts.length?'待确认：'+value.missing_facts.map(x=>x.label).join('、'):'核心资料已收集，请核对真实性与完整性。';status(value.notice);proposalPreview(value);if(busy)lockControls(true);}
    async function saveDraft(){const draft={};el('fields').querySelectorAll('textarea').forEach(n=>draft[n.name]=n.value);render(await request('/resume/sessions/'+active.id+'/draft',{method:'PUT',data:{draft}}));await list();}
    el('polish').addEventListener('click',()=>run(async()=>{if(!el('polish-consent').checked)throw Error('请先同意本次简历数据发送与知识库检索。');if(dirty)await saveDraft();status('AI 正在根据你的真实经历生成专属简历…');render(await request('/resume/sessions/'+active.id+'/polish',{method:'POST',data:{consent:true}}));proposalPreview(active);el('polish-consent').checked=false;status('专属简历建议稿已生成，请在下方对照核实后应用。');}));
    el('apply-proposal').addEventListener('click',()=>run(async()=>{if(!active?.proposal)return;const proposal=active.proposal;const unchanged=Object.keys(labels).every(key=>(active.draft[key]||'')===(proposal.source_facts[key]||''));if(dirty||!unchanged)throw Error('当前草稿已修改，请重新生成建议稿，以免覆盖新内容。');render(await request('/resume/sessions/'+active.id+'/draft',{method:'PUT',data:{draft:proposal.draft}}));await list();status('已应用并保存 AI 草稿，原始事实仍保留在建议稿中。可以继续编辑或下载 Word。');}));
    el('new').addEventListener('click',()=>run(async()=>{if(dirty)await saveDraft();render(await request('/resume/sessions',{method:'POST',data:{title:'我的求职简历'}}));await photo();await list();}));
    el('sessions').addEventListener('change',()=>run(async()=>{const id=el('sessions').value;if(!id)return;if(dirty)await saveDraft();render(await request('/resume/sessions/'+id));await photo();}));
    el('delete').addEventListener('click',()=>run(async()=>{if(!active)throw Error('请先选择简历。');if(!confirm('删除这份简历、对话和附带证件照？'))return;await request('/resume/sessions/'+active.id,{method:'DELETE'});active=null;dirty=false;el('workspace').hidden=true;await photo();await list();status('简历已删除。');}));
    el('chat').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const message=el('message').value.trim();if(!message)return;if(dirty)await saveDraft();status('正在整理本次回答…');render(await request('/resume/sessions/'+active.id+'/message',{method:'POST',data:{message,consent:el('chat-consent').checked}}));el('message').value='';el('chat-consent').checked=false;});});
    el('draft').addEventListener('submit',event=>{event.preventDefault();run(async()=>{await saveDraft();status('草稿已保存。');});});
    el('export').addEventListener('click',()=>run(async()=>{if(dirty)await saveDraft();const blob=await request('/resume/sessions/'+active.id+'/export.docx',{download:true});const url=URL.createObjectURL(blob),link=make('a');link.href=url;link.download='我的简历.docx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);status('Word 简历已导出。');}));
    el('portrait').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const file=el('photo-file').files[0];if(!file||!el('photo-consent').checked)throw Error('请选择照片并确认本次数据发送。');if(file.size>8*1024*1024)throw Error('照片不能超过 8MB。');if(dirty)await saveDraft();const body=new FormData();body.append('file',file);body.append('size',el('photo-size').value);body.append('background',el('photo-bg').value);body.append('consent','true');status('图片模型正在处理，请稍候…');const result=await request('/resume/sessions/'+active.id+'/portrait',{method:'POST',body});active.has_portrait=true;await photo();el('photo-file').value='';el('photo-consent').checked=false;status(result.notice);});});
    window.addEventListener('viewchange',event=>{if(event.detail==='resume')run(list);});
    window.addEventListener('pagehide',()=>{if(photoURL)URL.revokeObjectURL(photoURL);});
    window.addEventListener('account-data-erased',clearAccountData);
    run(list);
  }
  window.ResumeStudio={init};
})();
