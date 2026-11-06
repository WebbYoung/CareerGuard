"""Enterprise documents are reviewed by the platform, never government-certified."""
import json
import re
import sqlite3
from email.parser import BytesParser
from email.policy import default
from pathlib import PurePath
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from . import config
from .api import Input, authorize, payload, compute, read_bytes
from .database import connect, cipher, event, password_hash
from .platform_api import current, rotate, public_user, write_guard
from .services import ocr

router = APIRouter(prefix='/api')
MAX_LICENSE = 8 * 1024 * 1024
CHARS = '0123456789ABCDEFGHJKLMNPQRTUWXY'
WEIGHTS = (1,3,9,27,19,26,16,17,20,29,25,13,8,24,10,30,28)


def valid_credit_code(code):
    return (len(code) == 18 and all(c in CHARS for c in code)
            and CHARS[(31-sum(CHARS.index(c)*w for c,w in zip(code[:17],WEIGHTS))%31)%31] == code[-1])


async def registration_form(request):
    """Bounded multipart parsing in memory; Starlette spooled uploads are not used."""
    content_type = request.headers.get('content-type','')
    if not content_type.lower().startswith('multipart/form-data;') or '\r' in content_type or '\n' in content_type:
        raise HTTPException(415,'请使用文件表单提交。')
    body = await read_bytes(request, MAX_LICENSE + 32768)
    try:
        header=content_type.encode('ascii')
    except UnicodeEncodeError:
        raise HTTPException(415,'上传表单头无效。') from None
    message = BytesParser(policy=default).parsebytes(b'Content-Type: '+header+b'\r\nMIME-Version: 1.0\r\n\r\n'+body)
    if not message.is_multipart() or message.defects:
        raise HTTPException(422,'上传表单无效。')
    fields, license_file = {}, None
    for part in message.iter_parts():
        name = part.get_param('name',header='content-disposition')
        if part.is_multipart() or part.defects or not name:
            raise HTTPException(422,'上传表单无效。')
        data = part.get_payload(decode=True)
        if not isinstance(data,bytes): raise HTTPException(422,'上传表单无效。')
        if name == 'license':
            if license_file is not None: raise HTTPException(422,'请仅上传一份营业执照。')
            license_file = (data, PurePath(part.get_filename() or '').suffix.lower(), part.get_content_type())
        else:
            if name not in {'username','password','name','credit_code','contact_role','acknowledgment'} or name in fields or len(data)>4096:
                raise HTTPException(422,'表单字段无效。')
            try: fields[name]=data.decode('utf-8')
            except UnicodeDecodeError: raise HTTPException(422,'表单编码无效。') from None
    if not license_file or set(fields) != {'username','password','name','credit_code','contact_role','acknowledgment'}:
        raise HTTPException(422,'请填写完整注册信息并上传营业执照。')
    return fields, license_file


def inspect_license(data,extension,content_type):
    if not data or len(data)>MAX_LICENSE: raise HTTPException(413,'营业执照大小需为1字节至8MB。')
    actual=ocr.validate_signature(data,extension,content_type)
    if actual!='pdf':
        ocr._image(data)
    else:
        import pypdfium2 as pdfium
        try:
            with pdfium.PdfDocument(data) as doc:
                if not 1 <= len(doc) <= config.MAX_PAGES: raise HTTPException(413,'PDF需为1至8页。')
                for i in range(len(doc)):
                    page=doc[i]
                    try:
                        w,h=page.get_size()
                        if w<=0 or h<=0 or w*h*4>config.MAX_PIXELS: raise HTTPException(413,'PDF页面尺寸超过限制。')
                    finally: page.close()
        except HTTPException: raise
        except Exception: raise HTTPException(415,'PDF损坏、已加密或无法解析。') from None


