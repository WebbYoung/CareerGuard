"""入口分离与访客权限必须由服务端执行。"""
from fastapi.testclient import TestClient
from app.main import app

def test_guest_only_has_fixed_demo_and_admin_is_seeded():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
        for path in ('/','/login','/register','/demo'):
            assert c.get(path).status_code==200
        assert c.get('/app',follow_redirects=False).status_code==303
        assert c.get('/admin',follow_redirects=False).status_code==303
        assert c.post('/api/materials/text',json={'kind':'resume','text':'Python'}).status_code==401
        demo=c.get('/api/demo').json()
        assert demo['mode']=='fixed_demo' and demo['risk']['score']>0
        result=c.post('/api/auth/login',json={'username':'admin','password':'admin'})
        assert result.status_code==200 and result.json()['user']['role']=='admin'
        c.headers['X-CSRF-Token']=result.json()['csrf_token']
        assert c.get('/admin').status_code==200
        assert 'platform.js' not in c.get('/admin').text
        assert 'admin.js' in c.get('/admin').text

def test_new_registered_account_cannot_access_admin():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
        result=c.post('/api/auth/register',json={'username':'normal_demo','password':'Safe-testing-2026!'})
        assert result.status_code==200 and result.json()['user']['role']=='user'
        c.headers['X-CSRF-Token']=result.json()['csrf_token']
        assert c.get('/app').status_code==200
        assert c.get('/admin').status_code==403
        assert 'auth-password' not in c.get('/app').text


def test_default_admin_initialization_runs_once():
    from app.database import connect,ensure_superuser,password_hash,password_ok
    ensure_superuser()
    with connect() as db:
        assert password_ok('admin',db.execute("SELECT password FROM users WHERE username='admin'").fetchone()[0])
        db.execute("UPDATE users SET password=? WHERE username='admin'",(password_hash('Updated-testing-password!'),))
    ensure_superuser()
    with connect() as db:
        assert password_ok('Updated-testing-password!',db.execute("SELECT password FROM users WHERE username='admin'").fetchone()[0])


def test_account_materials_survive_cache_restart_and_session_cookie():
    from app.store import store
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        login=c.post('/api/auth/register',json={'username':'persist_demo','password':'Persistence-safe-2026!'})
        assert login.status_code==200
        assert all('max-age' not in v.lower() for v in login.headers.get_list('set-cookie'))
        c.headers['X-CSRF-Token']=login.json()['csrf_token']
        material=c.post('/api/materials/text',json={'kind':'resume','text':'技能：Python、SQL；项目：实现查询接口。'}).json()
        c.post('/api/privacy',json={'material_id':material['id']})
        with store.lock:store.sessions.clear()
        assert c.get('/app').status_code==200
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        assert c.get('/api/materials').json()['items'][0]['id']==material['id']
        assert c.get('/api/profile/materials').json()['analyses'][0]['kind']=='privacy'
        c.post('/api/auth/logout')
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        login=c.post('/api/auth/login',json={'username':'persist_demo','password':'Persistence-safe-2026!'})
        c.headers['X-CSRF-Token']=login.json()['csrf_token']
        assert c.get('/api/materials/'+material['id']).json()['text']==material['text']
