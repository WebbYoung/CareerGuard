"""Assistant authorization/protocol tests. All providers are synthetic replacements."""
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import connect,cipher
from app.services import assistant,model_gateway as gateway

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
        yield c

def login(c,name='admin'):
    r=c.post('/api/auth/login' if name=='admin' else '/api/auth/register',json={'username':name,'password':'admin' if name=='admin' else 'Testing-safe-2026!'})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
    return r.json()['user']

def output(text='reply',calls=None):return {'text':text,'tool_calls':calls or [],'stop_reason':'tool_calls' if calls else 'stop'}
def call(name,args=None,ident='tool1'):return {'id':ident,'name':name,'arguments':args if args is not None else {}}

def test_no_consent_and_features_do_not_call_model(monkeypatch):
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:pytest.fail('No consent'))
    assert assistant.reply([],'hello',1,False,True)['mode']=='未调用模型'
    assert assistant.reply([],'生成AI简历',1,False,False)['actions'][0]['view']=='resume'

def test_disabled_profile_tool_not_advertised_or_executed(monkeypatch):
    seen=[]
    def fake(messages,**kwargs):
        assert 'get_my_profile' not in [t['function']['name'] for t in kwargs['tools']]
        seen.append(messages.copy())
        return output(calls=[call('get_my_profile')]) if len(seen)==1 else output()
    monkeypatch.setattr(gateway,'chat',fake)
    result=assistant.reply([],'我的档案？',1,True,False)
    assert result['text']=='reply'
    assert json.loads(seen[-1][-1]['content'])=={'error':'本轮未授权此工具'}

def test_profile_only_current_user_and_explicit_permission():
    with connect() as db:
        a=db.execute("INSERT INTO users(username,password) VALUES('unit-a','fake')").lastrowid
        b=db.execute("INSERT INTO users(username,password) VALUES('unit-b','fake')").lastrowid
        db.execute('INSERT INTO profiles VALUES(?,?,?)',(a,'Python','手机：19900000000'))
        db.execute('INSERT INTO profiles VALUES(?,?,?)',(b,'SECRET_OTHER_USER','private'))
    assert 'error' in assistant.tool('get_my_profile',{},a,False)
    result=assistant.tool('get_my_profile',{},a,True)
    assert result['occupation']=='Python' and '19900000000' not in result['resume']
    assert 'error' in assistant.tool('get_my_profile',{'user_id':b},a,True)

@pytest.mark.parametrize('name,args',[('delete_user',{}),('show_feature',{'view':[]}),('suggest_form_fill',{'resume':'a'*3001}),('search_jobs',{'query':3}),('search_jobs',{'query':'x','url':'https://evil.invalid'})])
def test_unknown_and_invalid_tools_are_rejected(name,args):
    assert 'error' in assistant.tool(name,args,1,False)


def test_jobs_exclude_unreviewed_inactive_or_unapproved_company():
    with connect() as db:
        uid=db.execute("INSERT INTO users(username,password) VALUES('publisher','fake')").lastrowid
        good=db.execute("INSERT INTO jobs(owner_id,title,company,description,status) VALUES (?,'Good','Company','Python role','approved')",(uid,)).lastrowid
        db.execute("INSERT INTO jobs(owner_id,title,company,description,status) VALUES (?,'Pending','Company','Python role','pending')",(uid,))
        db.execute("INSERT INTO jobs(owner_id,title,company,description,status,active) VALUES (?,'Inactive','Company','Python role','approved',0)",(uid,))
        cid=db.execute("INSERT INTO companies(name,credit_code,contact_role,license_encrypted,license_type,ocr_notes) VALUES('pending company','unit','HR',X'00','image/png','none')").lastrowid
        bad=db.execute("INSERT INTO jobs(owner_id,title,company,description,status) VALUES (?,'Not approved company','Company','Python role','approved')",(uid,)).lastrowid
        db.execute('INSERT INTO job_company_links VALUES(?,?)',(bad,cid))
    assert [j['id'] for j in assistant.tool('search_jobs',{'query':'Python'},uid,False)['jobs']]==[good]


