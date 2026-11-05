"""星图派生视图：状态与技能覆盖率由服务端计算，不采信模型给出的百分比。"""
from copy import deepcopy


def required_ids(tree,career):
    nodes={n['id']:n for n in tree['nodes']};required=set()
    def visit(nid):
        if nid in required:return
        required.add(nid)
        for pid in nodes[nid]['prerequisites']:visit(pid)
    for nid in career['core_skill_ids']:visit(nid)
    return required


def decorate(tree,progress,occupation='目标职业',major=''):
    value=deepcopy(tree);done=set(progress)
    value['learner_label']=(major+'学习者') if major else value.get('learner_label','学习者成长起点')
    # 旧路线只具有单岗位，按原节点派生终点，不冒充新增AI结果。
    if not value.get('careers'):
        value['careers']=[{'id':'legacy-career','name':occupation,'description':value['summary'],
                           'core_skill_ids':[n['id'] for n in value['nodes']],'projects':['完成路线中的综合实践任务']}]
    counts={n['id']:0 for n in value['nodes']}
    for career in value['careers']:
        ids=required_ids(value,career);completed=ids&done
        career.update(required_skill_ids=sorted(ids),required_count=len(ids),completed_count=len(completed),
                      coverage=round(100*len(completed)/len(ids),1) if ids else 0,
                      mastered=sorted(completed),missing=sorted(ids-done))
        for nid in ids:counts[nid]+=1
    for node in value['nodes']:
        node['status']='completed' if node['id'] in done else 'available' if set(node['prerequisites'])<=done else 'locked'
        node['shared_count']=counts[node['id']]
    return value
