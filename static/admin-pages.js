/* Independent pages preserve mounted forms and their unsaved state. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.AdminPages=api;})(typeof window==='undefined'?this:window,function(){
  'use strict';
  const pages={
    overview:['平台总览','PLATFORM / OVERVIEW','查看平台运行、账号规模与近期使用情况。','grid'],
    users:['用户管理','ACCOUNTS / MEMBERS','维护平台账号和访问状态。','user'],
    jobs:['岗位审核与推荐','JOBS / MODERATION','审核企业岗位，维护面向求职者的推荐机会。','list'],
    reviews:['点评管理','REVIEWS / MODERATION','维护公开点评，处理不适宜展示的内容。','check'],
    companies:['企业材料审核','COMPANIES / VERIFICATION','核验企业原件和资料，处理认证申请。','shield'],
    models:['AI 模型设置','INTELLIGENCE / MODELS','分别配置对话、向量与图片模型；保存配置不会自动连接。','spark'],
    knowledge:['共享知识库','KNOWLEDGE / LIBRARY','维护知识文档，查看检索状态并按需手动构建索引。','file'],
    security:['安全与审计','SECURITY / AUDIT','检查内置防护，验证提示注入规则并查看操作审计。','lock'],
    mail:['邮件与通知','MAIL / DELIVERY','配置邮件服务，管理平台邮件通知。','arrow']
  };
  const aliases={'#view-admin':'overview','#admin-users':'users','#admin-publish':'jobs','#admin-jobs':'jobs','#admin-reviews':'reviews','#admin-companies':'companies','#admin-ai-settings':'models','#admin-security':'security'};
  function resolve(href){const u=new URL(href,'http://localhost'),p=u.searchParams.get('page');return Object.hasOwn(pages,p)?p:(!p&&aliases[u.hash])||'overview';}
  function pageURL(href,page){const u=new URL(href,'http://localhost');u.searchParams.set('page',Object.hasOwn(pages,page)?page:'overview');u.hash='';return u.pathname+u.search;}
  function render(doc,page){
    page=Object.hasOwn(pages,page)?page:'overview';
    doc.querySelectorAll('[data-admin-page]').forEach(el=>{el.hidden=!el.dataset.adminPage.split(' ').includes(page);});
    doc.querySelectorAll('[data-admin-route]').forEach(link=>{const active=link.dataset.adminRoute===page;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
    const [title,eyebrow,description]=pages[page];
    for(const [id,value] of [['admin-page-title',title],['admin-page-eyebrow',eyebrow],['admin-page-description',description],['admin-breadcrumb','管理后台 / '+title]]){const el=doc.getElementById(id);if(el)el.textContent=value;}
    doc.title=title+' · 职安管理控制台';return page;
  }
  let started=false;
  function refresh(){return render(document,resolve(location.href));}
  function go(page,{replace=false,focus=true}={}){const href=pageURL(location.href,page);if(href!==location.pathname+location.search+location.hash)history[replace?'replaceState':'pushState']({},'',href);refresh();if(focus)document.getElementById('admin-page-title')?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
  function init(){
    if(started)return refresh();started=true;
    const nav=document.querySelector('.admin-sidebar nav');nav.replaceChildren();
    Object.entries(pages).forEach(([key,[title,,,icon]])=>{const link=document.createElement('a');link.href=pageURL('/admin',key);link.dataset.adminRoute=key;link.className='nav-item';const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('aria-hidden','true');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-'+icon);svg.append(use);const label=document.createElement('span');label.textContent=title;link.append(svg,label);nav.append(link);});
    nav.addEventListener('click',e=>{const link=e.target.closest('[data-admin-route]');if(!link||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();go(link.dataset.adminRoute);});
    window.addEventListener('popstate',()=>{refresh();document.getElementById('admin-page-title')?.focus({preventScroll:true});});
    go(resolve(location.href),{replace:true,focus:false});document.getElementById('admin-main').removeAttribute('aria-busy');
  }
  return {pages,resolve,pageURL,render,init,go,refresh};
});
