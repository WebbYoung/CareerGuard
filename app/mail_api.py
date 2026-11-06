"""Station mail endpoints. GET never creates messages or changes read state."""
import asyncio
import hashlib
import secrets
import time
from fastapi import APIRouter,HTTPException,Request,Query
from pydantic import Field
from .api import Input,payload
from .platform_api import current,write_guard
from .database import connect,event
from .services import mail

router=APIRouter(prefix='/api')
class Compose(Input):
    application_id:int|None=Field(default=None,gt=0)
    recipient_id:int|None=Field(default=None,gt=0)
    subject:str=Field(min_length=1,max_length=160)
    body:str=Field(min_length=1,max_length=12000)
    sync_email:bool=False
class Reply(Input):
    body:str=Field(min_length=1,max_length=12000)
    sync_email:bool=False
class Address(Input):
    email:str=Field(max_length=254)
    consent:bool=False
class Code(Input):
    code:str=Field(pattern=r'^\d{6}$')
class SMTP(Input):
    host:str=Field(max_length=253)
    port:int=587
    username:str=Field(min_length=1,max_length=254)
    password:str=Field(default='',max_length=512)
    from_address:str=Field(max_length=254)
    enabled:bool=False

def subject_text(text):
    if not text.strip() or any(ord(x)<32 or ord(x)==127 for x in text):raise HTTPException(422,'主题不能为空或含控制字符。')
    return text.strip()
def body_text(text):
    if not text.strip():raise HTTPException(422,'请填写正文。')
    return text.strip()
def state(db,uid):
    return {'cursor':db.execute('SELECT COALESCE(MAX(id),0) FROM mail_messages WHERE sender_id=? OR recipient_id=?',(uid,uid)).fetchone()[0], 'unread':db.execute('SELECT COUNT(*) FROM mail_messages WHERE recipient_id=? AND read_at IS NULL',(uid,)).fetchone()[0]}
def summary(db,uid,sent=False):
    column='sender_id' if sent else 'recipient_id'
    rows=db.execute(f'''SELECT t.id,t.subject,t.application_id,t.created,MAX(m.id) AS last_message_id,COUNT(CASE WHEN m.recipient_id=? AND m.read_at IS NULL THEN 1 END) AS unread FROM mail_threads t JOIN mail_messages m ON m.thread_id=t.id WHERE EXISTS(SELECT 1 FROM mail_messages x WHERE x.thread_id=t.id AND x.{column}=?) GROUP BY t.id ORDER BY last_message_id DESC LIMIT 100''',(uid,uid)).fetchall()
    return {'items':[dict(r) for r in rows],**state(db,uid),'mode':'internal_mail'}

@router.get('/mail/inbox')
async def inbox(request:Request):
    u=current(request)
    with connect() as db:return summary(db,u['id'])
@router.get('/mail/sent')
async def sent(request:Request):
    u=current(request)
    with connect() as db:return summary(db,u['id'],True)
@router.get('/mail/events')
async def events(request:Request,after:int=Query(0,ge=0),timeout:float=Query(0,ge=0,le=20)):
    u=current(request);deadline=time.monotonic()+timeout
    while True:
        with connect() as db:
            live=db.execute('SELECT disabled,data_generation FROM users WHERE id=?',(u['id'],)).fetchone()
            if not live or live['disabled']:raise HTTPException(401,'账号已停用，请重新登录。')
            if live['data_generation']!=u['data_generation']:raise HTTPException(409,'账号数据已变更，请刷新页面。')
            data=state(db,u['id'])
        if data['cursor']>after or time.monotonic()>=deadline or await request.is_disconnected():return data
        await asyncio.sleep(.5)
