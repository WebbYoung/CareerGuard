'use strict';
// 原生界面扩展。所有用户和模型内容以 textContent 渲染。
const platform={user:null,tree:null,jobs:[],exam:null,interview:null,reviewJob:null,applicationId:null,applicationJob:null,
  skills:[],pending:false,recognition:null,listening:false,voiceTimer:null,silenceTimer:null,voiceEpoch:0,interviewEpoch:0};
const extTitles={tree:'职业技能树',exam:'技能考试',interview:'AI 面试',jobs:'岗位推荐',profile:'个人中心'};
Object.assign(titles,extTitles);

function button(label,fn,kind='secondary'){
  const b=node('button','button '+kind,label);b.type='button';b.addEventListener('click',()=>platformRun(fn,b));return b;
}
async function platformRun(fn,b){
  if(platform.pending)return;
  platform.pending=true;if(b){b.disabled=true;b.setAttribute('aria-busy','true');}
  try{await fn();}catch(e){if(e.name!=='AbortError')toast(e.message||'操作未完成，请重试。',true);}
  finally{platform.pending=false;if(b){b.disabled=false;b.removeAttribute('aria-busy');}}
}
function signed(){if(!platform.user){location.href='/login';throw Error('请先登录。');}}
function consentChecked(id){if(!$(id).checked)throw Error('请先勾选本次 AI 数据发送说明。');}
function empty(root,message){root.replaceChildren(node('p','empty-mini',message));}

