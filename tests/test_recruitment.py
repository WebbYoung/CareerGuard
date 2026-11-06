"""Recruitment consent and company scoping without model calls."""
import importlib.util
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import database
from app.api import router as base
from app.platform_api import router as platform


def test_recruitment_module_exists():
    assert importlib.util.find_spec('app.recruitment_api') is not None, 'Recruitment consent API is missing'


@pytest.fixture
def client(monkeypatch):
    if importlib.util.find_spec('app.recruitment_api') is None:pytest.skip('API not implemented')
    from app.recruitment_api import router
    from app.services.recruitment_schema import SCHEMA
    monkeypatch.setattr(database,'SCHEMA',database.SCHEMA+SCHEMA)
    app=FastAPI();app.include_router(base);app.include_router(platform);app.include_router(router)
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/auth/session').json()['csrf_token']
        r=c.post('/api/auth/register',json={'username':'applicant','password':'Testing-safe-2026!'})
        c.headers['X-CSRF-Token']=r.json()['csrf_token']
        uid=r.json()['user']['id']
        with database.connect() as db:
            company_user=db.execute("INSERT INTO users(username,password,role) VALUES ('employer','unused','company')").lastrowid
            cid=db.execute("INSERT INTO companies(name,credit_code,contact_role,license_encrypted,license_type,ocr_notes,status) VALUES ('企业','91350211M000100Y43','经理',X'01','image/png','{}','approved')").lastrowid
            db.execute('INSERT INTO company_memberships(company_id,user_id) VALUES (?,?)',(cid,company_user))
            jid=db.execute("INSERT INTO jobs(owner_id,title,company,description,status) VALUES (?,'后端开发','企业','Python 岗位说明','approved')",(company_user,)).lastrowid
            db.execute('INSERT INTO job_company_links VALUES (?,?)',(jid,cid))
        c.uid=uid;c.jid=jid;c.cid=cid;c.company_user=company_user
        yield c


def apply(c,**updates):
    c.put('/api/profile',json={'occupation':'后端','resume':'真实技能 Python 项目经历'})
    return c.post(f'/api/jobs/{c.jid}/apply',json={'resume_source':'profile','share_resume':True,**updates})


def test_explicit_consent_snapshot_and_idempotence(client):
    c=client
    assert apply(c,share_resume=False).status_code==422
    r=apply(c);assert r.status_code==200,r.text
    aid=r.json()['id'];assert apply(c).json()['id']==aid
    with database.connect() as db:
        row=db.execute('SELECT * FROM job_applications WHERE id=?',(aid,)).fetchone()
        assert b'Python' not in row['resume_encrypted']
        assert db.execute('SELECT COUNT(*) FROM application_interviews').fetchone()[0]==0
    assert c.get('/api/applications').json()['items'][0]['id']==aid
    assert c.get('/api/company/candidates').status_code==403
    assert c.delete(f'/api/applications/{aid}').status_code==200
    with database.connect() as db:
        assert db.execute('SELECT resume_encrypted FROM job_applications WHERE id=?',(aid,)).fetchone()[0] is None


def test_server_only_interview_links_and_company_scope(client):
    from app.recruitment_api import attach_interview,candidate_view,validate_application
    from fastapi import HTTPException
    c=client;aid=apply(c,interview_consent=True).json()['id']
    with database.connect() as db:
        user=dict(db.execute('SELECT * FROM users WHERE id=?',(c.uid,)).fetchone())
        iid=db.execute("INSERT INTO interviews(user_id,occupation) VALUES (?,'后端开发')",(c.uid,)).lastrowid
        with pytest.raises(HTTPException):attach_interview(db,user,aid,iid,'伪造职业')
        attach_interview(db,user,aid,iid,'后端开发')
        attach_interview(db,user,aid,iid,'后端开发')
        company=dict(db.execute('SELECT * FROM companies WHERE id=?',(c.cid,)).fetchone())
        result=candidate_view(db,company,aid)
        assert result['interview_count']==1
        assert 'Python' in result['resume']['text']
        assert 'history' not in result and 'score' not in result
        with pytest.raises(HTTPException):candidate_view(db,{'id':999},aid)
        db.execute("UPDATE companies SET status='rejected' WHERE id=?",(c.cid,))
        with pytest.raises(HTTPException):validate_application(db,user,aid,'后端开发')


def test_draft_ownership_and_actual_resume_only(client):
    from app.resume_api import encrypted
    c=client
    with database.connect() as db:
        db.execute('INSERT INTO resume_sessions(id,user_id,content) VALUES (?,?,?)',('owned',c.uid,encrypted({'draft':{'skills':'事实技能'},'messages':[{'content':'私密对话'}],'proposal':{'draft':{'skills':'AI建议'}}})))
    body={'resume_source':'studio','resume_session_id':'owned','share_resume':True}
    r=c.post(f'/api/jobs/{c.jid}/apply',json=body);assert r.status_code==200,r.text
    with database.connect() as db:
        row=db.execute('SELECT resume_encrypted FROM job_applications').fetchone()
        value=database.cipher().decrypt(row[0]).decode()
        assert '事实技能' in value and '私密对话' not in value and 'AI建议' not in value
    assert c.post(f'/api/jobs/{c.jid}/apply',json={**body,'resume_session_id':'not-owned'}).status_code==404



