async function loadAdmin(){
  signed();if(platform.user.role!=='admin')throw Error('仅管理员可访问后台。');
  const [data,model,jobs]=await Promise.all([api('/admin/overview'),api('/admin/model'),api('/admin/jobs')]);
  await refreshAudit();
  const metrics=$('#admin-metrics');metrics.replaceChildren();const labels={users:'注册用户',jobs:'发布岗位',reviews:'岗位点评',trees:'生成路线',exams:'技能练习',interviews:'面试会话',active_users_today:'今日活跃用户',companies:'入驻企业',mail_messages:'站内邮件',active_applications:'有效岗位投递'};
  Object.entries(data.totals).forEach(([key,count])=>{const card=node('article','panel');card.append(node('p','fine-print',labels[key]||key),node('strong','metric-value',count));metrics.append(card);});
  $('#admin-provider').value=model.provider;$('#admin-model').value=model.model;$('#admin-key').value='';text('#admin-key-status',model.has_key?'已有服务端密钥，页面不显示原值。':'尚未配置云端密钥。');
  const a=$('#admin-activity');a.replaceChildren();data.activity.forEach(x=>a.append(node('div','admin-row',`${x.action} · ${x.count} 次`)));
  const daily=$('#admin-daily');daily.replaceChildren();data.daily.forEach(x=>daily.append(node('div','admin-row',`${x.day} · ${x.count} 次操作`)));
  const users=$('#admin-users');users.replaceChildren();data.users.forEach(u=>{const row=node('div','admin-row');row.append(node('span','',`${u.username} · ${u.role==='admin'?'管理员':u.role==='company'?'企业管理员':'用户'} · ${u.disabled?'已停用':'正常'}`));if(u.id!==platform.user.id)row.append(button(u.disabled?'启用账号':'停用账号',async()=>{await api('/admin/users/'+u.id,{method:'PATCH',data:{disabled:!u.disabled}});await loadAdmin();}));if(u.id!==platform.user.id)row.append(button('发送通知',async()=>{window.AdminPages.go('mail');await window.CareerMail.compose({recipient_id:u.id,subject:'平台通知'});}));users.append(row);});
  const reviews=$('#admin-reviews');reviews.replaceChildren();data.reviews.forEach(r=>{const row=node('div','admin-row'),content=node('div');content.append(node('strong','',`${r.company} · ${r.title} · ${r.rating} 分`),node('p','',r.body));row.append(content,button(r.hidden?'恢复公开':'隐藏点评',async()=>{await api('/admin/reviews/'+r.id,{method:'PATCH',data:{hidden:!r.hidden}});await loadAdmin();}));reviews.append(row);});
  const list=$('#admin-jobs');list.replaceChildren();jobs.items.forEach(j=>{
    const row=node('div','admin-row'),content=node('div');content.append(node('strong','',`${j.company} · ${j.title}`),node('p','',j.description),node('p','fine-print',`${j.publisher} · ${{pending:'待审核',approved:'已通过',rejected:'未通过'}[j.status]}`));
    if(j.review_note)content.append(node('p','fine-print','审核意见：'+j.review_note));
    const note=node('textarea');note.rows=2;note.maxLength=500;note.placeholder='审核意见（拒绝时必填）';note.setAttribute('aria-label','审核意见：'+j.title);content.append(note);row.append(content);
    const review=async status=>{await api('/admin/jobs/'+j.id+'/review',{method:'PATCH',data:{status,note:note.value.trim()}});await loadAdmin();toast(status==='approved'?'审核通过，岗位已展示。':'已拒绝，审核意见已反馈。');};
    if(j.status!=='approved')row.append(button('通过',()=>review('approved')));
    if(j.status!=='rejected')row.append(button('拒绝',()=>review('rejected')));
    row.append(button('下架',async()=>{await api('/jobs/'+j.id,{method:'DELETE'});await loadAdmin();}));list.append(row);
  });

}
async function saveModel(){await api('/admin/model',{method:'PUT',data:{provider:$('#admin-provider').value,model:$('#admin-model').value.trim(),api_key:$('#admin-key').value.trim()}});$('#admin-key').value='';text('#admin-model-result','配置已保存，后续 AI 请求将使用新配置。');}
async function testModel(){const result=await api('/admin/model/test',{method:'POST'});text('#admin-model-result',result.message);}

