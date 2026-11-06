"""Configured model operations. Configuration/status never perform network I/O."""
import base64
import hashlib
import http.client
import ipaddress
import json
import math
import os
import secrets
import socket
import ssl
import threading
from urllib.parse import urlsplit
from .. import config

KINDS = ('chat', 'embedding', 'image')
OFFICIAL_HOSTS = {'api.openai.com', 'api.anthropic.com', 'api.deepseek.com', 'api.moonshot.cn', 'api.moonshot.ai', 'dashscope.aliyuncs.com', 'api.siliconflow.cn', 'api.siliconflow.com', 'open.bigmodel.cn', 'api.minimax.chat', 'api.minimax.io', 'generativelanguage.googleapis.com'}
_settings = {}
_lock = threading.RLock()
MAX_RESPONSE = 24 * 1024 * 1024

class GatewayError(Exception):
    safe_message = '模型服务不可用、配置无效或响应未通过校验，请检查管理员配置。'
    def __init__(self, message=None):
        super().__init__(message or self.safe_message)


def defaults(kind):
    if kind == 'chat':
        local = config.LLM_PROVIDER == 'ollama'
        return {'provider':config.LLM_PROVIDER, 'protocol':'ollama' if local else 'openai', 'base_url':'http://127.0.0.1:11434' if local else config.DEEPSEEK_BASE_URL, 'model':config.OLLAMA_MODEL if local else config.DEEPSEEK_MODEL, 'api_key':'' if local else config.DEEPSEEK_API_KEY, 'dimensions':None}
    prefix = kind.upper()
    return {'provider':'openai', 'protocol':'openai', 'base_url':os.getenv(prefix+'_BASE_URL','https://api.openai.com/v1'), 'model':os.getenv(prefix+'_MODEL',''), 'api_key':os.getenv(prefix+'_API_KEY',''), 'dimensions':None}


def get_settings(kind='chat', include_secret=False):
    if kind not in KINDS: raise ValueError('invalid model kind')
    with _lock: value = dict(_settings.get(kind) or defaults(kind))
    if not include_secret:
        value['has_key'] = bool(value.pop('api_key', ''))
    return value


def configured(kind='chat'):
    s = get_settings(kind, True)
    return bool(s['model'] and (s['protocol']=='ollama' or s.get('api_key')))


def is_custom_chat():
    with _lock: return 'chat' in _settings


def load_settings():
    """Called at startup after DB schema installation. No probes or automatic indexing."""
    from ..database import connect, cipher
    with connect() as db:
        rows = db.execute("SELECT name,value FROM settings WHERE name IN ('ai:chat','ai:embedding','ai:image','model')").fetchall()
    found = {}
    for row in rows:
        try:
            value = json.loads(cipher().decrypt(row['value'].encode()))
            if row['name']=='model':
                if any(r['name']=='ai:chat' for r in rows): continue
                s = defaults('chat');s.update(value)
                s['protocol']='ollama' if value.get('provider')=='ollama' else 'openai'
                s['base_url']='http://127.0.0.1:11434' if s['protocol']=='ollama' else config.DEEPSEEK_BASE_URL
                found['chat']=s
            else: found[row['name'].split(':',1)[1]]=value
        except Exception:
            # Corrupted encrypted configuration must never silently select another model.
            found[row['name'].split(':')[-1] if ':' in row['name'] else 'chat']={**defaults('chat'),'model':'','api_key':''}
    with _lock: _settings.clear();_settings.update(found)


def validate_endpoint(value, protocol='openai', resolve=False):
    try: u=urlsplit(value)
    except Exception: raise ValueError('模型地址格式无效。') from None
    if u.username or u.password or u.query or u.fragment or not u.hostname or len(value)>400 or any(c in value for c in '\r\n\\'):
        raise ValueError('模型地址不能包含凭据、参数或片段。')
    try: port=u.port
    except ValueError: raise ValueError('模型端口无效。') from None
    if protocol=='ollama':
        if value.rstrip('/')!='http://127.0.0.1:11434': raise ValueError('Ollama仅允许本机固定地址。')
        return u, '127.0.0.1'
    allowed=OFFICIAL_HOSTS | {h.strip().lower() for h in os.getenv('MODEL_ALLOWED_HOSTS','').split(',') if h.strip()}
    if u.scheme!='https' or port not in (None,443) or u.hostname.lower() not in allowed:
        raise ValueError('模型地址必须为允许主机的HTTPS 443地址；自定义网关需配置MODEL_ALLOWED_HOSTS。')
    if not resolve: return u, None
    try: addresses=socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)
    except OSError: raise GatewayError() from None
    ips={a[4][0] for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips): raise GatewayError()
    return u, sorted(ips)[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, ip, timeout):
        super().__init__(host,port=443,timeout=timeout,context=ssl.create_default_context());self.pinned_ip=ip
    def connect(self):
        raw=socket.create_connection((self.pinned_ip,443),self.timeout,self.source_address)
        try: self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close();raise


