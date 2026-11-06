"""Consent-scoped applications. Companies never receive private interview content."""
import json
from typing import Literal
from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import Field
from .api import Input,payload
from .database import connect,cipher,encode,event
from .platform_api import current,write_guard
from .company_api import membership
from .services.resume_builder import Draft,FIELDS

router=APIRouter(prefix='/api')

class Apply(Input):
    resume_source:Literal['profile','studio']
    resume_session_id:str|None=Field(default=None,max_length=100)
    share_resume:bool=False
    interview_consent:bool=False


def public_job(db,jid):
    row=db.execute("""SELECT j.*,l.company_id FROM jobs j JOIN job_company_links l ON l.job_id=j.id
      JOIN companies c ON c.id=l.company_id WHERE j.id=? AND j.active=1 AND j.status='approved' AND c.status='approved'""",(jid,)).fetchone()
    if not row:raise HTTPException(404,'岗位未公开、已下架或企业材料尚未通过平台审核。')
    return dict(row)


def validate_application(db,user,application_id,occupation=None):
    row=db.execute("SELECT * FROM job_applications WHERE id=? AND user_id=? AND status='active' AND share_resume=1 AND interview_consent=1",(application_id,user['id'])).fetchone()
    if not row:raise HTTPException(404,'投递不存在、已撤回或未授权岗位面试。')
    job=public_job(db,row['job_id'])
    if row['company_id']!=job['company_id'] or row['occupation']!=job['title'] or row['jd']!=job['description']:
        raise HTTPException(409,'岗位内容已更新，请重新确认授权后面试。')
    if occupation is not None and occupation!=row['occupation']:raise HTTPException(422,'面试岗位必须与授权投递一致。')
    return dict(row)


def attach_interview(db,user,application_id,interview_id,occupation=None):
    application=validate_application(db,user,application_id,occupation)
    row=db.execute('SELECT user_id,occupation FROM interviews WHERE id=?',(interview_id,)).fetchone()
    if not row or row['user_id']!=user['id'] or row['occupation']!=application['occupation']:
        raise HTTPException(422,'面试记录与授权账号或岗位不一致。')
    db.execute('INSERT OR IGNORE INTO application_interviews(application_id,interview_id) VALUES (?,?)',(application_id,interview_id))


def snapshot(db,user,data):
    if data.resume_source=='profile':
        row=db.execute('SELECT resume FROM profiles WHERE user_id=?',(user['id'],)).fetchone()
        if not row or not row['resume'].strip():raise HTTPException(422,'请先保存个人简历，或选择简历工作室中的简历。')
        return {'source':'profile','text':row['resume']}
    row=db.execute('SELECT content FROM resume_sessions WHERE id=? AND user_id=?',(data.resume_session_id,user['id'])).fetchone()
    if not row:raise HTTPException(404,'所选简历不存在或不属于当前账号。')
    draft=Draft.model_validate(json.loads(cipher().decrypt(row['content'].encode()))['draft']).model_dump()
    if not any(draft.values()):raise HTTPException(422,'所选简历为空，请先填写真实资料。')
    return {'source':'studio','fields':draft,'text':'\n\n'.join(FIELDS[k]+'\n'+v for k,v in draft.items() if v)}


@router.post('/jobs/{jid}/apply')
async def apply(jid:int,request:Request):
    user=current(request);data=await payload(request,Apply)
    if user['role']=='company':raise HTTPException(403,'企业账号不能作为求职者投递。')
    if not data.share_resume:raise HTTPException(422,'请主动同意向本岗位企业共享所选简历快照。')
    with connect() as db:
        write_guard(db,user);job=public_job(db,jid);resume=snapshot(db,user,data)
        encrypted=cipher().encrypt(encode(resume).encode())
        db.execute("""INSERT INTO job_applications(user_id,job_id,company_id,resume_source,resume_encrypted,share_resume,interview_consent,occupation,jd)
          VALUES (?,?,?,?,?,1,?,?,?) ON CONFLICT(user_id,job_id) DO UPDATE SET resume_source=excluded.resume_source,
          resume_encrypted=excluded.resume_encrypted,share_resume=1,interview_consent=excluded.interview_consent,
          occupation=excluded.occupation,jd=excluded.jd,status='active',updated=CURRENT_TIMESTAMP""",
          (user['id'],jid,job['company_id'],data.resume_source,encrypted,int(data.interview_consent),job['title'],job['description']))
        aid=db.execute('SELECT id FROM job_applications WHERE user_id=? AND job_id=?',(user['id'],jid)).fetchone()[0]
        event(db,user['id'],'application_share')
    return {'id':aid,'application_id':aid,'job':job,'occupation':job['title'],'jd':job['description']}


