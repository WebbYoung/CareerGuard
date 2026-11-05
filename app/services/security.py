"""启发式注入检测是纵深防御之一，不能宣称能识别所有攻击。"""
import re
import unicodedata

PATTERNS = [
    ('指令覆盖', r'(?:忽略|无视|忘记|覆盖|绕过).{0,24}(?:指令|提示词|规则|限制|系统)'),
    ('指令覆盖', r'(?:ignore|disregard|forget|override|bypass).{0,65}(?:instruction|prompt|rule|system|restriction)'),
    ('系统信息索取', r'(?:输出|泄露|显示|读取|打印|告诉我).{0,24}(?:系统提示|环境变量|密钥|秘密|api.?key)'),
    ('系统信息索取', r'(?:reveal|print|show|leak|read).{0,60}(?:system.?prompt|secret|api.?key|environment.?variable)'),
    ('伪造角色边界', r'\[/?inst\]|<\|(?:im_start|system|assistant)|(?:^|\n)\s*(?:system|developer)\s*:'),
    ('角色劫持', r'(?:你现在|从现在起).{0,16}(?:扮演|不受限制|越狱)|do.?anything.?now|jailbreak'),
    ('工具执行请求', r'(?:执行|运行|调用).{0,14}(?:shell|powershell|curl|系统命令|工具)|(?:fetch|requests\.get)\s*\('),
]


def inspect_injection(text: str) -> dict:
    normalized = unicodedata.normalize('NFKC', text)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Cf')
    compact = re.sub(r'[ \t]+', '', normalized)
    reasons = sorted({name for name, pattern in PATTERNS
                      if re.search(pattern, normalized, re.I | re.S) or re.search(pattern, compact, re.I | re.S)})
    return {'blocked': bool(reasons), 'reasons': reasons,
            'message': '检测到可能改变系统行为的指令，已阻止进入分析与模型。' if reasons else '未命中当前注入规则；不代表材料绝对安全。'}


def clean_text(text: str) -> str:
    """去除控制字符、规范换行；保留偏移所依据的最终文本。"""
    text = unicodedata.normalize('NFKC', text).replace('\r\n', '\n').replace('\r', '\n')
    text = ''.join(c for c in text if c in '\n\t' or not unicodedata.category(c).startswith('C'))
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')).strip()


def classify_material(text: str) -> str:
    if re.search(r'工作经历|项目经历|教育经历|求职意向|个人简历|技能[：:]', text):
        return 'resume'
    if re.search(r'日结|押金|培训费|招聘|诚聘|代收|刷单', text):
        return 'recruitment'
    if re.search(r'岗位职责|任职要求|职位描述|岗位要求|要求|负责', text):
        return 'jd'
    return 'unknown'
