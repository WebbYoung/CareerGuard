"""Encrypted, account-scoped conversations with optimistic concurrency and wipe guards."""
import json
import secrets
from fastapi import APIRouter,Request,HTTPException
from pydantic import Field
from .api import Input,payload,compute
from .database import connect,cipher,event
from .platform_api import current,write_guard
from .services import assistant,model_gateway

router=APIRouter(prefix='/api/assistant')
class Message(Input):
    message:str=Field(min_length=1,max_length=4000)
    consent:bool=False
    allow_profile:bool=False

def owned(db,sid,user):
    row=db.execute('SELECT * FROM assistant_threads WHERE id=? AND user_id=?',(sid,user['id'])).fetchone()
    if not row:raise HTTPException(404,'对话不存在')
    return row

def decode_history(row):
    try:
        history=json.loads(cipher().decrypt(row['content'].encode()))
        if not isinstance(history,list) or len(history)>80 or any(not isinstance(m,dict) or m.get('role') not in ('user','assistant') or not isinstance(m.get('content'),str) or len(m['content'])>16000 for m in history):raise ValueError()
        return [{'role':m['role'],'content':m['content']} for m in history]
    except Exception:
        raise HTTPException(409,'对话记录不可读取，请删除后新建对话') from None

@router.get('/threads')
async def list_threads(request:Request):
    user=current(request)
    with connect() as db:
        rows=db.execute('SELECT id,revision,created,updated FROM assistant_threads WHERE user_id=? ORDER BY updated DESC,rowid DESC LIMIT 20',(user['id'],)).fetchall()
    return {'items':[dict(row) for row in rows]}

@router.get('/threads/{sid}')
async def get_thread(sid:str,request:Request):
    user=current(request)
    with connect() as db:row=owned(db,sid,user)
    return {'id':row['id'],'revision':row['revision'],'created':row['created'],'updated':row['updated'],'messages':decode_history(row)}

@router.post('/threads')
async def create(request:Request):
    user=current(request);sid=secrets.token_urlsafe(18)
    with connect() as db:
        write_guard(db,user)
        if db.execute('SELECT COUNT(*) FROM assistant_threads WHERE user_id=?',(user['id'],)).fetchone()[0]>=100:raise HTTPException(409,'请先清理旧对话')
        db.execute('INSERT INTO assistant_threads(id,user_id,content) VALUES(?,?,?)',(sid,user['id'],cipher().encrypt(b'[]').decode()))
    return {'id':sid}

@router.delete('/threads/{sid}')
async def delete(sid:str,request:Request):
    user=current(request)
    with connect() as db:
        write_guard(db,user);owned(db,sid,user)
        db.execute('DELETE FROM assistant_threads WHERE id=?',(sid,));event(db,user['id'],'assistant_delete')
    return {'deleted':True}

@router.post('/threads/{sid}/messages')
async def message(sid:str,request:Request):
    user=current(request);data=await payload(request,Message)
    if not data.message.strip():raise HTTPException(422,'请输入问题')
    with connect() as db:row=owned(db,sid,user)
    history=decode_history(row)
    if len(history)>=80:raise HTTPException(409,'本段对话已达40轮，请新建对话')
    try:result=await compute(assistant.reply,history,data.message,user['id'],data.consent,data.allow_profile,user['data_generation'])
    except model_gateway.GatewayError as exc:raise HTTPException(503,exc.safe_message) from None
    history.extend([{'role':'user','content':data.message},{'role':'assistant','content':result['text']}])
    with connect() as db:
        write_guard(db,user)
        changed=db.execute('UPDATE assistant_threads SET content=?,revision=revision+1,updated=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND revision=?',(cipher().encrypt(json.dumps(history,ensure_ascii=False).encode()).decode(),sid,user['id'],row['revision'])).rowcount
        if not changed:raise HTTPException(409,'对话已更新或删除，请重新开始')
        event(db,user['id'],'assistant_message')
    return result
