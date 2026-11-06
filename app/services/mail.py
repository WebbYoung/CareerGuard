"""Encrypted internal mail and opt-in SMTP. No transport runs when saving configuration."""
import hashlib
import ipaddress
import json
import os
import re
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from fastapi import HTTPException
from ..database import cipher

OFFICIAL_HOSTS={'smtp.qq.com','smtp.163.com','smtp.126.com','smtp.gmail.com','smtp.office365.com','smtp-mail.outlook.com','smtp.exmail.qq.com','smtp.feishu.cn','smtp.qiye.aliyun.com'}

def encrypt(text):return cipher().encrypt(text.encode())
def decrypt(blob):return cipher().decrypt(blob).decode()

def email_address(value):
    value=value.strip()
    if len(value)>254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}',value):
        raise HTTPException(422,'邮箱格式无效。')
    return value

def validate_config(data):
    host=data['host'].strip().lower().rstrip('.')
    allowed=OFFICIAL_HOSTS|{h.strip().lower() for h in os.getenv('SMTP_ALLOWED_HOSTS','').split(',') if h.strip()}
    if host not in allowed or data['port'] not in (465,587) or not re.fullmatch(r'[a-z0-9.-]+',host):
        raise HTTPException(422,'仅支持服务器允许的SMTP主机与465 SSL或587 STARTTLS。')
    try:ipaddress.ip_address(host)
    except ValueError:pass
    else:raise HTTPException(422,'SMTP必须使用允许的域名。')
    return {**data,'host':host,'from_address':email_address(data['from_address'])}

def smtp_config(db):
    row=db.execute("SELECT value FROM settings WHERE name='mail-smtp'").fetchone()
    return json.loads(decrypt(row['value'].encode())) if row else None

def send_email(config,to,subject,body):
    """Resolve once, reject every nonpublic address, pin the socket while retaining TLS SNI."""
    config=validate_config(config)
    if not config.get('enabled'):raise ValueError('SMTP disabled')
    addresses=socket.getaddrinfo(config['host'],config['port'],type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Nonpublic SMTP destination')
    address=addresses[0][4][0]
    context=ssl.create_default_context()
    class PinnedSMTP(smtplib.SMTP):
        def _get_socket(self,host,port,timeout):return socket.create_connection((address,port),timeout)
    class PinnedSSL(smtplib.SMTP_SSL):
        def _get_socket(self,host,port,timeout):
            raw=socket.create_connection((address,port),timeout)
            try:return context.wrap_socket(raw,server_hostname=config['host'])
            except Exception:raw.close();raise
    transport=PinnedSSL(context=context,timeout=12) if config['port']==465 else PinnedSMTP(timeout=12)
    transport._host=config['host']
    with transport as smtp:
        smtp.connect(config['host'],config['port']);smtp.ehlo()
        if config['port']==587:smtp.starttls(context=context);smtp.ehlo()
        smtp.login(config['username'],config['password'])
        message=EmailMessage();message['From']=config['from_address'];message['To']=email_address(to);message['Subject']=subject
        message.set_content(body)
        smtp.send_message(message)

def limit(db,uid,maximum=20):
    now=int(time.time())
    db.execute('DELETE FROM mail_actions WHERE created<?',(now-3600,))
    if db.execute('SELECT COUNT(*) FROM mail_actions WHERE user_id=? AND created>?',(uid,now-60)).fetchone()[0]>=maximum:
        raise HTTPException(429,'邮件操作过于频繁，请一分钟后重试。')
    db.execute('INSERT INTO mail_actions(user_id,created) VALUES (?,?)',(uid,now))

def application(db,aid,uid):
    row=db.execute('''SELECT a.*,l.company_id AS linked_company FROM job_applications a JOIN jobs j ON j.id=a.job_id JOIN job_company_links l ON l.job_id=j.id JOIN company_memberships m ON m.company_id=l.company_id JOIN companies c ON c.id=l.company_id WHERE a.id=? AND m.user_id=? AND c.status='approved' ''',(aid,uid)).fetchone()
    if not row or not row['share_resume'] or row['status']!='active' or row['company_id']!=row['linked_company']:
        raise HTTPException(403,'仅可联系主动投递本企业岗位并授权共享简历的求职者。')
    return row

def thread(db,tid,uid):
    row=db.execute('SELECT * FROM mail_threads WHERE id=?',(tid,)).fetchone()
    if not row or (uid not in (row['candidate_id'],row['creator_id']) and not db.execute('SELECT 1 FROM mail_messages WHERE thread_id=? AND (sender_id=? OR recipient_id=?)',(tid,uid,uid)).fetchone()):
        raise HTTPException(404,'邮件会话不存在。')
    return row

def deliver(mid,recipient,subject,body,sync):
    if not sync:return 'internal'
    from ..database import connect,event
    with connect() as db:
        row=db.execute('SELECT * FROM mail_addresses WHERE user_id=? AND verified=1 AND consent=1',(recipient,)).fetchone()
        conf=smtp_config(db)
    state='email_unavailable'
    if row and conf and conf.get('enabled'):
        try:send_email(conf,decrypt(row['email_encrypted']),subject,body);state='email_sent'
        except Exception:state='email_failed'
    with connect() as db:
        message=db.execute('SELECT sender_id FROM mail_messages WHERE id=?',(mid,)).fetchone()
        if message:
            db.execute('UPDATE mail_messages SET delivery=? WHERE id=?',(state,mid))
            event(db,message['sender_id'],'mail_delivery_'+state)
    return state
