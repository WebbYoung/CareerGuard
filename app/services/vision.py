"""本机几何提示：仅人脸朝向、位置与手部位移，不做人脸身份或心理推断。

图像只作为单次推理输入，不写入材料表、日志、文件或LLM请求。
跨帧仅保留最多4秒的几何数值，监测停止或过期后释放。
"""
import importlib.util
import io
import math
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from ..config import ROOT

MODEL_DIR=ROOT/'models'/'vision'
MAX_FRAME_BYTES=450000
_model_lock=threading.RLock()
_models=None


def model_status():
    ready=importlib.util.find_spec('mediapipe') is not None and all((MODEL_DIR/n).is_file() for n in ('face_landmarker.task','hand_landmarker.task'))
    return {'ready':ready,'model':'MediaPipe Face Landmarker + Hand Landmarker',
            'message':'镜头分析已就绪。' if ready else '镜头分析暂不可用，请联系管理员。',
            'processing':'local','stores_video':False,'identity_recognition':False}


def decode_frame(raw):
    if len(raw)>MAX_FRAME_BYTES:raise HTTPException(413,'摄像头帧超过大小限制。')
    if not raw.startswith(b'\xff\xd8\xff'):raise HTTPException(415,'摄像头帧必须为JPEG。')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            w,h=image.size
            if image.format!='JPEG':raise HTTPException(415,'摄像头帧必须为JPEG。')
            if w<120 or h<90 or w>1280 or h>960 or w*h>1228800:
                raise HTTPException(413,'摄像头分辨率不符合限制。')
            image.load()
            return np.ascontiguousarray(image.convert('RGB'))
    except HTTPException:raise
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(415,'摄像头帧无法解码。') from None


def euler_angles(matrix):
    a=np.asarray(matrix,dtype=float)
    if a.shape!=(4,4) or not np.isfinite(a).all():raise ValueError('invalid transform')
    u,_,vt=np.linalg.svd(a[:3,:3]);rotation=u@vt
    if np.linalg.det(rotation)<0:
        u[:,-1]*=-1;rotation=u@vt
    sy=math.hypot(rotation[0,0],rotation[1,0])
    return {'yaw':round(math.degrees(math.atan2(-rotation[2,0],sy)),1),
            'pitch':round(math.degrees(math.atan2(rotation[2,1],rotation[2,2])),1),
            'roll':round(math.degrees(math.atan2(rotation[1,0],rotation[0,0])),1)}


def _get_models():
    global _models
    if _models is not None:return _models
    if not model_status()['ready']:raise HTTPException(503,'镜头分析暂不可用。')
    try:
        import mediapipe as mp
        base=mp.tasks.BaseOptions
        tasks=mp.tasks.vision
        face=tasks.FaceLandmarker.create_from_options(tasks.FaceLandmarkerOptions(
            base_options=base(model_asset_buffer=(MODEL_DIR/'face_landmarker.task').read_bytes()),
            running_mode=tasks.RunningMode.IMAGE,num_faces=2,
            min_face_detection_confidence=.6,min_face_presence_confidence=.6,
            output_face_blendshapes=False,output_facial_transformation_matrixes=True))
        try:
            hands=tasks.HandLandmarker.create_from_options(tasks.HandLandmarkerOptions(
                base_options=base(model_asset_buffer=(MODEL_DIR/'hand_landmarker.task').read_bytes()),
                running_mode=tasks.RunningMode.IMAGE,num_hands=2,
                min_hand_detection_confidence=.6,min_hand_presence_confidence=.6))
        except Exception:
            face.close();raise
        _models=(mp,face,hands)
    except HTTPException:raise
    except Exception:raise HTTPException(503,'镜头分析加载失败，请联系管理员。') from None
    return _models


def infer(raw):
    rgb=decode_frame(raw)
    started=time.perf_counter()
    with _model_lock:
        mp,face_model,hand_model=_get_models()
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb)
        faces=face_model.detect(image);hands=hand_model.detect(image)
    result={'face_count':len(faces.face_landmarks),'face':None,'hands':[]}
    if len(faces.face_landmarks)==1:
        points=faces.face_landmarks[0]
        xs=[p.x for p in points];ys=[p.y for p in points]
        box=[float(np.clip(v,0,1)) for v in (min(xs),min(ys),max(xs),max(ys))]
        result['face']={'box':box,'center':[(box[0]+box[2])/2,(box[1]+box[3])/2],
                        'width':box[2]-box[0],'height':box[3]-box[1],
                        'angles':euler_angles(faces.facial_transformation_matrixes[0])}
    for hand in hands.hand_landmarks:
        points=[[round(float(p.x),4),round(float(p.y),4)] for p in hand]
        result['hands'].append({'points':points,'center':np.mean(points,axis=0).tolist()})
    result['inference_ms']=round((time.perf_counter()-started)*1000,1)
    return result


MESSAGES={
 'face_missing':'未检测到清晰人脸，请回到镜头内并检查光线。',
 'multiple_faces':'画面中检测到多张人脸，请保持单人入镜。',
 'off_center':'人脸偏离画面中心，请调整坐姿或摄像头位置。',
 'face_size':'请调整与摄像头的距离，让脸部完整清晰地入镜。',
 'turned_head':'头部朝向偏离，请自然回正、面向摄像头。',
 'head_motion':'画面中的头部位置持续移动，可尝试放稳摄像头并减少晃动。',
 'hand_near_face':'手部进入脸部画面区域，可将手自然放低。',
 'hand_motion':'检测到连续手部位移，可尝试减少重复动作。',
}


