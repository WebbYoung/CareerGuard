"""API 仅处理边界、权限与编排，业务逻辑在独立服务中。"""
import asyncio
import json
import secrets
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from starlette.concurrency import run_in_threadpool
from . import config
from .store import store
from .services import ocr, llm
from .services.security import inspect_injection, clean_text, classify_material
from .services.pii import detect_pii, redact
from .services.risk import assess_risk
from .services.classifier import predict_category
from .services.career import build_report

router = APIRouter(prefix='/api')
jobs = asyncio.Semaphore(2)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TextInput(Input):
    text: str = Field(min_length=1, max_length=config.MAX_TEXT)
    kind: Literal['auto','resume','recruitment','jd'] = 'auto'


class MaterialInput(Input):
    material_id: str = Field(min_length=1, max_length=64)


class CareerInput(Input):
    resume_id: str = Field(min_length=1, max_length=64)
    jd_id: str = Field(min_length=1, max_length=64)


class CheckInput(Input):
    text: str = Field(min_length=1, max_length=config.MAX_TEXT)


async def read_bytes(request: Request, maximum: int) -> bytes:
    """先限制 Content-Length，再逐块限制实际长度；不使用 UploadFile 的磁盘溢出缓存。"""
    length = request.headers.get('content-length')
    if length:
        try:
            declared = int(length)
        except ValueError:
            raise HTTPException(400, '无效的内容长度。') from None
        if declared < 0 or declared > maximum:
            raise HTTPException(413, '请求超过大小限制。')
    body = bytearray()
    async for part in request.stream():
        if len(body)+len(part) > maximum:
            raise HTTPException(413, '请求超过大小限制。')
        body.extend(part)
    return bytes(body)


async def payload(request: Request, schema):
    if request.headers.get('content-type','').split(';')[0] != 'application/json':
        raise HTTPException(415, '此接口只接受 JSON。')
    try:
        return schema.model_validate_json(await read_bytes(request, config.MAX_JSON))
    except (ValidationError, ValueError):
        # 不回显验证器中携带的原始敏感输入。
        raise HTTPException(422, '输入格式不正确、包含未知字段或超过文字长度限制。') from None


def authorize(request: Request):
    sid = request.cookies.get('cg_session')
    session = store.require(sid)
    if request.method not in {'GET','HEAD'}:
        token = request.headers.get('x-csrf-token','')
        if not token.isascii() or not secrets.compare_digest(token, session.csrf):
            raise HTTPException(403, '安全令牌无效，请刷新页面。')
    return sid, session.generation


def check_material(sid: str, text: str):
    detection = inspect_injection(text)
    if detection['blocked']:
        store.log(sid, 'injection_blocked', 'blocked')
        raise HTTPException(422, detection['message'])


async def compute(fn, *args):
    if jobs.locked():
        raise HTTPException(503, '分析任务繁忙，请等待当前任务完成。')
    async with jobs:
        return await run_in_threadpool(fn, *args)


@router.get('/session')
async def bootstrap(request: Request, response: Response):
    sid, session = store.bootstrap(request.cookies.get('cg_session'))
    from .platform_api import identity
    try:
        user=identity(request)
        store.bind(sid,user['id'])
    except HTTPException as exc:
        if exc.status_code!=401:raise
    response.set_cookie('cg_session', sid, httponly=True, samesite=config.COOKIE_SAMESITE,secure=config.COOKIE_SECURE, path='/')
    return {'csrf_token':session.csrf, 'ttl_minutes':config.SESSION_TTL//60,
            'limits':{'upload_mb':8,'pdf_pages':8,'text_chars':config.MAX_TEXT,'materials':24},
            'models':{'ocr':{'configured':ocr.model_configured(),'name':'PaddleOCR · PP-OCRv5'},
                      'llm':await run_in_threadpool(llm.status)}}


@router.get('/materials')
async def list_materials(request: Request):
    sid, _ = authorize(request)
    with store.lock:
        return {'items':[{'id':m['id'],'kind':m['kind'],'source':m['source'],'chars':len(m['text'])}
                         for m in store.require(sid).materials.values()]}


@router.get('/materials/{mid}')
async def get_material(mid: str, request: Request):
    sid, _ = authorize(request)
    return store.get(sid, mid)


@router.post('/materials/text')
async def text_material(request: Request):
    sid, generation = authorize(request)
    data = await payload(request, TextInput)
    check_material(sid, data.text)  # 清洗前检测，避免清洗掩盖攻击。
    text = clean_text(data.text)
    if not text:
        raise HTTPException(422, '材料清洗后为空，请补充有效文本。')
    check_material(sid, text)
    detected = classify_material(text)
    result = store.save(sid, generation, {'text':text,'kind':detected if data.kind=='auto' else data.kind,
                                        'detected_kind':detected,'source':'text','lines':[],'pages':0})
    store.log(sid, 'upload', count=1)
    return result


@router.post('/materials/upload')
async def upload(request: Request):
    sid, generation = authorize(request)
    content_type = request.headers.get('content-type','').split(';')[0].lower()
    extension = request.headers.get('x-file-extension','').lower()
    kind = request.headers.get('x-material-type','auto')
    if kind not in {'auto','resume','recruitment','jd'}:
        raise HTTPException(422, '材料类型无效。')
    try:
        raw = await read_bytes(request, config.MAX_UPLOAD)
        result = await compute(ocr.parse_upload, raw, extension, content_type)
        # raw 不进入 store；函数结束后释放引用。
        store.guard(sid, generation)
        check_material(sid, result['text'])
        text = clean_text(result['text'])
        detected = classify_material(text)
        result.update(text=text,kind=detected if kind=='auto' else kind,detected_kind=detected)
        saved = store.save(sid, generation, result)
        store.log(sid, 'upload', count=1)
        return saved
    except HTTPException as exc:
        with store.lock:
            store.guard(sid, generation)
            if exc.status_code != 422 or '系统行为' not in str(exc.detail):
                store.log(sid, 'upload_rejected', 'rejected')
        raise


