"""访客使用临时缓存，账号材料在SQLite持久化，内存层保留容量与代数保护。"""
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone
import secrets
import threading
import time
from fastapi import HTTPException
from . import config


@dataclass
class Session:
    user_id: int | None = None
    data_generation: int = 0
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    touched: float = field(default_factory=time.monotonic)
    generation: int = 0
    materials: dict = field(default_factory=dict)
    audit: deque = field(default_factory=lambda: deque(maxlen=200))


class MemoryStore:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def reap(self):
        with self.lock:
            expired = [sid for sid, s in self.sessions.items() if time.monotonic()-s.touched > (604800 if s.user_id else config.SESSION_TTL)]
            for sid in expired:
                self.sessions[sid].generation += 1
                del self.sessions[sid]

    def bootstrap(self, sid: str | None):
        with self.lock:
            self.reap()
            if sid not in self.sessions:
                if len(self.sessions) >= config.MAX_SESSIONS:
                    raise HTTPException(503, '本地会话容量已满，请稍后重试。')
                sid = secrets.token_urlsafe(32)
                self.sessions[sid] = Session()
            session = self.sessions[sid]
            session.touched = time.monotonic()
            return sid, session

    def require(self, sid: str | None) -> Session:
        with self.lock:
            self.reap()
            if sid not in self.sessions:
                raise HTTPException(401, '会话已过期，请刷新页面；旧缓存已释放。')
            session = self.sessions[sid]
            session.touched = time.monotonic()
            return session

    def guard(self, sid: str, generation: int) -> Session:
        session = self.require(sid)
        if session.generation != generation:
            raise HTTPException(409, '任务期间缓存已清空，本次结果已丢弃。')
        if session.user_id:
            from .database import connect
            with connect() as db:row=db.execute('SELECT data_generation,disabled FROM users WHERE id=?',(session.user_id,)).fetchone()
            if not row or row['disabled'] or row['data_generation']!=session.data_generation:
                raise HTTPException(409,'任务期间账号资料已变更，本次结果已丢弃。')
        return session

    def log(self, sid: str, action: str, status: str = 'ok', count: int = 0):
        with self.lock:
            session = self.require(sid)
            session.audit.append({'time': datetime.now(timezone.utc).isoformat(),
                                  'action': action, 'status': status, 'count': count})
            if session.user_id:
                from .database import connect,event
                with connect() as db:
                    db.execute('INSERT INTO security_events(user_id,action,status,count,created) VALUES (?,?,?,?,?)',
                               (session.user_id,action,status,count,datetime.now(timezone.utc).isoformat()))
                    event(db,session.user_id,action)

    def bind(self,sid,user_id):
        """账号会话重建时从SQLite恢复材料，绝不复用其他账号的内存数据。"""
        from .database import connect
        import json
        with self.lock:
            session=self.require(sid)
            with connect() as db:
                rows=db.execute('SELECT content FROM materials WHERE user_id=? ORDER BY created LIMIT 24',(user_id,)).fetchall()
                row=db.execute('SELECT data_generation FROM users WHERE id=?',(user_id,)).fetchone()
            if session.user_id==user_id and row['data_generation']!=session.data_generation:
                session.generation+=1
            session.materials={m['id']:m for m in (json.loads(r['content']) for r in rows)}
            session.user_id=user_id
            session.data_generation=row['data_generation']

    def save(self, sid: str, generation: int, material: dict):
        with self.lock:
            session = self.guard(sid, generation)
            if len(session.materials) >= config.MAX_MATERIALS:
                raise HTTPException(409, '每个会话最多保留24份材料，请先删除或清空。')
            mid = secrets.token_urlsafe(16)
            material = {**material, 'id': mid}
            if session.user_id:
                from .database import connect,encode
                with connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute('SELECT data_generation,disabled FROM users WHERE id=?',(session.user_id,)).fetchone()
                    if not row or row['disabled'] or row['data_generation']!=session.data_generation:
                        raise HTTPException(409,'任务期间账号资料已变更，本次结果已丢弃。')
                    db.execute('INSERT INTO materials(id,user_id,content) VALUES (?,?,?)',(mid,session.user_id,encode(material)))
            session.materials[mid] = material
            return material

    def get(self, sid: str, mid: str):
        with self.lock:
            material = self.require(sid).materials.get(mid)
            if material is None:
                raise HTTPException(404, '材料不存在或已被清空。')
            return dict(material)

    def clear(self, sid: str):
        with self.lock:
            session = self.require(sid)
            count = len(session.materials)
            session.generation += 1
            session.materials.clear()
            if session.user_id:
                from .database import connect
                with connect() as db:
                    db.execute('DELETE FROM materials WHERE user_id=?',(session.user_id,))
                    db.execute('UPDATE users SET data_generation=data_generation+1 WHERE id=?',(session.user_id,))
                    session.data_generation=db.execute('SELECT data_generation FROM users WHERE id=?',(session.user_id,)).fetchone()[0]
            session.audit.clear()
            self.log(sid, 'clear', count=count)
            return count


store = MemoryStore()