@router.get('/applications')
async def applications(request:Request,response:Response):
    user=current(request);response.headers['Cache-Control']='no-store'
    with connect() as db:
        rows=db.execute('''SELECT a.id,a.job_id,a.status,a.share_resume,a.interview_consent,a.created,a.updated,j.title,j.company
          FROM job_applications a JOIN jobs j ON j.id=a.job_id WHERE a.user_id=? ORDER BY a.updated DESC,a.id DESC LIMIT 200''',(user['id'],)).fetchall()
    return {'items':[dict(r) for r in rows]}


@router.delete('/applications/{aid}')
async def withdraw(aid:int,request:Request):
    user=current(request)
    with connect() as db:
        write_guard(db,user)
        n=db.execute("UPDATE job_applications SET status='withdrawn',share_resume=0,interview_consent=0,resume_encrypted=NULL,updated=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",(aid,user['id'])).rowcount
        if not n:raise HTTPException(404,'投递不存在。')
        event(db,user['id'],'application_withdraw')
    return {'withdrawn':True}


def candidate_view(db,company,aid):
    row=db.execute("""SELECT a.id,a.user_id,a.job_id,a.created,a.updated,a.resume_encrypted,j.title,u.username,
      CASE WHEN a.interview_consent=1 THEN (SELECT COUNT(*) FROM application_interviews ai WHERE ai.application_id=a.id) ELSE 0 END AS interview_count
      FROM job_applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.user_id
      WHERE a.id=? AND a.company_id=? AND a.status='active' AND a.share_resume=1 AND u.disabled=0""",(aid,company['id'])).fetchone()
    if not row:raise HTTPException(404,'候选人未授权、已撤回或不属于本企业。')
    result=dict(row);result['resume']=json.loads(cipher().decrypt(result.pop('resume_encrypted')))
    return result


@router.get('/company/candidates')
async def candidates(request:Request,response:Response,job_id:int|None=None):
    user=current(request);response.headers['Cache-Control']='no-store'
    with connect() as db:
        company=membership(db,user,True)
        if job_id is not None and not db.execute('SELECT 1 FROM job_company_links WHERE job_id=? AND company_id=?',(job_id,company['id'])).fetchone():raise HTTPException(404,'岗位不属于本企业。')
        rows=db.execute("""SELECT a.id FROM job_applications a JOIN users u ON u.id=a.user_id
          WHERE a.company_id=? AND a.status='active' AND a.share_resume=1 AND u.disabled=0
          AND (? IS NULL OR a.job_id=?) ORDER BY a.updated DESC,a.id DESC LIMIT 500""",(company['id'],job_id,job_id)).fetchall()
        items=[candidate_view(db,company,r['id']) for r in rows]
        stats=db.execute("""SELECT j.id AS job_id,COUNT(DISTINCT CASE WHEN a.status='active' AND a.share_resume=1 AND u.disabled=0 THEN a.user_id END) AS applicant_count,
          COUNT(DISTINCT CASE WHEN ai.interview_id IS NOT NULL AND a.interview_consent=1 AND a.status='active' AND a.share_resume=1 AND u.disabled=0 THEN a.user_id END) AS interview_users
          FROM jobs j JOIN job_company_links l ON l.job_id=j.id LEFT JOIN job_applications a ON a.job_id=j.id
          LEFT JOIN users u ON u.id=a.user_id LEFT JOIN application_interviews ai ON ai.application_id=a.id
          WHERE l.company_id=? GROUP BY j.id""",(company['id'],)).fetchall()
    return {'items':items,'jobs':[dict(r) for r in stats]}


@router.get('/company/candidates/{aid}')
async def candidate(aid:int,request:Request,response:Response):
    user=current(request);response.headers['Cache-Control']='no-store'
    with connect() as db:return candidate_view(db,membership(db,user,True),aid)


def clear_user_applications(db,uid):
    """Call in personal-data deletion transaction; revoke access and erase snapshots."""
    db.execute("UPDATE job_applications SET status='withdrawn',share_resume=0,interview_consent=0,resume_encrypted=NULL,updated=CURRENT_TIMESTAMP WHERE user_id=?",(uid,))
