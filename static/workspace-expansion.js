/* Mount trusted same-origin feature fragments after account bootstrap completes. */
(function(){
  'use strict';
  let mounting=null;
  async function mount(){
    if(mounting)return mounting;
    mounting=(async()=>{
      const main=document.querySelector('#main');
      if(!main||!window.ResumeStudio)return;
      let section=document.querySelector('#view-resume');
      if(!section){
        const response=await fetch('/static/resume-studio.html',{credentials:'same-origin',cache:'no-store',redirect:'error'});
        if(!response.ok)throw Error('简历工作室加载失败，请刷新页面。');
        const template=document.createElement('template');
        // Fixed application-owned HTML only. All resume and AI content uses textContent.
        template.innerHTML=await response.text();
        section=template.content.querySelector('#view-resume');
        if(!section)throw Error('简历工作室页面不完整，请刷新页面。');
        main.insertBefore(template.content,main.querySelector('.page-footer'));
      }
      titles.resume='AI 简历生成';
      window.ResumeStudio.init(section);
      const nav=document.querySelector('.nav-item[data-view="resume"]');
      if(nav){nav.disabled=false;nav.removeAttribute('aria-label');}
      window.dispatchEvent(new CustomEvent('workspace-expanded',{detail:{views:['resume']}}));
      if(location.hash==='#resume'&&typeof show==='function')show('resume');
    })();
    try{await mounting;}catch(error){mounting=null;if(typeof toast==='function')toast(error.message,true);}
  }
  window.addEventListener('platform-loaded',mount,{once:true});
  window.addEventListener('hashchange',()=>{
    if(location.hash==='#resume'&&document.querySelector('#view-resume')&&typeof show==='function')show('resume');
  });
  if(window.careerPlatformReady===true)mount();
})();