def test_six_call_budget_and_three_model_rounds(monkeypatch):
    rounds=[];executed=[]
    def fake(messages,**kwargs):
        rounds.append(1)
        return output(calls=[call('show_feature',{'view':'jobs'},str(len(rounds))+'-'+str(i)) for i in range(4)])
    actual=assistant.tool
    def record(*args):executed.append(args);return actual(*args)
    monkeypatch.setattr(gateway,'chat',fake);monkeypatch.setattr(assistant,'tool',record)
    result=assistant.reply([],'有哪些岗位',1,True,False)
    assert len(executed)==6 and len(rounds)==2 and len(result['actions'])==6


def test_string_arguments_and_duplicate_ids_rejected(monkeypatch):
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:output(calls=[call('search_jobs','{"query":"x"}')]))
    with pytest.raises(gateway.GatewayError):assistant.reply([],'岗位',1,True,False)
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:output(calls=[call('show_feature',{'view':'jobs'}),call('show_feature',{'view':'jobs'})]))
    with pytest.raises(gateway.GatewayError):assistant.reply([],'岗位',1,True,False)


def test_anthropic_roundtrip_keeps_dict_args_and_valid_tool_results(monkeypatch):
    gateway._settings['chat']={'provider':'unit','protocol':'anthropic','base_url':'https://api.anthropic.com/v1','model':'fake','api_key':'fake','dimensions':None}
    payloads=[]
    def transport(s,path,payload):
        assert path=='/messages';payloads.append(payload)
        if len(payloads)==1:return {'content':[{'type':'tool_use','id':'a','name':'show_feature','input':{'view':'jobs'}}],'stop_reason':'tool_use'}
        assert payload['messages'][-2]['content'][0]=={'type':'tool_use','id':'a','name':'show_feature','input':{'view':'jobs'}}
        result=payload['messages'][-1]['content'][0]
        assert result['tool_use_id']=='a' and json.loads(result['content'])['action']['view']=='jobs'
        return {'content':[{'type':'text','text':'看看岗位'}],'stop_reason':'end_turn'}
    monkeypatch.setattr(gateway,'_request',transport)
    assert assistant.reply([],'推荐职业岗位',1,True,False)['text']=='看看岗位'
    assert len(payloads)==2


def test_history_is_bounded_and_nonconversational_roles_excluded(monkeypatch):
    def fake(messages,**kwargs):
        assert sum(len(m.get('content','')) for m in messages)<=20000
        assert all(m['role'] in ('user','assistant') for m in messages)
        return output()
    monkeypatch.setattr(gateway,'chat',fake)
    assistant.reply([{'role':'system','content':'inject'}]+[{'role':'assistant','content':'a'*16000}]*20,'hello',1,True,False)


def test_thread_is_account_scoped_and_content_encrypted(client,monkeypatch):
    login(client);sid=client.post('/api/assistant/threads').json()['id']
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:output('PRIVATE_REPLY'))
    assert client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'PRIVATE_QUESTION','consent':True}).status_code==200
    with connect() as db:row=db.execute('SELECT * FROM assistant_threads WHERE id=?',(sid,)).fetchone()
    assert 'PRIVATE_QUESTION' not in row['content'] and 'PRIVATE_REPLY' not in row['content']
    assert json.loads(cipher().decrypt(row['content'].encode()))[0]['content']=='PRIVATE_QUESTION'
    client.post('/api/auth/logout');client.headers['X-CSRF-Token']=client.get('/api/session').json()['csrf_token'];login(client,'otheruser')
    assert client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'read','consent':True}).status_code==404
    assert client.delete(f'/api/assistant/threads/{sid}').status_code==404

