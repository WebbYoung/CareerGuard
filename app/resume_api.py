"""Account-owned encrypted resume sessions; never persist original selfies."""
import json
import secrets
from email.parser import BytesParser
from email.policy import default
from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import Field
from .api import Input,payload,compute,read_bytes
from .database import connect,cipher,encode,event
from .platform_api import current,write_guard
from .services import resume_builder as builder

router=APIRouter(prefix='/api/resume')

class Create(Input):
    title:str=Field(default='我的求职简历',max_length=80)
class Message(Input):
    message:str=Field(min_length=1,max_length=4000)
    consent:bool=False
class Edit(Input):
    draft:builder.Draft
class Polish(Input):
    consent:bool=False

def owned(db,sid,user):
    row=db.execute('SELECT * FROM resume_sessions WHERE id=? AND user_id=?',(sid,user['id'])).fetchone()
    if row is None:raise HTTPException(404,'简历不存在或已删除。')
    return row
def decode(row):return json.loads(cipher().decrypt(row['content'].encode()))
def view(row):
    value=decode(row)
    return dict(value,id=row['id'],created=row['created'],updated=row['updated'],revision=row['revision'],has_portrait=bool(row['portrait']),missing_facts=builder.missing_facts(value['draft']))
def encrypted(value):return cipher().encrypt(encode(value).encode()).decode()
def save(sid,user,value,revision,action=None):
    with connect() as db:
        write_guard(db,user)
        changed=db.execute('UPDATE resume_sessions SET content=?,revision=revision+1,updated=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND revision=?',(encrypted(value),sid,user['id'],revision)).rowcount
        if not changed:raise HTTPException(409,'简历已更新或删除，请重新打开后再操作。')
        if action:event(db,user['id'],action)
        return view(owned(db,sid,user))

