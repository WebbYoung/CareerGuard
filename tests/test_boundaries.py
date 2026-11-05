"""缓存与模型适配边界；模型替身仅测试协议，不声称真实模型已验证。"""
import asyncio
import io
import json
import time
import numpy as np
import pypdfium2 as pdfium
import pytest
from fastapi import HTTPException
from PIL import Image
from app import config
from app.api import read_bytes
from app.store import MemoryStore
from app.services import llm, ocr
from app.services.security import inspect_injection


def test_expiry_removes_material_and_rejects_stale_session(monkeypatch):
    cache = MemoryStore()
    sid, session = cache.bootstrap(None)
    cache.save(sid, 0, {'text':'合成材料'})
    session.touched = time.monotonic()-1801
    with pytest.raises(HTTPException) as error:
        cache.require(sid)
    assert error.value.status_code == 401
    assert sid not in cache.sessions


def test_clear_prevents_inflight_task_from_restoring_material():
    cache = MemoryStore()
    sid, session = cache.bootstrap(None)
    generation = session.generation
    cache.clear(sid)
    with pytest.raises(HTTPException) as error:
        cache.save(sid, generation, {'text':'迟到的原文'})
    assert error.value.status_code == 409
    assert not cache.require(sid).materials


def test_session_capacity_rejects_new_session_instead_of_evicting_active(monkeypatch):
    cache = MemoryStore()
    monkeypatch.setattr(config, 'MAX_SESSIONS', 1)
    sid,_ = cache.bootstrap(None)
    with pytest.raises(HTTPException) as error:
        cache.bootstrap(None)
    assert error.value.status_code == 503
    assert sid in cache.sessions


def test_chunked_upload_is_bounded_even_without_content_length():
    class StreamRequest:
        headers = {}
        async def stream(self):
            yield b'a'*4
            yield b'b'*4
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_bytes(StreamRequest(), 6))
    assert error.value.status_code == 413


def test_many_page_pdf_rejected_without_invoking_model():
    buffer = io.BytesIO()
    with pdfium.PdfDocument.new() as doc:
        for _ in range(9):
            doc.new_page(200,200)
        doc.save(buffer)
    with pytest.raises(HTTPException) as error:
        ocr.parse_upload(buffer.getvalue(),'.pdf','application/pdf')
    assert error.value.status_code == 413


def test_valid_pdf_renders_in_memory_and_reaches_ocr(monkeypatch):
    buffer = io.BytesIO()
    with pdfium.PdfDocument.new() as doc:
        doc.new_page(200,100)
        doc.save(buffer)
    def recognize(image, page):
        assert isinstance(image,np.ndarray)
        assert image.shape == (200,400,3)
        return [{'text':'合成PDF材料','confidence':.97,'low_confidence':False,'page':page,'box':[]}]
    monkeypatch.setattr(ocr,'_recognize',recognize)
    result = ocr.parse_upload(buffer.getvalue(),'.pdf','application/pdf')
    assert result['pages'] == 1
    assert result['text'] == '合成PDF材料'
    assert result['lines'][0]['page'] == 1


def test_ocr_adapter_returns_low_confidence_and_boxes_without_file_paths(monkeypatch):
    class Engine:
        def predict(self, image):
            assert isinstance(image, np.ndarray)
            return [{'rec_texts':['招聘示例','先交押金'], 'rec_scores':[.97,.72],
                     'rec_polys':np.array([[[0,0],[10,0],[10,5],[0,5]],[[0,5],[10,5],[10,10],[0,10]]])}]
    monkeypatch.setattr(ocr,'_get_engine',lambda:Engine())
    buffer=io.BytesIO()
    Image.new('RGB',(40,40),'white').save(buffer,format='PNG')
    result=ocr.parse_upload(buffer.getvalue(),'.png','image/png')
    assert result['text']=='招聘示例\n先交押金'
    assert result['lines'][1]['low_confidence']
    assert result['lines'][1]['box']==[[0,5],[10,5],[10,10],[0,10]]


def test_llm_without_configuration_does_not_attempt_network(monkeypatch):
    monkeypatch.setattr(config,'OLLAMA_MODEL','')
    def forbidden(*args,**kwargs):
        pytest.fail('未配置模型时不得请求服务')
    monkeypatch.setattr(llm,'_local_json',forbidden)
    assert not llm.explain('风险','文字',{'R1':{}})['used']


def test_llm_unrecognized_citation_rejected(monkeypatch):
    monkeypatch.setattr(llm,'status',lambda:{'ready':True})
    monkeypatch.setattr(llm,'_local_json',lambda *a,**kw:{'response':json.dumps({'summary':'请核验','suggestions':[{'text':'核验主体','evidence_ids':['FAKE']}]})})
    assert not llm.explain('风险','文字',{'R1':{}})['used']


def test_llm_valid_json_is_used_and_input_pii_masked(monkeypatch):
    monkeypatch.setattr(llm,'status',lambda:{'ready':True})
    phone='199'+'0'*8
    def protocol(path,payload,timeout):
        assert phone not in payload['prompt']
        assert '***' in payload['prompt']
        return {'response':json.dumps({'summary':'存在待核验的收费线索。','suggestions':[{'text':'请核验收费依据。','evidence_ids':['R1']}]})}
    monkeypatch.setattr(llm,'_local_json',protocol)
    result=llm.explain('风险','手机：'+phone,{'R1':{'category':'收费'}})
    assert result['used']
    assert result['content']['suggestions'][0]['evidence_ids']==['R1']


@pytest.mark.parametrize('summary',['一定是诈骗','保证录用','请访问https://example.invalid'])
def test_llm_unsafe_certainty_and_links_rejected(monkeypatch,summary):
    monkeypatch.setattr(llm,'status',lambda:{'ready':True})
    monkeypatch.setattr(llm,'_local_json',lambda *a,**kw:{'response':json.dumps({'summary':summary,'suggestions':[]})})
    assert not llm.explain('风险','文字',{'R1':{}})['used']


def test_upload_rejects_valid_signature_with_wrong_extension():
    with pytest.raises(HTTPException) as error:
        ocr.validate_signature(b'%PDF-1.7\n', '.png','image/png')
    assert error.value.status_code==415


def test_ocr_initialization_disables_installed_version_host_checks(monkeypatch):
    import os
    import sys
    from types import SimpleNamespace
    monkeypatch.delenv('DISABLE_MODEL_SOURCE_CHECK',raising=False)
    monkeypatch.setattr(ocr,'_engine',None)
    monkeypatch.setattr(ocr,'model_configured',lambda:True)
    def constructor(**kwargs):
        assert os.environ.get('DISABLE_MODEL_SOURCE_CHECK') == 'True'
        assert kwargs['use_doc_orientation_classify'] is False
        assert kwargs['use_doc_unwarping'] is False
        assert kwargs['use_textline_orientation'] is False
        return object()
    monkeypatch.setitem(sys.modules,'paddleocr',SimpleNamespace(PaddleOCR=constructor))
    assert ocr._get_engine() is not None
