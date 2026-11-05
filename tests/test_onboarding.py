from fastapi.testclient import TestClient
from app.main import app


def register(client,username):
    client.headers['X-CSRF-Token']=client.get('/api/auth/session').json()['csrf_token']
    result=client.post('/api/auth/register',json={'username':username,'password':'Guide-testing-2026!'})
    assert result.status_code==200
    client.headers['X-CSRF-Token']=result.json()['csrf_token']


def test_new_user_guide_is_private_and_survives_login():
    with TestClient(app) as a, TestClient(app) as b:
        register(a,'guide_alpha');register(b,'guide_beta')
        initial=a.get('/api/onboarding');assert initial.status_code==200
        assert initial.json()['auto_start'] is True and initial.json()['step']==0
        assert initial.json()['steps']==10
        assert a.post('/api/onboarding',json={'action':'progress','step':4}).status_code==200
        assert b.get('/api/onboarding').json()['step']==0
        assert a.post('/api/onboarding',json={'action':'skip','step':4}).json()['status']=='skipped'
        a.post('/api/auth/logout')
        a.headers['X-CSRF-Token']=a.get('/api/auth/session').json()['csrf_token']
        login=a.post('/api/auth/login',json={'username':'guide_alpha','password':'Guide-testing-2026!'})
        a.headers['X-CSRF-Token']=login.json()['csrf_token']
        saved=a.get('/api/onboarding').json()
        assert saved['status']=='skipped' and saved['auto_start'] is False


def test_guide_requires_session_csrf_and_valid_step():
    with TestClient(app) as c:
        assert c.get('/api/onboarding').status_code==401
        register(c,'guide_valid')
        assert c.post('/api/onboarding',json={'action':'progress','step':10}).status_code==422
        assert c.post('/api/onboarding',json={'action':'complete','step':2}).status_code==422
        c.headers['X-CSRF-Token']='invalid'
        assert c.post('/api/onboarding',json={'action':'skip','step':0}).status_code==403


def test_complete_is_not_repeated_and_existing_admin_can_replay():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        result=c.post('/api/auth/login',json={'username':'admin','password':'admin'})
        c.headers['X-CSRF-Token']=result.json()['csrf_token']
        assert c.get('/api/onboarding').json()['auto_start'] is False
        assert c.post('/api/onboarding',json={'action':'start','step':0}).json()['auto_start'] is True
        assert c.post('/api/onboarding',json={'action':'progress','step':9}).status_code==200
        assert c.post('/api/onboarding',json={'action':'complete','step':9}).json()['auto_start'] is False
        assert c.get('/api/onboarding').json()['status']=='completed'
        assert c.post('/api/onboarding',json={'action':'start','step':0}).json()['step']==0
