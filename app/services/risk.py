"""可解释规则分数，不是诈骗概率；分类增强不覆盖规则结论。"""
import re

DISCLAIMER = '本结果仅为文本风险线索，不能判定一定是诈骗，也不构成法律或录用意见。低风险不等于安全，请通过自行确认的正规渠道核验。'
RULES = [
    ('押金收费', r'押金|保证金|入职费|服装费|办卡费', 30, '核实是否要求先付款，询问收费依据与书面退还条款。'),
    ('培训收费', r'培训费|培训贷|付费培训|先培训后上岗', 30, '核实培训是否自愿、收费主体、合同内容和贷款责任。'),
    ('刷单返利', r'刷单|垫付|返佣任务|做单返利', 45, '不要垫资完成任务，核验工作内容和劳动关系。'),
    ('异常薪酬诱导', r'高薪日结|日入\s*\d+|月入\s*\d+万|零门槛高薪|无需经验.*?高薪', 20, '核验薪酬构成、工作时间和实际考核条件。'),
    ('资金代收转移', r'代收转账|代收款|代转账|走流水|跑分|代收.{0,8}转账', 45, '避免提供账户或代收代转资金，核验资金与岗位的关联。'),
    ('账户及证件控制', r'出租银行卡|出借银行卡|扣押身份证|上交银行卡|提供验证码', 45, '不提供账户控制权或验证码，确认身份证件使用范围。'),
    ('私下沟通诱导', r'私聊领任务|下载不明|点击链接.{0,8}(?:注册|认证)', 15, '自行查找正规招聘渠道，避免通过文案链接提交敏感信息。'),
]
NEGATION = re.compile(r'(?:不收(?:取)?|无需(?:支付|缴纳)?|不需(?:要)?|无须|不参与|禁止|拒绝|切勿|警惕|防范|谨防|没有|无)(?:任何|额外|所谓|支付|缴纳|进行|的|\s){0,5}$')


def assess_risk(text: str) -> dict:
    findings = []
    for category, pattern, weight, advice in RULES:
        matches = []
        for match in re.finditer(pattern, text, re.I):
            # 只看当前子句，避免前一子句的“不收”遮蔽后一收费项目。
            prefix = re.split(r'[，,。；;！!\n]|但是|但|然而|仍需', text[:match.start()])[-1][-18:]
            if NEGATION.search(prefix):
                continue
            matches.append(match)
        for index, match in enumerate(matches):
            findings.append({'id': f'R{len(findings)+1}', 'category': category, 'quote': match.group(),
                             'start': match.start(), 'end': match.end(), 'weight': weight if index == 0 else 0,
                             'advice': advice})
    score = min(100, sum(f['weight'] for f in findings))
    return {'score': score, 'level': '高风险' if score >= 60 else '中风险' if score >= 25 else '低风险',
            'findings': findings, 'disclaimer': DISCLAIMER,
            'score_basis': '可解释规则加权；同类线索只计分一次；非诈骗概率。'}