async function loadAccount(){
  const result=await api('/auth/me');platform.user=result.user;
  const u=platform.user,admin=u?.role==='admin';
  if(!u){location.replace('/login');return;}
  text('#account-role',u?(admin?'管理员':'已登录'):'访客');
  text('#account-status',u?`你好，${u.username}。你的学习数据按账号独立保存。`:'登录后保存目标职业、简历摘要、技能路线、考试和面试记录。');
  text('#signed-name',u?u.username:'');text('#account-top',u?u.username:'登录 / 注册');
  $('#job-recommend-label').hidden=true;
  $('#job-recommended').checked=false;
  const footer=$('.sidebar-footer');
  footer.replaceChildren(node('span','avatar',u?u.username[0].toUpperCase():'访'));
  const info=node('span','',u?u.username:'访客');footer.append(info,node('span','online-dot'));
  if(window.AccountCard)await window.AccountCard.load(u);
}
async function logout(){
  platform.editJob=null;window.CameraAssist?.stop();
  stopVoice();platform.interviewEpoch++;
  const result=await api('/auth/logout',{method:'POST'});state.epoch++;clearLocal();resetPlatform();state.csrf=result.csrf_token;
  location.assign('/');
}
function resetPlatform(){
  platform.editJob=null;platform.applicationId=null;platform.applicationJob=null;window.CameraAssist?.stop();window.StarMap?.clearAll();
  if($('#interview-application-note'))$('#interview-application-note').hidden=true;
  stopVoice();platform.interviewEpoch++;platform.tree=null;platform.exam=null;platform.interview=null;platform.skills=[];
  ['#profile-occupation','#profile-resume','#tree-major','#tree-occupation','#tree-jd','#interview-occupation','#interview-jd','#interview-answer','#voice-interim','#review-body','#admin-key'].forEach(s=>{const el=$(s);if(el){if('value'in el)el.value='';else el.textContent='';}});
  ['#tree-scene','#node-selection','#exam-questions','#exam-result','#wrongbook-list','#interview-history','#exam-history','#profile-materials','#profile-reports','#interview-messages','#admin-metrics','#admin-users','#admin-reviews','#admin-jobs','#review-list'].forEach(s=>$(s)?.replaceChildren());
  document.querySelectorAll('#view-tree input[type=checkbox],#view-interview input[type=checkbox]').forEach(el=>el.checked=false);
  $('#tree-workspace').hidden=true;$('#exam-submit').hidden=true;$('#tree-saved').replaceChildren(new Option('选择个人路线',''));
  document.querySelectorAll('dialog[open]').forEach(d=>d.close());
}
let profileLoadEpoch=0,profileWipeEpoch=0;
async function loadProfile(){
  const profileEpoch=++profileLoadEpoch;
  if(!platform.user)return;
  const [p,wrong,history,exams,materials,reports]=await Promise.all([api('/profile'),api('/learning/wrongbook'),api('/interviews'),api('/learning/exams'),api('/profile/materials'),api('/career/reports')]);
  if(profileEpoch!==profileLoadEpoch)return;
  $('#profile-occupation').value=p.occupation;$('#profile-resume').value=p.resume;
  if(!$('#tree-occupation').value)$('#tree-occupation').value=p.occupation;
  if(!$('#interview-occupation').value)$('#interview-occupation').value=p.occupation;
  const materialList=$('#profile-materials');materialList.replaceChildren();
  materials.items.forEach(m=>{const card=node('article','finding');card.append(node('strong','',`${kinds[m.kind]||'材料'} · ${m.chars} 字`));card.append(button('打开材料',async()=>{await refreshMaterials(m.id);await loadMaterial(m.id);show('materials');}));
    materials.analyses.filter(a=>a.material_id===m.id).forEach(a=>{const d=node('details');d.append(node('summary','',a.kind==='risk'?'已保存的风险研判':'已保存的脱敏预览'));if(a.kind==='risk'){d.append(node('p','',`${a.result.level} · ${a.result.score} 分`));a.result.findings.forEach(f=>d.append(node('p','',f.category+'：'+f.advice)));}else d.append(node('pre','text-preview',a.result.redacted_text));card.append(d);});
    card.append(button('删除材料',async()=>{if(!confirm('删除此材料及其分析记录？'))return;await api('/materials/'+m.id,{method:'DELETE'});await refreshMaterials();await loadProfile();}));materialList.append(card);});
  const reportList=$('#profile-reports');reportList.replaceChildren();reports.items.forEach(item=>{const r=item.report,card=node('article','finding');card.append(node('strong','',`${r.requirements.length} 项岗位要求 · ${r.gaps.length} 项待补充`),button('打开职业报告',async()=>{renderCareer(r);show('career');if(r.jd_id){const jd=await api('/materials/'+r.jd_id);inheritCareer(r,jd.text);}}));reportList.append(card);});
  const w=$('#wrongbook-list');w.replaceChildren();
  wrong.items.forEach(q=>{const card=node('article','panel job-card');card.append(node('span','badge amber',`${q.skill} · 错 ${q.mistakes} 次 · 连对 ${q.correct_streak} 次`),node('h3','',q.question));const d=node('details'),s=node('summary','','查看标准答案与解析');d.append(s,node('p','',`答案：${'ABCD'[q.answer]} · ${q.options[q.answer]}`),node('p','',q.explanation));card.append(d);w.append(card);});
  if(!wrong.items.length)empty(w,'暂时没有错题。每次技能考试提交后，会自动收集答错的题目。');
  const h=$('#interview-history');h.replaceChildren();
  history.items.forEach(item=>{const d=node('details','finding'),s=node('summary','',`${item.occupation} · ${Math.floor(item.history.length/2)} 轮 · ${item.ended?'已结束':'可继续'}`);d.append(s);
    item.history.forEach(m=>{d.append(node('p','',(m.role==='user'?'我的回答：':'面试官：')+m.content));if(m.feedback)d.append(node('p','fine-print','反馈：'+m.feedback));});
    if(!item.ended)d.append(button('继续面试',()=>{platform.interview=item;$('#interview-occupation').value=item.occupation;renderConversation(item.history);show('interview');text('#voice-status','已恢复文字对话，可开启语音回答。');}));h.append(d);});
  const e=$('#exam-history');e.replaceChildren();
  exams.items.forEach(item=>{const d=node('details','finding');d.append(node('summary','',`练习 #${item.id} · ${item.result?item.result.score+' 分':'未提交'} · ${item.count} 题`));
    if(item.result){item.result.details.forEach(q=>d.append(node('p','',`${q.correct?'✓':'○'} ${q.question} — ${q.explanation}`)));}
    else d.append(button('继续答题',async()=>{renderExam(await api('/learning/exams/'+item.id));show('exam');}));e.append(d);});
}
async function saveProfile(){signed();const p=await api('/profile',{method:'PUT',data:{occupation:$('#profile-occupation').value.trim(),resume:$('#profile-resume').value.trim()}});$('#profile-resume').value=p.resume;toast('已保存脱敏档案摘要。');}
async function useProfile(){signed();const p=await api('/profile');if(!p.resume)throw Error('请先保存简历摘要。');await addText(p.resume,'resume');$('#tree-occupation').value=p.occupation;$('#interview-occupation').value=p.occupation;show('career');toast('档案摘要已加入当前简历材料，可选择岗位生成职业报告。');}

