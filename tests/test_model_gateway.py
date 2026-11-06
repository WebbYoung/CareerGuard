"""Offline contract tests. No real provider or embedding transport is used."""
import json
import socket
import pytest
from app import config
from app.services import model_gateway as g

@pytest.fixture(autouse=True)
def isolated_gateway(monkeypatch):
    monkeypatch.setattr(g,'_settings',{})
    def deny(*args,**kwargs): raise AssertionError('Unexpected network access')
    monkeypatch.setattr(socket,'create_connection',deny)
    monkeypatch.setattr(socket,'getaddrinfo',deny)


def setup_model(protocol='openai',kind='chat'):
    g._settings[kind]={'provider':'unit','protocol':protocol,'base_url':'https://api.openai.com/v1','model':'unit-model','api_key':'fake-test-key','dimensions':None}


def test_config_and_status_do_not_resolve_or_request(monkeypatch):
    setup_model()
    assert g.status()['configuration_only']
    assert g.status()['connected'] is None
    assert 'fake-test-key' not in json.dumps(g.get_settings())
    result=g.save_settings('chat',{'model':'changed','api_key':''})
    assert result['has_key'] and g.get_settings(include_secret=True)['api_key']=='fake-test-key'


def test_settings_encrypted_and_survive_load():
    from app.database import connect
    setup_model();g.save_settings('chat',{})
    with connect() as db: encrypted=db.execute("SELECT value FROM settings WHERE name='ai:chat'").fetchone()[0]
    assert 'fake-test-key' not in encrypted
    g._settings.clear();g.load_settings()
    assert g.get_settings(include_secret=True)['api_key']=='fake-test-key'

@pytest.mark.parametrize('url',['http://api.openai.com','https://api.openai.com:444','https://user:pass@api.openai.com','https://api.openai.com?key=x','https://api.openai.com#frag','https://127.0.0.1','https://api.openai.com.evil.test'])
def test_endpoint_policy_rejects_untrusted_urls(url):
    with pytest.raises(ValueError): g.validate_endpoint(url)


def test_dns_rejects_any_nonpublic_address(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    with pytest.raises(g.GatewayError):g.validate_endpoint('https://api.openai.com',resolve=True)


def test_openai_tool_roundtrip(monkeypatch):
    setup_model();seen={}
    def fake(s,path,payload):
        seen.update(payload);assert path=='/chat/completions'
        return {'choices':[{'message':{'content':None,'tool_calls':[{'id':'t1','function':{'name':'lookup','arguments':'{"query":"Python"}'}}]},'finish_reason':'tool_calls'}]}
    monkeypatch.setattr(g,'_request',fake)
    r=g.chat([{'role':'user','content':'learn Python'},{'role':'assistant','content':'','tool_calls':[{'id':'old','name':'lookup','arguments':{'query':'old'}}]},{'role':'tool','tool_call_id':'old','content':'result'}])
    assert r['tool_calls']==[{'id':'t1','name':'lookup','arguments':{'query':'Python'}}]
    assert json.loads(seen['messages'][1]['tool_calls'][0]['function']['arguments'])=={'query':'old'}


def test_anthropic_tool_conversion(monkeypatch):
    setup_model('anthropic');seen={}
    def fake(s,path,payload):
        seen.update(payload);assert path=='/messages'
        return {'content':[{'type':'text','text':'answer'},{'type':'tool_use','id':'new','name':'lookup','input':{'x':1}}],'stop_reason':'tool_use'}
    monkeypatch.setattr(g,'_request',fake)
    r=g.chat([{'role':'user','content':'question'},{'role':'assistant','content':'','tool_calls':[{'id':'old','name':'lookup','arguments':{}}]},{'role':'tool','tool_call_id':'old','content':'found'}],tools=[{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}])
    assert seen['messages'][2]['content'][0]['tool_use_id']=='old'
    assert seen['tools'][0]['input_schema']=={'type':'object'}
    assert r['text']=='answer' and r['tool_calls'][0]['arguments']=={'x':1}


def test_embed_rejects_invalid_vectors(monkeypatch):
    setup_model(kind='embedding')
    monkeypatch.setattr(g,'_request',lambda *a,**k:{'data':[{'index':0,'embedding':[float('nan')]}]})
    with pytest.raises(g.GatewayError):g.embed(['text'])


def test_image_url_is_never_fetched(monkeypatch):
    setup_model(kind='image')
    monkeypatch.setattr(g,'_request',lambda *a,**k:{'data':[{'url':'https://example.invalid/private'}]})
    with pytest.raises(g.GatewayError):g.image_edit(b'input','image/png',size='1024x1536',background='blue')


def test_image_color_maps_to_prompt_and_opaque(monkeypatch):
    import base64
    setup_model(kind='image');seen={}
    def fake(s,path,**kw):
        seen.update(kw)
        return {'data':[{'b64_json':base64.b64encode(b'\x89PNG\r\n\x1a\nunit').decode()}]}
    monkeypatch.setattr(g,'_request',fake)
    assert g.image_edit(b'input','image/png',background='blue')['mime']=='image/png'
    assert b'Plain blue background' in seen['body'] and b'\r\n\r\nopaque\r\n' in seen['body']


def test_actual_transport_pins_validated_ip_and_does_not_follow_redirect(monkeypatch):
    setup_model();requests=[];resolved=[]
    def dns(host,port,**kwargs):
        resolved.append(host)
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
    monkeypatch.setattr(socket,'getaddrinfo',dns)
    class Connection:
        def __init__(self,host,ip,timeout):assert host=='api.openai.com' and ip=='8.8.8.8'
        def request(self,method,path,body=None,headers=None):requests.append(path)
        def getresponse(self):return type('Response',(),{'status':302})()
        def close(self):pass
    monkeypatch.setattr(g,'PinnedHTTPSConnection',Connection)
    with pytest.raises(g.GatewayError):g.chat([{'role':'user','content':'unit'}])
    assert requests==['/v1/chat/completions'] and resolved==['api.openai.com']


def test_pinned_https_keeps_certificate_host_and_uses_numeric_ip(monkeypatch):
    calls=[]
    class Raw:
        def close(self):pass
    class TLS:
        def wrap_socket(self,raw,server_hostname):calls.append(('tls',server_hostname));return raw
    def connect(address,timeout,source):calls.append(('connect',address));return Raw()
    monkeypatch.setattr(socket,'create_connection',connect)
    conn=g.PinnedHTTPSConnection('api.openai.com','8.8.8.8',5);conn._context=TLS();conn.connect()
    assert calls==[('connect',('8.8.8.8',443)),('tls','api.openai.com')]


def test_ollama_tools_use_object_arguments(monkeypatch):
    setup_model('ollama');g._settings['chat']['base_url']='http://127.0.0.1:11434'
    def fake(s,path,payload):
        assert path=='/api/chat'
        assert payload['messages'][0]['tool_calls'][0]['function']['arguments']=={'x':1}
        return {'message':{'content':'ok'},'done_reason':'stop'}
    monkeypatch.setattr(g,'_request',fake)
    assert g.chat([{'role':'assistant','tool_calls':[{'id':'x','name':'lookup','arguments':{'x':1}}]}])['text']=='ok'


def test_generic_remote_provider_strips_raw_resume_fields():
    from app.services import llm
    setup_model()
    evidence=llm._safe_evidence({'raw_resume':'private','raw_jd':'private','resume_evidence':['private'],'skill':'Python'})
    assert evidence=={'skill':'Python'}
