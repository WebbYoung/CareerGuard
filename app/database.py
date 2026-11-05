"""SQLite 持久层。仅保存显式提交资料，不接收上传文件字节。"""
import os
import json
import sqlite3
import secrets
import hashlib
from pathlib import Path
from contextlib import contextmanager
from cryptography.fernet import Fernet
from .config import ROOT

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', disabled INTEGER NOT NULL DEFAULT 0,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS auth_sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY REFERENCES users(id), occupation TEXT NOT NULL DEFAULT '', resume TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 company TEXT NOT NULL, description TEXT NOT NULL, recommended INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), user_id INTEGER NOT NULL REFERENCES users(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), body TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(job_id,user_id));
CREATE TABLE IF NOT EXISTS trees(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), occupation TEXT NOT NULL, jd TEXT NOT NULL, content TEXT NOT NULL, progress TEXT NOT NULL DEFAULT '[]', created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), tree_id INTEGER REFERENCES trees(id), content TEXT NOT NULL,
 result TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS wrongbook(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), question TEXT NOT NULL, content TEXT NOT NULL,
 mistakes INTEGER NOT NULL DEFAULT 1, correct_streak INTEGER NOT NULL DEFAULT 0, UNIQUE(user_id,question));
CREATE TABLE IF NOT EXISTS interviews(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), occupation TEXT NOT NULL,
 history TEXT NOT NULL DEFAULT '[]', ended INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),content TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS career_reports(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),content TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS security_events(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,status TEXT NOT NULL,count INTEGER NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyses(user_id INTEGER NOT NULL REFERENCES users(id),material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,kind TEXT NOT NULL,content TEXT NOT NULL,PRIMARY KEY(user_id,material_id,kind));
'''


@contextmanager
def connect():
    path = Path(os.getenv('CG_DB_PATH', str(ROOT/'.runtime'/'platform.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript(SCHEMA)
    if 'data_generation' not in {r[1] for r in db.execute('PRAGMA table_info(users)')}:
        db.execute('ALTER TABLE users ADD COLUMN data_generation INTEGER NOT NULL DEFAULT 0')
        db.commit()
    if 'major' not in {r[1] for r in db.execute('PRAGMA table_info(trees)')}:
        db.execute("ALTER TABLE trees ADD COLUMN major TEXT NOT NULL DEFAULT ''")
        db.commit()
    if 'assessment_progress' not in {r[1] for r in db.execute('PRAGMA table_info(trees)')}:
        # 旧版自我记录保留在progress；考试解锁单独保存，不把自记误当考核结果。
        db.execute("ALTER TABLE trees ADD COLUMN assessment_progress TEXT NOT NULL DEFAULT '[]'")
        db.commit()
    if 'unlock_node' not in {r[1] for r in db.execute('PRAGMA table_info(exams)')}:
        db.execute('ALTER TABLE exams ADD COLUMN unlock_node TEXT')
        db.commit()
    # 兼容已有数据库：旧用户岗位重新送审，管理员岗位继续公开。
    if 'status' not in {r[1] for r in db.execute('PRAGMA table_info(jobs)')}:
        db.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        db.execute("ALTER TABLE jobs ADD COLUMN review_note TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE jobs ADD COLUMN reviewed_by INTEGER REFERENCES users(id)")
        db.execute("ALTER TABLE jobs ADD COLUMN reviewed_at TEXT")
        db.execute("UPDATE jobs SET status='approved' WHERE owner_id IN (SELECT id FROM users WHERE role='admin')")
        db.commit()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def password_hash(password: str, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt+':'+value


def password_ok(password, stored):
    return secrets.compare_digest(password_hash(password, stored.split(':')[0]), stored)


def ensure_superuser():
    """按本次明确配置完成一次默认账号迁移，随后启动不再重设密码。"""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM settings WHERE name='superuser-default-v1'").fetchone():
            return
        existing=db.execute('SELECT id FROM users WHERE username=?',('admin',)).fetchone()
        if not existing:
            db.execute('INSERT INTO users(username,password,role) VALUES (?,?,?)',('admin',password_hash('admin'),'admin'))
        else:
            db.execute("UPDATE users SET password=?,role='admin',disabled=0 WHERE id=?",(password_hash('admin'),existing['id']))
            db.execute('DELETE FROM auth_sessions WHERE user_id=?',(existing['id'],))
        db.execute("INSERT INTO settings(name,value) VALUES ('superuser-default-v1','initialized')")


def cipher():
    """每次按运行目录读取密钥；运行目录不得加入源码包。"""
    path = Path(os.getenv('CG_MASTER_KEY_PATH', str(ROOT/'.runtime'/'master.key')))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
    return Fernet(path.read_bytes())


def event(db, uid, action):
    db.execute('INSERT INTO events(user_id,action) VALUES (?,?)', (uid,action))
    # 限制统计明细增长，保留最近50000次操作，不记录正文/密钥/音频。
    db.execute('DELETE FROM events WHERE id < (SELECT MAX(id)-50000 FROM events)')
