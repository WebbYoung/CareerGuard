"""Company contracts using isolated SQLite, synthetic documents and no OCR/model service."""
import io
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import database
from app.api import router as base_router
from app.platform_api import router as platform_router
from app.company_api import router, CHARS, WEIGHTS, valid_credit_code
from app.services.company_schema import SCHEMA


@pytest.fixture
def company_client(monkeypatch):
    monkeypatch.setattr(database,'SCHEMA',database.SCHEMA+SCHEMA)
    app=FastAPI();app.include_router(base_router);app.include_router(platform_router);app.include_router(router)
    with TestClient(app) as client:
        session(client)
        yield client


def session(client):
    client.headers['X-CSRF-Token']=client.get('/api/auth/session').json()['csrf_token']


def code(prefix='91350211M000100Y4'):
    return prefix+CHARS[(31-sum(CHARS.index(c)*w for c,w in zip(prefix,WEIGHTS))%31)%31]


def png():
    out=io.BytesIO();Image.new('RGB',(20,20),'white').save(out,format='PNG');return out.getvalue()


def submit(client,username='company01',credit=None,**changes):
    fields={'username':username,'password':'Company-safe-2026!','name':'合成测试有限公司','credit_code':credit or code(),'contact_role':'人事经理','acknowledgment':'true'}
    fields.update(changes)
    return client.post('/api/company/register',data=fields,files={'license':('license.png',png(),'image/png')})


def admin(client):
    r=client.post('/api/auth/login',json={'username':'admin','password':'admin'});assert r.status_code==200,r.text
    session(client)


def company_login(client,name='company01'):
    r=client.post('/api/auth/login',json={'username':name,'password':'Company-safe-2026!'});assert r.status_code==200,r.text
    session(client)


def test_credit_checksum():
    assert valid_credit_code(code())
    assert not valid_credit_code(code()[:-1]+'Z')
    assert not valid_credit_code('0'*17+'I')
    assert not valid_credit_code('short')


def test_register_encrypted_pending_and_duplicate_rollback(company_client):
    c=company_client;r=submit(c);assert r.status_code==200,r.text
    assert r.json()['user']['role']=='company';session(c)
    company=c.get('/api/company/me').json()['company'];assert company['status']=='pending'
    assert company['ocr_notes']['source']=='manual'
    assert 'license_encrypted' not in company
    with database.connect() as db:
        stored=db.execute('SELECT license_encrypted FROM companies').fetchone()[0]
        assert stored!=png() and database.cipher().decrypt(stored)==png()
    assert c.post('/api/company/jobs',json={'title':'开发','description':'职责'}).status_code==403
    assert submit(c,username='rollback_user').status_code==409
    with database.connect() as db:
        assert db.execute("SELECT 1 FROM users WHERE username='rollback_user'").fetchone() is None


def test_file_and_consent_validation_before_password_or_ocr(company_client,monkeypatch):
    c=company_client
    import app.company_api as mod
    monkeypatch.setattr(mod,'password_hash',lambda *_:pytest.fail('password hash must follow file validation'))
    monkeypatch.setattr(mod.ocr,'parse_upload',lambda *_:pytest.fail('no OCR for rejected upload'))
    fields={'username':'company01','password':'Company-safe-2026!','name':'合成公司','credit_code':code(),'contact_role':'经理','acknowledgment':'true'}
    for data,name,mime in [(b'not-a-png','file.png','image/png'),(png(),'file.pdf','application/pdf')]:
        r=c.post('/api/company/register',data=fields,files={'license':(name,data,mime)})
        assert r.status_code==415,r.text
    assert submit(c,acknowledgment='false').status_code==422
    assert submit(c,credit='bad').status_code==422
    with database.connect() as db: assert db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]==0


