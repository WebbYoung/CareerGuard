"""图片/PDF 只从 bytes 解码，PaddleOCR 只接受 ndarray；绝不传入 URL/文件名。"""
import io
import os
import threading
import warnings
from pathlib import Path
import numpy as np
from PIL import Image
from fastapi import HTTPException
from .. import config

Image.MAX_IMAGE_PIXELS = config.MAX_PIXELS
_engine = None
_lock = threading.Lock()


def model_configured() -> bool:
    return bool(config.OCR_DET_DIR and config.OCR_REC_DIR and
                Path(config.OCR_DET_DIR).is_dir() and Path(config.OCR_REC_DIR).is_dir())


def _image(data: bytes) -> np.ndarray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {'PNG','JPEG'} or image.width * image.height > config.MAX_PIXELS:
                    raise HTTPException(413, '图像格式不支持或像素超过1200万。')
                image.load()
                return np.array(image.convert('RGB'))
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, '图像像素超过安全限制。') from None
    except Exception:
        raise HTTPException(415, '无法解码图片，请上传有效的 PNG 或 JPEG。') from None


def validate_signature(data: bytes, extension: str, content_type: str):
    actual = ('png' if data.startswith(b'\x89PNG\r\n\x1a\n') else
              'jpeg' if data.startswith(b'\xff\xd8\xff') else
              'pdf' if data.startswith(b'%PDF-') else None)
    allowed = {'.png': ('png','image/png'), '.jpg': ('jpeg','image/jpeg'),
               '.jpeg': ('jpeg','image/jpeg'), '.pdf': ('pdf','application/pdf')}
    if extension not in allowed or allowed[extension] != (actual, content_type):
        raise HTTPException(415, '只接受扩展名、内容类型与文件签名一致的 PNG/JPEG/PDF。')
    return actual


def _get_engine():
    global _engine
    if not model_configured():
        raise HTTPException(503, 'OCR 模型尚未配置。请安装模型依赖并设置本地 OCR_DET_DIR / OCR_REC_DIR；可先使用文字样例。')
    if _engine is None:
        # 关闭模型源检查；显式本地目录避免应用自动下载。禁用所有额外预处理模型。
        os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        os.environ.setdefault('PADDLE_PDX_CACHE_HOME', str(config.ROOT / '.runtime-cache' / 'paddlex'))
        os.environ.setdefault('PADDLE_HOME', str(config.ROOT / '.runtime-cache' / 'paddle'))
        try:
            from paddleocr import PaddleOCR
            _engine = PaddleOCR(
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                text_detection_model_dir=config.OCR_DET_DIR,
                text_recognition_model_dir=config.OCR_REC_DIR,
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, device='cpu',
            )
        except Exception:
            raise HTTPException(503, 'OCR 初始化失败。请检查 PaddleOCR 3.x、PaddlePaddle 和配套本地模型；详细信息不写入用户日志。') from None
    return _engine


def _recognize(image: np.ndarray, page: int) -> list[dict]:
    with _lock:  # OCR 推理管线不是可重入对象。
        engine = _get_engine()
        try:
            results = list(engine.predict(image))
            lines = []
            for result in results:
                texts = result.get('rec_texts', [])
                scores = result.get('rec_scores', [])
                polys = result.get('rec_polys', [])
                for i, (text, score) in enumerate(zip(texts, scores)):
                    lines.append({'text': str(text), 'confidence': round(float(score),4),
                                  'low_confidence': float(score) < config.OCR_CONFIDENCE,
                                  'page': page, 'box': np.asarray(polys[i]).tolist() if i < len(polys) else []})
            return lines
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, 'OCR 未能完成识别，请使用更清晰的材料或手动粘贴文字。') from None


def parse_upload(data: bytes, extension: str, content_type: str) -> dict:
    """不调用 save()/临时文件，也不提取 PDF 内的链接、附件或执行脚本。"""
    actual = validate_signature(data, extension, content_type)
    lines = []
    if actual != 'pdf':
        lines = _recognize(_image(data), 1)
        pages = 1
    else:
        import pypdfium2 as pdfium
        try:
            with pdfium.PdfDocument(data) as doc:
                pages = len(doc)
                if pages < 1 or pages > config.MAX_PAGES:
                    raise HTTPException(413, 'PDF 需为1至8页。')
                for i in range(pages):
                    # PdfPage 不提供上下文管理协议，使用显式 finally 释放原生资源。
                    page = doc[i]
                    try:
                        width, height = page.get_size()
                        if width <= 0 or height <= 0 or width * height * 4 > config.MAX_PIXELS:
                            raise HTTPException(413, 'PDF 页面渲染尺寸超过安全限制。')
                        bitmap = page.render(scale=2)
                        try:
                            image = bitmap.to_pil().convert('RGB')
                            try:
                                lines.extend(_recognize(np.array(image), i+1))
                            finally:
                                image.close()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(415, 'PDF 无法解析、已加密或文件损坏。') from None
    if not lines:
        raise HTTPException(422, '未识别到文本，请提高图片清晰度。')
    text = '\n'.join(line['text'] for line in lines)
    if len(text) > config.MAX_TEXT:
        raise HTTPException(413, '识别文字超过30000字，请拆分材料。')
    return {'text': text, 'lines': lines, 'pages': pages, 'source': 'PaddleOCR'}
