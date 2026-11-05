"""仅接收已同意的本机JPEG帧，所有权与CSRF校验，不写图片到数据库。"""
import time
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from .api import Input,payload,read_bytes,compute
from .platform_api import current
from .services import vision

router=APIRouter(prefix='/api/vision')


class Start(Input):
    consent:bool=False
    sensitivity:Literal['relaxed','standard','strict']='standard'


@router.get('/status')
async def status(request:Request):
    current(request)
    return vision.model_status()


@router.post('/session')
async def start(request:Request):
    user=current(request);data=await payload(request,Start)
    if not data.consent:raise HTTPException(422,'请先同意摄像头画面分析。')
    if not vision.model_status()['ready']:raise HTTPException(503,'镜头分析暂不可用，请联系管理员。')
    return vision.monitors.create(user['id'],data.sensitivity)


def owned(request,mid):
    user=current(request)
    return vision.monitors.require(mid,user['id'],request.headers.get('x-vision-token',''))


@router.post('/{mid}/frame')
async def frame(mid:str,request:Request):
    monitor=owned(request,mid)
    if request.headers.get('content-type','').split(';')[0]!='image/jpeg':raise HTTPException(415,'摄像头帧只接受JPEG。')
    raw=await read_bytes(request,vision.MAX_FRAME_BYTES)
    with vision.monitors.lock:
        if monitor.busy or time.monotonic()-monitor.last_at<.18:raise HTTPException(429,'帧率过高，请降低采样频率。')
        monitor.busy=True;monitor.touched=time.monotonic()
    try:
        observation=await compute(vision.infer,raw)
        with vision.monitors.lock:
            current=owned(request,mid)
            if current is not monitor:raise HTTPException(409,'摄像头监测已更新，旧结果已丢弃。')
            monitor.last_at=time.monotonic();monitor.touched=monitor.last_at;monitor.observation=observation
            return monitor.tracker.update(observation,monitor.last_at)
    finally:monitor.busy=False


@router.post('/{mid}/calibrate')
async def calibrate(mid:str,request:Request):
    with vision.monitors.lock:
        monitor=owned(request,mid)
        if not monitor.observation or time.monotonic()-monitor.last_at>2:raise HTTPException(409,'请等待实时画面识别后再校准。')
        monitor.tracker.calibrate(monitor.observation)
    return {'ok':True,'message':'已校准当前正面朝向。'}


@router.delete('/{mid}')
async def stop(mid:str,request:Request):
    with vision.monitors.lock:
        owned(request,mid);del vision.monitors.items[mid]
    return {'ok':True}