def license_notes(data,extension,content_type,name,code):
    notes={'source':'manual','message':'本地OCR未配置，需人工核对原件。','name_match':None,'credit_code_match':None,
           'disclaimer':'仅进行平台材料审核，不代表政府真实性认证。'}
    if not ocr.model_configured(): return notes
    try:
        result=ocr.parse_upload(data,extension,content_type)
        text=re.sub(r'\s+','',result['text'])
        codes=re.findall(r'[0-9A-Z]{18}',text.upper())
        name_match=re.search(r'(?:企业名称|名称)[：:]?([^\n]{2,100})',result['text'])
        notes.update(source='local_ocr',message='已识别本地文字，请结合原件人工审核。',name_match=re.sub(r'\s+','',name) in text,
                     credit_code_match=code in text.upper(),detected_credit_codes=codes[:8],
                     detected_name=name_match.group(1).strip() if name_match else None)
    except Exception:
        notes['message']='本地OCR未能完成，需人工核对原件。'
    return notes


def company_view(row):
    keys=('id','name','credit_code','contact_role','status','review_note','reviewed_at','created')
    return {**{k:row[k] for k in keys},'ocr_notes':json.loads(row['ocr_notes']),
            'license_url':f"/api/company/{row['id']}/license"}


def membership(db,user,approved=False):
    if user['role']!='company': raise HTTPException(403,'请使用企业账号登录。')
    row=db.execute('SELECT c.* FROM companies c JOIN company_memberships m ON m.company_id=c.id WHERE m.user_id=? AND m.role=?',(user['id'],'administrator')).fetchone()
    if not row: raise HTTPException(403,'没有企业管理权限。')
    if approved and row['status']!='approved': raise HTTPException(403,'企业须先通过平台材料审核才能提交岗位。')
    return row