def test_admin_review_job_lifecycle_and_revocation(company_client):
    c=company_client;r=submit(c);cid=r.json()['company_id'];session(c)
    assert c.get('/api/admin/companies').status_code==403
    assert c.patch(f'/api/admin/companies/{cid}/review',json={'status':'approved'}).status_code==403
    assert c.get(f'/api/company/{cid}/license').content==png()
    assert c.get(f'/api/admin/companies/{cid}/license').status_code==403
    admin(c)
    assert c.get('/api/admin/companies').json()['items'][0]['id']==cid
    assert c.get(f'/api/admin/companies/{cid}/license').headers['cache-control']=='no-store'
    assert c.patch(f'/api/admin/companies/{cid}/review',json={'status':'approved','note':'材料一致'}).status_code==200
    company_login(c)
    r=c.post('/api/company/jobs',json={'title':'Python开发','description':'招聘职责'});assert r.status_code==200,r.text
    jid=r.json()['id'];assert r.json()['status']=='pending'
    assert c.post('/api/company/jobs',json={'title':'伪造','description':'职责','company':'冒充公司'}).status_code==422
    assert c.get('/api/jobs').json()['items']==[]
    admin(c)
    assert c.patch(f'/api/admin/jobs/{jid}/review',json={'status':'approved','note':'通过'}).status_code==200
    assert len(c.get('/api/jobs').json()['items'])==1
    company_login(c)
    assert c.put(f'/api/company/jobs/{jid}',json={'title':'更新开发岗位','description':'岗位更新'}).status_code==200
    assert c.get('/api/jobs').json()['items']==[]
    admin(c)
    c.patch(f'/api/admin/jobs/{jid}/review',json={'status':'approved','note':'通过'})
    assert c.patch(f'/api/admin/companies/{cid}/review',json={'status':'rejected','note':''}).status_code==422
    assert c.patch(f'/api/admin/companies/{cid}/review',json={'status':'rejected','note':'材料有误'}).status_code==200
    assert c.get('/api/jobs').json()['items']==[]
    company_login(c)
    assert c.put(f'/api/company/jobs/{jid}',json={'title':'不能修改','description':'未通过'}).status_code==403
    assert c.delete(f'/api/company/jobs/{jid}').status_code==200


def test_company_tenant_isolation_and_csrf(company_client):
    c=company_client;cid=submit(c).json()['company_id'];session(c);admin(c)
    c.patch(f'/api/admin/companies/{cid}/review',json={'status':'approved'})
    company_login(c);jid=c.post('/api/company/jobs',json={'title':'岗位甲','description':'职责甲'}).json()['id']
    second=submit(c,username='company02',credit=code('91350211M000100Y5'));assert second.status_code==200,second.text
    session(c);second_id=second.json()['company_id'];admin(c)
    c.patch(f'/api/admin/companies/{second_id}/review',json={'status':'approved'})
    company_login(c,'company02')
    assert c.get('/api/company/jobs').json()['items']==[]
    assert c.get(f'/api/company/{cid}/license').status_code==403
    assert c.put(f'/api/company/jobs/{jid}',json={'title':'越权','description':'越权'}).status_code==404
    assert c.delete(f'/api/company/jobs/{jid}').status_code==404
    assert c.post('/api/company/jobs',headers={'X-CSRF-Token':'bad'},json={'title':'岗位','description':'职责'}).status_code==403


def test_ocr_is_local_hint_and_missing_matches_do_not_certify(company_client,monkeypatch):
    from app.services import ocr
    monkeypatch.setattr(ocr,'model_configured',lambda:True)
    monkeypatch.setattr(ocr,'parse_upload',lambda *_:{'text':'名称：其他合成公司\n统一社会信用代码：'+code('91350211M000100Y5')})
    c=company_client;r=submit(c);assert r.status_code==200,r.text
    session(c);company=c.get('/api/company/me').json()['company'];notes=company['ocr_notes']
    assert notes['source']=='local_ocr' and notes['name_match'] is False and notes['credit_code_match'] is False
    assert company['status']=='pending'
    assert notes['detected_name']=='其他合成公司'
    assert '政府' in notes['disclaimer']


def test_bounded_upload_and_invalid_pdf(company_client):
    c=company_client
    fields={'username':'company01','password':'Company-safe-2026!','name':'合成公司','credit_code':code(),'contact_role':'经理','acknowledgment':'true'}
    assert c.post('/api/company/register',json=fields).status_code==415
    r=c.post('/api/company/register',data=fields,files={'license':('broken.pdf',b'%PDF-broken','application/pdf')})
    assert r.status_code==415
    r=c.post('/api/company/register',data=fields,files={'license':('large.png',b'\x89PNG\r\n\x1a\n'+b'x'*(8*1024*1024),'image/png')})
    assert r.status_code==413
    with database.connect() as db: assert db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]==0
