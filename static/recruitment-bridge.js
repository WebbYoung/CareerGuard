/* Only fixed application events can prepare the interview form; model consent stays manual. */
(() => {
  'use strict';
  let mailHost=null,mounted=false,mailReady=false,lastUnread=null;
  function prepare(detail){
    if(!detail||typeof detail.occupation!=='string'||typeof detail.jd!=='string')return;
    const id=detail.application_id;
    if(id!==null&&(!Number.isInteger(id)||id<1))return;
    stopVoice();window.CameraAssist?.stop();platform.interviewEpoch++;platform.interview=null;
    platform.applicationId=id;platform.applicationJob=detail.job||null;
    document.querySelector('#interview-occupation').value=detail.occupation.slice(0,160);
    document.querySelector('#interview-jd').value=detail.jd.slice(0,12000);
    document.querySelector('#interview-consent').checked=false;
    document.querySelector('#interview-messages').replaceChildren();
    document.querySelector('#interview-answer').value='';
    const note=document.querySelector('#interview-application-note');note.hidden=!id;
    document.querySelector('#interview-application-context').textContent=id?'已授权向该岗位企业投递简历。正式开始后计入此岗位面试人数；面试对话、评分、声音和镜头画面不向企业公开。':'';
    show('interview');toast(detail.notice||'岗位已填好。核对后勾选AI授权，再开始面试。');
  }
  async function initMail(){
    if(!mailHost||!window.CareerMail)return;
    if(mailReady){await window.CareerMail.refresh();return;}
    mailReady=true;
    try{await window.CareerMail.init(mailHost);}catch(e){mailReady=false;toast(e.message,true);}
  }
  function mount(){
    if(mounted)return;mounted=true;
    titles.mail='站内邮件';
    const section=node('section','view');section.id='view-mail';section.hidden=true;
    const heading=node('div','page-heading'),title=node('div');title.append(node('h1','','每一次沟通，都有回音。'),node('p','','接收企业意向邀请与平台通知，回复后继续了解机会。'));heading.append(title);
    mailHost=node('article','panel');mailHost.id='career-mail-host';section.append(heading,mailHost);
    document.querySelector('#main').insertBefore(section,document.querySelector('.page-footer'));
    const nav=node('button','nav-item');nav.type='button';nav.dataset.view='mail';
    const badge=node('span','badge green');badge.hidden=true;badge.setAttribute('aria-hidden','true');
    nav.append(icon('list'),node('span','','站内邮件'),badge);
    document.querySelector('.sidebar nav').insertBefore(nav,document.querySelector('.nav-item[data-view="profile"]'));
    nav.onclick=()=>show('mail');
    window.addEventListener('career:application-ready',event=>prepare(event.detail));
    window.addEventListener('viewchange',event=>{if(event.detail==='mail')initMail().catch(e=>toast(e.message,true));});
    window.addEventListener('career:mail-state',event=>{
      const count=Number(event.detail?.unread);if(!Number.isInteger(count)||count<0)return;
      badge.hidden=!count;badge.textContent=count>99?'99+':String(count);nav.setAttribute('aria-label',count?'站内邮件，'+count+'封未读':'站内邮件');
      if(lastUnread!==null&&count>lastUnread)toast('收到新的站内邮件，可前往收件箱查看。');lastUnread=count;
    });
    window.addEventListener('account-data-erased',()=>{mailReady=false;initMail().catch(e=>toast(e.message,true));});
    initMail().catch(e=>toast(e.message,true));
    if(location.hash==='#mail')show('mail');
    window.addEventListener('hashchange',()=>{if(location.hash==='#mail')show('mail');});
  }
  if(window.careerPlatformReady)mount();else window.addEventListener('platform-loaded',mount,{once:true});
})();