async function loadTrees(){
  if(!platform.user)return;
  const data=await api('/learning/trees');const select=$('#tree-saved'),old=String(platform.tree?.id||'');
  select.replaceChildren(new Option('选择已保存的路线',''));data.items.forEach(t=>select.append(new Option(t.occupation+' · '+t.tree.nodes.length+' 个技能',String(t.id))));
  platform.savedTrees=data.items;if(old)select.value=old;
  if(!platform.tree&&window.StarMap.mode!=='demo'&&data.items.length)renderTree(data.items[0]);
}
async function generateTree(){
  signed();consentChecked('#tree-consent');const major=$('#tree-major').value.trim(),occupation=$('#tree-occupation').value.trim()||(major?major+'相关职业探索':'');if(!occupation)throw Error('请填写专业或目标职业。');
  text('#tree-state','AI 正在铺设技能路径…原路线保留。');
  try{const result=await api('/learning/tree',{method:'POST',data:{major,occupation,jd:$('#tree-jd').value.trim(),skills:platform.skills,consent:true}});renderTree(result);await loadTrees();toast('已生成并保存 AI 技能树。');}
  catch(error){text('#tree-state',error.message+' 原路线仍保留，可重试。');throw error;}
  if(platform.tree)text('#tree-state','AI 生成路线为学习参考。须通过节点考核才能解锁后续技能。');
}
function renderTree(value){
  platform.tree=value;$('#tree-major').value=value.major||'';$('#tree-occupation').value=value.occupation;$('#tree-jd').value=value.jd;$('#tree-saved').value=String(value.id);window.StarMap.load(value);
}
function selectSkill(id){if(id)window.StarMap.select(id);else window.StarMap.clear();}
function renderExam(exam){
  platform.exam=exam;const root=$('#exam-questions');root.replaceChildren();$('#exam-result').replaceChildren();$('#exam-submit').hidden=false;
  text('#exam-meta',`${exam.questions.length} 道单选题 · ${exam.source}`);
  exam.questions.forEach((q,i)=>{const field=node('fieldset','exam-question');field.append(node('legend','',`${i+1}. [${q.skill}] ${q.question}`));q.options.forEach((option,j)=>{const label=node('label','answer-option'),radio=node('input');radio.type='radio';radio.name='answer-'+i;radio.value=String(j);label.append(radio,node('span','',`${'ABCD'[j]}. ${option}`));field.append(label);});root.append(field);});
}
async function submitExam(){
  signed();if(!platform.exam)throw Error('没有进行中的练习。');
  const answers=platform.exam.questions.map((_,i)=>{const el=$(`input[name="answer-${i}"]:checked`);return el?Number(el.value):-1;});if(answers.includes(-1))throw Error('请完成每一道题。');
  const result=await api('/learning/exams/'+platform.exam.id+'/submit',{method:'POST',data:{answers}});$('#exam-submit').hidden=true;$('#exam-questions').querySelectorAll('input').forEach(el=>el.disabled=true);
  const root=$('#exam-result');root.replaceChildren(node('h2','',`${result.score} 分 · 本次练习反馈`));
  await window.StarMap.applyExam(result);
  if(result.tree_id){root.append(node('p','fine-print',result.unlocked?.length?'节点考核通过，技能已点亮，前置满足的后续技能已解锁。':'本次未新增技能完成记录。节点考核须满足至少3题、正确率80%与前置要求。'),button('返回职业成长星图',()=>show('tree')));}
  result.details.forEach((q,i)=>{const card=node('article','answer-feedback'+(q.correct?'':' wrong'));card.append(node('strong','',`${i+1}. ${q.correct?'回答正确':'已加入错题本'}`),node('p','',`你的选择：${'ABCD'[q.chosen]} · 参考答案：${'ABCD'[q.answer]}`),node('p','',q.explanation));root.append(card);});
  root.append(node('p','fine-print','AI 生成的题目和解析可能有误，请结合课程资料核对。本分数仅代表本次练习。'));toast('考试已提交，答错的题目已自动收集。');
}
async function practice(){signed();renderExam(await api('/learning/practice',{method:'POST'}));show('exam');}