@router.get('/sessions')
async def sessions(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT * FROM resume_sessions WHERE user_id=? ORDER BY updated DESC LIMIT 100',(user['id'],)).fetchall()
    return {'items':[{'id':r['id'],'title':decode(r).get('title','我的求职简历'),'updated':r['updated']} for r in rows]}

@router.post('/sessions')
async def create(request:Request):
    user=current(request);data=await payload(request,Create)
    value=builder.new_session();value['title']=data.title
    sid=secrets.token_urlsafe(18)
    with connect() as db:
        write_guard(db,user)
        if db.execute('SELECT COUNT(*) FROM resume_sessions WHERE user_id=?',(user['id'],)).fetchone()[0]>=100:raise HTTPException(409,'最多保存100份简历，请先删除旧简历。')
        db.execute('INSERT INTO resume_sessions(id,user_id,content) VALUES (?,?,?)',(sid,user['id'],encrypted(value)))
        event(db,user['id'],'resume_create')
        return view(owned(db,sid,user))

@router.get('/sessions/{sid}')
async def get(sid:str,request:Request):
    user=current(request)
    with connect() as db:return view(owned(db,sid,user))

@router.delete('/sessions/{sid}')
async def delete(sid:str,request:Request):
    user=current(request)
    with connect() as db:
        write_guard(db,user);owned(db,sid,user)
        db.execute('DELETE FROM resume_sessions WHERE id=? AND user_id=?',(sid,user['id']))
        event(db,user['id'],'resume_delete')
    return {'deleted':True}

@router.post('/sessions/{sid}/message')
async def message(sid:str,request:Request):
    user=current(request);data=await payload(request,Message)
    if not data.message.strip():raise HTTPException(422,'请填写有效内容。')
    with connect() as db:row=owned(db,sid,user)
    value=decode(row)
    if len(value['messages'])>=80:raise HTTPException(409,'对话已达40轮，请在编辑区继续修改。')
    result=await compute(builder.collect,value,data.message.strip(),data.consent)
    return save(sid,user,result,row['revision'])

@router.put('/sessions/{sid}/draft')
async def edit(sid:str,request:Request):
    user=current(request);data=await payload(request,Edit)
    with connect() as db:row=owned(db,sid,user)
    value=decode(row);value['draft']=data.draft.model_dump()
    value['title']=value['draft']['goal'][:70] or value.get('title','我的求职简历')
    value['next_field']=next((k for k in builder.QUESTIONS if not value['draft'].get(k) and k not in value['collected']),None)
    return save(sid,user,value,row['revision'],'resume_draft_update')

@router.post('/sessions/{sid}/polish')
async def polish(sid:str,request:Request):
    user=current(request);data=await payload(request,Polish)
    if not data.consent:raise HTTPException(422,'请同意本次将简历事实发送至 AI 进行个性化整理。')
    with connect() as db:row=owned(db,sid,user)
    value=decode(row);proposal=await compute(builder.polish,value)
    value['proposal']=proposal
    # Source snapshots are retained separately even after an explicitly applied proposal.
    value.setdefault('original_facts',[])
    value['original_facts']=(value['original_facts']+[proposal['source_facts']])[-12:]
    result=save(sid,user,value,row['revision'],'resume_polish')
    return result

@router.get('/sessions/{sid}/export.docx')
async def export(sid:str,request:Request):
    user=current(request)
    with connect() as db:row=owned(db,sid,user)
    data=await compute(builder.export_docx,decode(row)['draft'],cipher().decrypt(row['portrait']) if row['portrait'] else None)
    with connect() as db:
        write_guard(db,user);owned(db,sid,user);event(db,user['id'],'resume_export')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':'attachment; filename="resume.docx"','Cache-Control':'no-store'})

def multipart(raw,content_type):
    # Parse bounded bytes in memory, avoiding UploadFile's disk-spooling behavior.
    if '\r' in content_type or '\n' in content_type:raise HTTPException(400,'无效请求。')
    msg=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
    if not msg.is_multipart():raise HTTPException(415,'请使用 multipart/form-data 上传。')
    result={}
    for part in msg.iter_parts():
        name=part.get_param('name',header='content-disposition')
        if name not in {'file','size','background','consent'} or name in result:raise HTTPException(422,'上传字段无效。')
        value=part.get_payload(decode=True)
        if value is None:raise HTTPException(422,'上传内容无效。')
        if name!='file' and len(value)>80:raise HTTPException(422,'字段过长。')
        try:result[name]=value if name=='file' else value.decode('utf-8')
        except UnicodeError:raise HTTPException(422,'字段编码无效。') from None
    return result

@router.post('/sessions/{sid}/portrait')
async def portrait(sid:str,request:Request):
    user=current(request)
    with connect() as db:row=owned(db,sid,user)
    fields=multipart(await read_bytes(request,8*1024*1024+16384),request.headers.get('content-type',''))
    if fields.get('consent')!='true':raise HTTPException(422,'请明确同意本次照片发送与处理。')
    processed=await compute(builder.portrait,fields.get('file',b''),fields.get('size','1inch'),fields.get('background','white'))
    with connect() as db:
        write_guard(db,user)
        changed=db.execute('UPDATE resume_sessions SET portrait=?,revision=revision+1,updated=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND revision=?',(cipher().encrypt(processed),sid,user['id'],row['revision'])).rowcount
        if not changed:raise HTTPException(409,'简历已更新或删除，照片未保存，请重试。')
        event(db,user['id'],'resume_portrait_generate')
    return {'saved':True,'notice':'已加密保存处理后的证件照，原自拍未保存。请核对相貌与证件用途要求。'}

@router.get('/sessions/{sid}/portrait')
async def get_portrait(sid:str,request:Request):
    user=current(request)
    with connect() as db:row=owned(db,sid,user)
    if not row['portrait']:raise HTTPException(404,'尚未生成证件照。')
    return Response(cipher().decrypt(row['portrait']),media_type='image/png',headers={'Cache-Control':'no-store'})
