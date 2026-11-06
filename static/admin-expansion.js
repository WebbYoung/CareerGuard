(() => {
  'use strict';
  let mounted=false;
  async function mount(){
    if(mounted||!window.CareerGuardAdminReady)return;
    mounted=true;
    const root=document.querySelector('#view-admin');
    if(!root)return;
    // Retain the legacy DOM because overview refresh still updates these fields.
    const legacy=document.querySelector('#admin-provider')?.closest('article');
    if(legacy){legacy.hidden=true;legacy.setAttribute('aria-hidden','true');if(legacy.parentElement?.classList.contains('two-col'))legacy.parentElement.style.gridTemplateColumns='minmax(0,1fr)';}
    const section=(id,title,description)=>{
      const article=document.createElement('section');article.id=id;article.className='panel spaced';
      const heading=document.createElement('h2');heading.textContent=title;
      const intro=document.createElement('p');intro.className='fine-print';intro.textContent=description;
      const body=document.createElement('div');article.append(heading,intro,body);
      root.insertBefore(article,document.querySelector('#admin-security'));
      const link=document.createElement('a');link.href='#'+id;link.textContent=title;document.querySelector('.admin-sidebar nav')?.append(link);
      return body;
    };
    const company=section('admin-companies','企业材料审核','查看原件，核对企业信息；材料通过后企业可提交待审岗位。');
    const models=section('admin-ai-settings','AI模型与知识库','分别配置对话、Embedding与图片模型；保存配置不会自动连接。');
    async function load(component,container){
      try{if(!component)throw Error('管理组件未加载，请刷新页面。');await component.init(container);}
      catch(error){const message=document.createElement('p');message.textContent=error.message;message.setAttribute('role','status');container.append(message);}
    }
    // ModelSettingsUI uses the existing admin node/api/toast helpers, whose
    // signatures already match its UI adapter. Do not redeclare global helpers.
    await Promise.allSettled([load(window.CompanyAdminUI,company),load(window.ModelSettingsUI,models)]);
    if(location.hash==='#admin-companies'||location.hash==='#admin-ai-settings')document.querySelector(location.hash)?.scrollIntoView({behavior:'auto'});
  }
  document.addEventListener('admin-loaded',mount);
  if(window.CareerGuardAdminReady)mount();
})();