async function loadJobs(){
  const [data,mine]=await Promise.all([api('/jobs'),api('/jobs/mine')]);platform.jobs=data.items;renderJobs();
  const root=$('#my-job-list');root.replaceChildren();
  mine.items.forEach(j=>{const card=node('div','finding');card.append(node('strong','',j.company+' · '+j.title),node('span','badge '+(j.status==='approved'?'green':'amber'),{pending:'待审核',approved:'已通过',rejected:'未通过'}[j.status]),node('p','',j.description));if(j.review_note)card.append(node('p','fine-print','审核意见：'+j.review_note));card.append(button('修改并重新提交',()=>{platform.editJob=j.id;$('#job-title').value=j.title;$('#job-company').value=j.company;$('#job-description').value=j.description;const panel=$('#job-title').closest('details');panel.open=true;panel.scrollIntoView({behavior:'smooth'});toast('修改后点击提交审核。');}));root.append(card);});
  if(!mine.items.length)empty(root,'暂无提交记录。');
}
function renderJobs(){
  const root=$('#job-list'),query=$('#job-search').value.trim().toLowerCase();root.replaceChildren();
  const jobs=platform.jobs.filter(j=>[j.title,j.company,j.description].join(' ').toLowerCase().includes(query));
  jobs.forEach(j=>{const card=node('article','panel job-card');card.append(node('span','badge '+(j.recommended?'green':'neutral'),j.recommended?'管理员推荐 · 待自行核验':'用户分享 · 未核验'),node('h3','',j.title),node('strong','',j.company),node('p','job-description',j.description),node('p','fine-print',`${j.rating===null?'暂无评分':j.rating+' / 5 分'} · ${j.review_count} 条点评`));
    const row=node('div','button-row');row.append(button('用于职业规划',async()=>{await addText(j.description,'jd');$('#tree-occupation').value=j.title;$('#tree-jd').value=j.description;$('#interview-occupation').value=j.title;$('#interview-jd').value=j.description.slice(0,6000);show('career');toast('岗位已加入 JD 材料，可选择简历生成报告。');}),button('查看 / 写点评',()=>openReviews(j)));row.prepend(button('一键面试',()=>window.RecruitmentUI.open(j),'primary'));card.append(row);root.append(card);});
  if(!jobs.length)empty(root,'暂无匹配岗位。管理员可以添加推荐岗位，登录用户也可手动分享。');
}
async function publishJob(){
  signed();const editing=platform.editJob;
  const result=await api(editing?'/jobs/'+editing:'/jobs',{method:editing?'PUT':'POST',data:{title:$('#job-title').value.trim(),company:$('#job-company').value.trim(),description:$('#job-description').value.trim(),recommended:platform.user.role==='admin'&&$('#job-recommended').checked}});
  platform.editJob=null;['#job-title','#job-company','#job-description'].forEach(s=>$(s).value='');await loadJobs();toast(result.status==='pending'?'岗位已提交，等待管理员审核。':'岗位已发布。');
}
async function openReviews(job){
  platform.reviewJob=job;text('#review-title',job.company+' · '+job.title);$('#review-body').value='';
  const data=await api('/jobs/'+job.id+'/reviews'),root=$('#review-list');root.replaceChildren();
  data.items.forEach(r=>{const card=node('article','finding');card.append(node('span','badge neutral',r.rating+' / 5 分 · 用户体验'),node('p','',r.body));root.append(card);});
  if(!data.items.length)empty(root,'还没有公开点评。');if(!$('#review-dialog').open)$('#review-dialog').showModal();
}
async function saveReview(){signed();if(!platform.reviewJob)return;await api('/jobs/'+platform.reviewJob.id+'/reviews',{method:'POST',data:{rating:Number($('#review-rating').value),body:$('#review-body').value.trim()}});await openReviews(platform.reviewJob);await loadJobs();toast('点评已更新，其他用户可以查看。');}

