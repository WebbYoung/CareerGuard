"""Explicit resume sharing and server-owned interview links."""
SCHEMA='''
CREATE TABLE IF NOT EXISTS job_applications(
 id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 resume_source TEXT NOT NULL CHECK(resume_source IN ('profile','studio')),
 resume_encrypted BLOB,share_resume INTEGER NOT NULL DEFAULT 0,
 interview_consent INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','withdrawn')),
 occupation TEXT NOT NULL,jd TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(user_id,job_id));
CREATE INDEX IF NOT EXISTS application_company ON job_applications(company_id,job_id,status);
CREATE TABLE IF NOT EXISTS application_interviews(
 application_id INTEGER NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
 interview_id INTEGER NOT NULL UNIQUE REFERENCES interviews(id) ON DELETE CASCADE,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(application_id,interview_id));
'''
