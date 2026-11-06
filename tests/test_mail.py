"""Offline station-mail authorization and delivery contracts."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import database
from app.api import router as base_router
from app.platform_api import router as platform_router

@pytest.fixture
def mailbox(monkeypatch):
    from app.mail_api import router
    from app.services.mail_schema import SCHEMA
    from app.services.recruitment_schema import SCHEMA as RECRUITMENT_SCHEMA
    monkeypatch.setattr(database,'SCHEMA',database.SCHEMA+RECRUITMENT_SCHEMA+SCHEMA)
    with database.connect() as db:
        for uid,role in [(1,'company'),(2,'user'),(3,'user'),(4,'company'),(5,'admin')]:
            db.execute('INSERT INTO users(id,username,password,role) VALUES (?,?,?,?)',(uid,'actor'+str(uid),'unused',role))
        db.execute("INSERT INTO companies(id,name,credit_code,contact_role,status,license_encrypted,license_type,ocr_notes) VALUES (1,'合成公司','test','HR','approved',X'00','png','{}')")
        db.execute('INSERT INTO company_memberships(company_id,user_id) VALUES (1,1)')
        db.execute("INSERT INTO jobs(id,owner_id,title,company,description,status) VALUES (1,1,'开发','公司','职责','approved')")
        db.execute('INSERT INTO job_company_links VALUES (1,1)')
        db.execute("INSERT INTO job_applications(id,user_id,job_id,share_resume,company_id,status,resume_source,occupation,jd) VALUES (1,2,1,1,1,'active','profile','开发','岗位'),(2,3,1,0,1,'active','profile','开发','岗位')")
    app=FastAPI();app.include_router(base_router);app.include_router(platform_router);app.include_router(router)
    with TestClient(app) as c:
        def login(uid):
            import hashlib,time
            token='mail-test-'+str(uid)
            with database.connect() as db:
                db.execute('INSERT OR REPLACE INTO auth_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,int(time.time())+600))
            c.cookies.set('cg_auth',token)
            c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        yield c,login

def test_mail_module_exists():
    from app import mail_api
    assert mail_api.router

def test_company_send_scoped_and_encrypted(mailbox):
    c,login=mailbox;login(1)
    r=c.post('/api/mail/threads',json={'application_id':1,'subject':'意向询问','body':'请确认应聘意向'})
    assert r.status_code==200,r.text
    tid=r.json()['id']
    assert c.post('/api/mail/threads',json={'application_id':2,'subject':'询问','body':'你好'}).status_code==403
    assert c.post('/api/mail/threads',json={'application_id':1,'recipient_id':3,'subject':'询问','body':'你好'}).status_code==422
    with database.connect() as db:
        stored=db.execute('SELECT body_encrypted FROM mail_messages').fetchone()[0]
        assert b'\xe8\xaf\xb7' not in stored
        assert database.cipher().decrypt(stored).decode()=='请确认应聘意向'
    login(4);assert c.get(f'/api/mail/threads/{tid}').status_code==404
    assert c.post('/api/mail/threads',json={'application_id':1,'subject':'询问','body':'你好'}).status_code==403

def test_inbox_get_no_read_reply_csrf_and_events(mailbox):
    c,login=mailbox;login(1)
    tid=c.post('/api/mail/threads',json={'application_id':1,'subject':'询问','body':'你好'}).json()['id']
    login(2)
    assert c.get('/api/mail/inbox').json()['unread']==1
    assert c.get(f'/api/mail/threads/{tid}').json()['messages'][0]['body']=='你好'
    assert c.get('/api/mail/inbox').json()['unread']==1
    assert c.get('/api/mail/events?after=0&timeout=0').json()['unread']==1
    assert c.post('/api/mail/threads',json={'application_id':1,'subject':'越权','body':'你好'}).status_code==403
    token=c.headers.pop('X-CSRF-Token')
    assert c.post(f'/api/mail/threads/{tid}/read').status_code==403
    c.headers['X-CSRF-Token']=token
    assert c.post(f'/api/mail/threads/{tid}/read').status_code==200
    assert c.get('/api/mail/inbox').json()['unread']==0
    assert c.post(f'/api/mail/threads/{tid}/reply',json={'body':'愿意了解'}).status_code==200
    login(1);assert c.get('/api/mail/inbox').json()['unread']==1
    assert len(c.get('/api/mail/sent').json()['items'])==1
    login(3);assert c.post(f'/api/mail/threads/{tid}/reply',json={'body':'越权'}).status_code==404

def test_admin_notification_rate_and_mailbox_pending(mailbox):
    c,login=mailbox;login(5)
    assert c.post('/api/mail/threads',json={'recipient_id':2,'subject':'通知','body':'系统维护'}).status_code==200
    assert c.post('/api/mail/threads',json={'recipient_id':999,'subject':'通知','body':'你好'}).status_code==404
    assert c.post('/api/admin/mail/config',json={'host':'127.0.0.1','port':587,'username':'a','password':'b','from_address':'test@example.com'}).status_code==422
    login(2)
    r=c.post('/api/mail/address',json={'email':'person@example.com'})
    assert r.status_code==200 and r.json()['verified'] is False
    assert c.get('/api/mail/address').json()['outbound_available'] is False
    for _ in range(21):
        response=c.post('/api/mail/threads/1/reply',json={'body':'测试'})
    assert response.status_code==429



def test_verified_opt_in_smtp_delivery_and_failure(mailbox,monkeypatch):
    from app.services import mail
    c,login=mailbox;sent=[]
    monkeypatch.setattr(mail,'send_email',lambda conf,to,subject,body:sent.append((to,subject,body)))
    login(5)
    config={'host':'smtp.qq.com','port':587,'username':'test','password':'secret','from_address':'sender@example.com','enabled':True}
    assert c.post('/api/admin/mail/config',json=config).status_code==200
    assert not sent
    response=c.get('/api/admin/mail/config').json()
    assert 'password' not in response and response['password_configured']
    login(2)
    c.post('/api/mail/address',json={'email':'person@example.com','consent':True})
    assert c.post('/api/mail/address/send-code').json()['sent']
    code=sent[-1][2].split('：')[1].split('，')[0]
    assert c.post('/api/mail/address/verify',json={'code':'wrong'}).status_code==422
    assert c.post('/api/mail/address/verify',json={'code':code}).json()['verified']
    assert c.post('/api/mail/address/verify',json={'code':code}).status_code==422
    login(1)
    r=c.post('/api/mail/threads',json={'application_id':1,'subject':'联系','body':'职业机会','sync_email':True})
    assert r.json()['delivery']=='email_sent'
    assert sent[-1][0]=='person@example.com'
    def broken(*args):raise OSError('synthetic failure')
    monkeypatch.setattr(mail,'send_email',broken)
    r=c.post('/api/mail/threads',json={'application_id':1,'subject':'联系','body':'仍保留站内','sync_email':True})
    assert r.json()['delivery']=='email_failed' and r.json()['internal_delivered']
    login(2);assert c.get('/api/mail/inbox').json()['unread']==2
    c.post('/api/mail/address',json={'email':'new@example.com','consent':True})
    assert c.get('/api/mail/address').json()['verified'] is False

def test_smtp_rejects_private_dns_before_transport(monkeypatch):
    import socket
    from app.services import mail
    config={'host':'smtp.qq.com','port':587,'username':'test','password':'secret','from_address':'sender@example.com','enabled':True}
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',587))])
    with pytest.raises(ValueError,match='Nonpublic'):mail.send_email(config,'test@example.com','subject','body')

def test_revoked_application_cannot_receive_company_reply(mailbox):
    c,login=mailbox;login(1)
    tid=c.post('/api/mail/threads',json={'application_id':1,'subject':'联系','body':'你好'}).json()['id']
    with database.connect() as db:db.execute("UPDATE job_applications SET status='withdrawn' WHERE id=1")
    assert c.post(f'/api/mail/threads/{tid}/reply',json={'body':'继续联系'}).status_code==403
    assert c.post('/api/mail/threads',json={'application_id':1,'subject':'联系','body':'你好'}).status_code==403

def test_smtp_pins_public_address_and_requires_starttls(monkeypatch):
    import socket
    from app.services import mail
    calls=[]
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',587))])
    monkeypatch.setattr(socket,'create_connection',lambda dest,timeout:calls.append(('socket',dest)) or object())
    class Transport:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def connect(self,host,port):self._get_socket(host,port,12)
        def ehlo(self):calls.append(('ehlo',))
        def starttls(self,context):calls.append(('tls',self._host))
        def login(self,*args):calls.append(('login',))
        def send_message(self,message):calls.append(('message',message['To']))
    monkeypatch.setattr(mail.smtplib,'SMTP',Transport)
    mail.send_email({'host':'smtp.qq.com','port':587,'username':'x','password':'y','from_address':'sender@example.com','enabled':True},'recipient@example.com','主题','正文')
    assert calls[0]==('socket',('8.8.8.8',587))
    assert calls.index(('tls','smtp.qq.com'))<calls.index(('login',))
    assert calls[-1]==('message','recipient@example.com')

def test_subject_headers_and_verification_attempt_limit(mailbox,monkeypatch):
    from app.services import mail
    c,login=mailbox;login(5)
    assert c.post('/api/mail/threads',json={'recipient_id':2,'subject':'a\r\nBcc:x@example.com','body':'正文'}).status_code==422
    monkeypatch.setattr(mail,'send_email',lambda *args:None)
    c.post('/api/admin/mail/config',json={'host':'smtp.qq.com','port':587,'username':'x','password':'y','from_address':'a@example.com','enabled':True})
    login(2);c.post('/api/mail/address',json={'email':'b@example.com','consent':True});c.post('/api/mail/address/send-code')
    import hashlib,time
    with database.connect() as db:
        db.execute('UPDATE mail_addresses SET code_hash=?,code_expires=? WHERE user_id=2',(hashlib.sha256(b'2:123456').hexdigest(),int(time.time())+600))
    for _ in range(5):assert c.post('/api/mail/address/verify',json={'code':'000000'}).status_code==422
    assert c.post('/api/mail/address/verify',json={'code':'123456'}).status_code==422


def test_stale_identity_cannot_create_mail_after_data_reset(mailbox,monkeypatch):
    import app.mail_api as module
    c,login=mailbox;login(1);original=module.current
    def stale(request,*args):
        user=original(request,*args)
        with database.connect() as db:db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(user['id'],))
        return user
    monkeypatch.setattr(module,'current',stale)
    assert c.post('/api/mail/threads',json={'application_id':1,'subject':'联系','body':'过期请求'}).status_code==409

def test_mail_audit_contains_only_actions(mailbox,monkeypatch):
    from app.services import mail
    c,login=mailbox;login(5)
    c.post('/api/admin/mail/config',json={'host':'smtp.qq.com','port':587,'username':'x','password':'private-pass','from_address':'sender@example.com','enabled':True})
    login(1);tid=c.post('/api/mail/threads',json={'application_id':1,'subject':'private-subject','body':'private-body'}).json()['id']
    login(2);c.post(f'/api/mail/threads/{tid}/read');c.post(f'/api/mail/threads/{tid}/reply',json={'body':'private-reply'})
    c.post('/api/mail/address',json={'email':'private@example.com','consent':True})
    monkeypatch.setattr(mail,'send_email',lambda *args:None)
    c.post('/api/mail/address/send-code')
    with database.connect() as db:
        actions=[r[0] for r in db.execute('SELECT action FROM events')]
    assert {'mail_send','mail_reply','mail_read','mail_address_save','mail_smtp_save','mail_smtp_enabled','mail_code_sent','mail_delivery_internal'}<=set(actions)
    assert not any('private' in action or '@' in action for action in actions)

def test_failed_old_code_send_does_not_clear_new_code(mailbox,monkeypatch):
    from app.services import mail
    c,login=mailbox;login(5)
    c.post('/api/admin/mail/config',json={'host':'smtp.qq.com','port':587,'username':'x','password':'y','from_address':'sender@example.com','enabled':True})
    login(2);c.post('/api/mail/address',json={'email':'person@example.com'})
    def racing(*args):
        with database.connect() as db:db.execute("UPDATE mail_addresses SET code_hash='newer-digest' WHERE user_id=2")
        raise OSError('private transport details')
    monkeypatch.setattr(mail,'send_email',racing)
    response=c.post('/api/mail/address/send-code');assert response.status_code==502
    with database.connect() as db:
        assert db.execute('SELECT code_hash FROM mail_addresses WHERE user_id=2').fetchone()[0]=='newer-digest'
        assert db.execute("SELECT 1 FROM events WHERE action='mail_code_failed'").fetchone()

@pytest.mark.parametrize('change',["disabled=1","data_generation=data_generation+1"])
def test_longpoll_stops_after_account_change(mailbox,monkeypatch,change):
    import asyncio
    from fastapi import HTTPException
    import app.mail_api as module
    c,login=mailbox;login(2)
    with database.connect() as db:user=dict(db.execute('SELECT * FROM users WHERE id=2').fetchone())
    monkeypatch.setattr(module,'current',lambda request:user)
    original=asyncio.sleep
    async def changed(_):
        with database.connect() as db:db.execute('UPDATE users SET '+change+' WHERE id=2')
        await original(0)
    monkeypatch.setattr(module.asyncio,'sleep',changed)
    class Request:
        async def is_disconnected(self):return False
    with pytest.raises(HTTPException) as exc:asyncio.run(module.events(Request(),after=0,timeout=.05))
    assert exc.value.status_code in (401,409)

def test_mail_ui_reinitialization_ignores_stale_address_and_emits_state(tmp_path):
    import subprocess
    from pathlib import Path
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class E{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.className='';this.classList={add:()=>{},toggle:()=>{}};this.isConnected=true;}
append(...e){this.children.push(...e);}prepend(e){this.children.unshift(e);}replaceChildren(...e){this.children=e;}setAttribute(){}focus(){}
querySelector(s){return this.children.find(e=>s==='[data-unread]'?Object.hasOwn(e.dataset,'unread'):e.className===s.slice(1))||this.children.map(e=>e.querySelector(s)).find(Boolean)||null;}}
let state=[],timers=[],addressCalls=0,release,waiting;
global.window={dispatchEvent:e=>state.push(e.detail)};global.CustomEvent=class{constructor(name,options){this.detail=options.detail;}};
global.document={createElement:t=>new E(t)};global.setTimeout=f=>(timers.push(f),timers.length);global.clearTimeout=()=>{};
global.fetch=async(path,options)=>({ok:true,json:async()=>{
 if(path.endsWith('/auth/session'))return {csrf_token:'token'};
 if(path.endsWith('/auth/me'))return {user:{role:'user'}};
 if(path.includes('/mail/inbox'))return {items:[],cursor:0,unread:1};
 if(path.includes('/mail/events'))return {cursor:0,unread:2};
 if(path.endsWith('/mail/address')){addressCalls++;if(addressCalls===1)return await new Promise(resolve=>{release=()=>resolve({email:'stale@example.com',verified:true});waiting();});return {email:'',verified:false};}
 throw Error(path);
}});
vm.runInThisContext(fs.readFileSync(process.argv[2],'utf8'));
(async()=>{let ready=new Promise(r=>waiting=r),a=new E('div'),b=new E('div');const old=window.CareerMail.init(a);await ready;await window.CareerMail.init(b);release();await old;
 const all=e=>[e,...e.children.flatMap(all)];assert(!all(b).some(e=>e.value==='stale@example.com'));assert.equal(all(b).filter(e=>e.className==='mail-settings').length,1);
 assert(state.some(x=>x.unread===1));await timers.at(-1)();assert(state.some(x=>x.unread===2));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    harness=tmp_path/'mail-ui-check.cjs';harness.write_text(script,encoding='utf-8')
    result=subprocess.run(['node',str(harness),str(Path('static/mail-ui.js').resolve())],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr

def test_mail_admin_and_inbox_can_mount_concurrently(tmp_path):
    import subprocess
    from pathlib import Path
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class E{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.className='';this.classList={add:()=>{},toggle:()=>{}};this.isConnected=true;}
append(...e){this.children.push(...e);}prepend(e){this.children.unshift(e);}replaceChildren(...e){this.children=e;}setAttribute(){}focus(){}
querySelector(s){return this.children.find(e=>s==='[data-unread]'?Object.hasOwn(e.dataset,'unread'):e.className===s.slice(1))||this.children.map(e=>e.querySelector(s)).find(Boolean)||null;}}
global.window={dispatchEvent:()=>{}};global.CustomEvent=class{};global.document={createElement:t=>new E(t)};global.setTimeout=()=>1;global.clearTimeout=()=>{};
global.fetch=async(path)=>({ok:true,json:async()=>{
 if(path.endsWith('/auth/session'))return {csrf_token:'token'};
 if(path.endsWith('/auth/me'))return {user:{role:'admin'}};
 if(path.includes('/mail/inbox'))return {items:[],cursor:0,unread:0};
 if(path.endsWith('/mail/address'))return {email:'',verified:false};
 if(path.endsWith('/admin/mail/config'))return {host:'smtp.qq.com',port:587,enabled:false};
 throw Error(path);
}});
vm.runInThisContext(fs.readFileSync(process.argv[2],'utf8'));
(async()=>{const admin=new E('div'),inbox=new E('div');await Promise.all([window.MailAdminUI.init(admin),window.CareerMail.init(inbox)]);
 assert(admin.children.some(e=>e.tag==='form'),'SMTP configuration form must survive concurrent inbox initialization');
 assert(inbox.querySelector('.mail-settings'),'Inbox must also finish initialization');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    harness=tmp_path/'mail-concurrent-check.cjs';harness.write_text(script,encoding='utf-8')
    result=subprocess.run(['node',str(harness),str(Path('static/mail-ui.js').resolve())],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