@router.post('/mail/threads')
async def compose(request:Request):
    u=current(request);d=await payload(request,Compose);subject=subject_text(d.subject);body=body_text(d.body)
    with connect() as db:
        write_guard(db,u);mail.limit(db,u['id'])
        company=None
        if u['role']=='company':
            if d.recipient_id is not None:raise HTTPException(422,'收件人由投递记录确定，请勿指定收件人。')
            a=mail.application(db,d.application_id,u['id']);recipient=a['user_id'];company=a['linked_company']
        elif u['role']=='admin':
            if d.application_id or not d.recipient_id:raise HTTPException(422,'管理员通知需指定站内用户编号。')
            recipient=d.recipient_id
        else:raise HTTPException(403,'求职者可回复已有邮件。')
        if recipient==u['id'] or not db.execute('SELECT 1 FROM users WHERE id=? AND disabled=0',(recipient,)).fetchone():raise HTTPException(404,'收件用户不存在。')
        tid=db.execute('INSERT INTO mail_threads(application_id,company_id,candidate_id,creator_id,subject) VALUES (?,?,?,?,?)',(d.application_id,company,recipient,u['id'],subject)).lastrowid
        mid=db.execute('INSERT INTO mail_messages(thread_id,sender_id,recipient_id,body_encrypted) VALUES (?,?,?,?)',(tid,u['id'],recipient,mail.encrypt(body))).lastrowid
        event(db,u['id'],'mail_send')
        event(db,u['id'],'mail_delivery_internal')
    delivery=await asyncio.to_thread(mail.deliver,mid,recipient,subject,body,d.sync_email)
    return {'id':tid,'message_id':mid,'delivery':delivery,'internal_delivered':True}
@router.get('/mail/threads/{tid}')
async def get_thread(tid:int,request:Request):
    u=current(request)
    with connect() as db:
        t=mail.thread(db,tid,u['id'])
        messages=db.execute('SELECT m.*,s.username AS sender FROM mail_messages m JOIN users s ON s.id=m.sender_id WHERE thread_id=? ORDER BY m.id LIMIT 500',(tid,)).fetchall()
        return {**dict(t),'messages':[{k:r[k] for k in ('id','sender_id','recipient_id','sender','read_at','delivery','created')}|{'body':mail.decrypt(r['body_encrypted'])} for r in messages]}
@router.post('/mail/threads/{tid}/read')
async def read_thread(tid:int,request:Request):
    u=current(request)
    with connect() as db:
        write_guard(db,u);mail.thread(db,tid,u['id']);db.execute('UPDATE mail_messages SET read_at=CURRENT_TIMESTAMP WHERE thread_id=? AND recipient_id=? AND read_at IS NULL',(tid,u['id']))
        event(db,u['id'],'mail_read')
        return state(db,u['id'])
@router.post('/mail/threads/{tid}/reply')
async def reply(tid:int,request:Request):
    u=current(request);d=await payload(request,Reply);body=body_text(d.body)
    with connect() as db:
        write_guard(db,u);t=mail.thread(db,tid,u['id']);mail.limit(db,u['id'])
        if u['id']!=t['candidate_id'] and t['application_id']:mail.application(db,t['application_id'],u['id'])
        recipient=t['creator_id'] if u['id']==t['candidate_id'] else t['candidate_id']
        if not db.execute('SELECT 1 FROM users WHERE id=? AND disabled=0',(recipient,)).fetchone():raise HTTPException(404,'收件用户不可用。')
        mid=db.execute('INSERT INTO mail_messages(thread_id,sender_id,recipient_id,body_encrypted) VALUES (?,?,?,?)',(tid,u['id'],recipient,mail.encrypt(body))).lastrowid
        subject=t['subject']
        event(db,u['id'],'mail_reply')
        event(db,u['id'],'mail_delivery_internal')
    return {'id':tid,'message_id':mid,'delivery':await asyncio.to_thread(mail.deliver,mid,recipient,subject,body,d.sync_email),'internal_delivered':True}

@router.get('/mail/address')
async def get_address(request:Request):
    u=current(request)
    with connect() as db:
        row=db.execute('SELECT * FROM mail_addresses WHERE user_id=?',(u['id'],)).fetchone();conf=mail.smtp_config(db)
    return {'email':mail.decrypt(row['email_encrypted']) if row else '', 'verified':bool(row and row['verified']),'consent':bool(row and row['consent']),'outbound_available':bool(conf and conf.get('enabled'))}
