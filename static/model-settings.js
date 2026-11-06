'use strict';
window.ModelSettingsUI = (() => {
  function field(parent,label,type='text') {
    const box=node('div','field'),caption=node('label','',label),input=node(type==='textarea'?'textarea':type==='select'?'select':'input');
    if(!['textarea','select'].includes(type))input.type=type;
    const id='model-setting-'+Math.random().toString(36).slice(2);input.id=id;caption.htmlFor=id;
    box.append(caption,input);parent.append(box);return input;
  }
  function action(parent,label,fn){
    const b=node('button','button secondary',label);b.type='button';parent.append(b);
    b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){toast(e.message,true);}finally{b.disabled=false;}});return b;
  }
  async function init(container){
    container.replaceChildren();
    for(const [kind,label] of [['chat','对话 / Agent模型'],['embedding','Embedding向量模型'],['image','证件照图片编辑模型']]){
      const box=node('article','panel spaced');box.append(node('h3','',label));container.append(box);
      const protocol=field(box,'接口协议','select');
      for(const [v,t] of [['openai','OpenAI兼容'],...(kind==='chat'?[['anthropic','Anthropic Messages']]:[]),...(kind!=='image'?[['ollama','本机Ollama']]:[])]){const o=node('option','',t);o.value=v;protocol.append(o);}
      const provider=field(box,'供应商名称'),url=field(box,'API基础地址（HTTPS443，主机需在允许列表）'),model=field(box,'模型名称'),key=field(box,'API密钥（留空保留已保存值）','password');
      key.autocomplete='new-password';const dimensions=kind==='embedding'?field(box,'向量维度（可选）','number'):null;
      const message=node('p','muted');box.append(message);
      const settings=await api('/admin/ai-settings/'+kind);
      protocol.value=settings.protocol;provider.value=settings.provider;url.value=settings.base_url;model.value=settings.model;if(dimensions)dimensions.value=settings.dimensions||'';
      message.textContent=settings.message+(settings.has_key?' · 已保存密钥':' · 未保存密钥');
      action(box,'保存配置',async()=>{
        const data={kind,provider:provider.value.trim(),protocol:protocol.value,base_url:url.value.trim(),model:model.value.trim(),api_key:key.value,dimensions:dimensions&&dimensions.value?Number(dimensions.value):null};
        const result=await api('/admin/ai-settings/'+kind,{method:'PUT',data});key.value='';message.textContent='已保存配置；尚未连接验证。'+(result.has_key?' · 已保存密钥':'');toast('模型配置已保存，未发起连接。');await refreshKnowledge();
      });
    }
    const kb=node('article','panel spaced');kb.append(node('h3','','共享知识库'));container.append(kb);
    const status=node('p','muted');status.setAttribute('aria-live','polite');kb.append(status);
    const title=field(kb,'知识标题'),content=field(kb,'知识正文','textarea');content.rows=7;content.maxLength=100000;title.maxLength=120;
    let editing=null;
    action(kb,'保存知识文档',async()=>{await api('/admin/knowledge'+(editing?'/'+editing:''),{method:editing?'PUT':'POST',data:{title:title.value,content:content.value}});editing=null;title.value='';content.value='';await refreshKnowledge();toast('知识已保存，需手动构建向量索引。');});
    action(kb,'取消编辑',async()=>{editing=null;title.value='';content.value='';});
    const upload=field(kb,'上传UTF-8 TXT / Markdown','file');upload.accept='.txt,.md,text/plain,text/markdown';
    action(kb,'导入所选文本',async()=>{const file=upload.files[0];if(!file)throw Error('请选择文本文件。');if(file.size>100000)throw Error('文件超过100KB。');await api('/admin/knowledge',{method:'POST',data:{title:file.name.slice(0,120),content:await file.text()}});upload.value='';await refreshKnowledge();toast('文本已导入，尚未生成Embedding。');});
    const build=action(kb,'手动构建向量索引（调用已配置Embedding）',async()=>{status.textContent='正在调用Embedding构建索引…';try{await api('/admin/knowledge/index',{method:'POST',data:{}});toast('向量索引已构建。');}finally{await refreshKnowledge();}});
    action(kb,'刷新索引状态',async()=>refreshKnowledge());const list=node('div');kb.append(list);
    async function refreshKnowledge(){
      if(!container.contains(kb))return;
      const data=await api('/admin/knowledge');const s=data.state;
      status.textContent=`文档 ${s.documents} · 分块 ${s.chunks} · 当前模型已索引 ${s.indexed_chunks} · ${s.retrieval_mode==='vector'?'向量检索':'关键词降级检索'}。${s.message}`;
      build.disabled=!s.embedding_configured||s.building||!s.chunks;list.replaceChildren();
      for(const d of data.documents){const row=node('div','panel spaced');row.append(node('strong','',d.title),node('p','muted',d.content.slice(0,160)));action(row,'编辑',async()=>{editing=d.id;title.value=d.title;content.value=d.content;title.focus();});action(row,'删除文档',async()=>{await api('/admin/knowledge/'+d.id,{method:'DELETE'});await refreshKnowledge();});list.append(row);}
    }
    await refreshKnowledge();
  }
  return {init};
})();
