"""Appended to database.SCHEMA by the application bootstrap."""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS knowledge_documents(id INTEGER PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL, revision TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS knowledge_chunks(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, content TEXT NOT NULL, vector TEXT, fingerprint TEXT, revision TEXT NOT NULL, UNIQUE(document_id,ordinal));
'''