@router.post('/company/register')
async def register(request:Request,response:Response):
    authorize(request)
    fields,(raw,ext,mime)=await registration_form(request)
    name=fields['name'].strip(); code=fields['credit_code'].strip().upper(); role=fields['contact_role'].strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-]{4,32}',fields['username']) or not 10<=len(fields['password'])<=128 or len(set(fields['password']))<5:
        raise HTTPException(422,'账号需4至32位字母数字、下划线或短横线；密码至少10位且包含5种不同字符。')
    if not 2<=len(name)<=160 or not 1<=len(role)<=100 or not valid_credit_code(code):
        raise HTTPException(422,'企业名称、联系人职务或统一社会信用代码格式/校验位无效。')
    if fields['acknowledgment']!='true': raise HTTPException(422,'需同意加密保存营业执照并供平台管理员审核。')
    await compute(inspect_license,raw,ext,mime)
    hashed=await compute(password_hash,fields['password'])
    notes=await compute(license_notes,raw,ext,mime,name,code)
    encrypted=cipher().encrypt(raw)
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            uid=db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'company')",(fields['username'],hashed)).lastrowid
            cid=db.execute('INSERT INTO companies(name,credit_code,contact_role,license_encrypted,license_type,ocr_notes) VALUES (?,?,?,?,?,?)',(name,code,role,encrypted,mime,json.dumps(notes,ensure_ascii=False))).lastrowid
            db.execute('INSERT INTO company_memberships(company_id,user_id) VALUES (?,?)',(cid,uid))
            event(db,uid,'company_submitted')
            user=public_user(db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    except sqlite3.IntegrityError: raise HTTPException(409,'账号或统一社会信用代码已注册。') from None
    return {'user':user,'company_id':cid,'status':'pending','csrf_token':rotate(request,response,uid)}


@router.get('/company/me')
async def me(request:Request):
    user=current(request)
    with connect() as db: return {'company':company_view(membership(db,user))}


@router.get('/company/jobs')
async def jobs(request:Request):
    user=current(request)
    with connect() as db:
        company=membership(db,user)
        rows=db.execute('SELECT j.* FROM jobs j JOIN job_company_links l ON l.job_id=j.id WHERE l.company_id=? ORDER BY j.id DESC LIMIT 500',(company['id'],)).fetchall()
    return {'items':[dict(r) for r in rows]}


class CompanyJob(Input):
    title:str=Field(min_length=1,max_length=160)
    description:str=Field(min_length=1,max_length=12000)


@router.post('/company/jobs')
async def create_job(request:Request):
    user=current(request); data=await payload(request,CompanyJob)
    if not data.title.strip() or not data.description.strip(): raise HTTPException(422,'请填写岗位标题与说明。')
    with connect() as db:
        write_guard(db,user); company=membership(db,user,True)
        jid=db.execute("INSERT INTO jobs(owner_id,title,company,description,recommended,status) VALUES (?,?,?,?,1,'pending')",(user['id'],data.title.strip(),company['name'],data.description.strip())).lastrowid
        db.execute('INSERT INTO job_company_links VALUES (?,?)',(jid,company['id']))
        event(db,user['id'],'company_job_submitted')
    return {'id':jid,'status':'pending'}


@router.put('/company/jobs/{jid}')
async def edit_job(jid:int,request:Request):
    user=current(request); data=await payload(request,CompanyJob)
    if not data.title.strip() or not data.description.strip(): raise HTTPException(422,'请填写岗位标题与说明。')
    with connect() as db:
        write_guard(db,user); company=membership(db,user,True)
        if not db.execute('SELECT 1 FROM job_company_links WHERE job_id=? AND company_id=?',(jid,company['id'])).fetchone(): raise HTTPException(404,'岗位不存在。')
        db.execute("UPDATE jobs SET title=?,description=?,company=?,active=1,status='pending',recommended=1,review_note='',reviewed_by=NULL,reviewed_at=NULL WHERE id=?",(data.title.strip(),data.description.strip(),company['name'],jid))
        event(db,user['id'],'company_job_updated')
    return {'id':jid,'status':'pending'}


@router.delete('/company/jobs/{jid}')
async def delete_job(jid:int,request:Request):
    user=current(request)
    with connect() as db:
        write_guard(db,user); company=membership(db,user)
        if not db.execute('SELECT 1 FROM job_company_links WHERE job_id=? AND company_id=?',(jid,company['id'])).fetchone(): raise HTTPException(404,'岗位不存在。')
        db.execute('UPDATE jobs SET active=0 WHERE id=?',(jid,)); event(db,user['id'],'company_job_offline')
    return {'ok':True}


@router.get('/admin/companies')
async def admin_companies(request:Request):
    current(request,True)
    with connect() as db: rows=db.execute("SELECT * FROM companies ORDER BY (status='pending') DESC,id DESC LIMIT 500").fetchall()
    return {'items':[company_view(row) for row in rows]}


class CompanyReview(Input):
    status:Literal['approved','rejected']
    note:str=Field(default='',max_length=2000)


@router.patch('/admin/companies/{cid}/review')
async def review(cid:int,request:Request):
    user=current(request,True); data=await payload(request,CompanyReview)
    if data.status=='rejected' and not data.note.strip(): raise HTTPException(422,'请填写退回原因。')
    with connect() as db:
        write_guard(db,user)
        if not db.execute('SELECT 1 FROM companies WHERE id=?',(cid,)).fetchone(): raise HTTPException(404,'企业不存在。')
        db.execute('UPDATE companies SET status=?,review_note=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(data.status,data.note.strip(),user['id'],cid))
        if data.status!='approved':
            db.execute("UPDATE jobs SET status='pending',review_note='企业材料未通过审核',reviewed_by=NULL,reviewed_at=NULL WHERE id IN (SELECT job_id FROM job_company_links WHERE company_id=?)",(cid,))
        event(db,user['id'],f'company_review_{data.status}:{cid}')
    return {'id':cid,'status':data.status}


@router.get('/admin/companies/{cid}/license')
@router.get('/company/{cid}/license')
async def license_original(cid:int,request:Request):
    user=current(request)
    if request.url.path.startswith('/api/admin/') and user['role']!='admin':
        raise HTTPException(403,'仅网站管理员可操作。')
    with connect() as db:
        if user['role']!='admin' and not db.execute('SELECT 1 FROM company_memberships WHERE company_id=? AND user_id=?',(cid,user['id'])).fetchone(): raise HTTPException(403,'无权查看营业执照。')
        row=db.execute('SELECT license_encrypted,license_type FROM companies WHERE id=?',(cid,)).fetchone()
        if not row: raise HTTPException(404,'企业不存在。')
        raw=cipher().decrypt(row['license_encrypted']); event(db,user['id'],f'company_license_view:{cid}')
    ext={'image/png':'png','image/jpeg':'jpg','application/pdf':'pdf'}[row['license_type']]
    return Response(raw,media_type=row['license_type'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':f'inline; filename="license-{cid}.{ext}"'})
