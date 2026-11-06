"""Synthetic tests only: gateway functions are replaced before any call."""
import io
import json
import zipfile
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import resume_api
from app.services import resume_builder as builder,model_gateway,rag
from app.services.resume_schema import SCHEMA
from app.database import connect,cipher,password_hash

def png():
    stream=io.BytesIO();Image.new('RGB',(300,400),'white').save(stream,format='PNG');return stream.getvalue()

@pytest.fixture
def resume_client(monkeypatch):
    with connect() as db:
        db.executescript(SCHEMA)
        uid=db.execute('INSERT INTO users(username,password) VALUES (?,?)',('synthetic-resume',password_hash('synthetic-password'))).lastrowid
        user=dict(db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    monkeypatch.setattr(resume_api,'current',lambda request:user)
    monkeypatch.setattr(model_gateway,'chat',lambda *a,**k: {'text':'请补充你实际承担的职责。'})
    monkeypatch.setattr(model_gateway,'image_edit',lambda *a,**k:{'bytes':png(),'mime':'image/png'})
    monkeypatch.setattr(rag,'search',lambda *a,**k:{'citations':[{'id':1,'title':'合成知识','text':'用真实行动说明职责'}],'retrieval_mode':'keyword_fallback'})
    app=FastAPI();app.include_router(resume_api.router)
    with TestClient(app) as c:yield c,user

def test_guided_collection_and_manual_export(resume_client):
    c,user=resume_client
    value=c.post('/api/resume/sessions',json={}).json();sid=value['id']
    r=c.post(f'/api/resume/sessions/{sid}/message',json={'message':'Python 开发实习','consent':False})
    assert r.status_code==200,r.text
    assert r.json()['draft']['goal']=='Python 开发实习'
    assert r.json()['next_field']=='experience'
    assert r.json()['mode']=='guided'
    draft=r.json()['draft'];draft.update(identity='合成人员\nsynthetic@example.invalid',education='测试学校，计算机专业，2020—2024')
    assert c.put(f'/api/resume/sessions/{sid}/draft',json={'draft':draft}).status_code==200
    r=c.get(f'/api/resume/sessions/{sid}/export.docx');assert r.status_code==200
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        text=archive.read('word/document.xml').decode();assert '测试学校' in text and 'Python 开发实习' in text
    with connect() as db:
        row=db.execute('SELECT * FROM resume_sessions WHERE id=?',(sid,)).fetchone()
        assert '测试学校' not in row['content']
        assert '测试学校' in cipher().decrypt(row['content'].encode()).decode()
    assert c.delete(f'/api/resume/sessions/{sid}').status_code==200
    assert c.get(f'/api/resume/sessions/{sid}').status_code==404

def test_ai_coaching_cannot_write_fabricated_facts(resume_client,monkeypatch):
    c,_=resume_client
    monkeypatch.setattr(model_gateway,'chat',lambda *a,**k:{'text':'虚构大学、虚构公司、提升999%。'})
    sid=c.post('/api/resume/sessions',json={}).json()['id']
    r=c.post(f'/api/resume/sessions/{sid}/message',json={'message':'后端实习','consent':True}).json()
    assert r['mode']=='ai' and r['draft']['goal']=='后端实习'
    assert '虚构' not in json.dumps(r['draft'],ensure_ascii=False)

def test_unconfigured_ai_preserves_answer(resume_client,monkeypatch):
    c,_=resume_client
    def unavailable(*a,**k):raise model_gateway.GatewayError('未配置')
    monkeypatch.setattr(model_gateway,'chat',unavailable)
    sid=c.post('/api/resume/sessions',json={}).json()['id']
    r=c.post(f'/api/resume/sessions/{sid}/message',json={'message':'数据分析','consent':True})
    assert r.status_code==200 and r.json()['draft']['goal']=='数据分析'
    assert '未配置' in r.json()['notice']

def test_portrait_consent_validation_and_processed_only(resume_client):
    c,_=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    url=f'/api/resume/sessions/{sid}/portrait'
    assert c.post(url,files={'file':('selfie.png',png(),'image/png')},data={'consent':'false'}).status_code==422
    assert c.post(url,files={'file':('fake.png',b'not an image','image/png')},data={'consent':'true'}).status_code==415
    r=c.post(url,files={'file':('selfie.png',png(),'image/png')},data={'consent':'true','background':'blue','size':'2inch'})
    assert r.status_code==200,r.text
    result=c.get(url);assert result.status_code==200
    with Image.open(io.BytesIO(result.content)) as image:assert image.size==(413,579)
    with connect() as db:
        row=db.execute('SELECT portrait FROM resume_sessions WHERE id=?',(sid,)).fetchone()
        assert not row['portrait'].startswith(b'\x89PNG')
        assert cipher().decrypt(row['portrait'])==result.content

def test_owner_isolation(resume_client,monkeypatch):
    c,user=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    monkeypatch.setattr(resume_api,'current',lambda request:{**user,'id':99999})
    assert c.get(f'/api/resume/sessions/{sid}').status_code==404
    assert c.post(f'/api/resume/sessions/{sid}/message',json={'message':'test','consent':True}).status_code==404

def test_stale_generation_does_not_save_model_result(resume_client,monkeypatch):
    c,user=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    def changed(*a,**k):
        with connect() as db:db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(user['id'],))
        return {'text':'synthetic'}
    monkeypatch.setattr(model_gateway,'chat',changed)
    r=c.post(f'/api/resume/sessions/{sid}/message',json={'message':'will not persist','consent':True})
    assert r.status_code==409
    with connect() as db:assert 'will not persist' not in cipher().decrypt(db.execute('SELECT content FROM resume_sessions WHERE id=?',(sid,)).fetchone()['content'].encode()).decode()

