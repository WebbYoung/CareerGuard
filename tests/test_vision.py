"""画面几何与生命周期验证，不从姿态推断心理状态或诚信。"""
import io
import math
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app


def observed(yaw=0,center=(.5,.45),hands=None):
    return {'face_count':1,'face':{'center':list(center),'width':.3,'height':.4,'box':[.35,.25,.65,.65],
            'angles':{'yaw':yaw,'pitch':0,'roll':0}},'hands':hands or [],'inference_ms':12}


def test_pose_geometry_and_debounce():
    from app.services.vision import euler_angles, VisionTracker
    a=math.radians(30)
    r=np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
    matrix=np.eye(4);matrix[:3,:3]=r
    assert abs(euler_angles(matrix)['yaw']-30)<.1
    tracker=VisionTracker('standard')
    assert tracker.update(observed(),0)['status']=='ok'
    assert tracker.update(observed(yaw=40),1)['status']!='adjust'
    assert tracker.update(observed(yaw=40),3.2)['status']=='adjust'
    assert tracker.update(observed(),3.6)['status']=='ok'
    with pytest.raises(HTTPException):tracker.calibrate(observed(yaw=60))


def test_face_absence_multiple_and_hand_proximity_are_only_geometric():
    from app.services.vision import VisionTracker
    tracker=VisionTracker('strict')
    tracker.update({'face_count':0,'face':None,'hands':[]},0)
    result=tracker.update({'face_count':0,'face':None,'hands':[]},3)
    assert 'face_missing' in result['alerts']
    assert 'score' not in result and 'emotion' not in result and 'identity' not in result
    near={'center':[.5,.45],'points':[[.5,.45]]*21}
    tracker=VisionTracker('strict');tracker.update(observed(hands=[near]),0)
    assert 'hand_near_face' in tracker.update(observed(hands=[near]),3)['alerts']


def test_image_validation_rejects_bad_signature_and_oversized_pixels():
    from app.services.vision import decode_frame
    with pytest.raises(HTTPException):decode_frame(b'not image')
    b=io.BytesIO();Image.new('RGB',(1600,1600)).save(b,format='JPEG')
    with pytest.raises(HTTPException):decode_frame(b.getvalue())


@pytest.fixture
def signed_client():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        login=c.post('/api/auth/login',json={'username':'admin','password':'admin'}).json()
        c.headers['X-CSRF-Token']=login['csrf_token']
        yield c


def test_camera_api_is_private_bounded_and_does_not_store_frames(signed_client,monkeypatch):
    from app.services import vision
    from app.database import connect
    c=signed_client
    monkeypatch.setattr(vision,'model_status',lambda:{'ready':True,'model':'MediaPipe','message':'可用'})
    monkeypatch.setattr(vision,'infer',lambda raw:observed())
    assert c.post('/api/vision/session',json={'consent':False}).status_code==422
    monitor=c.post('/api/vision/session',json={'consent':True}).json()
    mid=monitor['id'];headers={'Content-Type':'image/jpeg','X-Vision-Token':monitor['token']}
    b=io.BytesIO();Image.new('RGB',(320,240)).save(b,format='JPEG')
    r=c.post(f'/api/vision/{mid}/frame',content=b.getvalue(),headers=headers)
    assert r.status_code==200,r.text
    assert r.json()['face_count']==1
    assert c.post(f'/api/vision/{mid}/frame',content=b'x'*(vision.MAX_FRAME_BYTES+1),headers=headers).status_code==413
    assert c.post(f'/api/vision/{mid}/frame',content=b.getvalue(),headers={**headers,'X-Vision-Token':'wrong'}).status_code==404
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM materials').fetchone()[0]==0
    assert c.delete(f'/api/vision/{mid}',headers={'X-Vision-Token':monitor['token']}).status_code==200
    assert c.post(f'/api/vision/{mid}/frame',content=b.getvalue(),headers=headers).status_code==404


def test_monitor_isolation_between_accounts(signed_client,monkeypatch):
    from app.services import vision
    monkeypatch.setattr(vision,'model_status',lambda:{'ready':True})
    c=signed_client
    monitor=c.post('/api/vision/session',json={'consent':True}).json()
    user=c.post('/api/auth/register',json={'username':'camera_user','password':'Camera-testing-2026!'}).json()
    c.headers['X-CSRF-Token']=user['csrf_token']
    assert c.delete('/api/vision/'+monitor['id'],headers={'X-Vision-Token':monitor['token']}).status_code==404


def test_guest_cannot_start_camera_monitor():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        assert c.post('/api/vision/session',json={'consent':True}).status_code==401


def test_repeated_hand_motion_and_short_nod_debounce():
    from app.services.vision import VisionTracker
    tracker=VisionTracker('standard')
    result=None
    for i in range(12):
        x=[.15,.4,.65,.4][i%4]
        hand={'center':[x,.85],'points':[[x,.85]]*21}
        result=tracker.update(observed(hands=[hand]),i*.4)
    assert 'hand_motion' in result['alerts']
    tracker=VisionTracker('standard')
    tracker.update(observed(),0);tracker.update(observed(yaw=35),.5)
    assert tracker.update(observed(),1)['alerts']==[]
