"""Shared admin knowledge, explicit embedding build, labelled keyword fallback."""
import hashlib
import json
import math
import re
import threading
from ..database import connect
from . import model_gateway as gateway

_build_lock=threading.Lock()

def _revision(text): return hashlib.sha256(text.encode()).hexdigest()

def _chunks(text, size=800, overlap=120):
    return [text[start:start+size] for start in range(0,len(text),size-overlap) if text[start:start+size].strip()]

def documents():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT id,title,content,revision,created FROM knowledge_documents ORDER BY id DESC')]

def save_document(title,content,document_id=None):
    if not isinstance(title,str) or not title.strip() or len(title)>120 or not isinstance(content,str) or not content.strip() or len(content)>100000: raise ValueError('知识标题或正文无效。')
    rev=_revision(content)
    with connect() as db:
        if document_id is None:
            if db.execute('SELECT COUNT(*) FROM knowledge_documents').fetchone()[0]>=100: raise ValueError('知识文档数量已达上限。')
            document_id=db.execute('INSERT INTO knowledge_documents(title,content,revision) VALUES (?,?,?)',(title.strip(),content,rev)).lastrowid
        else:
            if db.execute('SELECT id FROM knowledge_documents WHERE id=?',(document_id,)).fetchone() is None: raise LookupError('知识文档不存在。')
            db.execute('UPDATE knowledge_documents SET title=?,content=?,revision=? WHERE id=?',(title.strip(),content,rev,document_id))
            db.execute('DELETE FROM knowledge_chunks WHERE document_id=?',(document_id,))
        db.executemany('INSERT INTO knowledge_chunks(document_id,ordinal,content,revision) VALUES (?,?,?,?)',[(document_id,i,c,rev) for i,c in enumerate(_chunks(content))])
    return {'id':document_id,'revision':rev,'indexed':False}

def delete_document(document_id):
    with connect() as db:
        if db.execute('DELETE FROM knowledge_documents WHERE id=?',(document_id,)).rowcount!=1: raise LookupError('知识文档不存在。')
    return {'deleted':True}

def state():
    fp=gateway.fingerprint()
    with connect() as db:
        count=db.execute('SELECT COUNT(*) FROM knowledge_documents').fetchone()[0]
        chunks=db.execute('SELECT COUNT(*),SUM(CASE WHEN vector IS NOT NULL AND fingerprint=? THEN 1 ELSE 0 END) FROM knowledge_chunks',(fp,)).fetchone()
    return {'documents':count,'chunks':chunks[0],'indexed_chunks':chunks[1] or 0,'embedding_configured':gateway.configured('embedding'),'fingerprint':fp,'building':_build_lock.locked(),'retrieval_mode':'vector' if chunks[0] and chunks[0]==chunks[1] else 'keyword_fallback','message':'仅管理员点击构建时生成向量；更改Embedding模型后需重新构建。'}

def build_index():
    if not _build_lock.acquire(False): raise ValueError('索引正在构建。')
    try:
        if not gateway.configured('embedding'): raise ValueError('请先配置Embedding模型，再手动构建。')
        fp=gateway.fingerprint()
        with connect() as db:
            rows=[dict(r) for r in db.execute('SELECT id,document_id,content,revision FROM knowledge_chunks ORDER BY id')]
        vectors=[]
        for start in range(0,len(rows),32): vectors.extend(gateway.embed([r['content'] for r in rows[start:start+32]]))
        if fp!=gateway.fingerprint(): raise ValueError('构建期间Embedding配置改变，请重新构建。')
        dimensions={len(v) for v in vectors}
        if len(dimensions)>1: raise ValueError('Embedding维度不一致。')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=[(r['id'],r['revision']) for r in db.execute('SELECT id,revision FROM knowledge_chunks ORDER BY id')]
            if current!=[(r['id'],r['revision']) for r in rows]: raise ValueError('构建期间知识文档已改变，请重新构建。')
            for row,vector in zip(rows,vectors): db.execute('UPDATE knowledge_chunks SET vector=?,fingerprint=? WHERE id=?',(json.dumps(vector,separators=(',',':')),fp,row['id']))
        return state()
    finally: _build_lock.release()

def cosine(a,b):
    if not a or len(a)!=len(b) or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in [*a,*b]): raise ValueError('invalid vectors')
    na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
    if not na or not nb or not math.isfinite(na*nb): raise ValueError('invalid vector norm')
    return max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/(na*nb)))

def _terms(text):
    text=text.lower();terms=set(re.findall(r'[a-z0-9_]+',text))
    for part in re.findall(r'[\u4e00-\u9fff]+',text):
        terms.update(part[i:i+2] for i in range(max(1,len(part)-1)))
    return terms

def search(query,limit=5):
    if not isinstance(query,str) or len(query)>4000 or not query.strip(): return {'citations':[],'retrieval_mode':'keyword_fallback','message':'检索词为空或过长。'}
    limit=max(1,min(int(limit),10));fp=gateway.fingerprint()
    with connect() as db:
        rows=[dict(r) for r in db.execute('SELECT c.*,d.title FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id ORDER BY c.id')]
    mode='keyword_fallback';reason='未配置可用向量索引，使用关键词检索。';scored=[]
    if rows and gateway.configured('embedding') and all(r['fingerprint']==fp and r['vector'] for r in rows):
        try:
            vector=gateway.embed([query])[0]
            scored=[(cosine(vector,json.loads(r['vector'])),r) for r in rows]
            mode='vector';reason='使用当前Embedding模型的向量索引。'
        except Exception: reason='向量检索不可用或索引维度无效，已降级为关键词检索。'
    if mode=='keyword_fallback':
        terms=_terms(query)
        scored=[(len(terms & _terms(r['title']+' '+r['content']))/max(1,len(terms)),r) for r in rows]
    scored.sort(key=lambda pair:(-pair[0],pair[1]['id']))
    citations=[{'id':'kb-'+str(r['id']),'document_id':r['document_id'],'title':r['title'],'text':r['content'],'score':round(score,5)} for score,r in scored[:limit] if score>0]
    return {'citations':citations,'retrieval_mode':mode,'message':reason}
