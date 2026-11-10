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

# CORS：默认不允许任何跨域来源。部署为独立前端 / 反向代理时用 EXTRA_CORS_ORIGINS 追加，
# 逗号分隔、写全 scheme（如 https://app.example.com）；精确匹配，不支持通配。
CORS_ORIGINS = tuple(
    o.strip().rstrip('/') for o in os.getenv('EXTRA_CORS_ORIGINS', '').split(',') if o.strip())

# 跨站携带 Cookie 需要 samesite=none 且 secure=true（浏览器强制），且必须走 HTTPS。
# 默认保持 strict：同源部署下最紧，跨域场景由部署方显式打开。
_SAMESITE_RAW = os.getenv('CG_COOKIE_SAMESITE', 'strict').strip().lower()
COOKIE_SAMESITE = _SAMESITE_RAW if _SAMESITE_RAW in ('strict', 'lax', 'none') else 'strict'
COOKIE_SECURE = os.getenv('CG_COOKIE_SECURE', '0') == '1'
