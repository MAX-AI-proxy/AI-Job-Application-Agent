"""Reproducible fictional showcase using existing Python functions; no API calls."""
import argparse
import ast
import io
import json
import shutil
import socket
import sys
import tempfile
from contextlib import ExitStack, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import database, documents, operations, pdf_generator, policy, rules
from app import configuration, style_references
import main as cli
from reportlab import rl_config


def load_tool_bodies(workspace):
    """Call original tool bodies without importing the SDK or loading .env."""
    names = {
        'cfg', 'lies_lebenslauf', 'bekannte_bewerbungen', 'offene_stellen',
        'stelle_abrufen', 'stelle_speichern', 'stilreferenzen_lesen',
        '_job_and_guard', 'anschreiben_pdf_erstellen', 'kurze_email_erstellen',
    }
    source = ast.parse((ROOT / 'app/agent.py').read_text(encoding='utf-8'))
    nodes = []
    for node in source.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
    assert {node.name for node in nodes} == names
    namespace = {
        'ROOT': workspace, 'json': json, 'connect': database.connect,
        'key': database.key, 'now': database.now, 'MAX_RESULTS': 5, '_new_jobs': 0,
        'assess': policy.assess, 'assess_saved_job': policy.assess_saved_job,
        'canonical_url': policy.canonical_url, 'make_pdf': pdf_generator.make_pdf,
        'ensure_draft_status': operations.ensure_draft_status,
        'save_email': operations.save_email,
        'read_style_references': style_references.read_style_references,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app/agent.py', 'exec'), namespace)
    return namespace


def isolated_application(workspace, scenario):
    """Only data paths and PDF clock/serialization are scoped to the fixture."""
    stack = ExitStack()
    for module in (database, documents, operations, pdf_generator, policy, rules):
        stack.enter_context(patch.object(module, 'ROOT', workspace))
    stack.enter_context(patch.object(database, 'DB_PATH', workspace / 'data/state/showcase.sqlite3'))
    stack.enter_context(patch.object(database, 'CSV_PATH', workspace / 'data/input/bewerbungen.csv'))
    stack.enter_context(patch.object(policy, 'CACHE_FILE', workspace / 'data/state/routen_cache.json'))
    stack.enter_context(patch.object(documents, 'DOCUMENT_SOURCES', [
        (workspace / 'config/00_START_HIER.md', 'instructions'),
        (workspace / 'config/00_STILKOMPASS_ANSCHREIBEN.md', 'style_guide'),
    ]))
    stack.enter_context(patch.object(socket.socket, 'connect',
                                    side_effect=RuntimeError('Network is disabled in the showcase.')))
    stack.enter_context(patch.object(socket, 'create_connection',
                                    side_effect=RuntimeError('Network is disabled in the showcase.')))
    stack.enter_context(patch.object(socket, 'getaddrinfo',
                                    side_effect=RuntimeError('Network is disabled in the showcase.')))
    stack.enter_context(patch.object(socket.socket, 'connect_ex',
                                    side_effect=RuntimeError('Network is disabled in the showcase.')))
    sample_date = date.fromisoformat(scenario['sample_date'])
    class FixedDate(date):
        @classmethod
        def today(cls):
            return sample_date
    stack.enter_context(patch.object(pdf_generator, 'date', FixedDate))
    stack.enter_context(patch.object(rl_config, 'invariant', 1))
    return stack


def prepare_inputs(workspace, scenario):
    for folder in ('config', 'data/input/lebenslauf', 'data/input/stilreferenzen', 'data/state'):
        (workspace / folder).mkdir(parents=True, exist_ok=True)
    for name in ('00_START_HIER.md', '00_STILKOMPASS_ANSCHREIBEN.md'):
        shutil.copyfile(ROOT / 'config' / name, workspace / 'config' / name)
    configs = {
        'absender.json': json.dumps(scenario['applicant'], ensure_ascii=False, indent=2),
        'entfernung.json': json.dumps(scenario['distance_settings'], ensure_ascii=False, indent=2),
        'suchprofil.md': scenario['search_profile'],
        'projektstand.md': scenario['confirmed_projects'],
        'bewerbungsregeln.md': scenario['writing_rules'],
    }
    for name, text in configs.items():
        (workspace / 'config' / name).write_text(text + '\n', encoding='utf-8')
    (workspace / 'data/input/lebenslauf/fictional_cv.txt').write_text(scenario['cv_facts'], encoding='utf-8')
    (workspace / 'data/input/bewerbungen.csv').write_text(
        'unternehmen,stelle,status,bewerbungsdatum,stellen_url,notiz\n', encoding='utf-8')
    for name in ('startup_sample.txt', 'corporate_sample.txt', 'tech_sample.txt'):
        (workspace / 'data/input/stilreferenzen' / name).write_bytes(b'')
    settings = configuration.load_distance_settings(workspace)
    cache = {}
    for destination, distance in scenario['prepared_route_distances'].items():
        cache_key = 'v2:' + json.dumps([
            settings.origin_longitude, settings.origin_latitude,
            settings.origin_city.casefold(), destination.casefold(),
        ], ensure_ascii=False, separators=(',', ':'))
        cache[cache_key] = distance
    (workspace / 'data/state/routen_cache.json').write_text(json.dumps(cache), encoding='utf-8')


def run_showcase(output_dir=None):
    """Produce only fictional exported artifacts; delete the temporary database."""
    output = Path(output_dir) if output_dir else ROOT / 'docs/demo'
    output.mkdir(parents=True, exist_ok=True)
    scenario = json.loads((ROOT / 'docs/demo/scenario.json').read_text(encoding='utf-8'))
    transcript = io.StringIO()
    results = {
        'fictional': True, 'live_api_calls': 0, 'sample_date': scenario['sample_date'],
        'prepared_inputs': ['job listings and search results', 'fit scores and reasoning',
                            'cover-letter prose', '180 km road-distance cache value'],
        'actual_code': ['CV/CSV import and hashing', 'existing agent tool function bodies',
                        'eligibility and duplicate checks', 'distance-cache lookup and threshold',
                        'SQLite persistence and selection', 'style-reference reading',
                        'PDF rendering and text checks', 'draft-status update', 'CLI formatters'],
        'jobs': [],
    }
    with tempfile.TemporaryDirectory(prefix='.portfolio-test-showcase-', dir=ROOT) as temporary:
        workspace = Path(temporary)
        prepare_inputs(workspace, scenario)
        with isolated_application(workspace, scenario), redirect_stdout(transcript):
            tools = load_tool_bodies(workspace)
            print('$ python -B scripts/run_showcase.py')
            print('OFFLINE SHOWCASE: all data fictional; no OpenAI or routing requests.')
            print('Scores, reasoning, letter prose and one route distance are prepared inputs.')
            database.initialize()
            operations.initialize_extensions()
            total, new = database.import_applications()
            imported, unchanged = documents.import_documents()
            assert scenario['cv_facts'].strip() in tools['lies_lebenslauf']()
            assert json.loads(tools['bekannte_bewerbungen']()) == []
            print(f'\n[1] Imported {imported} documents; {total} previous applications.')
            print('[2] Process prepared listing data through the original save tool:')
            for job in scenario['jobs']:
                decision, reason = policy.assess(
                    job['company'], job['title'], job['url'], job['location'],
                    job['attendance'], job['application_format'],
                    job['original_application_open'], job['description'])
                assert decision == job['expected_status'], (job['label'], decision)
                saved = tools['stelle_speichern'](
                    job['company'], job['title'], job['url'], job['location'],
                    job['remote_model'], job['attendance'], job['application_format'],
                    job['original_application_open'], job['description'],
                    job['prepared_fit_score'], job['prepared_reason'], job['prepared_evidence'])
                with database.connect() as db:
                    row = db.execute('SELECT id,workflow_status FROM jobs WHERE url=?',
                                     (job['url'],)).fetchone()
                results['jobs'].append({
                    'label': job['label'], 'company': job['company'], 'title': job['title'],
                    'prepared_fit_score': job['prepared_fit_score'], 'url': job['url'],
                    'decision': decision, 'rule_reason': reason,
                    'stored': row is not None, 'job_id': row['id'] if row else None,
                    'requirements': job['description'], 'prepared_analysis': job['prepared_reason'],
                })
                print(f"  {job['label']}: prepared score {job['prepared_fit_score']}/10 -> {decision}")
                print('     ' + saved)
            with database.connect() as db:
                chosen = db.execute("""SELECT j.id FROM jobs j
                    WHERE j.workflow_status='bereit'
                    AND NOT EXISTS(SELECT 1 FROM drafts d WHERE d.job_id=j.id)
                    AND NOT EXISTS(SELECT 1 FROM email_drafts e WHERE e.job_id=j.id)
                    ORDER BY j.fit_score DESC,j.id DESC LIMIT 1""").fetchone()
            assert chosen is not None
            job_id = chosen['id']
            assert json.loads(tools['stelle_abrufen'](job_id))['company'] == scenario['jobs'][0]['company']
            print(f'\n[3] Selected ready job {job_id} from SQLite.')
            reference = json.loads(tools['stilreferenzen_lesen']([scenario['chosen_style']]))
            assert reference[scenario['chosen_style']] == style_references.EMPTY_REFERENCE_NOTICE
            print('[4] Technical style selected for this fixture; empty reference -> style-guide fallback.')
            letter = scenario['prepared_letter']
            print('[5] Pass prepared fictional prose to the existing PDF tool:')
            args = (job_id, letter['subject'], letter['salutation'], letter['paragraphs'],
                    letter['closing'], letter['recipient'])
            message = tools['anschreiben_pdf_erstellen'](*args)
            print('    ' + message)
            assert message.startswith('PDF:'), message
            with database.connect() as db:
                draft = db.execute('SELECT * FROM drafts WHERE job_id=?', (job_id,)).fetchone()
                application = db.execute('SELECT status FROM applications').fetchone()
                final_jobs = dict(db.execute('SELECT id,workflow_status FROM jobs').fetchall())
                counts = database.counts()
            assert application['status'] == 'entwurf'
            assert counts['drafts'] == counts['applications'] == 1 and counts['jobs'] == 2
            repeated = tools['anschreiben_pdf_erstellen'](*args)
            assert 'bereits vorhanden' in repeated
            print('[6] Status changed to entwurf; duplicate draft request rejected.')
            print('    ' + repeated)
            print('\nActual CLI jobs formatter (main.jobs):')
            cli.jobs()
            print('\nActual CLI applications formatter (main.applications):')
            cli.applications()
            shutil.copyfile(workspace / draft['pdf_path'], output / 'cover_letter.pdf')
            (output / 'cover_letter.txt').write_text(draft['content'] + '\n', encoding='utf-8')
            for item in results['jobs']:
                item['final_workflow_status'] = final_jobs.get(item['job_id'], 'not_saved')
            results.update({
                'selected_job_id': job_id, 'application_status': application['status'],
                'draft_status': draft['status'], 'stored_jobs': counts['jobs'],
                'application_count': counts['applications'], 'draft_count': counts['drafts'],
                'duplicate_draft_rejected': True, 'chosen_style': scenario['chosen_style'],
                'style_fallback_used': True, 'artifact': 'cover_letter.pdf',
                'database_published': False,
            })
            print('\nExported: cover_letter.pdf, cover_letter.txt, results.json, terminal.txt')
            print('Temporary SQLite and input workspace removed; nothing submitted or sent.')
    text = transcript.getvalue()
    (output / 'terminal.txt').write_text(text, encoding='utf-8')
    (output / 'results.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return results, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Destination for fictional artifacts.')
    args = parser.parse_args()
    _, transcript = run_showcase(args.output_dir)
    print(transcript, end='')


if __name__ == '__main__':
    main()
