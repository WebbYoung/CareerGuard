"""Enterprise submission schema; appended to the platform schema by database.py."""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS companies(
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,credit_code TEXT NOT NULL UNIQUE,
 contact_role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected')),
 license_encrypted BLOB NOT NULL,license_type TEXT NOT NULL,
 ocr_notes TEXT NOT NULL,review_note TEXT NOT NULL DEFAULT '',
 reviewed_by INTEGER REFERENCES users(id),reviewed_at TEXT,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS company_memberships(
 company_id INTEGER NOT NULL REFERENCES companies(id),user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
 role TEXT NOT NULL DEFAULT 'administrator',PRIMARY KEY(company_id,user_id));
CREATE TABLE IF NOT EXISTS job_company_links(
 job_id INTEGER PRIMARY KEY REFERENCES jobs(id),company_id INTEGER NOT NULL REFERENCES companies(id));
'''