@router.post('/mail/address')
async def set_address(request:Request):
    u=current(request);d=await payload(request,Address);email=mail.email_address(d.email)
    with connect() as db:
        write_guard(db,u);mail.limit(db,u['id'])
        old=db.execute('SELECT * FROM mail_addresses WHERE user_id=?',(u['id'],)).fetchone()
        verified=bool(old and old['verified'] and mail.decrypt(old['email_encrypted'])==email)
        db.execute('INSERT INTO mail_addresses(user_id,email_encrypted,verified,consent) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET email_encrypted=excluded.email_encrypted,verified=excluded.verified,consent=excluded.consent,code_hash=NULL,code_expires=NULL,attempts=0',(u['id'],mail.encrypt(email),int(verified),int(d.consent)))
        event(db,u['id'],'mail_address_save')
    return {'verified':verified,'message':'邮箱已保存；验证后才可接收外发邮件。'}
@router.post('/mail/address/send-code')
async def send_code(request:Request):
    u=current(request);code=str(secrets.randbelow(1000000)).zfill(6)
    code_digest=hashlib.sha256((str(u['id'])+':'+code).encode()).hexdigest()
    with connect() as db:
        write_guard(db,u);mail.limit(db,u['id'],5);row=db.execute('SELECT * FROM mail_addresses WHERE user_id=?',(u['id'],)).fetchone();conf=mail.smtp_config(db)
        if not row or not conf or not conf.get('enabled'):raise HTTPException(409,'请先保存邮箱，且管理员需启用SMTP。')
        db.execute('UPDATE mail_addresses SET code_hash=?,code_expires=?,attempts=0 WHERE user_id=?',(code_digest,int(time.time())+600,u['id']))
        destination=mail.decrypt(row['email_encrypted'])
    try:await asyncio.to_thread(mail.send_email,conf,destination,'Career Guard 邮箱验证','验证码：'+code+'，十分钟有效。')
    except Exception:
        with connect() as db:
            db.execute('UPDATE mail_addresses SET code_hash=NULL WHERE user_id=? AND code_hash=?',(u['id'],code_digest))
            event(db,u['id'],'mail_code_failed')
        raise HTTPException(502,'验证码发送失败，请检查SMTP配置后重试。') from None
    with connect() as db:event(db,u['id'],'mail_code_sent')
    return {'sent':True}
@router.post('/mail/address/verify')
async def verify_address(request:Request):
    u=current(request);d=await payload(request,Code)
    with connect() as db:
        write_guard(db,u);row=db.execute('SELECT * FROM mail_addresses WHERE user_id=?',(u['id'],)).fetchone()
        valid=bool(row and row['code_hash'] and row['code_expires']>=int(time.time()) and row['attempts']<5)
        digest=hashlib.sha256((str(u['id'])+':'+d.code).encode()).hexdigest()
        valid=valid and secrets.compare_digest(digest,row['code_hash'])
        if row:db.execute('UPDATE mail_addresses SET attempts=attempts+1 WHERE user_id=?',(u['id'],))
        if valid:db.execute('UPDATE mail_addresses SET verified=1,code_hash=NULL WHERE user_id=?',(u['id'],))
        event(db,u['id'],'mail_address_verified' if valid else 'mail_address_verify_failed')
    if not valid:raise HTTPException(422,'验证码无效、过期或尝试次数过多。')
    return {'verified':True}
@router.get('/admin/mail/config')
async def get_config(request:Request):
    current(request,True)
    with connect() as db:conf=mail.smtp_config(db)
    return ({k:v for k,v in conf.items() if k!='password'}|{'password_configured':bool(conf.get('password'))}) if conf else {'enabled':False,'password_configured':False}
@router.post('/admin/mail/config')
async def save_config(request:Request):
    u=current(request,True);d=await payload(request,SMTP);conf=mail.validate_config(d.model_dump())
    with connect() as db:
        write_guard(db,u);old=mail.smtp_config(db)
        if not conf['password'] and old and old['host']==conf['host'] and old['username']==conf['username']:conf['password']=old['password']
        if conf['enabled'] and not conf['password']:raise HTTPException(422,'启用SMTP需填写密码。')
        import json
        db.execute("INSERT INTO settings(name,value) VALUES ('mail-smtp',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(mail.encrypt(json.dumps(conf)).decode(),))
        event(db,u['id'],'mail_smtp_save')
        if bool(old and old.get('enabled'))!=conf['enabled']:
            event(db,u['id'],'mail_smtp_enabled' if conf['enabled'] else 'mail_smtp_disabled')
    return {'saved':True,'enabled':conf['enabled'],'notice':'配置已保存，未连接或测试SMTP。'}


