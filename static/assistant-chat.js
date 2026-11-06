/* Fixed action vocabulary: model text is never interpreted as HTML or selectors. */
(() => {
  'use strict';
  const make=(tag,cls,text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
  const dialog=make('dialog','assistant-chat');dialog.setAttribute('aria-labelledby','assistant-chat-title');
  const header=make('header'),title=make('h2','','小安 · 职业伙伴');title.id='assistant-chat-title';
  const close=make('button','icon-button','×');close.type='button';close.setAttribute('aria-label','关闭小安对话');header.append(title,close);
  const tools=make('div','button-row'),guide=make('button','button secondary','新手引导'),fresh=make('button','button secondary','清空对话');tools.append(guide,fresh);
  const log=make('div','assistant-log');log.setAttribute('role','log');log.setAttribute('aria-live','polite');
  const suggestions=make('div','assistant-suggestions');
  const form=make('form'),input=make('textarea');input.rows=2;input.maxLength=4000;input.placeholder='哪里不会，问小安…';input.setAttribute('aria-label','向小安提问');
  function checkbox(text){const l=make('label','check-line'),i=make('input');i.type='checkbox';l.append(i,document.createTextNode(text));form.append(l);return i;}
  form.append(input);const consent=checkbox('允许将本轮对话发送至已配置的AI服务'),profile=checkbox('本轮允许小安读取我的脱敏求职档案');
  const send=make('button','button primary','发送给小安');send.type='submit';form.append(send);
  const note=make('p','fine-print','建议请自行核验。小安只会提出填写建议，由你确认填入并保存。');
  dialog.append(header,tools,log,suggestions,form,note);document.body.append(dialog);
  let sid=null,busy=false,generation=0,restored=false;
  function bubble(text,role='assistant'){const e=make('div','assistant-message '+role,text);log.append(e);log.scrollTop=log.scrollHeight;return e;}
  function shutdown(){dialog.close();}
  close.onclick=shutdown;
  const views=new Set(['overview','materials','risk','privacy','career','tree','exam','interview','jobs','profile','resume']);
  function navigate(view){if(!views.has(view))return;shutdown();if(window.CareerGuide)window.CareerGuide.explain(view);else window.show(view);}
  function render(result){
    const block=bubble(result.text);block.append(make('small','',result.mode||'AI辅助'));
    for(const j of (result.jobs||[]).slice(0,8)){const card=make('div','assistant-job',j.title+' · '+j.company);const b=make('button','button secondary','查看岗位');b.type='button';b.onclick=()=>{shutdown();window.show('jobs');const s=document.querySelector('#job-search');if(s){s.value=j.title;s.dispatchEvent(new Event('input',{bubbles:true}));}};card.append(b);block.append(card);}
    for(const c of (result.citations||[]).slice(0,8))block.append(make('p','assistant-citation','依据：'+c.title+' — '+String(c.text||'').slice(0,400)));
    for(const a of (result.actions||[]).slice(0,8)){
      if(a.type==='explain_feature'&&views.has(a.view)){const b=make('button','button secondary','带我到这里');b.type='button';b.onclick=()=>navigate(a.view);block.append(b);}
      if(a.type==='fill_profile'&&a.fields&&typeof a.fields==='object'){
        const fields=Object.entries(a.fields).filter(([k,v])=>['occupation','resume'].includes(k)&&typeof v==='string'&&v.length<=(k==='occupation'?100:3000));
        block.append(make('pre','',fields.map(([k,v])=>(k==='occupation'?'目标岗位':'经历摘要')+'：'+v).join('\n')));
        const b=make('button','button secondary','确认填入个人中心');b.type='button';b.onclick=async()=>{shutdown();try{await window.CareerProfile.fill(Object.fromEntries(fields));}catch(e){window.toast(e.message,true);}};block.append(b);
      }
    }
    log.scrollTop=log.scrollHeight;
  }
  async function ask(text){
    if(busy||!text.trim())return;const epoch=generation;busy=true;send.disabled=true;input.value='';bubble(text,'user');
    try{if(!sid)sid=(await window.api('/assistant/threads',{method:'POST',data:{}})).id;const r=await window.api('/assistant/threads/'+sid+'/messages',{method:'POST',data:{message:text,consent:consent.checked,allow_profile:profile.checked}});if(epoch===generation)render(r);}
    catch(e){if(epoch===generation)bubble(e.message||'暂时无法获取回复。');}
    finally{busy=false;send.disabled=false;}
  }
  for(const q of ['如何上传招聘截图？','怎么生成AI简历？','职业规划从哪里开始？','帮我推荐合适岗位']){const b=make('button','button secondary',q);b.type='button';b.onclick=()=>ask(q);suggestions.append(b);}
  form.onsubmit=e=>{e.preventDefault();ask(input.value);};
  guide.onclick=()=>{shutdown();window.CareerGuide?.start();};
  fresh.onclick=async()=>{if(busy)return;try{if(sid)await window.api('/assistant/threads/'+sid,{method:'DELETE'});sid=null;generation++;log.replaceChildren();bubble('你好，我是小安。可以问我职业问题，也可以让我带你找到功能入口。');}catch(e){bubble(e.message);}};
  window.addEventListener('account-data-erased',()=>{generation++;sid=null;restored=true;log.replaceChildren();bubble('个人对话资料已清除，可以开始新的对话。');});
  window.CareerAssistant={async open(){
    if(dialog.open)return;dialog.showModal();input.focus();
    if(restored||sid||busy)return;const epoch=generation;busy=true;send.disabled=true;
    try{
      const list=await window.api('/assistant/threads');
      if(epoch!==generation)return;
      if(list.items.length){const saved=await window.api('/assistant/threads/'+list.items[0].id);if(epoch!==generation)return;sid=saved.id;log.replaceChildren();for(const m of saved.messages)bubble(m.content,m.role==='user'?'user':'assistant');}
      restored=true;
    }catch(e){if(epoch===generation)bubble(e.message);}
    finally{busy=false;send.disabled=false;}
  }};
  bubble('你好，我是小安。聊聊你的职业目标，或告诉我哪里不会用。');
})();
