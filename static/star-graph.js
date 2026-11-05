/* 共享图算法与匿名演示课程。职业数由数据决定，九方向仅存在于演示课程。 */
window.StarGraph=(()=>{
  const stages=['公共基础技能','职业方向','专业技能','项目实战'];
  function required(graph,career){const map=new Map(graph.nodes.map(n=>[n.id,n])),out=new Set();function visit(id){if(out.has(id)||!map.has(id))return;out.add(id);map.get(id).prerequisites.forEach(visit);}career.core_skill_ids.forEach(visit);return out;}
  function decorate(graph,progress){const done=new Set(progress),g=JSON.parse(JSON.stringify(graph));g.nodes.forEach(n=>{n.status=done.has(n.id)?'completed':n.prerequisites.every(id=>done.has(id))?'available':'locked';n.shared_count=0;});g.careers.forEach(c=>{const ids=required(g,c);c.required_skill_ids=[...ids];c.mastered=[...ids].filter(id=>done.has(id));c.missing=[...ids].filter(id=>!done.has(id));c.required_count=ids.size;c.completed_count=c.mastered.length;c.coverage=ids.size?Math.round(c.completed_count/ids.size*1000)/10:0;g.nodes.forEach(n=>{if(ids.has(n.id))n.shared_count++;});});return g;}
  function layout(graph,focus=null){
    const cx=950,cy=850,points=new Map(),career=graph.careers.find(c=>c.id===focus);
    const visible=career?required(graph,career):new Set(graph.nodes.filter(n=>n.stage===stages[0]).slice(0,6).map(n=>n.id));
    stages.forEach((stage,layer)=>{const nodes=graph.nodes.filter(n=>visible.has(n.id)&&(n.stage||stages[2])===stage);nodes.forEach((n,i)=>{const angle=-Math.PI/2+i*2*Math.PI/Math.max(nodes.length,1)+(career?layer*.85:0),radius=career?[250,350,470,580][layer]:260;points.set(n.id,{x:cx+Math.cos(angle)*radius,y:cy+Math.sin(angle)*radius,kind:'skill'});});});
    graph.careers.filter(c=>!career||c.id===focus).forEach(c=>{const i=graph.careers.findIndex(x=>x.id===c.id),angle=-Math.PI/2+i*2*Math.PI/graph.careers.length;points.set(c.id,{x:cx+Math.cos(angle)*640,y:cy+Math.sin(angle)*640,kind:'career'});});
    points.set('student',{x:cx,y:cy,kind:'student'});return {width:1900,height:1700,cx,cy,points,visible,focus:career};
  }
  // 以屏幕尺寸校验间隔，不因节点标签的逆缩放而挤到一起。
  function overlaps(a,b,zoom){return Math.abs(a.x-b.x)*zoom<144&&Math.abs(a.y-b.y)*zoom<138;}
  function freePosition(point,others,zoom){
    const marginX=85/zoom,marginY=45/zoom;
    for(let k=0;k<1000;k++){
      const angle=k*2.399963229728653,radius=19*Math.sqrt(k)/zoom;
      const p={...point,x:Math.max(marginX,point.x+Math.cos(angle)*radius),y:Math.max(marginY,point.y+Math.sin(angle)*radius)};
      if(others.every(other=>!overlaps(p,other,zoom)))return p;
    }
    return {...point,x:Math.max(marginX,...others.map(p=>p.x+160/zoom)),y:Math.max(marginY,point.y)};
  }
  function separate(layout,zoom,overrides=new Map(),shown=null){
    const output={...layout,points:new Map([...layout.points].map(([id,p])=>[id,{...p}]))},placed=[];
    const entries=[...output.points].filter(([id])=>!shown||shown.has(id)).sort(([a,x],[b,y])=>Number(overrides.has(b))-Number(overrides.has(a))||({student:0,career:1,skill:2}[x.kind]-{student:0,career:1,skill:2}[y.kind]));
    for(const [id,original] of entries){const candidate={...original,...overrides.get(id)},p=freePosition(candidate,placed,zoom);output.points.set(id,p);placed.push(p);output.width=Math.max(output.width,p.x+90/zoom);output.height=Math.max(output.height,p.y+100/zoom);}
    return output;
  }
  function demo(){
    const nodes=[];const add=(id,name,stage,prerequisites,description,task)=>nodes.push({id,name,stage,prerequisites,description,task,resources:['课程资料：待补充','实践文档：待补充']});
    add('cs','计算机基础',stages[0],[],'理解计算机组成、操作系统与数据表示。','制作一次程序从输入到输出的执行流程图。');
    add('code','程序设计',stages[0],['cs'],'掌握变量、控制流程、函数和数据结构。','交付一个带异常处理的命令行工具。');
    add('git','Git 协作',stages[0],['cs'],'理解版本、分支、合并和协作评审。','用分支开发并提交一次带测试记录的合并。');
    add('net','网络基础',stages[0],['cs'],'理解TCP/IP、DNS、HTTP与请求响应。','解释一次请求的路径并绘制协议交互图。');
    add('db','数据与 SQL',stages[0],['code'],'理解关系数据、SQL查询、索引与事务。','交付有主外键约束的数据库与查询脚本。');
    add('http','HTTP 与接口',stages[2],['net','code'],'设计可验证的接口输入、状态码和错误响应。','编写接口契约与错误处理测试。');
    add('linux','Linux 运维',stages[2],['net','git'],'管理进程、权限、日志与服务运行环境。','交付服务部署清单与排错记录。');
    add('python','Python 数据工具',stages[2],['code','db'],'使用Python进行结构化数据处理与验证。','交付包含校验与单元测试的数据处理程序。');
    const specs=[
      ['frontend','前端开发','构建清晰、可访问的交互界面。','Web 交互工程',['http','git'],'实现响应式界面、状态管理和可访问交互。','交付具有加载、空态、错误态的Web应用。'],
      ['backend','后端开发','设计稳定的业务接口与数据服务。','服务端工程',['http','db'],'实现鉴权、事务、分页和异常处理。','交付带接口文档与测试的服务。'],
      ['data','数据分析','把数据转化为可解释的业务发现。','分析与可视化',['python','db'],'清洗数据、建立指标并解释分析限制。','交付可复现的数据分析与图表报告。'],
      ['ai','AI 应用开发','将模型能力接入可靠的应用流程。','模型应用工程',['python','http'],'构建检索、结构化输出与效果评估。','交付带证据引用与失败降级的AI助手。'],
      ['security','网络安全','分析风险并建设可验证的安全防护。','安全防护工程',['linux','http'],'完成输入校验、权限设计与安全测试。','交付受控环境安全测试和修复验证报告。'],
      ['cloud','云计算运维','构建可观测、可恢复的服务环境。','容器与服务运维',['linux','http'],'完成容器化、监控告警和恢复演练。','交付部署配置、监控和回滚记录。'],
      ['qa','软件测试','用系统化验证提高交付质量。','自动化测试工程',['python','http'],'设计边界用例与自动化回归流程。','交付覆盖正常、边界与异常路径的测试套件。'],
      ['mobile','移动应用','打造适应设备与触控的移动体验。','移动端工程',['http','git'],'实现移动页面、离线状态与生命周期管理。','交付可在窄屏操作的移动应用。'],
      ['iot','物联网开发','连接设备、数据与业务服务。','设备与协议工程',['linux','code'],'处理设备消息、连接重试和数据上报。','交付设备仿真、协议说明与故障恢复演示。']];
    const careers=specs.map(([id,name,description,skill,deps,content,task])=>{
      const direction='dir_'+id,professional='skill_'+id,project='proj_'+id;
      add(direction,name+'方向',stages[1],['code','git'],'了解'+name+'的工作任务、交付方式与能力边界。','完成一份岗位能力与学习目标清单。');
      add(professional,skill,stages[2],[direction,...deps],content,task);
      add(project,'项目：'+name,stages[3],[professional,'git'],'综合运用已学技能，形成可演示、可复现的成果。',task+'包含README、测试记录与成果说明。');
      return {id:'career_'+id,name,description,core_skill_ids:[project],projects:[task]};
    });
    return {learner_label:'计算机专业学习者（演示）',title:'计算机专业 · 职业成长星图',summary:'从共享基础出发，在交汇的技能路径中探索九大职业。',nodes,careers};
  }
  return {stages,required,decorate,layout,demo,overlaps,freePosition,separate};
})();
