"""Synthetic structured responses only; no live model, user records or credentials."""
import json
import pytest
from fastapi import HTTPException
from app.services import growth,model_gateway as gateway

REPLY={'question':'请介绍一个你亲自完成的项目。','feedback':'','focus':'项目实践'}

def setup(monkeypatch,responses):
    monkeypatch.setattr(gateway,'is_custom_chat',lambda:True)
    calls=[]
    def fake(messages,**options):
        calls.append((messages,options))
        value=responses[min(len(calls)-1,len(responses)-1)]
        return value if isinstance(value,dict) else {'text':value,'tool_calls':[],'stop_reason':'stop'}
    monkeypatch.setattr(gateway,'chat',fake);return calls

@pytest.mark.parametrize('wrap',[
    lambda s:'```json\n'+s+'\n```',
    lambda s:'以下是JSON结果：\n'+s+'\n请按需使用。',
    lambda s:'<think>仅供内部思考的格式 {不应作为结果}</think>\n```json\n'+s+'\n```',
    lambda s:'\ufeff'+s,
])
def test_common_json_wrappers_do_not_fail_valid_result(monkeypatch,wrap):
    calls=setup(monkeypatch,[wrap(json.dumps(REPLY,ensure_ascii=False))])
    assert growth.generate_json('首轮问题',{'occupation':'测试岗位'},growth.InterviewReply)==REPLY
    assert len(calls)==1
    assert calls[0][1]['response_schema']==growth.InterviewReply.model_json_schema()

def test_invalid_schema_gets_one_repair_with_validation_paths(monkeypatch):
    invalid=json.dumps({'question':'真实问题','focus':'技能'},ensure_ascii=False)
    calls=setup(monkeypatch,[invalid,json.dumps(REPLY,ensure_ascii=False)])
    assert growth.generate_json('问题',{},growth.InterviewReply)==REPLY
    assert len(calls)==2 and 'feedback' in calls[1][0][-1]['content']

def test_repair_is_bounded_and_does_not_accept_extra_fields(monkeypatch):
    calls=setup(monkeypatch,[json.dumps({**REPLY,'passed':True},ensure_ascii=False)])
    with pytest.raises(HTTPException) as e:growth.generate_json('问题',{},growth.InterviewReply)
    assert e.value.status_code==502 and len(calls)==2
    assert '原记录保留' in str(e.value.detail)

def test_explicit_truncation_never_saves_even_complete_looking_json(monkeypatch):
    calls=setup(monkeypatch,[{'text':json.dumps(REPLY),'tool_calls':[],'stop_reason':'length'}])
    with pytest.raises(HTTPException) as e:growth.generate_json('问题',{},growth.InterviewReply)
    assert len(calls)==1 and '长度' in str(e.value.detail)

def test_gateway_failure_is_not_misreported_as_schema_error(monkeypatch):
    setup(monkeypatch,[])
    def fail(*a,**k):raise gateway.GatewayError()
    monkeypatch.setattr(gateway,'chat',fail)
    with pytest.raises(HTTPException) as e:growth.generate_json('问题',{},growth.InterviewReply)
    assert '配置' in str(e.value.detail) and '合格的结构化' not in str(e.value.detail)

def test_ambiguous_json_and_duplicate_keys_are_not_silently_selected(monkeypatch):
    for raw in [json.dumps(REPLY)+'\n'+json.dumps(REPLY),json.dumps(REPLY)+'\nnull','true\n'+json.dumps(REPLY),
                'true\n```json\n'+json.dumps(REPLY)+'\n```','```json\n'+json.dumps(REPLY)+'\n```\nnull',
                '{"question":"第一题","question":"第二题","feedback":"","focus":"项目"}']:
        setup(monkeypatch,[raw])
        with pytest.raises(HTTPException):growth.generate_json('问题',{},growth.InterviewReply)

def test_graph_cycles_still_rejected_after_repair(monkeypatch):
    tree={'title':'真实技能树','summary':'学习参考','nodes':[{'id':'n1','name':'技能','description':'介绍','prerequisites':['n1'],'task':'实践'}]}
    calls=setup(monkeypatch,[json.dumps(tree,ensure_ascii=False)])
    with pytest.raises(HTTPException):growth.generate_json('技能树',{},growth.Tree)
    assert len(calls)==2

@pytest.mark.parametrize('protocol',['openai','ollama','anthropic'])
def test_gateway_requests_a_structured_output_channel(monkeypatch,protocol):
    gateway._settings['chat']={'provider':'synthetic','protocol':protocol,'base_url':'http://127.0.0.1:11434' if protocol=='ollama' else 'https://api.openai.com','model':'synthetic','api_key':'synthetic-key','dimensions':None}
    seen=[]
    def request(settings,path,payload):
        seen.append(payload)
        if protocol=='anthropic':return {'content':[{'type':'tool_use','id':'format1','name':'submit_result','input':REPLY}],'stop_reason':'tool_use'}
        if protocol=='ollama':return {'message':{'content':json.dumps(REPLY)},'done':True,'done_reason':'stop'}
        return {'choices':[{'message':{'content':json.dumps(REPLY)},'finish_reason':'stop'}]}
    monkeypatch.setattr(gateway,'_request',request)
    result=gateway.chat([{'role':'user','content':'合成岗位'}],response_schema=growth.InterviewReply.model_json_schema())
    assert json.loads(result['text'])==REPLY and not result['tool_calls']
    if protocol=='openai':assert seen[0]['response_format']=={'type':'json_object'}
    elif protocol=='ollama':assert seen[0]['format']==growth.InterviewReply.model_json_schema()
    else:assert seen[0]['tool_choice']=={'type':'tool','name':'submit_result'}


def test_valid_document_without_finish_metadata_still_requires_schema_validation(monkeypatch):
    setup(monkeypatch,[{'text':json.dumps(REPLY),'tool_calls':[],'stop_reason':None}])
    assert growth.generate_json('问题',{},growth.InterviewReply)==REPLY


def test_failed_generation_leaves_existing_database_tree_unchanged(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import connect
    calls=setup(monkeypatch,['{"nodes":'])
    with TestClient(app) as c:
        c.headers['X-CSRF-Token']=c.get('/api/session').json()['csrf_token']
        auth=c.post('/api/auth/login',json={'username':'admin','password':'admin'}).json()
        c.headers['X-CSRF-Token']=auth['csrf_token']
        with connect() as db:
            original=json.dumps({'title':'已有记录','summary':'合成数据','nodes':[{'id':'n1','name':'基础技能','description':'合成技能说明','prerequisites':[],'task':'完成一项练习'}]})
            tid=db.execute('INSERT INTO trees(user_id,occupation,jd,content) VALUES (?,?,?,?)',(auth['user']['id'],'合成岗位','合成要求',original)).lastrowid
        r=c.post('/api/learning/tree',json={'occupation':'合成岗位','jd':'合成要求','consent':True})
        assert r.status_code==502 and len(calls)==2
        with connect() as db:
            assert db.execute('SELECT COUNT(*) FROM trees').fetchone()[0]==1
            assert db.execute('SELECT content FROM trees WHERE id=?',(tid,)).fetchone()[0]==original