def test_delete_personal_data_revokes_all_shared_snapshots(client):
    from app.recruitment_api import clear_user_applications
    c=client;aid=apply(c).json()['id']
    with database.connect() as db:
        clear_user_applications(db,c.uid)
        row=db.execute('SELECT status,share_resume,resume_encrypted FROM job_applications WHERE id=?',(aid,)).fetchone()
        assert tuple(row)==('withdrawn',0,None)


def test_pending_job_cannot_receive_application(client):
    c=client
    with database.connect() as db:db.execute("UPDATE jobs SET status='pending' WHERE id=?",(c.jid,))
    assert apply(c).status_code==404


def test_company_api_only_returns_own_authorized_candidate(client,monkeypatch):
    import app.recruitment_api as api
    c=client;aid=apply(c).json()['id']
    with database.connect() as db:user=dict(db.execute('SELECT * FROM users WHERE id=?',(c.company_user,)).fetchone())
    monkeypatch.setattr(api,'current',lambda request:user)
    result=c.get('/api/company/candidates');assert result.status_code==200,result.text
    assert result.json()['items'][0]['id']==aid
    assert result.json()['jobs'][0]['interview_users']==0
    assert c.get('/api/company/candidates?job_id=999').status_code==404
    assert c.get('/api/company/candidates/999').status_code==404
    with database.connect() as db:db.execute("UPDATE companies SET status='pending' WHERE id=?",(c.cid,))
    assert c.get(f'/api/company/candidates/{aid}').status_code==403


def test_interview_endpoint_uses_authorized_job_and_counts_once(client,monkeypatch):
    from app.services import growth
    c=client;aid=apply(c,interview_consent=True).json()['id'];evidence=[]
    def answer(task,data,schema):
        evidence.append(data)
        return {'question':'介绍一个真实项目。','feedback':'','focus':'项目实践'}
    monkeypatch.setattr(growth,'generate_json',answer)
    r=c.post('/api/interviews',json={'occupation':'后端开发','jd':'替换后的无关岗位','consent':True,'application_id':aid})
    assert r.status_code==200,r.text
    assert evidence[0]['jd']=='Python 岗位说明'
    with database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM application_interviews WHERE application_id=?',(aid,)).fetchone()[0]==1
    c.delete(f'/api/applications/{aid}')
    r=c.post('/api/interviews',json={'occupation':'后端开发','consent':True,'application_id':aid})
    assert r.status_code==404 and len(evidence)==1


def test_withdraw_during_model_call_cannot_create_interview_link(client,monkeypatch):
    from app.services import growth
    c=client;aid=apply(c,interview_consent=True).json()['id']
    def withdraw_then_reply(*args):
        with database.connect() as db:
            db.execute("UPDATE job_applications SET status='withdrawn',share_resume=0,resume_encrypted=NULL WHERE id=?",(aid,))
        return {'question':'合成问题','feedback':'','focus':'技能'}
    monkeypatch.setattr(growth,'generate_json',withdraw_then_reply)
    r=c.post('/api/interviews',json={'occupation':'后端开发','consent':True,'application_id':aid})
    assert r.status_code==404
    with database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM interviews').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM application_interviews').fetchone()[0]==0


def test_personal_data_endpoint_revokes_shared_resume(client):
    c=client;aid=apply(c,interview_consent=True).json()['id']
    assert c.delete('/api/profile/data').status_code==200
    with database.connect() as db:
        row=db.execute('SELECT status,resume_encrypted FROM job_applications WHERE id=?',(aid,)).fetchone()
        assert tuple(row)==('withdrawn',None)


def test_reapplication_without_interview_consent_hides_previous_training(client,monkeypatch):
    import app.recruitment_api as api
    c=client;aid=apply(c,interview_consent=True).json()['id']
    with database.connect() as db:
        user=dict(db.execute('SELECT * FROM users WHERE id=?',(c.uid,)).fetchone())
        iid=db.execute("INSERT INTO interviews(user_id,occupation) VALUES (?,'后端开发')",(c.uid,)).lastrowid
        api.attach_interview(db,user,aid,iid,'后端开发')
    assert c.delete(f'/api/applications/{aid}').status_code==200
    assert apply(c,interview_consent=False).json()['id']==aid
    with database.connect() as db:
        company=dict(db.execute('SELECT * FROM companies WHERE id=?',(c.cid,)).fetchone())
        assert api.candidate_view(db,company,aid)['interview_count']==0
        employer=dict(db.execute('SELECT * FROM users WHERE id=?',(c.company_user,)).fetchone())
    monkeypatch.setattr(api,'current',lambda request:employer)
    result=c.get('/api/company/candidates').json()
    assert result['jobs'][0]['applicant_count']==1
    assert result['jobs'][0]['interview_users']==0
