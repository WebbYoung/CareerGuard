'use strict';
window.Portal={csrf:'',ready:null,async request(path,{method='GET',data}={}){
  await this.ready;
  const headers={};if(method!=='GET')headers['X-CSRF-Token']=this.csrf;
  if(data!==undefined)headers['Content-Type']='application/json';
  const response=await fetch('/api'+path,{method,headers,body:data===undefined?undefined:JSON.stringify(data),credentials:'same-origin',cache:'no-store',redirect:'error'});
  const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'操作未完成，请重试。');
  if(result.csrf_token)this.csrf=result.csrf_token;return result;
}};
Portal.ready=fetch('/api/auth/session',{credentials:'same-origin',cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('无法建立会话，请刷新。');Portal.csrf=(await r.json()).csrf_token;});
Portal.ready.catch(()=>{});
Portal.destination=role=>role==='admin'?'/admin':role==='company'?'/company':'/app';
document.querySelectorAll('[data-toggle-password]').forEach(b=>b.addEventListener('click',()=>{const field=document.getElementById('password');field.type=field.type==='password'?'text':'password';b.textContent=field.type==='password'?'显示':'隐藏';}));
const form=document.getElementById('account-form');
if(form)form.addEventListener('submit',async event=>{
  event.preventDefault();const b=form.querySelector('button[type=submit]'),message=document.getElementById('portal-message');
  b.disabled=true;message.textContent='正在验证账号…';
  try{
    const mode=document.body.dataset.page;
    const password=document.getElementById('password').value;
    if(mode==='register'&&password!==document.getElementById('confirm-password').value)throw Error('两次输入的密码不一致。');
    const result=await Portal.request('/auth/'+mode,{method:'POST',data:{username:document.getElementById('username').value.trim(),password}});
    document.getElementById('password').value='';
    const adminTarget=new URLSearchParams(location.search).get('next')==='admin';
    if(adminTarget&&result.user.role!=='admin'){message.textContent='已登录，网站管理后台仅限网站管理员。';const link=document.createElement('a');link.href=Portal.destination(result.user.role);link.textContent=result.user.role==='company'?'进入企业工作台 →':'进入求职工作台 →';message.append(link);return;}
    location.assign(Portal.destination(result.user.role));
  }catch(error){message.textContent=error.message;}finally{b.disabled=false;}
});
if(document.body.dataset.page==='home'){
  Portal.request('/auth/me').then(({user})=>{if(user){document.querySelectorAll('a[href=\"/demo\"],.hero-footnote').forEach(el=>el.hidden=true);const link=document.getElementById('home-account');link.href=Portal.destination(user.role);link.textContent=user.role==='company'?'企业工作台 ↗':'继续使用 ↗';if(user.role==='company')document.querySelectorAll('a[href^="/app"]').forEach(a=>a.href='/company');}}).catch(()=>{});
}
if(document.body.dataset.page==='demo'){
  let data,expiry;
  const clearDemo=()=>{document.getElementById('demo-output').replaceChildren();document.getElementById('demo-material').textContent='演示已清空，选择上方分类可重新查看。';};
  const touch=()=>{clearTimeout(expiry);expiry=setTimeout(clearDemo,30*60*1000);};
  document.querySelector('[data-clear-demo]').addEventListener('click',clearDemo);
  document.addEventListener('pointerdown',touch);document.addEventListener('keydown',touch);touch();
  const render=mode=>{
    document.querySelectorAll('[data-demo]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.demo===mode)));
    const original=document.getElementById('demo-material'),result=document.getElementById('demo-output');result.replaceChildren();
    const el=(tag,value,cls='')=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
    if(mode==='risk'){original.textContent=data.recruitment;result.append(el('div',data.risk.score+' / 100','demo-score'),el('p',data.risk.level+' · 规则评分','demo-caption'));const list=el('ul','','demo-findings');data.risk.findings.forEach(f=>list.append(el('li',f.category+'：'+f.advice)));result.append(list,el('p',data.risk.disclaimer,'demo-caption'));}
    if(mode==='privacy'){original.textContent='【固定合成简历】\n技能：Python、SQL、Git\n项目：完成数据清洗与查询报表\n邮箱：demo@example.invalid';result.append(el('h2','脱敏后预览'),el('pre',data.redacted),el('p','合成样例仅演示掩码效果，真实材料请登录后上传。','demo-caption'));}
    if(mode==='plan'){original.textContent='【合成岗位】Python 后端开发\n要求 Python、SQL、Git、FastAPI、Docker、自动化测试。';result.append(el('h2','从差距到下一步'));data.report.plan.forEach(w=>result.append(el('p','第 '+w.week+' 周 · '+w.focus),el('p',w.deliverable,'demo-caption')));result.append(el('p','固定样例与词项检索结果，未调用 AI。','demo-caption'));}
  };
  Portal.request('/demo').then(value=>{data=value;render('risk');}).catch(e=>document.getElementById('demo-material').textContent=e.message);
  document.querySelectorAll('[data-demo]').forEach(b=>b.addEventListener('click',()=>{if(data)render(b.dataset.demo);}));
}
