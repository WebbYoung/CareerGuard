(() => {
  'use strict';
  let mounted=false;
  async function mount(){
    if(mounted||!window.CareerGuardAdminReady)return;
    mounted=true;
    const root=document.querySelector('#view-admin');if(!root)return;
    const legacy=document.querySelector('#admin-provider')?.closest('article');
    if(legacy){legacy.hidden=true;legacy.setAttribute('aria-hidden','true');}
    const heading=root.querySelector('.page-heading');
    heading.querySelector('h1').id='admin-page-title';heading.querySelector('h1').tabIndex=-1;
    heading.querySelector('.eyebrow').id='admin-page-eyebrow';heading.querySelector('p').id='admin-page-description';
    const page=(id,route,...children)=>{const section=document.createElement('section');section.id=id;section.className='admin-page';section.dataset.adminPage=route;section.setAttribute('aria-labelledby','admin-page-title');section.hidden=true;section.append(...children);root.append(section);return section;};
    page('admin-overview-page','overview',document.querySelector('#admin-metrics'),document.querySelector('#admin-activity').closest('.two-col'));
    page('admin-users-page','users',document.querySelector('#admin-users').closest('article'));
    page('admin-jobs-page','jobs',document.querySelector('#admin-jobs').closest('article'),document.querySelector('#admin-publish'));
    page('admin-reviews-page','reviews',document.querySelector('#admin-reviews').closest('article'));
    document.querySelector('#admin-security').dataset.adminPage='security';
    const company=page('admin-companies','companies');
    // Keep a shared host: ModelSettingsUI checks container.contains(kb) on refresh.
    const models=page('admin-ai-settings','models knowledge');
    const mail=page('admin-mail','mail'),mailSettings=document.createElement('div'),mailBody=document.createElement('div');mailSettings.id='admin-mail-settings';mailBody.id='admin-mail-content';mailSettings.className='panel spaced';mailBody.className='panel spaced';mail.append(mailSettings,mailBody);
    window.AdminPages.init();
    async function load(component,container){try{if(!component)throw Error('管理组件未加载，请刷新页面。');await component.init(container);}catch(error){const message=document.createElement('p');message.className='panel';message.textContent=error.message;message.setAttribute('role','status');container.append(message);}}
    const splitModels=()=>{Array.from(models.children).filter(el=>el.tagName==='ARTICLE').forEach((card,index)=>{card.dataset.adminPage=index<3?'models':'knowledge';});window.AdminPages.refresh();};
    // Tag cards while the asynchronous component mounts, so another page never flashes.
    const observer=new MutationObserver(splitModels);observer.observe(models,{childList:true});
    const modelLoad=load(window.ModelSettingsUI,models).finally(()=>{observer.disconnect();splitModels();});
    await Promise.allSettled([load(window.CompanyAdminUI,company),modelLoad,load(window.MailAdminUI,mailSettings),load(window.MailUI||window.CareerMail,mailBody)]);
    window.AdminPages.refresh();document.dispatchEvent(new CustomEvent('admin-pages-ready'));
  }
  document.addEventListener('admin-loaded',mount);if(window.CareerGuardAdminReady)mount();
})();