function stopVoice(){
  platform.voiceEpoch++;clearTimeout(platform.voiceTimer);clearTimeout(platform.silenceTimer);platform.listening=false;
  if(platform.recognition){platform.recognition.onend=null;platform.recognition.abort();platform.recognition=null;}
  window.speechSynthesis?.cancel();$('#voice-orb')?.classList.remove('listening');
}
function speakQuestion(question){
  stopVoice();const epoch=platform.voiceEpoch;
  if(!$('#voice-speak').checked||!window.speechSynthesis){text('#voice-status','问题已显示，可以输入或语音回答。');return;}
  const speech=new SpeechSynthesisUtterance(question);speech.lang='zh-CN';speech.rate=1;
  const chinese=speechSynthesis.getVoices().find(v=>v.lang.toLowerCase().startsWith('zh'));if(chinese)speech.voice=chinese;
  text('#voice-status','面试官正在提问…可随时打断朗读。');
  speech.onend=()=>{if(epoch!==platform.voiceEpoch)return;text('#voice-status','轮到你回答了。');if($('#voice-auto').checked&&$('#voice-consent').checked&&state.view==='interview')listen();};
  speech.onerror=()=>{if(epoch===platform.voiceEpoch)text('#voice-status','语音朗读未完成，问题已保留在文字对话中。');};speechSynthesis.speak(speech);
}
function listen(){
  signed();if(!platform.interview)throw Error('请先开始或恢复面试。');if(!$('#voice-consent').checked)throw Error('请先同意浏览器语音识别说明。');
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Recognition){text('#voice-status','当前浏览器未提供语音识别，请使用支持的 Edge / Chrome，或输入文字回答。');return;}
  stopVoice();const epoch=platform.voiceEpoch,recognition=new Recognition();platform.recognition=recognition;
  recognition.lang='zh-CN';recognition.continuous=true;recognition.interimResults=true;
  let finalText=$('#interview-answer').value,hadError=false;
  recognition.onstart=()=>{if(epoch!==platform.voiceEpoch)return;platform.listening=true;$('#voice-orb').classList.add('listening');text('#voice-status','正在听你回答…停顿后可点击发送。');};
  recognition.onresult=event=>{if(epoch!==platform.voiceEpoch)return;let interim='';for(let i=event.resultIndex;i<event.results.length;i++){if(event.results[i].isFinal)finalText+=event.results[i][0].transcript;else interim+=event.results[i][0].transcript;}$('#interview-answer').value=finalText.slice(0,2500);text('#voice-interim',interim);clearTimeout(platform.silenceTimer);if($('#voice-auto').checked)platform.silenceTimer=setTimeout(()=>recognition.stop(),2200);};
  recognition.onerror=e=>{hadError=true;const messages={'not-allowed':'麦克风或语音服务未获授权，请检查浏览器设置或输入文字。','network':'浏览器语音识别服务连接失败，请改用文字回答。','no-speech':'没有检测到语音，可重新开始。','audio-capture':'未找到可用麦克风。'};text('#voice-status',messages[e.error]||'语音识别未完成，已识别文字仍可编辑。');};
  recognition.onend=()=>{if(epoch!==platform.voiceEpoch)return;platform.listening=false;platform.recognition=null;clearTimeout(platform.voiceTimer);clearTimeout(platform.silenceTimer);$('#voice-orb').classList.remove('listening');text('#voice-interim','');if(!hadError)text('#voice-status','转写已完成，可检查并发送。');if(!hadError&&$('#voice-auto').checked&&finalText.trim()&&state.view==='interview')platformRun(sendAnswer);};
  try{recognition.start();platform.voiceTimer=setTimeout(()=>recognition.stop(),180000);}catch{stopVoice();text('#voice-status','无法启动语音识别，请使用文字回答或检查浏览器权限。');}
}
function renderConversation(history){
  const root=$('#interview-messages');root.replaceChildren();history.forEach(m=>{if(m.feedback)root.append(node('div','bubble feedback-note','表达反馈：'+m.feedback));const bubble=node('div','bubble '+(m.role==='user'?'user':''));bubble.append(node('small','',m.role==='user'?'我的回答':'AI 面试官'+(m.focus?' · '+m.focus:'')),document.createTextNode(m.content));root.append(bubble);});
  root.scrollTop=root.scrollHeight;text('#interview-round',`${Math.floor(history.length/2)} / 12 轮`);
}
async function startInterview(){
  signed();consentChecked('#interview-consent');stopVoice();platform.interviewEpoch++;const epoch=platform.interviewEpoch;
  const result=await api('/interviews',{method:'POST',data:{occupation:$('#interview-occupation').value.trim(),jd:$('#interview-jd').value.trim(),consent:true,application_id:platform.applicationId}});if(epoch!==platform.interviewEpoch||state.view!=='interview')return;
  platform.interview=result;$('#interview-answer').value='';renderConversation(result.history);speakQuestion(result.question);
}
async function sendAnswer(){
  signed();if(!platform.interview)throw Error('请先开始面试。');consentChecked('#interview-consent');
  const answer=$('#interview-answer').value.trim();if(!answer)throw Error('请先输入或录入回答。');
  stopVoice();const epoch=platform.interviewEpoch;text('#voice-status','面试官正在结合你的回答准备追问…');
  const result=await api('/interviews/'+platform.interview.id+'/turn',{method:'POST',data:{answer,consent:true}});if(epoch!==platform.interviewEpoch||state.view!=='interview')return;
  platform.interview=result;$('#interview-answer').value='';renderConversation(result.history);speakQuestion(result.question);
}
async function endInterview(){stopVoice();window.CameraAssist?.stop();platform.interviewEpoch++;if(platform.interview){await api('/interviews/'+platform.interview.id+'/end',{method:'POST'});platform.interview=null;}text('#voice-status','本次面试已结束，文字记录可在个人中心查看。');}

