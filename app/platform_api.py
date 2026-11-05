"""账号、运营、职业学习 API。SQL参数化、账号归属检查与服务端判分。"""
import hashlib
import json
import random
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, ValidationError
from . import config
from .api import Input, authorize, payload, compute
from .database import connect, encode, password_hash, password_ok, cipher, event, ensure_superuser
from .store import store
from .services import growth, llm, starmap
from .services.onboarding import GUIDE_ID

router=APIRouter(prefix='/api')
failures=defaultdict(deque)


class Credentials(Input):
    username: str = Field(pattern=r'^[A-Za-z0-9_\-]{4,32}$')
    password: str = Field(min_length=1,max_length=128)


def public_user(row):
    return {k:row[k] for k in ('id','username','role','disabled','created')}


def current(request, admin=False):
    sid,_=authorize(request)
    user=identity(request,admin)
    store.bind(sid,user['id'])
    return user


def identity(request,admin=False):
    """账号身份与临时材料缓存分开，服务器Session可跨缓存重建继续使用。"""
    digest=hashlib.sha256(request.cookies.get('cg_auth','').encode()).hexdigest()
    with connect() as db:
        row=db.execute('SELECT u.* FROM users u JOIN auth_sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.disabled=0',(digest,int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401,'请先登录账号。')
    if admin and row['role']!='admin':
        raise HTTPException(403,'仅管理员可操作。')
    with connect() as db:
        db.execute('UPDATE auth_sessions SET expires=? WHERE token=?',(int(time.time())+604800,digest))
    return dict(row)


def rotate(request,response,uid=None):
    """身份切换清除旧匿名材料，轮换Cookie和CSRF，避免跨账号复用。"""
    old=request.cookies.get('cg_session')
    with store.lock:
        if old in store.sessions:
            store.sessions[old].generation+=1
            del store.sessions[old]
    sid,session=store.bootstrap(None)
    if uid:store.bind(sid,uid)
    response.set_cookie('cg_session',sid,httponly=True,samesite='strict',path='/')
    with connect() as db:
        token=request.cookies.get('cg_auth','')
        db.execute('DELETE FROM auth_sessions WHERE token=? OR expires<?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time())))
        if uid:
            token=secrets.token_urlsafe(40)
            db.execute('INSERT INTO auth_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,int(time.time())+604800))
            response.set_cookie('cg_auth',token,httponly=True,samesite='strict',path='/')
        else:
            response.delete_cookie('cg_auth',path='/')
    return session.csrf


@router.get('/auth/me')
async def me(request:Request):
    authorize(request)
    try:
        user=public_user(current(request))
    except HTTPException as exc:
        if exc.status_code!=401: raise
        user=None
    with connect() as db:
        setup=db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0
    return {'user':user,'setup_required':setup}


@router.post('/auth/register')
async def register(request:Request,response:Response):
    authorize(request)
    ensure_superuser()
    data=await payload(request,Credentials)
    if len(data.password)<10 or len(set(data.password))<5:
        raise HTTPException(422,'密码过于简单，请使用至少10位且包含多种字符的密码。')
    hashed=await compute(password_hash,data.password)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        role='user'
        try:
            uid=db.execute('INSERT INTO users(username,password,role) VALUES (?,?,?)',(data.username,hashed,role)).lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409,'账号已存在。') from None
        db.execute('INSERT INTO user_guides(user_id,guide_id) VALUES (?,?)',(uid,GUIDE_ID))
        event(db,uid,'register')
        user=public_user(db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    csrf=rotate(request,response,uid)
    return {'user':user,'csrf_token':csrf}


@router.post('/auth/login')
async def login(request:Request,response:Response):
    authorize(request)
    ensure_superuser()
    data=await payload(request,Credentials)
    key=request.client.host if request.client else 'local'
    queue=failures[key]
    while queue and queue[0]<time.monotonic()-60: queue.popleft()
    if len(queue)>=10: raise HTTPException(429,'登录尝试过多，请一分钟后重试。')
    with connect() as db:
        row=db.execute('SELECT * FROM users WHERE username=?',(data.username,)).fetchone()
    # 不存在账号也执行相同成本的散列，减小账号枚举的时序差异。
    valid=await compute(password_ok,data.password,row['password'] if row else password_hash('unused-password-value','0'*32))
    if not row or not valid or row['disabled']:
        queue.append(time.monotonic())
        raise HTTPException(401,'账号、密码不正确或账号已停用。')
    csrf=rotate(request,response,row['id'])
    with connect() as db: event(db,row['id'],'login')
    return {'user':public_user(row),'csrf_token':csrf}


@router.get('/auth/session')
async def auth_session(request:Request,response:Response):
    sid,session=store.bootstrap(request.cookies.get('cg_session'))
    response.set_cookie('cg_session',sid,httponly=True,samesite='strict',path='/')
    return {'csrf_token':session.csrf}


@router.get('/demo')
async def fixed_demo(request:Request):
    try:identity(request)
    except HTTPException:pass
    else:raise HTTPException(403,'演示仅供访客使用，请进入求职工作台。')
    from .services.risk import assess_risk
    from .services.career import build_report
    from .services.pii import redact
    recruitment='【固定合成演示】零门槛高薪日结，入职先交押金与培训费，使用个人账户代收转账。'
    resume='【固定合成简历】技能：Python、SQL、Git。项目：完成数据清洗与查询报表。邮箱：demo@example.invalid'
    jd='【固定合成岗位】Python 后端开发，要求 Python、SQL、Git、FastAPI、Docker、自动化测试。'
    return {'mode':'fixed_demo','recruitment':recruitment,'risk':assess_risk(recruitment),
            'redacted':redact(resume),'report':build_report(redact(resume),jd),
            'notice':'固定合成数据与本地规则演示，不调用AI、不提供上传或保存。'}


@router.post('/auth/logout')
async def logout(request:Request,response:Response):
    authorize(request)
    return {'csrf_token':rotate(request,response)}


class Profile(Input):
    occupation: str = Field(max_length=100)
    resume: str = Field(max_length=12000)


@router.get('/profile')
async def profile(request:Request):
    user=current(request)
    with connect() as db:
        row=db.execute('SELECT occupation,resume FROM profiles WHERE user_id=?',(user['id'],)).fetchone()
    return dict(row) if row else {'occupation':'','resume':''}


@router.put('/profile')
async def save_profile(request:Request):
    user=current(request)
    data=await payload(request,Profile)
    occupation=growth.validate_input(data.occupation)
    resume=growth.validate_input(data.resume)
    with connect() as db:
        db.execute('INSERT INTO profiles VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET occupation=excluded.occupation,resume=excluded.resume',(user['id'],occupation,resume))
        event(db,user['id'],'profile_save')
    return {'occupation':occupation,'resume':resume}


class Job(Input):
    title: str = Field(min_length=1,max_length=100)
    company: str = Field(min_length=1,max_length=100)
    description: str = Field(min_length=5,max_length=8000)
    recommended: bool = False


@router.get('/jobs')
async def jobs(request:Request):
    authorize(request)
    with connect() as db:
        rows=db.execute('''SELECT j.*,u.username AS publisher,COUNT(r.id) AS review_count,ROUND(AVG(r.rating),1) AS rating
         FROM jobs j JOIN users u ON u.id=j.owner_id LEFT JOIN reviews r ON r.job_id=j.id AND r.hidden=0
         WHERE j.active=1 AND j.status='approved' GROUP BY j.id ORDER BY j.recommended DESC,j.id DESC LIMIT 200''').fetchall()
    return {'items':[dict(r) for r in rows]}


@router.post('/jobs')
async def add_job(request:Request):
    user=current(request)
    data=await payload(request,Job)
    if data.recommended and user['role']!='admin': raise HTTPException(403,'推荐岗位仅由管理员发布。')
    fields=[growth.validate_input(x) for x in (data.title,data.company,data.description)]
    with connect() as db:
        status='approved' if user['role']=='admin' else 'pending'
        jid=db.execute('INSERT INTO jobs(owner_id,title,company,description,recommended,status) VALUES (?,?,?,?,?,?)',(user['id'],*fields,int(data.recommended),status)).lastrowid
        event(db,user['id'],'job_publish' if status=='approved' else 'job_submit')
    return {'id':jid,'recommended':data.recommended,'status':status}


@router.get('/jobs/mine')
async def my_jobs(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT * FROM jobs WHERE owner_id=? AND active=1 ORDER BY id DESC LIMIT 200',(user['id'],)).fetchall()
    return {'items':[dict(r) for r in rows]}


@router.put('/jobs/{jid}')
async def edit_job(jid:int,request:Request):
    user=current(request)
    data=await payload(request,Job)
    if data.recommended and user['role']!='admin':raise HTTPException(403,'推荐岗位仅由管理员发布。')
    fields=[growth.validate_input(x) for x in (data.title,data.company,data.description)]
    with connect() as db:
        job=db.execute('SELECT * FROM jobs WHERE id=? AND active=1',(jid,)).fetchone()
        if not job:raise HTTPException(404,'岗位不存在。')
        if job['owner_id']!=user['id']:raise HTTPException(403,'不能修改他人岗位。')
        status='approved' if user['role']=='admin' else 'pending'
        db.execute("UPDATE jobs SET title=?,company=?,description=?,recommended=?,status=?,review_note='',reviewed_by=NULL,reviewed_at=NULL WHERE id=?",(*fields,int(data.recommended),status,jid))
        event(db,user['id'],'job_resubmit')
    return {'id':jid,'status':status}


@router.get('/admin/jobs')
async def admin_jobs(request:Request):
    current(request,admin=True)
    with connect() as db:
        rows=db.execute("SELECT j.*,u.username AS publisher FROM jobs j JOIN users u ON u.id=j.owner_id WHERE j.active=1 ORDER BY (j.status='pending') DESC,j.id DESC LIMIT 500").fetchall()
    return {'items':[dict(r) for r in rows]}


class JobReview(Input):
    status: str = Field(pattern=r'^(approved|rejected)$')
    note: str = Field(default='',max_length=500)


@router.patch('/admin/jobs/{jid}/review')
async def moderate_job(jid:int,request:Request):
    user=current(request,admin=True)
    data=await payload(request,JobReview)
    note=data.note.strip()
    if data.status=='rejected' and not note:raise HTTPException(422,'请填写审核未通过的原因。')
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=? AND active=1",(jid,)).fetchone():raise HTTPException(404,'岗位不存在。')
        db.execute('UPDATE jobs SET status=?,review_note=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(data.status,note,user['id'],jid))
        event(db,user['id'],'job_'+data.status)
    return {'ok':True,'status':data.status}


@router.delete('/jobs/{jid}')
async def delete_job(jid:int, request:Request):
    user=current(request)
    with connect() as db:
        job=db.execute('SELECT owner_id FROM jobs WHERE id=?',(jid,)).fetchone()
        if not job: raise HTTPException(404,'岗位不存在。')
        if user['role']!='admin' and job['owner_id']!=user['id']: raise HTTPException(403,'不能下架他人岗位。')
        db.execute('UPDATE jobs SET active=0 WHERE id=?',(jid,))
        event(db,user['id'],'job_remove')
    return {'ok':True}


class Review(Input):
    rating: int = Field(ge=1,le=5)
    body: str = Field(min_length=5,max_length=1000)


@router.get('/jobs/{jid}/reviews')
async def reviews(jid:int,request:Request):
    authorize(request)
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=? AND active=1 AND status='approved'",(jid,)).fetchone():raise HTTPException(404,'岗位不存在。')
        rows=db.execute('SELECT id,rating,body,created FROM reviews WHERE job_id=? AND hidden=0 ORDER BY id DESC LIMIT 100',(jid,)).fetchall()
    return {'items':[dict(r) for r in rows]}


@router.post('/jobs/{jid}/reviews')
async def review(jid:int,request:Request):
    user=current(request)
    data=await payload(request,Review)
    body=growth.validate_input(data.body)
    if re.search(r'https?://|诈骗公司|骗子公司',body):
        raise HTTPException(422,'请描述可核验的个人体验，避免外部链接和未经核实的定性指控。')
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=? AND active=1 AND status='approved'",(jid,)).fetchone(): raise HTTPException(404,'岗位不存在。')
        db.execute('INSERT INTO reviews(job_id,user_id,rating,body) VALUES (?,?,?,?) ON CONFLICT(job_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body,created=CURRENT_TIMESTAMP',(jid,user['id'],data.rating,body))
        event(db,user['id'],'review_submit')
    return {'ok':True}


class TreeInput(Input):
    major: str = Field(default='',max_length=80)
    occupation: str = Field(min_length=1,max_length=100)
    jd: str = Field(default='',max_length=8000)
    skills: list[str] = Field(default_factory=list,max_length=24)
    consent: bool = False


def consent(data):
    if not data.consent: raise HTTPException(422,'请先确认向已配置模型发送本次资料。')


def owned(db,table,rid,uid):
    # table 只由代码常量传入，不接收用户表名。
    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND user_id=?',(rid,uid)).fetchone()
    if not row: raise HTTPException(404,'记录不存在或不属于当前账号。')
    return dict(row)


def write_guard(db,user):
    """模型运行时不持有SQL事务，写回时核对账号数据代数及启用状态。"""
    db.execute('BEGIN IMMEDIATE')
    row=db.execute('SELECT data_generation,disabled FROM users WHERE id=?',(user['id'],)).fetchone()
    if not row or row['disabled'] or row['data_generation']!=user['data_generation']:
        raise HTTPException(409,'任务期间个人资料已删除或账号状态已变更，本次结果已丢弃。')


def tree_view(row):
    return {'id':row['id'],'occupation':row['occupation'],'jd':row['jd'],'tree':starmap.decorate(growth.Tree.model_validate_json(row['content']).model_dump(),json.loads(row['assessment_progress']),row['occupation'],row['major']),
            'major':row['major'],'progress':json.loads(row['assessment_progress']),'source':'AI生成 · 学习参考'}


@router.get('/learning/trees')
async def trees(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT * FROM trees WHERE user_id=? ORDER BY id DESC LIMIT 30',(user['id'],)).fetchall()
    return {'items':[tree_view(r) for r in rows]}


@router.post('/learning/tree')
async def make_tree(request:Request):
    user=current(request)
    data=await payload(request,TreeInput);consent(data)
    occupation=growth.validate_input(data.occupation)
    major=growth.validate_input(data.major)
    jd=growth.validate_input(data.jd)
    if any(len(x)>80 for x in data.skills): raise HTTPException(422,'技能名称过长。')
    result=await compute(growth.generate_json,'面向任意专业与学习领域，按用户major、目标岗位、JD与能力缺口动态生成成长星图。不得默认用户为计算机专业；课程、实践和职业应与实际专业一致。learner_label使用对应专业学习者称呼。职业方向数量按输入需求决定，通常1至5个，禁止固定为九个。生成12至24个共享技能节点，公共基础技能→职业方向→专业技能→项目实战，依赖有向无环。多职业复用相同ID的基础与专业技能，允许多路径汇合，禁止复制互不关联的树。每个节点含stage、resources资源占位（不要URL）、task实战交付物；careers含id、name、description、core_skill_ids、projects，核心技能覆盖前置与项目。禁止输出录用概率或虚构完成状态。',
                         {'major':major,'occupation':occupation,'jd':jd,'gaps':data.skills},growth.Tree)
    try: result=growth.Tree.model_validate(result).model_dump()
    except ValidationError: raise HTTPException(502,'模型技能树含无效依赖，原树保留，请重试。') from None
    current(request)
    with connect() as db:
        write_guard(db,user)
        tid=db.execute('INSERT INTO trees(user_id,occupation,jd,content,major) VALUES (?,?,?,?,?)',(user['id'],occupation,jd,encode(result),major)).lastrowid
        event(db,user['id'],'tree_generate')
        row=db.execute('SELECT * FROM trees WHERE id=?',(tid,)).fetchone()
    return tree_view(row)


class Progress(Input):
    completed: list[str] = Field(max_length=64)


@router.put('/learning/trees/{tid}/progress')
async def progress(tid:int,request:Request):
    user=current(request);data=await payload(request,Progress)
    with connect() as db:
        row=owned(db,'trees',tid,user['id']);tree=growth.Tree.model_validate_json(row['content'])
        done=set(data.completed);ids={n.id for n in tree.nodes}
        if not done<=ids or any(n.id in done and not set(n.prerequisites)<=done for n in tree.nodes):
            raise HTTPException(422,'完成记录包含未知节点或尚未完成的前置技能。')
        if not done<=set(json.loads(row['assessment_progress'])):raise HTTPException(422,'技能须通过节点考核后完成，不能直接添加完成记录。')
        db.execute('UPDATE trees SET assessment_progress=? WHERE id=?',(encode(sorted(done)),tid))
        event(db,user['id'],'tree_progress')
    return {'completed':sorted(done)}


class ExamInput(Input):
    unlock: bool = False
    tree_id: int
    node_ids: list[str] = Field(min_length=1,max_length=8)
    consent: bool = False


def exam_view(eid,questions,unlock=False):
    return {'id':eid,'questions':[{k:q[k] for k in ('question','options','skill')} for q in questions],
            'source':'AI 节点考核 · 正确率80%通过' if unlock else 'AI 技能练习'}


@router.post('/learning/exams')
async def create_exam(request:Request):
    user=current(request);data=await payload(request,ExamInput);consent(data)
    with connect() as db: row=owned(db,'trees',data.tree_id,user['id'])
    selected=[n for n in json.loads(row['content'])['nodes'] if n['id'] in data.node_ids]
    if len(selected)!=len(set(data.node_ids)): raise HTTPException(422,'选择的技能不存在。')
    if data.unlock:
        if len(selected)!=1:raise HTTPException(422,'节点考核一次只选择一个技能。')
        if not set(selected[0]['prerequisites'])<=set(json.loads(row['assessment_progress'])):raise HTTPException(422,'请先通过前置技能考核。')

    result=await compute(growth.generate_json,'围绕用户所选技能生成5道四选一单选题，只有一个正确答案，answer为0到3，给出准确解析，skill必须来自所选技能名称。',{'occupation':row['occupation'],'skills':selected},growth.Questions)
    try: questions=growth.Questions.model_validate(result).model_dump()['questions']
    except ValidationError: raise HTTPException(502,'模型题目格式未通过校验。') from None
    if any(q['skill'] not in {n['name'] for n in selected} for q in questions): raise HTTPException(502,'模型返回了未选择的技能题目，请重试。')
    if data.unlock and (len(questions)<3 or len({q['question'] for q in questions})!=len(questions)):raise HTTPException(502,'节点考核需要至少3道不同题目，请重试。')
    current(request)
    with connect() as db:
        write_guard(db,user)
        eid=db.execute('INSERT INTO exams(user_id,tree_id,content,unlock_node) VALUES (?,?,?,?)',(user['id'],data.tree_id,encode(questions),selected[0]['id'] if data.unlock else None)).lastrowid
        event(db,user['id'],'exam_generate')
    return exam_view(eid,questions,data.unlock)


class Answers(Input):
    answers: list[int] = Field(min_length=1,max_length=8)


@router.post('/learning/exams/{eid}/submit')
async def submit(eid:int,request:Request):
    user=current(request);data=await payload(request,Answers)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        exam=owned(db,'exams',eid,user['id'])
        if exam['result'] is not None: raise HTTPException(409,'本次考试已提交，请创建新的练习。')
        questions=json.loads(exam['content'])
        if len(data.answers)!=len(questions) or any(a<0 or a>3 for a in data.answers): raise HTTPException(422,'请完成每道题并选择有效选项。')
        details=[]
        for q,answer in zip(questions,data.answers):
            correct=answer==q['answer'];details.append({**q,'chosen':answer,'correct':correct})
            if not correct:
                db.execute('INSERT INTO wrongbook(user_id,question,content) VALUES (?,?,?) ON CONFLICT(user_id,question) DO UPDATE SET mistakes=mistakes+1,correct_streak=0,content=excluded.content',(user['id'],q['question'],encode(q)))
            else:
                db.execute('UPDATE wrongbook SET correct_streak=correct_streak+1 WHERE user_id=? AND question=?',(user['id'],q['question']))
        result={'score':round(100*sum(x['correct'] for x in details)/len(details)),'details':details}
        result.update(unlocked=[],tree_id=exam['tree_id'])
        if exam['unlock_node'] and exam['tree_id']:
            tree_row=owned(db,'trees',exam['tree_id'],user['id']);tree=json.loads(tree_row['content'])
            skill=next((n for n in tree['nodes'] if n['id']==exam['unlock_node']),None)
            done=set(json.loads(tree_row['assessment_progress']))
            if (skill and len(details)>=3 and all(q['skill']==skill['name'] for q in details)
                and sum(q['correct'] for q in details)/len(details)>=.8 and set(skill['prerequisites'])<=done):
                done.add(skill['id']);result['unlocked']=[skill['id']]
                db.execute('UPDATE trees SET assessment_progress=? WHERE id=?',(encode(sorted(done)),exam['tree_id']))
                event(db,user['id'],'skill_exam_pass')
            result['progress']=sorted(done)

        db.execute('UPDATE exams SET result=? WHERE id=?',(encode(result),eid));event(db,user['id'],'exam_submit')
    return result


@router.get('/learning/wrongbook')
async def wrongbook(request:Request):
    user=current(request)
    with connect() as db: rows=db.execute('SELECT * FROM wrongbook WHERE user_id=? ORDER BY mistakes DESC,id DESC LIMIT 200',(user['id'],)).fetchall()
    return {'items':[{'id':r['id'],'mistakes':r['mistakes'],'correct_streak':r['correct_streak'],**json.loads(r['content'])} for r in rows]}


@router.get('/learning/exams')
async def exam_history(request:Request):
    user=current(request)
    with connect() as db: rows=db.execute('SELECT * FROM exams WHERE user_id=? ORDER BY id DESC LIMIT 50',(user['id'],)).fetchall()
    return {'items':[{'id':r['id'],'count':len(json.loads(r['content'])),
                     'result':json.loads(r['result']) if r['result'] else None} for r in rows]}


@router.get('/learning/exams/{eid}')
async def get_exam(eid:int,request:Request):
    user=current(request)
    with connect() as db: exam=owned(db,'exams',eid,user['id'])
    if exam['result']: raise HTTPException(409,'该考试已经提交，请到个人中心查看结果。')
    return exam_view(eid,json.loads(exam['content']),bool(exam['unlock_node']))


@router.delete('/profile/data')
async def erase_learning(request:Request):
    user=current(request)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(user['id'],))
        for table in ('exams','wrongbook','interviews','trees','profiles','materials','career_reports'):
            db.execute(f'DELETE FROM {table} WHERE user_id=?',(user['id'],))
        event(db,user['id'],'learning_erase')
    return {'ok':True}


@router.get('/career/reports')
async def career_history(request:Request):
    user=current(request)
    with connect() as db:rows=db.execute('SELECT id,content,created FROM career_reports WHERE user_id=? ORDER BY id DESC LIMIT 30',(user['id'],)).fetchall()
    return {'items':[{'id':r['id'],'report':json.loads(r['content']),'created':r['created']} for r in rows]}


@router.get('/profile/materials')
async def profile_materials(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT id,content,created FROM materials WHERE user_id=? ORDER BY created DESC LIMIT 24',(user['id'],)).fetchall()
        analyses=db.execute('SELECT material_id,kind,content FROM analyses WHERE user_id=?',(user['id'],)).fetchall()
    return {'items':[{'id':r['id'],'kind':json.loads(r['content'])['kind'],'chars':len(json.loads(r['content'])['text']),'created':r['created']} for r in rows],
            'analyses':[{'material_id':r['material_id'],'kind':r['kind'],'result':json.loads(r['content'])} for r in analyses]}


@router.post('/learning/practice')
async def practice(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT content FROM wrongbook WHERE user_id=? ORDER BY RANDOM() LIMIT 5',(user['id'],)).fetchall()
        if not rows: raise HTTPException(422,'还没有错题，先选择技能生成一次考试。')
        questions=[json.loads(r['content']) for r in rows]
        # 保留选项对应关系，随机抽题即可，不改变标准答案。
        eid=db.execute('INSERT INTO exams(user_id,content) VALUES (?,?)',(user['id'],encode(questions))).lastrowid
        event(db,user['id'],'wrongbook_practice')
    return exam_view(eid,questions)


class InterviewInput(Input):
    occupation: str = Field(min_length=1,max_length=100)
    jd: str = Field(default='',max_length=6000)
    consent: bool = False


class Turn(Input):
    answer: str = Field(min_length=1,max_length=2500)
    consent: bool = False


@router.post('/interviews')
async def interview_start(request:Request):
    user=current(request);data=await payload(request,InterviewInput);consent(data)
    occupation=growth.validate_input(data.occupation);jd=growth.validate_input(data.jd)
    reply=await compute(growth.generate_json,'扮演模拟面试官。根据岗位提出第一道具体问题，简短自然，每轮只问一道。feedback首轮为空，focus为考查技能。',{'occupation':occupation,'jd':jd},growth.InterviewReply)
    reply=growth.InterviewReply.model_validate(reply).model_dump()
    history=[{'role':'assistant','content':reply['question'],'feedback':reply['feedback'],'focus':reply['focus']}]
    current(request)
    with connect() as db:
        write_guard(db,user)
        iid=db.execute('INSERT INTO interviews(user_id,occupation,history) VALUES (?,?,?)',(user['id'],occupation,encode(history))).lastrowid
        event(db,user['id'],'interview_start')
    return {'id':iid,**reply,'history':history}


@router.post('/interviews/{iid}/turn')
async def interview_turn(iid:int,request:Request):
    user=current(request);data=await payload(request,Turn);consent(data)
    answer=growth.validate_input(data.answer)
    with connect() as db: row=owned(db,'interviews',iid,user['id'])
    history=json.loads(row['history'])
    if row['ended'] or len(history)>=25: raise HTTPException(409,'本次面试已结束或达到12轮上限，请开始新面试。')
    updated=history+[{'role':'user','content':answer}]
    reply=await compute(growth.generate_json,'你是模拟面试官，根据最近回答给出简短具体反馈，再提出一个相关追问或下一道岗位问题。不验证经历真假，不预测录用。只问一个问题。',{'occupation':row['occupation'],'conversation':updated[-13:]},growth.InterviewReply)
    reply=growth.InterviewReply.model_validate(reply).model_dump()
    updated.append({'role':'assistant','content':reply['question'],'feedback':reply['feedback'],'focus':reply['focus']})
    current(request)
    with connect() as db:
        changed=db.execute('UPDATE interviews SET history=? WHERE id=? AND user_id=? AND history=? AND ended=0',(encode(updated),iid,user['id'],row['history'])).rowcount
        if not changed: raise HTTPException(409,'面试已更新或结束，请重新打开记录。')
        event(db,user['id'],'interview_turn')
    return {'id':iid,**reply,'history':updated}


@router.get('/interviews')
async def interview_history(request:Request):
    user=current(request)
    with connect() as db: rows=db.execute('SELECT * FROM interviews WHERE user_id=? ORDER BY id DESC LIMIT 30',(user['id'],)).fetchall()
    return {'items':[{**dict(r),'history':json.loads(r['history'])} for r in rows]}


@router.post('/interviews/{iid}/end')
async def end_interview(iid:int,request:Request):
    user=current(request)
    with connect() as db:
        owned(db,'interviews',iid,user['id']);db.execute('UPDATE interviews SET ended=1 WHERE id=?',(iid,));event(db,user['id'],'interview_end')
    return {'ok':True}


@router.get('/admin/overview')
async def overview(request:Request):
    current(request,True)
    with connect() as db:
        totals={table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('users','jobs','reviews','trees','exams','interviews')}
        activity=[dict(r) for r in db.execute('SELECT action,COUNT(*) AS count FROM events GROUP BY action ORDER BY count DESC')]
        daily=[dict(r) for r in db.execute('SELECT date(created) AS day,COUNT(*) AS count FROM events GROUP BY day ORDER BY day DESC LIMIT 14')]
        totals['active_users_today']=db.execute("SELECT COUNT(DISTINCT user_id) FROM events WHERE date(created)=date('now')").fetchone()[0]
        users=[public_user(r) for r in db.execute('SELECT * FROM users ORDER BY id DESC LIMIT 300')]
        reviews=[dict(r) for r in db.execute('SELECT r.id,r.body,r.rating,r.hidden,j.title,j.company FROM reviews r JOIN jobs j ON r.job_id=j.id ORDER BY r.id DESC LIMIT 200')]
    return {'totals':totals,'activity':activity,'daily':daily,'users':users,'reviews':reviews}


@router.get('/admin/security/audit')
async def security_audit(request:Request):
    current(request,True)
    with connect() as db:
        rows=db.execute('SELECT action,status,count,created AS time FROM security_events ORDER BY id DESC LIMIT 400').fetchall()
    return {'items':[dict(r) for r in reversed(rows)]}


class UserChange(Input):
    disabled: bool


@router.patch('/admin/users/{uid}')
async def change_user(uid:int,request:Request):
    admin=current(request,True);data=await payload(request,UserChange)
    if uid==admin['id']: raise HTTPException(422,'不能停用当前管理员。')
    with connect() as db:
        row=db.execute('SELECT role FROM users WHERE id=?',(uid,)).fetchone()
        if not row: raise HTTPException(404,'用户不存在。')
        db.execute('UPDATE users SET disabled=? WHERE id=?',(int(data.disabled),uid))
        if data.disabled: db.execute('DELETE FROM auth_sessions WHERE user_id=?',(uid,))
        event(db,admin['id'],'user_status_change')
    return {'ok':True}


class Moderation(Input):
    hidden: bool


@router.patch('/admin/reviews/{rid}')
async def moderate(rid:int,request:Request):
    admin=current(request,True);data=await payload(request,Moderation)
    with connect() as db:
        if not db.execute('UPDATE reviews SET hidden=? WHERE id=?',(int(data.hidden),rid)).rowcount: raise HTTPException(404,'点评不存在。')
        event(db,admin['id'],'review_moderate')
    return {'ok':True}


class ModelSettings(Input):
    model: str = Field(pattern=r'^[A-Za-z0-9._:-]{1,100}$')
    api_key: str = Field(default='',max_length=250)
    provider: str = Field(default='deepseek',pattern=r'^(deepseek|ollama)$')


def load_model_settings():
    with connect() as db: row=db.execute("SELECT value FROM settings WHERE name='model'").fetchone()
    if row:
        value=json.loads(cipher().decrypt(row['value'].encode()))
        config.LLM_PROVIDER=value['provider']
        if value['provider']=='deepseek':
            config.DEEPSEEK_MODEL=value['model'];config.DEEPSEEK_API_KEY=value['api_key']
        else: config.OLLAMA_MODEL=value['model']


@router.get('/admin/model')
async def model_settings(request:Request):
    current(request,True)
    return {'provider':config.LLM_PROVIDER,'model':config.DEEPSEEK_MODEL if config.LLM_PROVIDER=='deepseek' else config.OLLAMA_MODEL,
            'has_key':bool(config.DEEPSEEK_API_KEY),'endpoint':'DeepSeek 官方 HTTPS / 本机 Ollama','voice':'浏览器语音识别与系统语音合成'}


@router.put('/admin/model')
async def save_model(request:Request):
    admin=current(request,True);data=await payload(request,ModelSettings)
    if data.api_key and (not data.api_key.isascii() or re.search(r'\s',data.api_key)): raise HTTPException(422,'密钥格式不正确。')
    if data.provider=='ollama' and 'cloud' in data.model.lower(): raise HTTPException(422,'本机模式不能配置云端模型名称。')
    key=data.api_key or config.DEEPSEEK_API_KEY
    value={'provider':data.provider,'model':data.model,'api_key':key}
    encrypted=cipher().encrypt(encode(value).encode()).decode()
    with connect() as db:
        db.execute("INSERT INTO settings VALUES ('model',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(encrypted,));event(db,admin['id'],'model_configure')
    load_model_settings()
    return {'ok':True,'message':'已保存，密钥不会回显。'}


@router.post('/admin/model/test')
async def test_model(request:Request):
    current(request,True)
    return await compute(llm.status)
