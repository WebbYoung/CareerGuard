"""首次使用引导：由当前Session确定账号，沿用CSRF校验。"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from .api import Input, payload
from .database import connect, event
from .platform_api import current
from .services.onboarding import GUIDE_ID, GUIDE_STEPS

router = APIRouter(prefix='/api')


class GuideUpdate(Input):
    action: Literal['start','progress','complete','skip']
    step: int = Field(default=0, ge=0, lt=GUIDE_STEPS)


def summary(row):
    status = row['status'] if row else 'not_started'
    return {'guide_id':GUIDE_ID,'steps':GUIDE_STEPS,'status':status,
            'step':row['step'] if row else 0,'auto_start':status in ('pending','active')}


@router.get('/onboarding')
async def read_guide(request:Request):
    user = current(request)
    with connect() as db:
        row = db.execute('SELECT status,step FROM user_guides WHERE user_id=? AND guide_id=?',(user['id'],GUIDE_ID)).fetchone()
    return summary(row)


@router.post('/onboarding')
async def update_guide(request:Request):
    user = current(request)
    data = await payload(request,GuideUpdate)
    if data.action == 'complete' and data.step != GUIDE_STEPS-1:
        raise HTTPException(422,'请完成最后一个引导步骤后再结束。')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status,step FROM user_guides WHERE user_id=? AND guide_id=?',(user['id'],GUIDE_ID)).fetchone()
        if data.action == 'start':
            status,step = 'active',0
        else:
            if row is None:
                raise HTTPException(409,'请先开启引导。')
            if row['status'] in ('completed','skipped'):
                return summary(row)
            status = {'progress':'active','complete':'completed','skip':'skipped'}[data.action]
            step = data.step
        db.execute('INSERT INTO user_guides(user_id,guide_id,status,step) VALUES (?,?,?,?) '
                   'ON CONFLICT(user_id,guide_id) DO UPDATE SET status=excluded.status,step=excluded.step,updated=CURRENT_TIMESTAMP',
                   (user['id'],GUIDE_ID,status,step))
        if data.action in ('complete','skip'):
            event(db,user['id'],'onboarding_'+status)
    return summary({'status':status,'step':step})
