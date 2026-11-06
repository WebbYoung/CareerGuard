"""Persistent RAG tests use a temporary DB and synthetic vectors only."""
import pytest
from app import database
from app.services import rag, model_gateway as gateway
from app.services.model_schema import SCHEMA

@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(database,'SCHEMA',database.SCHEMA+SCHEMA)
    monkeypatch.setattr(gateway,'_settings',{})
    monkeypatch.setattr(gateway,'_request',lambda *a,**k:pytest.fail('No network in RAG tests'))


def configured(monkeypatch):
    gateway._settings['embedding']={'provider':'unit','protocol':'openai','base_url':'https://api.openai.com/v1','model':'fake-embedding','api_key':'fake-key','dimensions':2}
    monkeypatch.setattr(gateway,'embed',lambda texts:[[1.,0.] if 'Python' in t else [0.,1.] for t in texts])


def test_ingestion_never_embeds_and_keyword_mode_visible(monkeypatch):
    monkeypatch.setattr(gateway,'embed',lambda *a:pytest.fail('No automatic embedding'))
    rag.save_document('Python指南','Python异常处理和项目测试。')
    result=rag.search('Python')
    assert result['retrieval_mode']=='keyword_fallback'
    assert result['citations'][0]['title']=='Python指南'
    assert not rag.state()['indexed_chunks']


def test_manual_build_persists_vectors_and_model_change_falls_back(monkeypatch):
    configured(monkeypatch)
    doc=rag.save_document('Python','Python异常处理');rag.save_document('SQL','SQL事务')
    assert rag.build_index()['indexed_chunks']==2
    result=rag.search('Python')
    assert result['retrieval_mode']=='vector' and result['citations'][0]['document_id']==doc['id']
    gateway._settings['embedding']['model']='other-model'
    assert rag.search('Python')['retrieval_mode']=='keyword_fallback'
    assert rag.state()['indexed_chunks']==0


def test_edit_invalidates_and_delete_cascades(monkeypatch):
    configured(monkeypatch)
    doc=rag.save_document('Guide','Python testing');rag.build_index()
    rag.save_document('Guide','Python changed',doc['id'])
    assert rag.state()['indexed_chunks']==0
    rag.delete_document(doc['id'])
    assert rag.state()['chunks']==0
    with pytest.raises(LookupError):rag.delete_document(doc['id'])

@pytest.mark.parametrize('a,b',[([1.],[1.,2.]),([0.],[1.]),([float('inf')],[1.]),([True],[1.])])
def test_cosine_rejects_invalid_or_mismatched_vectors(a,b):
    with pytest.raises(ValueError):rag.cosine(a,b)


def test_cosine_and_corrupt_vector_fallback(monkeypatch):
    configured(monkeypatch)
    assert rag.cosine([1.,0.],[1.,0.])==1.
    rag.save_document('Python','Python testing');rag.build_index()
    with database.connect() as db:db.execute("UPDATE knowledge_chunks SET vector='[1,2,3]'")
    assert rag.search('Python')['retrieval_mode']=='keyword_fallback'


def test_concurrent_document_edit_discards_build(monkeypatch):
    configured(monkeypatch)
    doc=rag.save_document('Python','Python initial')
    def fake(texts):
        rag.save_document('Python','Python changed',doc['id'])
        return [[1.,0.] for t in texts]
    monkeypatch.setattr(gateway,'embed',fake)
    with pytest.raises(ValueError):rag.build_index()
    assert rag.state()['indexed_chunks']==0
