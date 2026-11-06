"""单元与协议测试不依赖真实权重或本机服务，避免受开发者环境配置影响。"""
import socket
import pytest
from app.services import model_gateway
from app import config


@pytest.fixture(autouse=True)
def isolated_model_configuration(monkeypatch,tmp_path):
    monkeypatch.setattr(model_gateway,'_settings',{})
    def forbidden_network(*args,**kwargs):
        raise AssertionError('Tests must mock all provider/embedding/image network transports')
    monkeypatch.setattr(socket,'create_connection',forbidden_network)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden_network)
    monkeypatch.setenv('CG_DB_PATH',str(tmp_path/'isolated.sqlite3'))
    monkeypatch.setenv('CG_MASTER_KEY_PATH',str(tmp_path/'isolated.key'))
    monkeypatch.setattr(config,'OCR_DET_DIR','')
    monkeypatch.setattr(config,'OCR_REC_DIR','')
    monkeypatch.setattr(config,'OLLAMA_MODEL','')
    monkeypatch.setattr(config,'LLM_PROVIDER','ollama',raising=False)
    monkeypatch.setattr(config,'DEEPSEEK_API_KEY','',raising=False)
    monkeypatch.setattr(config,'DEEPSEEK_BASE_URL','https://api.deepseek.com',raising=False)
    monkeypatch.setattr(config,'DEEPSEEK_MODEL','deepseek-flash',raising=False)
    monkeypatch.setattr(config,'ENABLE_CLASSIFIER',False)