def _request(s, operation, payload=None, body=None, content_type='application/json'):
    """Only fixed model operations; pin public IP while retaining hostname TLS/SNI."""
    allowed={'/chat/completions','/messages','/embeddings','/images/edits','/api/chat','/api/embed'}
    if operation not in allowed: raise GatewayError()
    u,ip=validate_endpoint(s['base_url'],s['protocol'],True)
    conn=http.client.HTTPConnection('127.0.0.1',11434,timeout=config.LLM_TIMEOUT) if s['protocol']=='ollama' else PinnedHTTPSConnection(u.hostname,ip,config.LLM_TIMEOUT)
    headers={'Content-Type':content_type}
    key=s.get('api_key','')
    if s['protocol']=='anthropic': headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
    elif key: headers['Authorization']='Bearer '+key
    try:
        data=body if body is not None else json.dumps(payload,ensure_ascii=False).encode()
        conn.request('POST',u.path.rstrip('/')+operation,body=data,headers=headers)
        response=conn.getresponse()
        if response.status<200 or response.status>=300: raise GatewayError()
        raw=response.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE: raise GatewayError()
        return json.loads(raw)
    except GatewayError: raise
    except Exception: raise GatewayError() from None
    finally: conn.close()


def save_settings(kind, value):
    from ..database import connect, cipher, encode
    if kind not in KINDS: raise ValueError('invalid model kind')
    if set(value)-{'provider','protocol','base_url','model','api_key','dimensions'}: raise ValueError('未知配置字段。')
    s=get_settings(kind,True);s.update({k:v for k,v in value.items() if k!='api_key'})
    if value.get('api_key'): s['api_key']=value['api_key'].strip()
    if s['protocol'] not in ('openai','anthropic','ollama') or (kind!='chat' and s['protocol']=='anthropic'): raise ValueError('此操作不支持所选协议。')
    for key in ('provider','model','api_key'):
        if not isinstance(s.get(key),str) or len(s[key])>(2048 if key=='api_key' else 120) or any(c in s[key] for c in '\r\n'): raise ValueError('模型配置格式无效。')
    if s['protocol']=='ollama' and 'cloud' in s['model'].lower(): raise ValueError('Ollama仅支持本机模型。')
    dim=s.get('dimensions')
    if dim is not None and (isinstance(dim,bool) or not isinstance(dim,int) or not 1<=dim<=65536): raise ValueError('向量维度无效。')
    validate_endpoint(s['base_url'],s['protocol'])
    encrypted=cipher().encrypt(encode(s).encode()).decode()
    with connect() as db: db.execute('INSERT INTO settings(name,value) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',('ai:'+kind,encrypted))
    with _lock: _settings[kind]=s
    return get_settings(kind)


def status(kind='chat'):
    s=get_settings(kind)
    try: validate_endpoint(s['base_url'],s['protocol']); ready=configured(kind)
    except ValueError: ready=False
    return {**s,'ready':ready,'configuration_only':True,'connected':None,'message':'已保存配置；尚未连接验证。' if ready else '模型尚未完整配置。'}


def fingerprint():
    s=get_settings('embedding');return hashlib.sha256(json.dumps({k:s[k] for k in ('provider','protocol','base_url','model','dimensions')},sort_keys=True).encode()).hexdigest()


def _calls(message):
    result=[]
    for c in message.get('tool_calls',[]):
        f=c.get('function',c);args=f.get('arguments',{})
        if isinstance(args,str): args=json.loads(args)
        if not isinstance(args,dict): raise GatewayError()
        result.append({'id':c.get('id') or secrets.token_hex(8),'name':f['name'],'arguments':args})
    return result