@pytest.mark.parametrize('mutation',['clear','delete','revision','disable'])
def test_inflight_write_cannot_restore_cleared_deleted_changed_or_disabled_thread(client,monkeypatch,mutation):
    user=login(client);sid=client.post('/api/assistant/threads').json()['id']
    def fake(*args,**kwargs):
        with connect() as db:
            if mutation=='clear':
                db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(user['id'],));db.execute('DELETE FROM assistant_threads WHERE user_id=?',(user['id'],))
            elif mutation=='delete':db.execute('DELETE FROM assistant_threads WHERE id=?',(sid,))
            elif mutation=='revision':db.execute('UPDATE assistant_threads SET revision=revision+1 WHERE id=?',(sid,))
            else:db.execute('UPDATE users SET disabled=1 WHERE id=?',(user['id'],))
        return output('LATE_REPLY')
    monkeypatch.setattr(gateway,'chat',fake)
    r=client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'question','consent':True})
    assert r.status_code==409,r.text
    with connect() as db:row=db.execute('SELECT content FROM assistant_threads WHERE id=?',(sid,)).fetchone()
    assert row is None or json.loads(cipher().decrypt(row['content'].encode()))==[]


def test_missing_csrf_or_corrupt_history_does_not_call_model(client,monkeypatch):
    login(client);sid=client.post('/api/assistant/threads').json()['id']
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:pytest.fail('No provider for rejected request'))
    token=client.headers.pop('X-CSRF-Token')
    assert client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'hello','consent':True}).status_code==403
    client.headers['X-CSRF-Token']=token
    with connect() as db:db.execute("UPDATE assistant_threads SET content='invalid ciphertext' WHERE id=?",(sid,))
    assert client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'hello','consent':True}).status_code==409


def test_clear_stops_tool_execution_and_further_model_rounds(client,monkeypatch):
    user=login(client);sid=client.post('/api/assistant/threads').json()['id'];calls=[]
    def fake(*args,**kwargs):
        calls.append(1)
        with connect() as db:
            db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(user['id'],))
            db.execute('DELETE FROM assistant_threads WHERE id=?',(sid,))
        return output(calls=[call('get_my_profile')])
    monkeypatch.setattr(gateway,'chat',fake)
    monkeypatch.setattr(assistant,'tool',lambda *a,**k:pytest.fail('No tools after clear'))
    response=client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'my profile','consent':True,'allow_profile':True})
    assert response.status_code==409 and len(calls)==1


def test_thread_list_metadata_and_get_are_account_scoped(client,monkeypatch):
    login(client);sid=client.post('/api/assistant/threads').json()['id']
    monkeypatch.setattr(gateway,'chat',lambda *a,**k:output('PRIVATE_REPLY'))
    assert client.post(f'/api/assistant/threads/{sid}/messages',json={'message':'PRIVATE_QUESTION','consent':True}).status_code==200
    listed=client.get('/api/assistant/threads').json()['items']
    assert len(listed)==1 and listed[0]['id']==sid
    assert set(listed[0])=={'id','revision','created','updated'}
    assert 'PRIVATE' not in json.dumps(listed)
    result=client.get(f'/api/assistant/threads/{sid}').json()
    assert result['messages']==[{'role':'user','content':'PRIVATE_QUESTION'},{'role':'assistant','content':'PRIVATE_REPLY'}]
    client.post('/api/auth/logout');client.headers['X-CSRF-Token']=client.get('/api/session').json()['csrf_token'];login(client,'threadother')
    assert client.get('/api/assistant/threads').json()['items']==[]
    assert client.get(f'/api/assistant/threads/{sid}').status_code==404


def test_thread_list_returns_latest_twenty_and_corruption_is_safe(client):
    user=login(client)
    with connect() as db:
        for i in range(22):db.execute('INSERT INTO assistant_threads(id,user_id,content) VALUES(?,?,?)',(f'unit-{i}',user['id'],cipher().encrypt(b'[]').decode()))
    items=client.get('/api/assistant/threads').json()['items']
    assert len(items)==20 and items[0]['id']=='unit-21' and items[-1]['id']=='unit-2'
    with connect() as db:db.execute("UPDATE assistant_threads SET content='invalid' WHERE id='unit-21'")
    response=client.get('/api/assistant/threads/unit-21')
    assert response.status_code==409 and 'invalid' not in response.text