def test_personalized_proposal_keeps_raw_draft_and_evidence(resume_client,monkeypatch):
    c,_=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    draft=builder.Draft(goal='Python 开发',skills='Python、SQL',projects='用 Python 清洗数据，编写 SQL 查询').model_dump()
    c.put(f'/api/resume/sessions/{sid}/draft',json={'draft':draft})
    polished={**draft,'summary':'使用 Python 和 SQL 完成数据清洗与查询。','projects':'使用 Python 完成数据清洗；编写 SQL 查询。'}
    response={'draft':polished,'evidence':{'summary':[draft['projects']],'projects':[draft['projects']],'skills':[draft['skills']]},'missing_facts':['请补充项目时间与可核实结果']}
    monkeypatch.setattr(model_gateway,'chat',lambda *a,**k:{'text':json.dumps(response,ensure_ascii=False)})
    assert c.post(f'/api/resume/sessions/{sid}/polish',json={'consent':False}).status_code==422
    r=c.post(f'/api/resume/sessions/{sid}/polish',json={'consent':True});assert r.status_code==200,r.text
    result=r.json();assert result['draft']==draft
    assert result['proposal']['draft']['projects']==polished['projects']
    assert result['proposal']['source_facts']==draft
    assert result['proposal']['retrieval_mode']=='keyword_fallback'
    assert result['proposal']['citations'][0]['title']=='合成知识'
    assert c.put(f'/api/resume/sessions/{sid}/draft',json={'draft':result['proposal']['draft']}).status_code==200
    saved=c.get(f'/api/resume/sessions/{sid}').json()
    assert saved['original_facts'][-1]==draft
    with connect() as db:assert {r['action'] for r in db.execute('SELECT action FROM events')} >= {'resume_create','resume_draft_update','resume_polish'}

def test_polish_blocks_unsubstantiated_claims(resume_client,monkeypatch):
    c,_=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    draft=builder.Draft(goal='开发实习',education='用户学校',skills='Python',experience='参与编写脚本').model_dump()
    c.put(f'/api/resume/sessions/{sid}/draft',json={'draft':draft})
    response={'draft':{**draft,'education':'虚构大学','experience':'在虚构集团主导开发，提升50%','skills':'Python、Java'},'evidence':{'experience':['参与编写脚本'],'skills':['Python']},'missing_facts':[]}
    monkeypatch.setattr(model_gateway,'chat',lambda *a,**k:{'text':json.dumps(response)})
    r=c.post(f'/api/resume/sessions/{sid}/polish',json={'consent':True});assert r.status_code==200,r.text
    proposed=r.json()['proposal'];assert proposed['draft']==draft
    assert {f['field'] for f in proposed['unsupported_facts']}=={'experience','skills'}

def test_polish_invalid_json_does_not_change_resume(resume_client,monkeypatch):
    c,_=resume_client;sid=c.post('/api/resume/sessions',json={}).json()['id']
    c.put(f'/api/resume/sessions/{sid}/draft',json={'draft':{'goal':'开发'}})
    monkeypatch.setattr(model_gateway,'chat',lambda *a,**k:{'text':'{"draft": "bad"}'})
    r=c.post(f'/api/resume/sessions/{sid}/polish',json={'consent':True});assert r.status_code==502
    assert c.get(f'/api/resume/sessions/{sid}').json()['draft']['goal']=='开发'