function inheritCareer(result,jd){
  platform.skills=result.gaps.map(g=>g.skill);const occupation=jd.split('\n').find(x=>/^\s*(?:目标岗位|岗位|职业|职位|求职意向)[：:]/.test(x))?.replace(/^.*?[：:]/,'').trim()||$('#tree-occupation').value.trim()||$('#profile-occupation').value.trim()||'目标岗位';
  $('#tree-occupation').value=occupation.slice(0,100);$('#tree-jd').value=jd.slice(0,8000);$('#interview-occupation').value=occupation.slice(0,100);$('#interview-jd').value=jd.slice(0,6000);
  text('#career-tree-note',`已带入岗位要求和 ${result.gaps.length} 项待补充技能。下一步生成技能树，再用节点考试检验学习。`);
}

const platformHandlers={logout,'save-profile':saveProfile,'use-profile':useProfile,
  'refresh-profile':async()=>{signed();await loadProfile();},'generate-tree':generateTree,'load-trees':loadTrees,
  'submit-exam':submitExam,practice,'load-jobs':loadJobs,'publish-job':publishJob,'save-review':saveReview,
  'detach-application':()=>{platform.applicationId=null;platform.applicationJob=null;$('#interview-application-note').hidden=true;toast('已切换为个人练习；已有投递可在我的投递中撤回。');},'my-applications':()=>window.RecruitmentUI.mine(),'start-interview':startInterview,'send-answer':sendAnswer,'end-interview':endInterview,listen,interrupt:()=>{stopVoice();text('#voice-status','已停止听写与朗读，文字仍可编辑。');},
  'erase-learning':async()=>{signed();if(!confirm('删除当前账号的头像、昵称、简介、材料、档案、职业报告、技能树、考试、错题与面试记录？此操作不可恢复，已发布岗位、点评与站内邮件保留；已投递的简历授权将撤回。'))return;stopVoice();platform.interviewEpoch++;await api('/profile/data',{method:'DELETE'});resetPlatform();window.dispatchEvent(new Event('account-data-erased'));await loadAccount();await loadProfile();toast('个人档案和学习记录已删除。');}
};

