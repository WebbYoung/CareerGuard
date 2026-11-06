"""Station mail schema. No initialization side effects."""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS mail_threads(id INTEGER PRIMARY KEY,application_id INTEGER REFERENCES job_applications(id),company_id INTEGER REFERENCES companies(id),candidate_id INTEGER NOT NULL REFERENCES users(id),creator_id INTEGER NOT NULL REFERENCES users(id),subject TEXT NOT NULL,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS mail_messages(id INTEGER PRIMARY KEY,thread_id INTEGER NOT NULL REFERENCES mail_threads(id) ON DELETE CASCADE,sender_id INTEGER NOT NULL REFERENCES users(id),recipient_id INTEGER NOT NULL REFERENCES users(id),body_encrypted BLOB NOT NULL,read_at TEXT,delivery TEXT NOT NULL DEFAULT 'internal',created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS mail_recipient ON mail_messages(recipient_id,id);
CREATE INDEX IF NOT EXISTS mail_thread ON mail_messages(thread_id,id);
CREATE TABLE IF NOT EXISTS mail_addresses(user_id INTEGER PRIMARY KEY REFERENCES users(id),email_encrypted BLOB NOT NULL,verified INTEGER NOT NULL DEFAULT 0,consent INTEGER NOT NULL DEFAULT 0,code_hash TEXT,code_expires INTEGER,attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mail_actions(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),created INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS mail_action_user ON mail_actions(user_id,created);
'''
