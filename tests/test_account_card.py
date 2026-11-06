"""Account presentation and avatar tests use disposable users and synthetic pixels."""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.database import connect

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
        yield c

def login(c,name='admin'):
    r=c.post('/api/auth/login' if name=='admin' else '/api/auth/register',json={'username':name,'password':'admin' if name=='admin' else 'Synthetic-safe-2026!'})
    assert r.status_code==200
    c.headers['X-CSRF-Token']=r.json()['csrf_token']

def image():
    b=io.BytesIO();Image.new('RGB',(420,280),'#517bdc').save(b,'JPEG',exif=b'Exif\x00\x00synthetic-metadata');return b.getvalue()

def test_account_details_save_and_reload(client):
    login(client)
    original=client.get('/api/account').json()
    assert original['username']=='admin' and not original['has_avatar']
    data={'nickname':'逐光者','city':'杭州','bio':'学习设计，把想法变成作品。'}
    r=client.put('/api/account',json=data)
    assert r.status_code==200,r.text
    for key,value in data.items():assert client.get('/api/account').json()[key]==value
    assert client.get('/api/auth/me').json()['user']['username']=='admin'
    assert client.put('/api/account',json={**data,'nickname':'x'*25}).status_code==422
    assert client.put('/api/account',json={**data,'role':'admin'}).status_code==422

def test_avatar_is_reencoded_private_and_removable(client):
    login(client)
    raw=image()
    r=client.post('/api/account/avatar',content=raw,headers={'Content-Type':'image/jpeg'})
    assert r.status_code==200,r.text
    assert r.json()['has_avatar']
    response=client.get('/api/account/avatar')
    assert response.headers['content-type']=='image/png'
    assert 'no-store' in response.headers['cache-control']
    with Image.open(io.BytesIO(response.content)) as im:
        assert im.size==(256,256) and not im.getexif()
    with connect() as db:
        saved=db.execute('SELECT avatar FROM account_details').fetchone()['avatar']
        assert raw not in saved and not saved.startswith(b'\x89PNG')
    assert client.delete('/api/account/avatar').status_code==200
    assert client.get('/api/account/avatar').status_code==404

def test_account_and_avatar_are_scoped_and_wiped(client):
    login(client)
    client.put('/api/account',json={'nickname':'私有昵称','bio':'私有简介','city':''})
    client.post('/api/account/avatar',content=image(),headers={'Content-Type':'image/jpeg'})
    login(client,'synthetic-other')
    assert client.get('/api/account').json()['nickname']==''
    assert client.get('/api/account/avatar').status_code==404
    login(client)
    assert client.delete('/api/profile/data').status_code==200
    assert client.get('/api/account').json()['nickname']==''
    assert client.get('/api/account/avatar').status_code==404

@pytest.mark.parametrize('kind,raw',[('image/svg+xml',b'<svg/>'),('image/png',b'not-an-image'),('image/jpeg',b'\xff\xd8\xffbad'),('image/gif',b'GIF89a')])
def test_avatar_rejects_unsafe_or_invalid_files(client,kind,raw):
    login(client)
    assert client.post('/api/account/avatar',content=raw,headers={'Content-Type':kind}).status_code in (415,422)

def test_avatar_requires_auth_csrf_and_size_limit(client):
    assert client.get('/api/account').status_code==401
    login(client)
    assert client.post('/api/account/avatar',content=image(),headers={'X-CSRF-Token':'bad','Content-Type':'image/jpeg'}).status_code==403
    assert client.post('/api/account/avatar',content=b'x'*(4*1024*1024+1),headers={'Content-Type':'image/jpeg'}).status_code==413
