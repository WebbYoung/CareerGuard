/* 固定引导内容与纯视口布局，无账号资料或业务执行。 */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.CareerGuideCore=api;})(typeof window==='undefined'?this:window,function(){
  'use strict';
  const STEPS=[
    {view:'overview',target:'#view-overview [data-go="materials"]',title:'你好，我是小安',body:'我会陪你认识职安。点击这里，从一份求职材料开始安全体检。准备好后点“我明白了”。'},
    {view:'materials',target:'#dropzone',title:'先读懂你的材料',body:'在这里上传简历、招聘截图或 PDF，也可以粘贴文字。识别后请核对低置信度内容。'},
    {view:'risk',target:'.risk-score-panel',title:'看清招聘风险',body:'选择招聘材料后查看风险线索与原文依据。分数反映话术风险，不是诈骗概率。'},
    {view:'privacy',target:'#privacy-select',title:'投递前，守住隐私',body:'选择简历检查敏感字段，对比脱敏前后，确认无误再导出投递版本。'},
    {view:'career',target:'#jd-text',title:'把岗位要求变成计划',body:'选择简历并填写岗位要求，生成能力差距、四周学习计划与有依据的建议。'},
    {view:'tree',target:'#tree-config summary',title:'点亮你的职业星图',body:'填写专业与目标，由 AI 生成共享技能路径。拖拽、缩放或点击节点，查看学习任务。'},
    {view:'exam',target:'#view-exam [data-go="tree"]',title:'用考核检验掌握程度',body:'先从技能树选择节点出题。完成考核解锁后续技能，错题会进入个人错题本。'},
    {view:'interview',target:'#interview-occupation',title:'练习，把经历说清楚',body:'填写岗位后与 AI 面试官逐轮对话。语音与镜头由你选择开启，也能直接文字回答。'},
    {view:'jobs',target:'#job-search',title:'发现适合自己的机会',body:'在这里搜索推荐岗位、查看点评。你也能提交岗位信息，审核通过后公开展示。'},
    {view:'profile',target:'#profile-occupation',title:'最后，设定你的目标',body:'在个人中心设置目标职业与简历，查看考试、面试和错题记录。以后点右侧的我，可以重看引导。'},
  ];
  const clamp=(n,a,b)=>Math.max(a,Math.min(n,b));
  function place(rect,{width,height},{bubbleHeight=218}={}){
    const margin=12,small=width<700,rw=small?96:150,rh=small?132:196,gap=small?8:14;
    const bw=Math.min(320,Math.max(120,width-margin*2-rw-gap)),bh=Math.min(bubbleHeight,height-margin*2),gw=bw+gap+rw,gh=Math.max(rh,bh);
    const left=clamp(rect.left,margin,width-margin),right=clamp(rect.right,margin,width-margin),top=clamp(rect.top,margin,height-margin),bottom=clamp(rect.bottom,margin,height-margin);
    const aim={x:(left+right)/2,y:(top+bottom)/2};
    const candidates=[{x:aim.x-gw/2,y:bottom+22},{x:aim.x-gw/2,y:top-gh-22},{x:right+22,y:aim.y-gh/2},{x:left-gw-22,y:aim.y-gh/2}];
    const fit=candidates.find(c=>c.x>=margin&&c.x+gw<=width-margin&&c.y>=margin&&c.y+gh<=height-margin);
    const base=fit||candidates.find(c=>c.y>=margin&&c.y+gh<=height-margin)||candidates[0];
    const x=clamp(base.x,margin,Math.max(margin,width-gw-margin)),y=clamp(base.y,margin,Math.max(margin,height-gh-margin));
    return {robot:{x:x+bw+gap,y:y+gh-rh,width:rw,height:rh},bubble:{x,y,width:bw,height:bh},aim,
      highlight:{x:left-5,y:top-5,width:Math.max(10,right-left+10),height:Math.max(10,bottom-top+10)}};
  }
  function createGate(){
    let version=0,active=false;
    return {get version(){return version;},get active(){return active;},begin(){return ++version;},
      enter(token){if(active||token!==version)return false;active=true;version++;return true;},
      close(){active=false;version++;}};
  }
  return {STEPS,place,createGate};
});
