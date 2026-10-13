"""Regressionsprüfungen ohne Netzwerk mit ausschließlich erfundenen Eingaben."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import application_manager, configuration, database, documents, operations, policy, rules, urls


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = 'Ausführliche erfundene Stellenbeschreibung für einen rein lokalen Test. ' * 4


class URLTests(unittest.TestCase):
    def test_distinct_job_identifiers_are_preserved(self):
        for left, right in (
            ('https://example.invalid/job?id=1', 'https://example.invalid/job?id=2'),
            ('https://example.invalid/job?job=', 'https://example.invalid/job'),
            ('https://example.invalid/job?gclid_job=1', 'https://example.invalid/job?gclid_job=2'),
            ('https://example.invalid/#/jobs/1', 'https://example.invalid/#/jobs/2'),
            ('https://example.invalid/job', 'https://example.invalid/job/'),
            ('https://example.invalid/job', 'https://www.example.invalid/job'),
            ('http://example.invalid/job', 'https://example.invalid/job'),
            ('https://example.invalid/job?id=1&id=2', 'https://example.invalid/job?id=2&id=1'),
        ):
            with self.subTest(left=left, right=right):
                self.assertTrue(urls.distinct_urls(left, right))
                self.assertFalse(urls.urls_match(left, right))

    def test_tracking_links_match_without_losing_job_parameters(self):
        self.assertTrue(urls.urls_match(
            'HTTPS://EXAMPLE.INVALID:443/job?id=7&utm_source=test&gclid=test#apply',
            'https://example.invalid/job?id=7#apply'))
        self.assertEqual(urls.canonical_url('https://example.invalid/job?id=7&fbclid=x&msclkid=y'),
                         'https://example.invalid/job?id=7')

    def test_invalid_urls_never_match(self):
        for value in ('', None, 'mailto:person@example.invalid', 'https://',
                      'https://example.invalid:invalid/job', 'https://user:password@example.invalid/job'):
            self.assertEqual(urls.canonical_url(value), '')
            self.assertFalse(urls.urls_match(value, value))

    def test_callers_use_the_shared_normalizer(self):
        self.assertIs(policy.canonical_url, urls.canonical_url)
        self.assertIs(application_manager.canonical_url, urls.canonical_url)
        self.assertIs(rules.urls_match, urls.urls_match)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='.portfolio-test-', dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'config').mkdir()
        (self.root / 'data/input/lebenslauf').mkdir(parents=True)
        (self.root / 'data/input/stilreferenzen').mkdir()
        for p in (ROOT / 'examples/config').iterdir():
            shutil.copyfile(p, self.root / 'config' / p.name)
        for name in ('00_START_HIER.md', '00_STILKOMPASS_ANSCHREIBEN.md'):
            shutil.copyfile(ROOT / 'config' / name, self.root / 'config' / name)
        shutil.copyfile(ROOT / 'examples/data/bewerbungen.csv', self.root / 'data/input/bewerbungen.csv')
        shutil.copyfile(ROOT / 'examples/data/lebenslauf.txt', self.root / 'data/input/lebenslauf/cv.txt')
        for p in (ROOT / 'data/input/stilreferenzen').iterdir():
            if p.suffix == '.txt':
                shutil.copyfile(p, self.root / 'data/input/stilreferenzen' / p.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in (database, documents, policy, rules, operations):
            self.stack.enter_context(patch.object(module, 'ROOT', self.root))
        self.stack.enter_context(patch.object(database, 'DB_PATH', self.root / 'data/state/test.sqlite3'))
        self.stack.enter_context(patch.object(database, 'CSV_PATH', self.root / 'data/input/bewerbungen.csv'))
        self.stack.enter_context(patch.object(policy, 'CACHE_FILE', self.root / 'data/state/routen_cache.json'))
        self.stack.enter_context(patch.object(documents, 'DOCUMENT_SOURCES', [
            (self.root / 'config/00_START_HIER.md', 'instructions'),
            (self.root / 'config/00_STILKOMPASS_ANSCHREIBEN.md', 'style_guide'),
        ]))
        database.initialize()
        operations.initialize_extensions()

    def settings(self, **changes):
        values = dict(origin_city='Teststadt', origin_longitude=0, origin_latitude=0,
                      max_weekly_distance_km=80, near_cities=['Nahstadt'], far_cities=['Fernstadt'])
        values.update(changes)
        (self.root / 'config/entfernung.json').write_text(json.dumps(values), encoding='utf-8')
        return configuration.load_distance_settings(self.root)

    def job(self, title='Testrolle', url='https://example.invalid/job?id=1', fmt='anschreiben'):
        with database.connect() as db:
            result = db.execute('''INSERT INTO jobs
                (company,title,url,description,location,remote_model,analysis_json,workflow_status,discovered_at)
                VALUES ('Testunternehmen',?,?,?,'Teststadt','Remote',?,'gefunden',?)''',
                (title, url, DESCRIPTION, json.dumps({'praesenzrhythmus':'keine',
                 'bewerbungsformat':fmt,'originalseite_bewerbung':True}), database.now()))
            return result.lastrowid

    def application(self, status='entwurf', url='https://example.invalid/job?id=1'):
        with database.connect() as db:
            result = db.execute('''INSERT INTO applications
                (unternehmen,stelle,company_key,role_key,status,stellen_url,created_at,updated_at)
                VALUES ('Testunternehmen','Testrolle','testunternehmen','testrolle',?,?,?,?)''',
                (status, url, database.now(), database.now()))
            return result.lastrowid

    def test_empty_templates_import_without_private_history(self):
        self.assertEqual(rules.excluded_companies(), [])
        self.assertEqual(database.import_applications(), (0, 0))
        self.assertEqual(documents.import_documents(), (6, 0))
        self.assertEqual(documents.import_documents(), (0, 6))
        with database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM documents WHERE kind='style_example' AND text_content=''").fetchone()[0], 3)

    def test_settings_validation_and_prompt_context(self):
        settings = self.settings()
        self.assertEqual(settings.max_weekly_distance_km, 80)
        self.assertIn('Teststadt', configuration.distance_policy_text(self.root))
        self.assertIn('80 km', configuration.distance_policy_text(self.root))
        for field, value in (('origin_city',''), ('origin_longitude',181), ('origin_latitude',-91),
                             ('origin_longitude',True), ('max_weekly_distance_km',-1),
                             ('max_weekly_distance_km',None), ('near_cities','Teststadt'),
                             ('origin_latitude',float('nan'))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.settings(**{field:value})

    def test_missing_distance_configuration_requires_review(self):
        (self.root / 'config/entfernung.json').unlink()
        self.assertIsNone(policy.distance_km('Zielstadt'))
        status, _ = policy.assess('Testunternehmen','Testrolle','https://example.invalid/job',
                                  'Zielstadt','woechentlich','anschreiben',True,DESCRIPTION)
        self.assertEqual(status, 'pruefen')
        self.assertEqual(policy.assess('Testunternehmen','Testrolle','https://example.invalid/job',
                                     'Zielstadt','keine','anschreiben',True,DESCRIPTION)[0], 'bereit')

    def test_weekly_distance_boundary_preserves_existing_rule(self):
        self.settings()
        for distance, expected in ((80,'bereit'), (80.1,'gesperrt'), (None,'pruefen')):
            with patch.object(policy, 'distance_km', return_value=distance):
                status, _ = policy.assess('Testunternehmen','Testrolle','https://example.invalid/job',
                                          'Zielstadt','woechentlich','anschreiben',True,DESCRIPTION)
            self.assertEqual(status, expected)

    def test_same_city_shortcut_and_configured_city_bands(self):
        self.settings()
        self.assertEqual(policy.distance_km('Teststadt'), 0)
        self.assertEqual(rules.location_band('Nahstadt'), 'regional')
        self.assertEqual(rules.location_band('Fernstadt'), 'fern')
        self.assertEqual(rules.location_band('Unbekannte Stadt'), 'unbekannt')
        self.assertIsNone(policy.distance_km('Remote'))

    def test_route_cache_is_separated_by_origin_without_network(self):
        calls = []
        class Response:
            def __init__(self, value): self.value = value
            def raise_for_status(self): pass
            def json(self): return self.value
        class Client:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, url, **kwargs):
                calls.append(url)
                if 'nominatim' in url:
                    return Response([{'lon':'2','lat':'3'}])
                return Response({'routes':[{'distance':125000}]})
        stub = SimpleNamespace(Client=Client, HTTPError=RuntimeError)
        settings = self.settings()
        policy.CACHE_FILE.write_text(json.dumps({'zielstadt':999}), encoding='utf-8')
        with patch.dict(sys.modules, {'httpx':stub}), patch.object(policy.time,'sleep'):
            self.assertEqual(policy.distance_km('Zielstadt',settings), 125)
            self.assertEqual(policy.distance_km('Zielstadt',settings), 125)
            self.assertEqual(len(calls), 2)
            changed = self.settings(origin_longitude=1)
            self.assertEqual(policy.distance_km('Zielstadt',changed), 125)
            self.assertEqual(len(calls), 4)
        self.assertIn('/0.0,0.0;2.0,3.0', calls[1])
        self.assertIn('/1.0,0.0;2.0,3.0', calls[3])

    def test_status_update_does_not_merge_jobs_with_same_title(self):
        first = self.job()
        second = self.job(url='https://example.invalid/job?id=2')
        application_manager.set_application_status(self.application(), 'beworben')
        with database.connect() as db:
            states = dict(db.execute('SELECT id,workflow_status FROM jobs').fetchall())
        self.assertEqual(states[first], 'beworben')
        self.assertEqual(states[second], 'gefunden')
        with self.assertRaisesRegex(ValueError,'Mögliche Doppelbewerbung'):
            application_manager.mark_job(second, 'beworben')

    def test_distinct_similar_jobs_require_review_instead_of_false_exact_match(self):
        self.application('beworben')
        self.assertEqual(policy.duplicate_application('Testunternehmen','Testrolle',
                         'https://example.invalid/job?id=2')[0], 'pruefen')
        self.assertEqual(rules.applied_or_uncertain('Testunternehmen','Testrolle',
                         'https://example.invalid/job?id=2'), 'status_unklar')
        self.assertEqual(policy.duplicate_application('Testunternehmen','Testrolle',
                         'https://example.invalid/job?id=1&utm_source=test')[0], 'gesperrt')

    def test_email_generation_and_status_guards_are_preserved(self):
        job_id = self.job(fmt='kurze_email')
        body = 'Hallo Testteam,\n\nDies ist ein erfundener Bewerbungstext für einen lokalen Test. ' * 3
        result = operations.save_email(job_id,'Testbewerbung',body)
        self.assertIn('nicht versendet', result)
        self.assertTrue((self.root / f'output/emails/{job_id:04d}_bewerbung_email.txt').is_file())
        with database.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM applications').fetchone()[0], 'entwurf')
            app_id = db.execute('SELECT id FROM applications').fetchone()[0]
        self.assertIn('existiert bereits', operations.save_email(job_id,'Testbewerbung',body))
        application_manager.set_application_status(app_id,'beworben')
        with self.assertRaises(ValueError):
            application_manager.set_application_status(app_id,'entwurf')
        application_manager.set_application_status(app_id,'absage')
        with self.assertRaises(ValueError):
            application_manager.set_application_status(app_id,'beworben')

    @unittest.skipUnless(importlib.util.find_spec('pypdf') and importlib.util.find_spec('reportlab'),
                         'PDF dependencies are not installed')
    def test_real_pdf_render_with_fictional_data(self):
        from app import pdf_generator
        from pypdf import PdfReader
        applicant = dict(name='Testperson',street='Testweg 1',zip_city='00000 Teststadt',
                         city='Teststadt',email='test@example.invalid',phone='0000 000000')
        paragraphs = 'Dies ist ein vollständig erfundener Brieftext für eine lokale PDF-Prüfung.'
        with patch.object(pdf_generator,'ROOT',self.root):
            try:
                path = pdf_generator.make_pdf(1,'Testunternehmen','Testrolle',applicant,
                       'Testbewerbung','Hallo Testteam,',paragraphs,'Viele Grüße','')
            except RuntimeError as exc:
                if 'Keine geeignete Schrift gefunden' in str(exc): self.skipTest(str(exc))
                raise
        pdf = PdfReader(self.root/path)
        self.assertEqual(len(pdf.pages), 1)
        self.assertIn(paragraphs, pdf.pages[0].extract_text())
        self.assertFalse(list((self.root/'output/anschreiben').glob('*.tmp.pdf')))

    def test_fresh_checkout_cli_with_public_templates(self):
        app_dir = self.root/'app'
        app_dir.mkdir()
        for p in (ROOT/'app').glob('*.py'): shutil.copyfile(p,app_dir/p.name)
        shutil.copyfile(ROOT/'main.py',self.root/'main.py')
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        environment.pop('PYTHONPATH',None)
        for command in ('init','import','status','applications','jobs','usage'):
            result = subprocess.run([sys.executable,'-B','main.py',command],cwd=self.root,
                                    env=environment,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'app/__pycache__').exists())


if __name__ == '__main__':
    unittest.main()
