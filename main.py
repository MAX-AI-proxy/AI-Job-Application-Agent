import argparse
import os
import time
from contextlib import contextmanager
from app.database import ROOT
from app.database import connect, counts, import_applications, initialize
from app.documents import import_documents
from app.application_manager import STATUSES, mark_job, set_application_status
from app.operations import initialize_extensions, usage_report



@contextmanager
def single_agent_run():
    """Verhindert zwei parallele Agentenläufe auf demselben Rechner."""
    lock = ROOT / 'data' / 'state' / 'agent.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime > 4 * 3600:
            raise RuntimeError(f'Veraltete Sperrdatei gefunden: {lock}. Bitte prüfen und manuell löschen.')
        raise RuntimeError('Ein Agentenlauf läuft bereits (agent.lock vorhanden).')
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)

def jobs():
    with connect() as db:
        rows = db.execute('''SELECT j.id, j.company, j.title, j.fit_score,
         j.workflow_status, j.url,
         (SELECT d.pdf_path FROM drafts d WHERE d.job_id=j.id ORDER BY id DESC LIMIT 1) pdf,
         (SELECT e.file_path FROM email_drafts e WHERE e.job_id=j.id) email
         FROM jobs j ORDER BY j.id DESC''').fetchall()
    for j in rows:
        print(f"{j['id']:>3} | {j['workflow_status']:<11} | {j['fit_score']}/10 | {j['company']} – {j['title']}")
        print('    ' + (j['pdf'] or j['email'] or j['url']))


def applications():
    with connect() as db:
        rows = db.execute('SELECT id, unternehmen, stelle, status FROM applications ORDER BY unternehmen,stelle').fetchall()
    for r in rows:
        print(f"{r['id']:>3} | {r['status']:<14} | {r['unternehmen']} – {r['stelle']}")


def main():
    parser = argparse.ArgumentParser(description='Lokaler Bewerbungsagent')
    sub = parser.add_subparsers(dest='command', required=True)
    for action in ('init', 'import', 'status', 'applications', 'jobs', 'search',
                   'draft-all', 'run', 'usage', 'schedule-mac'):
        sub.add_parser(action)
    for action in ('draft', 'email'):
        sub.add_parser(action).add_argument('id', type=int)
    p = sub.add_parser('mark-job')
    p.add_argument('id', type=int)
    p.add_argument('status', choices=STATUSES)
    p = sub.add_parser('set-status')
    p.add_argument('id', type=int)
    p.add_argument('status', choices=STATUSES)
    args = parser.parse_args()
    initialize()
    initialize_extensions()

    if args.command == 'init':
        print('Datenbank und Zusatz-Tabellen bereit.')
    elif args.command == 'import':
        total, new = import_applications()
        updated, unchanged = import_documents()
        print(f'Bewerbungen: {total} gelesen, {new} neu. Dokumente: {updated} geändert, {unchanged} unverändert.')
    elif args.command == 'status':
        for table, count in counts().items():
            print(f'{table}: {count}')
        with connect() as db:
            emails = db.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0]
        print(f'email_drafts: {emails}')
    elif args.command == 'jobs':
        jobs()
    elif args.command == 'applications':
        applications()
    elif args.command == 'mark-job':
        print(mark_job(args.id, args.status))
    elif args.command == 'set-status':
        print(set_application_status(args.id, args.status))
    elif args.command == 'usage':
        usage_report()
    elif args.command == 'schedule-mac':
        from app.scheduler import install_mac_schedule
        install_mac_schedule()
    else:
        from app.agent import suche_stellen, erstelle_entwurf, erstelle_alle_entwuerfe
        with single_agent_run():
            if args.command in ('search', 'run'):
                suche_stellen()
            if args.command in ('draft', 'email'):
                erstelle_entwurf(args.id)
            if args.command in ('draft-all', 'run'):
                erstelle_alle_entwuerfe(limit=3)


if __name__ == '__main__':
    main()
