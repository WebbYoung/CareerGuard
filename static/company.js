(() => {
  'use strict';
  let csrf='',editing=null,company=null;
  const $=s=>document.querySelector(s);
  const status={pending:'待平台审核',approved:'平台材料审核通过',rejected:'材料已退回'};
  function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
  function message(text,error=false){$('#company-message').textContent=text;$('#company-message').classList.toggle('company-error',error);}
  async function api(path,method='GET',data){const options={method,credentials:'same-origin',headers:{'X-CSRF-Token':csrf}};if(data instanceof FormData)options.body=data;else if(data){options.headers['Content-Type']='application/json';options.body=JSON.stringify(data);}const r=await fetch('/api'+path,options);const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'请求未完成，请重试。');if(result.csrf_token)csrf=result.csrf_token;return result;}
  function reset(){editing=null;$('#company-job-form').reset();$('#company-job-heading').textContent='提交招聘岗位';$('#company-job-cancel').hidden=true;}
  async function refresh(){
    const result=await api('/company/me');company=result.company;
    const info=$('#company-info');info.replaceChildren(el('h2',company.name),el('span',status[company.status]||company.status,'company-badge'),el('p','统一社会信用代码：'+company.credit_code),el('p','联系人职务：'+company.contact_role),el('p',company.review_note?'审核意见：'+company.review_note:'提交材料后，请等待平台人工审核。'),el('p',company.ocr_notes.message));
    info.append(el('p','此状态仅代表平台材料审核，不是政府真实性认证。','company-notice'));
    const original=el('a','查看已提交营业执照');original.href=company.license_url;original.target='_blank';original.rel='noopener';info.append(original);
    $('#company-job-fields').disabled=company.status!=='approved';
    message(company.status==='approved'?'企业材料已通过，可以提交岗位审核。':'当前暂不能提交或编辑岗位，您仍可下架已有岗位。');
    const {items}=await api('/company/jobs'),list=$('#company-jobs');list.replaceChildren();
    if(!items.length)list.append(el('p','还没有岗位。'));
    for(const job of items){const card=el('article',undefined,'company-job');card.append(el('h3',job.title),el('span',job.active?({pending:'岗位待审核',approved:'岗位已公开',rejected:'岗位已退回'}[job.status]||job.status):'已下架','company-badge'),el('p',job.description));if(job.review_note)card.append(el('p','岗位审核意见：'+job.review_note));const edit=el('button','编辑并重新送审');edit.type='button';edit.disabled=company.status!=='approved';edit.onclick=()=>{editing=job.id;const f=$('#company-job-form');f.elements.title.value=job.title;f.elements.description.value=job.description;$('#company-job-heading').textContent='编辑岗位 · 重新审核';$('#company-job-cancel').hidden=false;f.scrollIntoView({behavior:'auto',block:'center'});f.elements.title.focus();};card.append(edit);if(job.active){const down=el('button','下架');down.type='button';down.onclick=async()=>{down.disabled=true;try{await api('/company/jobs/'+job.id,'DELETE');await refresh();}catch(e){message(e.message,true);down.disabled=false;}};card.append(down);}list.append(card);}
  }
  async function start(){
    const session=await api('/auth/session');csrf=session.csrf_token;
    if(document.body.dataset.companyPage==='register'){
      $('#company-register').addEventListener('submit',async ev=>{ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('button[type=submit]'),file=form.elements.license.files[0];if(!file||file.size>8*1024*1024){message('请上传不超过8MB的营业执照。',true);return;}button.disabled=true;message('正在校验并提交材料，请稍候…');try{await api('/company/register','POST',new FormData(form));location.assign('/company');}catch(e){message(e.message,true);button.disabled=false;}});
      return;
    }
    const {user}=await api('/auth/me');if(!user){location.replace('/login?next=company');return;}if(user.role!=='company'){message('当前账号不是企业账号，请使用企业管理员账号登录。',true);return;}
    $('#company-refresh').onclick=()=>refresh().catch(e=>message(e.message,true));
    $('#company-logout').onclick=async()=>{try{await api('/auth/logout','POST');location.assign('/login');}catch(e){message(e.message,true);}};
    $('#company-job-cancel').onclick=reset;
    $('#company-job-form').onsubmit=async ev=>{ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('[type=submit]');button.disabled=true;try{await api('/company/jobs'+(editing?'/'+editing:''),editing?'PUT':'POST',{title:form.elements.title.value,description:form.elements.description.value});reset();await refresh();message('岗位已提交，等待网站管理员审核后公开。');}catch(e){message(e.message,true);}finally{button.disabled=false;}};
    await refresh();
  }
  start().catch(e=>message(e.message,true));
})();
