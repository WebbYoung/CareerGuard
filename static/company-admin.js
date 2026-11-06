(() => {
  'use strict';
  const status={pending:'待审核',approved:'平台材料审核通过',rejected:'已退回'};
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  window.CompanyAdminUI={async init(container){
    if(!container)return;
    container.replaceChildren();container.classList.add('company-admin-list');
    const notice=node('p','企业审核只核对提交材料，不代表政府认证；退回会同时停止本企业岗位公开。'),message=node('p'),refresh=node('button','刷新企业材料'),list=node('div');message.setAttribute('role','status');refresh.type='button';container.append(notice,refresh,message,list);
    let csrf='';
    async function call(path,method='GET',body){const r=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'X-CSRF-Token':csrf,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'操作失败');return data;}
    async function load(){
      refresh.disabled=true;message.textContent='正在读取企业材料…';
      try{csrf=(await call('/auth/session')).csrf_token;const {items}=await call('/admin/companies');list.replaceChildren();if(!items.length)list.append(node('p','暂无企业材料。'));
        for(const company of items){
          const card=node('article');card.className='company-card';const heading=node('h3',company.name),badge=node('span',status[company.status]||company.status);badge.className='company-badge';card.append(heading,badge,node('p','统一社会信用代码：'+company.credit_code),node('p','联系人职务：'+company.contact_role),node('p','提交时间：'+company.created));
          const notes=company.ocr_notes;card.append(node('p',notes.message),node('p','名称文字匹配：'+(notes.name_match===null?'未识别':notes.name_match?'一致':'未找到一致文字')+'；信用代码文字匹配：'+(notes.credit_code_match===null?'未识别':notes.credit_code_match?'一致':'未找到一致文字')));
          if(notes.detected_name)card.append(node('p','OCR名称候选：'+notes.detected_name));if(notes.detected_credit_codes?.length)card.append(node('p','OCR代码候选：'+notes.detected_credit_codes.join(' / ')));
          const original=node('a','查看营业执照原件');original.href='/api/admin/companies/'+company.id+'/license';original.target='_blank';original.rel='noopener';const download=node('a',' 下载原件');download.href=original.href;download.download='license-'+company.id;card.append(original,download);
          const label=node('label','审核意见（退回时必填）'),note=node('textarea');note.maxLength=2000;note.rows=3;note.value=company.review_note;label.append(note);card.append(label);
          for(const [value,title] of [['approved','通过平台材料审核'],['rejected','退回材料并停止岗位公开']]){const button=node('button',title);button.type='button';button.onclick=async()=>{if(value==='rejected'&&!note.value.trim()){message.textContent='请先填写退回原因。';note.focus();return;}const buttons=card.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await call('/admin/companies/'+company.id+'/review','PATCH',{status:value,note:note.value});await load();message.textContent='审核结果已保存。';}catch(e){message.textContent=e.message;buttons.forEach(b=>b.disabled=false);}};card.append(button);}list.append(card);
        }message.textContent='共 '+items.length+' 家企业。';
      }catch(e){message.textContent=e.message;}finally{refresh.disabled=false;}
    }
    refresh.onclick=load;await load();
  }};
})();