class VisionTracker:
    def __init__(self,sensitivity='standard'):
        self.sensitivity=sensitivity
        self.history=deque(maxlen=30)
        self.since={}
        self.baseline={'yaw':0,'pitch':0,'roll':0}
        self.calibrated=False

    def calibrate(self,observation):
        face=observation.get('face')
        if observation.get('face_count')!=1 or not face:
            raise HTTPException(409,'请先保持单张清晰人脸入镜。')
        angles=face['angles'];cx,cy=face['center']
        if any(abs(angles[k])>30 for k in angles) or not (.25<cx<.75 and .15<cy<.8):
            raise HTTPException(409,'请正对镜头并居中，再进行校准。')
        self.baseline=dict(angles);self.calibrated=True;self.history.clear();self.since.clear()

    def update(self,observation,now=None):
        now=time.monotonic() if now is None else now
        yaw,pitch,roll,hold,rate={'relaxed':(35,30,25,3,2.2),'standard':(25,25,20,2,1.4),'strict':(18,18,15,1.4,1)}[self.sensitivity]
        flags=set();face=observation.get('face');count=observation['face_count'];angles=None
        if count==0:flags.add('face_missing')
        elif count>1:flags.add('multiple_faces')
        elif face:
            cx,cy=face['center'];width=face['width']
            if not (.2<cx<.8 and .12<cy<.82):flags.add('off_center')
            if width<.12 or width>.72:flags.add('face_size')
            angles={k:round((face['angles'][k]-self.baseline[k]+180)%360-180,1) for k in self.baseline}
            if abs(angles['yaw'])>yaw or abs(angles['pitch'])>pitch or abs(angles['roll'])>roll:flags.add('turned_head')
            x0,y0,x1,y1=face['box']
            if any(any(x0-.03<x<x1+.03 and y0-.03<y<y1+.03 for x,y in h['points']) for h in observation['hands']):flags.add('hand_near_face')
            self.history.append((now,face['center'],max(width,.1),observation['hands']))
            while self.history and now-self.history[0][0]>4:self.history.popleft()
            if len(self.history)>=4 and now-self.history[0][0]>=1.2:
                positions=np.asarray([r[1] for r in self.history]);scale=float(np.median([r[2] for r in self.history]))
                # 仅检测画面坐标位移，不能区分摄像头移动、自然手势或个人原因。
                if float(np.linalg.norm(np.ptp(positions,axis=0)))/scale>.42:flags.add('head_motion')
                travel=0.;duration=0.
                for before,after in zip(self.history,list(self.history)[1:]):
                    dt=after[0]-before[0]
                    if dt<=0 or dt>1.5 or not before[3] or not after[3]:continue
                    for hand in after[3]:
                        prev=min(before[3],key=lambda h:np.linalg.norm(np.array(h['center'])-hand['center']))
                        if np.linalg.norm(np.array(prev['center'])-hand['center'])>.4:continue
                        travel+=float(np.mean(np.linalg.norm(np.asarray(hand['points'])-prev['points'],axis=1)))/scale
                    duration+=dt
                if duration>1 and travel/duration>rate:flags.add('hand_motion')
        if count!=1:self.history.clear()
        for flag in list(self.since):
            if flag not in flags:del self.since[flag]
        for flag in flags:self.since.setdefault(flag,now)
        alerts=sorted(f for f in flags if now-self.since[f]>=hold)
        return {'status':'adjust' if alerts else 'observing' if flags else 'ok',
                'alerts':alerts,'hints':[MESSAGES[f] for f in alerts],
                'face_count':count,'face_box':face['box'] if face and count==1 else None,
                'angles':angles,'hands':observation['hands'],'calibrated':self.calibrated,
                'thresholds':{'yaw':yaw,'pitch':pitch,'roll':roll,'hold_seconds':hold},
                'inference_ms':observation.get('inference_ms',0),
                'note':'仅为画面几何提示，不用于身份、情绪、注意力或面试成绩判断。'}


@dataclass
class Monitor:
    uid:int
    token:str
    tracker:VisionTracker
    touched:float=field(default_factory=time.monotonic)
    last_at:float=-float('inf')
    busy:bool=False
    observation:dict|None=None


class MonitorStore:
    def __init__(self):self.items={};self.lock=threading.RLock()
    def reap(self):
        with self.lock:
            now=time.monotonic()
            for key in list(self.items):
                if now-self.items[key].touched>60:del self.items[key]
    def create(self,uid,sensitivity):
        with self.lock:
            self.reap()
            for key in list(self.items):
                if self.items[key].uid==uid:del self.items[key]
            if len(self.items)>=16:raise HTTPException(503,'摄像头练习容量已满，请稍后重试。')
            mid=secrets.token_urlsafe(24);m=Monitor(uid,secrets.token_urlsafe(32),VisionTracker(sensitivity));self.items[mid]=m
            return {'id':mid,'token':m.token}
    def require(self,mid,uid,token):
        self.reap();m=self.items.get(mid)
        if not m or m.uid!=uid or not token.isascii() or not secrets.compare_digest(token,m.token):raise HTTPException(404,'摄像头监测已停止或不属于当前账号。')
        return m


monitors=MonitorStore()


def close_models():
    global _models
    with _model_lock:
        if _models:
            for model in _models[1:]:model.close()
            _models=None
