"""Admin-only model settings and explicitly indexed shared knowledge."""
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import Field
from .api import Input, payload, compute, read_bytes
from .platform_api import current
from .services import model_gateway as gateway, rag

router=APIRouter(prefix='/api/admin')
Kind=Literal['chat','embedding','image']

class SettingsInput(Input):
    kind: Kind='chat'
    provider: str=Field(default='openai',max_length=120)
    protocol: Literal['openai','anthropic','ollama']='openai'
    base_url: str=Field(max_length=400)
    model: str=Field(max_length=120)
    api_key: str=Field(default='',max_length=2048)
    dimensions: int | None=Field(default=None,ge=1,le=65536)

class DocumentInput(Input):
    title: str=Field(min_length=1,max_length=120)
    content: str=Field(min_length=1,max_length=100000)

async def work(fn,*args):
    try: return await compute(fn,*args)
    except (ValueError,gateway.GatewayError) as exc:
        raise HTTPException(422,str(exc) if not isinstance(exc,gateway.GatewayError) else exc.safe_message) from None
    except LookupError: raise HTTPException(404,'知识文档不存在。') from None

@router.get('/ai-settings')
async def settings(request:Request,kind:Kind='chat'):
    current(request,True)
    return gateway.status(kind)

@router.get('/ai-settings/{kind}')
async def settings_kind(kind:Kind,request:Request):
    return await settings(request,kind)

@router.put('/ai-settings')
async def save(request:Request):
    current(request,True)
    data=await payload(request,SettingsInput)
    return await work(gateway.save_settings,data.kind,data.model_dump(exclude={'kind'}))

@router.put('/ai-settings/{kind}')
async def save_kind(kind:Kind,request:Request):
    current(request,True)
    data=await payload(request,SettingsInput)
    return await work(gateway.save_settings,kind,data.model_dump(exclude={'kind'}))

@router.get('/knowledge')
async def knowledge(request:Request):
    current(request,True)
    return {'documents':await compute(rag.documents),'state':await compute(rag.state)}

@router.get('/knowledge/state')
async def knowledge_state(request:Request):
    current(request,True)
    return await compute(rag.state)

@router.post('/knowledge')
async def add_document(request:Request):
    current(request,True);data=await payload(request,DocumentInput)
    return await work(rag.save_document,data.title,data.content)

@router.put('/knowledge/{document_id:int}')
async def edit_document(document_id:int,request:Request):
    current(request,True);data=await payload(request,DocumentInput)
    return await work(rag.save_document,data.title,data.content,document_id)

@router.delete('/knowledge/{document_id:int}')
async def remove_document(document_id:int,request:Request):
    current(request,True)
    return await work(rag.delete_document,document_id)

@router.post('/knowledge/upload')
async def upload_document(request:Request):
    current(request,True)
    # Raw UTF-8 text only; never remote URL fetching, never resume ingestion.
    if request.headers.get('content-type','').split(';')[0] not in ('text/plain','text/markdown'): raise HTTPException(415,'请上传UTF-8 TXT或Markdown文本。')
    raw=await read_bytes(request,100000)
    try: content=raw.decode('utf-8-sig')
    except UnicodeDecodeError: raise HTTPException(422,'文件必须采用UTF-8编码。') from None
    return await work(rag.save_document,request.headers.get('x-document-title','知识文档')[:120],content)

@router.post('/knowledge/index')
async def index(request:Request):
    current(request,True)
    return await work(rag.build_index)
