"""保守的 PII 规则检测，返回原文偏移；不记录或持久化敏感值。"""
import re

LABELS = {'phone': '手机号', 'id_card': '身份证', 'address': '住址',
          'email': '邮箱', 'bank_card': '银行卡', 'emergency_contact': '紧急联系人'}
PATTERNS = [
    ('id_card', r'(?<!\d)(?:\d[ \t-]?){17}[\dXx](?!\d)'),
    ('bank_card', r'(?<!\d)(?:\d[ \t-]?){15,18}\d(?!\d|[Xx])'),
    ('phone', r'(?<!\d)(?:\+?86[ \t-]?)?1[3-9]\d[ \t-]?\d{4}[ \t-]?\d{4}(?!\d)'),
    ('email', r'(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+'),
    ('address', r'(?:家庭住址|居住地址|联系地址|详细地址|住址|地址)[：: \t]+([^\n；;，,]+)'),
    ('emergency_contact', r'(?:紧急联系人|紧急联系信息)[：: \t]+([^\n；;]+)'),
]


def detect_pii(text: str) -> list[dict]:
    """地址与联系人采用标签识别，无法保证识别无标签自然语言地址。"""
    fields = []
    for kind, pattern in PATTERNS:
        for match in re.finditer(pattern, text):
            start, end = match.span(1 if match.lastindex else 0)
            # 银行卡规则不重复认领已识别的身份证。
            if kind == 'bank_card' and any(f['start'] <= start and f['end'] >= end for f in fields):
                continue
            fields.append({'type': kind, 'label': LABELS[kind], 'start': start, 'end': end})
    return sorted(fields, key=lambda f: (f['start'], -f['end']))


def redact(text: str, fields: list[dict] | None = None) -> str:
    """合并重叠区间后整体替换，避免联系人内嵌电话发生偏移泄漏。"""
    fields = detect_pii(text) if fields is None else fields
    intervals: list[list[int]] = []
    for field in sorted(fields, key=lambda f: f['start']):
        start, end = field['start'], field['end']
        if intervals and start <= intervals[-1][1]:
            intervals[-1][1] = max(end, intervals[-1][1])
        else:
            intervals.append([start, end])
    result = text
    for start, end in reversed(intervals):
        result = result[:start] + '***' + result[end:]
    return result
