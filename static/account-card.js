/* Editable account identity. Avatar URLs are fixed same-origin endpoints only. */
(() => {
  'use strict';
  let account=null,user=null,initialized=false,dialog=null,epoch=0,pending=false;
  const $=s=>document.querySelector(s);
  const make=(tag,cls='',value='')=>{const el=document.createElement(tag);el.className=cls;el.textContent=value;return el;};
  const message=(value,error=false)=>{const el=$('#account-card-status');if(el){el.textContent=value;el.classList.toggle('is-error',error);}};
  function avatar(el,large=false){
    if(!el||!account)return;
    el.replaceChildren();
    if(account.has_avatar){const img=make('img');img.src='/api/account/avatar?v='+encodeURIComponent(account.avatar_revision);img.alt=large?'我的头像':'';img.draggable=false;el.append(img);}
    else el.textContent=Array.from(account.nickname||user?.username||'我')[0].toUpperCase();
  }
  function render(){
    if(!account||!user)return;
    const name=account.nickname||user.username;
    $('#signed-name').textContent=name;$('#account-username').textContent='账号 @'+user.username;
    $('#account-bio').textContent=account.bio||'用一句话，记录你的职业目标与个人风格。';
    $('#account-bio').classList.toggle('is-empty',!account.bio);
    $('#account-city').textContent=account.city?'城市 · '+account.city:'尚未填写城市';
    $('#account-joined').textContent=String(account.created||'').slice(0,10).replaceAll('-','.')+' 加入';
    $('#account-status').textContent='你好，'+name+'。在这里管理资料，查看属于你的每一步成长。';
    const footer=$('.sidebar-footer');
    if(footer){const image=make('span','avatar account-nav-avatar'),label=make('span','account-nav-name',name);avatar(image);footer.replaceChildren(image,label,make('span','online-dot'));}
    const top=$('.top-avatar');if(top){avatar(top);top.classList.add('account-nav-avatar');top.title=name;top.setAttribute('aria-label',name+'的头像');}
    const button=$('#account-top');if(button)button.textContent=name;
    avatar($('#account-avatar'),true);
    $('#account-remove-avatar').hidden=!account.has_avatar;
  }
  function setBusy(value){
    pending=value;
    for(const el of [$('#account-change-avatar'),$('#account-edit'),$('#account-avatar-file'),...dialog.querySelectorAll('input,textarea,button')])if(el)el.disabled=value;
    $('#account-change-avatar').setAttribute('aria-busy',String(value));
  }
  function initialize(){
    if(initialized||!$('#account-change-avatar'))return;
    initialized=true;dialog=make('dialog','account-editor');dialog.setAttribute('aria-labelledby','account-editor-heading');
    const heading=make('h2','','让资料，更像你');heading.id='account-editor-heading';
    const note=make('p','muted','昵称用于页面显示，登录账号保持不变。');
    const form=make('form'),fields={};
    for(const [key,label,limit,placeholder] of [['nickname','昵称',24,'怎么称呼你？'],['city','所在城市',40,'例如：杭州（选填）'],['bio','个人简介',160,'分享你的职业方向、兴趣或一句座右铭（选填）']]){
      const box=make('div','field'),caption=make('label','',label),input=make(key==='bio'?'textarea':'input');
      input.id='account-edit-'+key;input.name=key;input.maxLength=limit;input.placeholder=placeholder;caption.htmlFor=input.id;
      if(key==='bio')input.rows=4;else input.type='text';
      input.autocomplete=key==='nickname'?'nickname':key==='city'?'address-level2':'off';
      const hint=make('small','account-field-hint',key==='nickname'?'最多24字，留空则显示登录账号':'最多'+limit+'字');
      box.append(caption,input,hint);form.append(box);fields[key]=input;
    }
    const error=make('p','account-form-error');error.setAttribute('role','status');
    const controls=make('div','button-row'),cancel=make('button','button secondary','取消'),save=make('button','button primary','保存资料');cancel.type='button';save.type='submit';controls.append(cancel,save);form.append(error,controls);
    const remove=make('button','account-remove-avatar','恢复默认头像');remove.id='account-remove-avatar';remove.type='button';
    dialog.append(heading,note,form,remove);document.body.append(dialog);
    $('#account-edit').onclick=()=>{if(pending||!account)return;for(const key in fields)fields[key].value=account[key]||'';error.textContent='';dialog.showModal();fields.nickname.focus();};
    cancel.onclick=()=>dialog.close();
    dialog.addEventListener('cancel',e=>{if(pending)e.preventDefault();});
    form.onsubmit=async e=>{
      e.preventDefault();if(pending)return;const version=++epoch;setBusy(true);error.textContent='';
      try{const data=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value.trim()]));const result=await window.api('/account',{method:'PUT',data});if(version!==epoch)return;account=result;render();dialog.close();message('资料已保存，页面中的头像和称呼已同步。');window.toast?.('个人资料已保存。');}
      catch(e){if(version===epoch)error.textContent=e.message;}
      finally{if(version===epoch)setBusy(false);}
    };
    $('#account-change-avatar').onclick=()=>{if(!pending)$('#account-avatar-file').click();};
    $('#account-avatar-file').onchange=async e=>{
      const file=e.target.files?.[0];if(!file||pending)return;e.target.value='';
      if(!['image/png','image/jpeg','image/webp'].includes(file.type)){message('请选择PNG、JPEG或WebP静态图片。',true);return;}
      if(file.size>4*1024*1024){message('头像文件请控制在4MB以内。',true);return;}
      const version=++epoch;setBusy(true);message('正在处理头像…');
      try{const result=await window.api('/account/avatar',{method:'POST',body:file,headers:{'Content-Type':file.type}});if(version!==epoch)return;account=result;render();message('头像已更新。图片已自动居中裁切并去除原图元数据。');}
      catch(e){if(version===epoch)message(e.message,true);}
      finally{if(version===epoch)setBusy(false);}
    };
    remove.onclick=async()=>{
      if(pending)return;const version=++epoch;setBusy(true);
      try{const result=await window.api('/account/avatar',{method:'DELETE'});if(version!==epoch)return;account=result;render();message('已恢复默认头像。');}
      catch(e){if(version===epoch)error.textContent=e.message;}
      finally{if(version===epoch)setBusy(false);}
    };
    window.addEventListener('account-data-erased',()=>{
      epoch++;account=null;dialog.close();for(const f of Object.values(fields))f.value='';$('#account-avatar-file').value='';setBusy(false);
      for(const el of [$('#account-avatar'),$('.top-avatar'),$('.sidebar-footer .avatar')])el?.replaceChildren();
    });
  }
  window.AccountCard={async load(identity){
    initialize();if(!initialized||pending)return;user=identity;const version=++epoch;
    try{const result=await window.api('/account');if(version!==epoch)return;account=result;render();}
    catch(e){if(version===epoch)message('个人资料暂未加载：'+e.message,true);}
  }};
  const ready=()=>{if(!initialized&&typeof platform!=='undefined'&&platform.user)window.AccountCard.load(platform.user);};
  if(window.careerPlatformReady)ready();else window.addEventListener('platform-loaded',ready,{once:true});
})();
