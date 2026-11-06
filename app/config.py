"""环境变量提供模型初始配置；管理员可保存经端点策略校验的加密配置。"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
MAX_UPLOAD = 8 * 1024 * 1024
MAX_TEXT = 30000
MAX_JSON = 160000
MAX_PAGES = 8
MAX_PIXELS = 12_000_000
MAX_SESSIONS = 64
MAX_MATERIALS = 24
SESSION_TTL = 1800
OCR_CONFIDENCE = 0.85
OCR_DET_DIR = os.getenv('OCR_DET_DIR', '')
OCR_REC_DIR = os.getenv('OCR_REC_DIR', '')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', '').strip()
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'ollama').strip().lower()
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '').strip()
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').strip()
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash').strip()
LLM_TIMEOUT = min(120, max(5, int(os.getenv('LLM_TIMEOUT', '45'))))
ENABLE_CLASSIFIER = os.getenv('ENABLE_RISK_CLASSIFIER', '0') == '1'