@router.post('/privacy')
async def privacy(request: Request):
    sid, generation = authorize(request)
    data = await payload(request, MaterialInput)
    material = store.get(sid, data.material_id)
    fields = detect_pii(material['text'])
    masked = redact(material['text'], fields)
    store.log(sid, 'redact', count=len(fields))
    result={'fields':fields,'redacted_text':masked,
            'warning':'规则检测可能遗漏无标签地址、非标准格式或 OCR 错字。导出前请人工核对；脱敏仅导出文字，不是原图/PDF涂黑。'}
    save_analysis(sid,generation,data.material_id,'privacy',result)
    return result


def save_analysis(sid,generation,mid,kind,result):
    from .database import connect,encode
    with store.lock:
        session=store.guard(sid,generation)
        if not session.user_id:return
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            account=db.execute('SELECT data_generation,disabled FROM users WHERE id=?',(session.user_id,)).fetchone()
            if not account or account['disabled'] or account['data_generation']!=session.data_generation:
                raise HTTPException(409,'资料已删除，本次结果未保存。')
            db.execute('INSERT INTO analyses VALUES (?,?,?,?) ON CONFLICT(user_id,material_id,kind) DO UPDATE SET content=excluded.content',
                       (session.user_id,mid,kind,encode(result)))


@router.post('/materials/{mid}/export')
async def export(mid: str, request: Request):
    sid, _ = authorize(request)
    material = store.get(sid, mid)
    masked = redact(material['text'])
    store.log(sid, 'export', count=1)
    return Response(masked, media_type='text/plain; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="redacted-material.txt"'})


@router.post('/risk')
async def risk(request: Request):
    sid, generation = authorize(request)
    data = await payload(request, MaterialInput)
    text = store.get(sid, data.material_id)['text']
    check_material(sid, text)
    result = assess_risk(text)
    result['classification'] = await compute(predict_category, redact(text))
    evidence = {f['id']: {'category':f['category'],'quote':redact(f['quote']),'advice':f['advice']} for f in result['findings']}
    result['llm'] = await compute(llm.explain, '招聘风险提示与核验建议', text, evidence)
    save_analysis(sid,generation,data.material_id,'risk',result)
    with store.lock:
        store.guard(sid, generation)
        store.log(sid, 'risk', count=len(result['findings']))
    return result


@router.post('/career')
async def career(request: Request):
    sid, generation = authorize(request)
    data = await payload(request, CareerInput)
    cv = store.get(sid, data.resume_id)
    jd = store.get(sid, data.jd_id)
    if cv['kind'] != 'resume' or jd['kind'] != 'jd':
        raise HTTPException(422, '请选择一份简历和一份岗位 JD。')
    check_material(sid, cv['text'])
    check_material(sid, jd['text'])
    result = build_report(redact(cv['text']), redact(jd['text']))
    evidence = {s['id']:s for s in result['sources']}
    evidence['JD'] = {'requirements':result['requirements'],'unknown':result['unknown_requirements']}
    result['llm'] = await compute(llm.explain, '基于岗位证据给出能力补充与四周学习建议',
                                  redact(cv['text'])+'\n岗位JD：'+redact(jd['text']), evidence)
    with store.lock:
        store.guard(sid, generation)
        session=store.require(sid)
        if session.user_id:
            from .database import connect,encode
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                account=db.execute('SELECT data_generation,disabled FROM users WHERE id=?',(session.user_id,)).fetchone()
                if not account or account['disabled'] or account['data_generation']!=session.data_generation:
                    raise HTTPException(409,'资料已删除，本次报告未保存。')
                db.execute('INSERT INTO career_reports(user_id,content) VALUES (?,?)',(session.user_id,encode({**result,'resume_id':data.resume_id,'jd_id':data.jd_id})))
        store.log(sid, 'career', count=len(result['gaps']))
    return result


@router.post('/security/check')
async def security_check(request: Request):
    from .platform_api import current
    current(request, admin=True)
    sid, _ = authorize(request)
    data = await payload(request, CheckInput)
    result = inspect_injection(data.text)
    store.log(sid, 'injection_blocked' if result['blocked'] else 'security_check', 'blocked' if result['blocked'] else 'ok')
    return result


@router.get('/audit')
async def audit(request: Request):
    sid, _ = authorize(request)
    with store.lock:
        return {'items':list(store.require(sid).audit)}


@router.delete('/materials/{mid}')
async def delete_material(mid: str, request: Request):
    sid, _ = authorize(request)
    with store.lock:
        session = store.require(sid)
        if mid not in session.materials:
            raise HTTPException(404, '材料不存在。')
        del session.materials[mid]
        if session.user_id:
            from .database import connect
            with connect() as db:
                db.execute('DELETE FROM materials WHERE id=? AND user_id=?',(mid,session.user_id))
                db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(session.user_id,))
                session.data_generation=db.execute('SELECT data_generation FROM users WHERE id=?',(session.user_id,)).fetchone()[0]
        session.generation += 1
        store.log(sid, 'delete', count=1)
    return {'deleted':True}


@router.delete('/session/data')
async def clear(request: Request):
    sid, _ = authorize(request)
    return {'cleared':store.clear(sid), 'message':'材料与历史审计已清空，仅保留本次清空的无内容记录。'}