async function initPlatform(){
  const response=await fetch('/static/platform.html',{cache:'no-store',credentials:'same-origin'});if(!response.ok)throw Error('扩展页面加载失败，请刷新。');
  // 固定同源静态模板，无用户内容插值。后续数据仅用textContent。
  const template=document.createElement('template');template.innerHTML=await response.text();$('#main').insertBefore(template.content,$('.page-footer'));
  window.dispatchEvent(new Event('platform-ready'));
  const nav=$('.sidebar nav');
  const entries=[['tree','职业技能树','tree'],['exam','技能考试','check'],['interview','AI 面试','spark'],['jobs','岗位推荐','file'],['profile','个人中心','grid']];
  entries.forEach(([view,label,image])=>{const b=node('button','nav-item');b.dataset.view=view;b.append(icon(image),document.createTextNode(label));if(view==='admin'){b.id='nav-admin';b.hidden=true;}nav.append(b);});
  const account=node('button','button secondary small auth-top','个人中心');account.id='account-top';account.dataset.go='profile';$('.top-actions').prepend(account);
  const next=node('article','panel spaced');next.append(node('span','eyebrow','FROM PLAN TO PRACTICE'),node('h2','','把计划展开成技能树'),node('p','fine-print','先识别能力差距，再沿着技能依赖完成实践，用节点考试发现仍需巩固的部分。'));
  const note=node('p','fine-print');note.id='career-tree-note';next.append(note);const row=node('div','button-row');row.append(button('进入 AI 职业技能树',()=>show('tree'),'primary'),button('进入 AI 面试',()=>show('interview')));next.append(row);$('#view-career').append(next);
  document.addEventListener('click',event=>{const b=event.target.closest('[data-platform]');if(!b||!platformHandlers[b.dataset.platform])return;
    if(['interrupt','end-interview'].includes(b.dataset.platform)){Promise.resolve(platformHandlers[b.dataset.platform]()).catch(e=>toast(e.message,true));return;}
    platformRun(platformHandlers[b.dataset.platform],b);});
  window.StarMap.init();
  platform.canvas=window.TreeCanvas.attach($('#tree-scroll'),{onSelect:selectSkill,onClear:()=>selectSkill(null),onNodeDragMove:window.StarMap.dragNode,onNodeDragEnd:window.StarMap.endNodeDrag,onZoom:window.StarMap.wheelZoom});
  $('#tree-saved').addEventListener('change',()=>{const tree=platform.savedTrees?.find(t=>String(t.id)===$('#tree-saved').value);if(tree)renderTree(tree);});
  $('#job-search').addEventListener('input',renderJobs);
  $('#interview-answer').addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();platformRun(sendAnswer);}});
  $('#voice-consent').addEventListener('change',()=>{if(!$('#voice-consent').checked)stopVoice();});
  $('#interview-consent').addEventListener('change',()=>{if(!$('#interview-consent').checked){stopVoice();platform.interviewEpoch++;}});
  window.addEventListener('career-report',event=>inheritCareer(event.detail.result,event.detail.jd));
  window.addEventListener('account-data-erased',()=>{profileLoadEpoch++;profileWipeEpoch++;});
  window.addEventListener('platform-clear',()=>{stopVoice();platform.interviewEpoch++;platform.interview=null;platform.skills=[];$('#tree-jd').value='';$('#interview-jd').value='';$('#interview-answer').value='';$('#interview-messages').replaceChildren();text('#career-tree-note','当前会话已清空，已保存学习记录可从个人中心重新打开。');});
  window.addEventListener('viewchange',event=>{if(event.detail!=='tree')platform.canvas?.cancel();if(event.detail!=='interview'){stopVoice();platform.interviewEpoch++;}const loaders={profile:async()=>{await loadAccount();await loadProfile();},tree:loadTrees,jobs:loadJobs};const load=loaders[event.detail];if(load&&!(event.detail==='profile'&&window.careerProfileFilling))load().catch(e=>toast(e.message,true));});
  window.addEventListener('pagehide',stopVoice);document.addEventListener('visibilitychange',()=>{if(document.hidden)stopVoice();});
  // 原有会话启动完成后获取账号状态，不重复调用需要模型检查的bootstrap。
  if(!state.csrf)await new Promise(resolve=>{const timer=setInterval(()=>{if(state.csrf){clearInterval(timer);resolve();}},100);setTimeout(()=>{clearInterval(timer);resolve();},8000);});
  await loadAccount();
  window.careerPlatformReady = true;
  window.dispatchEvent(new Event('platform-loaded'));
}
initPlatform().catch(e=>toast(e.message,true));

window.CareerProfile={async fill(fields){const wipeEpoch=profileWipeEpoch;window.careerProfileFilling=true;try{show('profile');await loadAccount();await loadProfile();if(wipeEpoch!==profileWipeEpoch)return;for(const [key,value] of Object.entries(fields)){if(['occupation','resume'].includes(key)&&typeof value==='string')$('#profile-'+key).value=value;}}finally{window.careerProfileFilling=false;}}};
