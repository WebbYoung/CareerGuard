"""可选第三模型：字符 n-gram + 朴素贝叶斯；仅作教学增强，未经真实招聘语料验证。"""
from functools import lru_cache
from .. import config

SAMPLES = [
    ('先交押金后办理入职','收费风险'), ('支付培训费才能安排岗位','收费风险'),
    ('缴纳保证金领取任务','收费风险'), ('先培训后上岗需要贷款','收费风险'),
    ('刷单垫付完成任务返佣','任务返利风险'), ('做单返利需要先垫资','任务返利风险'),
    ('日结高薪零门槛先垫付','任务返利风险'), ('私聊领任务做单返佣','任务返利风险'),
    ('使用个人银行卡代收转账','资金转移风险'), ('帮忙代收款后转给他人','资金转移风险'),
    ('出借银行卡走流水','资金转移风险'), ('出租账户参与跑分','资金转移风险'),
    ('岗位要求Python和SQL参与数据分析','常规岗位描述'), ('负责系统开发有正式劳动合同','常规岗位描述'),
    ('招聘软件开发工程师要求接口测试','常规岗位描述'), ('不收押金无需培训费','常规岗位描述'),
    ('禁止刷单不允许代收转账','常规岗位描述'), ('薪酬面议按合同发放','常规岗位描述'),
]


@lru_cache(maxsize=1)
def _model():
    from sklearn.pipeline import make_pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    model = make_pipeline(TfidfVectorizer(analyzer='char', ngram_range=(2,4)), MultinomialNB())
    model.fit([x for x,y in SAMPLES], [y for x,y in SAMPLES])
    return model


def predict_category(text: str) -> dict:
    if not config.ENABLE_CLASSIFIER:
        return {'enabled': False, 'note': '可选分类增强未启用；风险分来自可解释规则。'}
    try:
        label = str(_model().predict([text])[0])
        return {'enabled': True, 'label': label,
                'note': '合成小样本分类模型，仅用于演示，不提供诈骗概率，不改变规则分。'}
    except Exception:
        return {'enabled': False, 'note': '分类模型依赖未就绪；规则分析仍可用。'}
