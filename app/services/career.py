"""轻量词项检索 RAG：从 JD 检索知识条目并绑定逐行材料证据。"""
import re
from .knowledge import KNOWLEDGE


def contains(text: str, alias: str) -> bool:
    pattern = re.escape(alias)
    if alias.isascii():
        pattern = r'(?<![\w])' + pattern + r'(?![\w])'
    return bool(re.search(pattern, text, re.I))


def build_report(resume: str, jd: str) -> dict:
    requirements, gaps, matched, sources = [], [], [], []
    segments = [x.strip() for x in re.split(r'[\n，,；;。]', jd) if x.strip()]
    for kid, skill, aliases, learning, deliverable, question in KNOWLEDGE:
        evidence = next((line for line in segments if any(contains(line, alias) for alias in aliases)), None)
        if evidence is None:
            continue
        cv_evidence = next((line for line in resume.splitlines() if any(contains(line, alias) for alias in aliases)), None)
        item = {'skill': skill, 'jd_evidence': evidence, 'resume_evidence': cv_evidence,
                'source_ids': [kid], 'status': '材料有提及' if cv_evidence else '材料未体现'}
        requirements.append(item)
        (matched if cv_evidence else gaps).append(item)
        sources.append({'id': kid, 'title': f'{skill} 学习条目', 'content': learning,
                        'origin': '项目内置职业知识库 v1'})
    unknown = [line for line in segments if not any(any(contains(line, a) for a in row[2]) for row in KNOWLEDGE)]
    # 一段中包含已知技能，也要暴露词表之外的重要要求。
    for line in segments:
        residual = line
        for row in KNOWLEDGE:
            for alias in row[2]:
                residual = re.sub(re.escape(alias), '', residual, flags=re.I)
        residual = re.sub(r'要求|熟悉|掌握|具备|了解|和|与|及|、|\s|[：:()（）/]', '', residual)
        if len(residual) > 3 and line not in unknown:
            unknown.append(line)
    targets = gaps or matched
    selected = [row for row in KNOWLEDGE if any(row[1] == g['skill'] for g in targets)]
    plan = []
    for i in range(4):
        # 把所有差距分配进四周；超过4项时合并，避免只规划前4项。
        week_rows = (selected[i::4] or [selected[i % len(selected)]]) if selected else []
        plan.append({'week': i+1, 'title': ['基础梳理','专项练习','项目整合','复盘与表达'][i],
                     'focus': '、'.join(row[1] for row in week_rows) if week_rows else '补充岗位资料与人工核验',
                     'tasks': [task for row in week_rows for task in [row[3], row[4]]] if week_rows else ['列出岗位的具体任务和评价标准。','补充脱敏的项目证据，再进行岗位能力对比。'],
                     'deliverable': '；'.join(row[4] for row in week_rows) if week_rows else '一份经人工核验的能力清单',
                     'source_ids': [row[0] for row in week_rows]})
    questions = [{'skill': row[1], 'question': row[5], 'source_ids': [row[0]],
                  'basis': '按岗位技能整理的练习题；非真实企业题库或频率统计'} for row in selected[:8]]
    return {'match_score': round(100*len(matched)/len(requirements)) if requirements else None,
            'score_label': '简历关键词证据覆盖率', 'requirements': requirements, 'matched': matched,
            'gaps': gaps, 'unknown_requirements': unknown, 'plan': plan, 'questions': questions, 'sources': sources,
            'disclaimer': '本报告只比较材料中已体现的证据。未提及不代表不会，关键词覆盖不等于能力、录用概率或求职保证；四周计划需按个人基础调整。'}
