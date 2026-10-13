"""Kurz-E-Mails, Entwurfsstatus und lokale Kostenübersicht."""
import json
import os
import re
from datetime import date
from pathlib import Path

from app.database import ROOT, connect, key, now
from app.policy import assess_saved_job


def initialize_extensions():
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS email_drafts (
                id INTEGER PRIMARY KEY,
                job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id),
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY,
                day TEXT NOT NULL,
                mode TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                model_cost_usd REAL NOT NULL,
                web_calls INTEGER NOT NULL,
                web_calls_known INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
        ''')


def ensure_draft_status(job):
    """Für eine neu vorbereitete Bewerbung nie 'beworben' überschreiben."""
    with connect() as db:
        existing = db.execute('''SELECT id, status FROM applications
            WHERE company_key=? AND role_key=?''',
            (key(job['company']), key(job['title']))).fetchone()
        if existing:
            if existing['status'] in ('beworben', 'absage', 'unklar'):
                raise ValueError(f"Bewerbung mit Status {existing['status']} existiert")
            if existing['status'] == 'nicht_beworben':
                db.execute('UPDATE applications SET status=?, updated_at=? WHERE id=?',
                           ('entwurf', now(), existing['id']))
        else:
            db.execute('''INSERT INTO applications
                (unternehmen, stelle, company_key, role_key, status,
                 bewerbungsdatum, stellen_url, notiz, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'entwurf', NULL, ?, ?, ?, ?)''',
                (job['company'], job['title'], key(job['company']), key(job['title']),
                 job['url'], 'Automatisch erstellt; nicht verschickt', now(), now()))
        db.execute('UPDATE jobs SET workflow_status=? WHERE id=?', ('entwurf', job['id']))


def save_email(job_id, subject, body):
    with connect() as db:
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        previous = db.execute('SELECT id FROM email_drafts WHERE job_id=?', (job_id,)).fetchone()
        previous_pdf = db.execute('SELECT id FROM drafts WHERE job_id=?', (job_id,)).fetchone()
    if job is None:
        return 'FEHLER: Unbekannte Job-ID'
    if previous or previous_pdf:
        return 'Nicht erstellt: Ein Entwurf existiert bereits'
    status, reason = assess_saved_job(job)
    if status != 'bereit':
        return f'Nicht erstellt: {reason}'
    info = json.loads(job['analysis_json'] or '{}')
    if info.get('bewerbungsformat') != 'kurze_email':
        return 'Nicht erstellt: Arbeitgeber verlangt keine kurze Bewerbungs-E-Mail'
    if not subject.strip() or not 120 <= len(body.strip()) <= 2200:
        return 'Nicht erstellt: Betreff fehlt oder E-Mail-Text ist unplausibel lang'
    if any(term in body.lower() for term in ('[name]', '[unternehmen]', '[platzhalter]')):
        return 'Nicht erstellt: Unausgefüllte Platzhalter'
    filename = f'{job_id:04d}_bewerbung_email.txt'
    dest = ROOT / 'output' / 'emails' / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f'Betreff: {subject.strip()}\n\n{body.strip()}\n', encoding='utf-8')
    with connect() as db:
        db.execute('''INSERT INTO email_drafts (job_id,subject,body,file_path,created_at)
                      VALUES (?,?,?,?,?)''', (job_id, subject.strip(), body.strip(),
                                               dest.relative_to(ROOT).as_posix(), now()))
    ensure_draft_status(job)
    return f'E-Mail-Entwurf gespeichert: {dest.relative_to(ROOT)} (nicht versendet)'


def spend_check():
    limit = float(os.getenv('MAX_DAILY_MODEL_USD', '1.50'))
    with connect() as db:
        spent = db.execute('SELECT COALESCE(SUM(model_cost_usd),0) FROM usage_log WHERE day=?',
                           (date.today().isoformat(),)).fetchone()[0]
    if spent >= limit:
        raise RuntimeError(f'Modell-Tagesbudget erreicht: ca. ${spent:.2f} von ${limit:.2f}. ' 
                           'Websuche und nicht protokollierte Fehlversuche sind darin nicht enthalten.')


def record_usage(mode, model, result):
    usage = result.context_wrapper.usage
    input_tokens = int(usage.input_tokens or 0)
    output_tokens = int(usage.output_tokens or 0)
    # Standard-Preise für GPT-6.1 Sol, Kosten nur näherungsweise.
    rates = {'gpt-6.1-sol': (2.0, 10.0), 'gpt-6-luna': (0.1, 0.5)}
    input_rate, output_rate = rates.get(model, (0, 0))
    estimated = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    web_calls = 0
    web_known = False
    for item in getattr(result, 'new_items', []):
        raw = getattr(item, 'raw_item', None)
        kind = getattr(raw, 'type', None)
        if isinstance(raw, dict):
            kind = raw.get('type', kind)
        if kind in ('web_search_call', 'web_search'):
            web_calls += 1
            web_known = True
    with connect() as db:
        db.execute('''INSERT INTO usage_log
            (day,mode,model,input_tokens,output_tokens,model_cost_usd,web_calls,web_calls_known,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (date.today().isoformat(),mode,model,input_tokens,output_tokens,
             estimated,web_calls,int(web_known),now()))
    print(f'Verbrauch: {input_tokens:,} Input / {output_tokens:,} Output. '
          f'Modellkosten grob ${estimated:.3f} + Websuche (Dashboard maßgeblich).')


def usage_report():
    with connect() as db:
        rows = db.execute('''SELECT day, COUNT(*) n, SUM(model_cost_usd) amount
          FROM usage_log GROUP BY day ORDER BY day DESC LIMIT 15''').fetchall()
    for row in rows:
        print(f"{row['day']}: {row['n']} Teil-Läufe, Modell grob ${row['amount']:.3f}, zzgl. Websuche")
    if not rows:
        print('Noch kein Lauf mit diesem Kostenprotokoll.')