def chat(messages, *, system='', tools=None, temperature=.3, max_tokens=2500, purpose='chat'):
    s=get_settings('chat',True)
    if not configured(): raise GatewayError('请先由管理员配置大模型。')
    try:
        if s['protocol']=='anthropic':
            converted=[]
            for m in messages:
                role=m['role']
                if role=='system': system+='\n'+str(m['content']);continue
                if role=='tool': entry={'role':'user','content':[{'type':'tool_result','tool_use_id':m['tool_call_id'],'content':str(m['content'])}]}
                else:
                    content=[{'type':'text','text':m['content']}] if m.get('content') else []
                    for c in _calls(m): content.append({'type':'tool_use','id':c['id'],'name':c['name'],'input':c['arguments']})
                    entry={'role':role,'content':content}
                if converted and converted[-1]['role']==entry['role']: converted[-1]['content'].extend(entry['content'])
                else: converted.append(entry)
            p={'model':s['model'],'messages':converted,'system':system,'temperature':temperature,'max_tokens':max_tokens}
            if tools: p['tools']=[{'name':t['function']['name'],'description':t['function'].get('description',''),'input_schema':t['function']['parameters']} for t in tools]
            r=_request(s,'/messages',p)
            return {'text':''.join(c.get('text','') for c in r['content'] if c['type']=='text'),'tool_calls':[{'id':c['id'],'name':c['name'],'arguments':c['input']} for c in r['content'] if c['type']=='tool_use'],'stop_reason':r.get('stop_reason','')}
        msgs=([{'role':'system','content':system}] if system else [])+messages
        # Normalized assistant calls can be round-tripped by tool agents.
        msgs=[dict(m) for m in msgs]
        for m in msgs:
            if m.get('tool_calls'): m['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['arguments'],ensure_ascii=False)}} if 'name' in c else c for c in m['tool_calls']]
        if s['protocol']=='ollama':
            for m in msgs:
                for c in m.get('tool_calls',[]):
                    args=c['function']['arguments']
                    if isinstance(args,str): c['function']['arguments']=json.loads(args)
        p={'model':s['model'],'messages':msgs,'stream':False}
        if s['protocol']=='ollama':
            p['options']={'temperature':temperature,'num_predict':max_tokens}
        else: p.update(temperature=temperature,max_tokens=max_tokens)
        if tools:p['tools']=tools
        r=_request(s,'/api/chat' if s['protocol']=='ollama' else '/chat/completions',p)
        choice=r if s['protocol']=='ollama' else r['choices'][0]
        m=choice['message']
        return {'text':m.get('content') or '', 'tool_calls':_calls(m),'stop_reason':choice.get('finish_reason',r.get('done_reason','stop'))}
    except GatewayError: raise
    except Exception: raise GatewayError() from None


def embed(texts):
    s=get_settings('embedding',True)
    if not configured('embedding'): raise GatewayError('请先配置Embedding，再手动构建索引。')
    p={'model':s['model'],'input':texts}
    if s.get('dimensions') and s['protocol']=='openai': p['dimensions']=s['dimensions']
    r=_request(s,'/api/embed' if s['protocol']=='ollama' else '/embeddings',p)
    try:
        vectors=r['embeddings'] if s['protocol']=='ollama' else [v['embedding'] for v in sorted(r['data'],key=lambda x:x['index'])]
        if len(vectors)!=len(texts): raise ValueError()
        dim=s.get('dimensions') or len(vectors[0])
        for v in vectors:
            if len(v)!=dim or not v or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) or not any(v): raise ValueError()
        return vectors
    except Exception: raise GatewayError('Embedding返回的向量数量、维度或数值无效。') from None


def image_edit(image_bytes,mime,*,size='1024x1024',background='auto'):
    s=get_settings('image',True)
    if not configured('image') or s['protocol']!='openai': raise GatewayError('请先配置支持图片编辑的模型。')
    if mime not in ('image/png','image/jpeg','image/webp') or len(image_bytes)>8*1024*1024 or size not in ('1024x1024','1024x1536','1536x1024','auto') or background not in ('auto','transparent','opaque','white','blue','red'): raise GatewayError('图片编辑输入无效。')
    boundary='cg'+secrets.token_hex(16);parts=[]
    fields={'model':s['model'],'prompt':'Create a centered head and shoulders professional career portrait preserving the exact same person and all facial features. Formal business attire, natural lighting. Plain '+(background if background in ('white','blue','red') else 'neutral')+' background.','size':size,'background':'opaque' if background in ('white','blue','red') else background}
    if not s['model'].startswith('gpt-image'): fields['response_format']='b64_json'
    for k,v in fields.items(): parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="portrait.{mime.split("/")[1]}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),image_bytes,f'\r\n--{boundary}--\r\n'.encode()])
    r=_request(s,'/images/edits',body=b''.join(parts),content_type='multipart/form-data; boundary='+boundary)
    try:
        raw=base64.b64decode(r['data'][0]['b64_json'],validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)>16*1024*1024: raise ValueError()
        return {'bytes':raw,'mime':'image/png'}
    except Exception: raise GatewayError('图片服务未返回有效PNG；不获取上游URL。') from None
