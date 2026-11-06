"""Resume persistence schema; content and processed portraits are encrypted."""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS resume_sessions(
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 content TEXT NOT NULL,portrait BLOB,revision INTEGER NOT NULL DEFAULT 0,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS resume_owner ON resume_sessions(user_id,updated);
'''
