"""Offline-Prüfungen mit temporären Daten ausschließlich in der Projektkopie."""
import ast
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import database, documents
from app.configuration import distance_policy_text
from app.style_references import EMPTY_REFERENCE_NOTICE, available_style_references, read_style_references
from test_pdf import main as layout_main, parse_reference


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ['corporate_sample.txt', 'startup_sample.txt', 'tech_sample.txt']
GUIDES = ['00_START_HIER.md', '00_STILKOMPASS_ANSCHREIBEN.md']
TEST_LETTERS = {
    name: 'FIKTIVE STILREFERENZ\n\nBetreff: Bewerbung für ein Testprojekt\n\n'
    + salutation + '\n\n'
    + 'Dieses erfundene Testprojekt untersucht verständliche Abläufe. '
      'Die Beschreibung dient ausschließlich einer lokalen Parserprüfung.\n\n'
    + closing + '\n\nTestperson\n'
    for name, salutation, closing in (
        ('startup_sample.txt', 'Hallo Testteam,', 'Viele Grüße'),
        ('corporate_sample.txt', 'Sehr geehrtes Testteam,', 'Mit freundlichen Grüßen'),
        ('tech_sample.txt', 'Guten Tag Testteam,', 'Beste Grüße'),
    )
}


class StyleReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='.style-reference-test-', dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.samples = self.root / 'data/input/stilreferenzen'
        self.samples.mkdir(parents=True)
        (self.root / 'data/input/lebenslauf').mkdir()
        (self.root / 'data/input/lebenslauf/cv.txt').write_text('Fiktive CV-Fakten', encoding='utf-8')
        (self.root / 'config').mkdir()
        for name in GUIDES:
            (self.root / 'config' / name).write_text(
                (ROOT / 'config' / name).read_text(encoding='utf-8'), encoding='utf-8')
        for name in SAMPLES:
            (self.samples / name).write_text(
                TEST_LETTERS[name],
                encoding='utf-8')

    def test_public_collection_is_readable_and_empty(self):
        self.assertEqual(available_style_references(root=ROOT), SAMPLES)
        loaded = json.loads(read_style_references(SAMPLES, root=ROOT))
        self.assertEqual(sorted(loaded), SAMPLES)
        for name, text in loaded.items():
            self.assertEqual(text, EMPTY_REFERENCE_NOTICE)
            self.assertEqual((ROOT / 'data/input/stilreferenzen' / name).read_bytes(), b'')

    def test_loader_rejects_invalid_requests(self):
        for names in ([], SAMPLES + [SAMPLES[0]], ['missing.txt'], ['../lebenslauf/cv.txt'],
                      [str(self.samples / SAMPLES[0])], ['sample.pdf']):
            with self.subTest(names=names):
                self.assertTrue(read_style_references(names, root=self.root).startswith('FEHLER:'))

    def test_symlink_cannot_expose_other_documents(self):
        (self.samples / 'linked.txt').symlink_to(self.root / 'data/input/lebenslauf/cv.txt')
        self.assertNotIn('linked.txt', available_style_references(root=self.root))
        self.assertTrue(read_style_references(['linked.txt'], root=self.root).startswith('FEHLER:'))

    def test_markdown_and_utf8_bom_remain_supported(self):
        (self.samples / 'local.md').write_text('Lokale Stilvorlage', encoding='utf-8-sig')
        result = json.loads(read_style_references(['local.md'], root=self.root))
        self.assertEqual(result['local.md'], 'Lokale Stilvorlage')
        self.assertIn('local.md', available_style_references(root=self.root))

    def document_context(self):
        stack = ExitStack()
        stack.enter_context(patch.object(database, 'DB_PATH', self.root / 'data/state/test.sqlite3'))
        stack.enter_context(patch.object(documents, 'ROOT', self.root))
        stack.enter_context(patch.object(documents, 'DOCUMENT_SOURCES', [
            (self.root / 'config' / GUIDES[0], 'instructions'),
            (self.root / 'config' / GUIDES[1], 'style_guide'),
        ]))
        return stack

    def test_import_updates_and_prunes_only_style_documents(self):
        with self.document_context():
            database.initialize()
            with database.connect() as db:
                for path, kind in (
                    ('data/input/stilreferenzen/removed.txt', 'style_example'),
                    ('data/input/stilreferenzen_pdf/removed.pdf', 'style_pdf_layout'),
                    ('data/input/lebenslauf/retained.txt', 'cv_facts'),
                ):
                    db.execute('''INSERT INTO documents
                        (relative_path,kind,sha256,text_content,updated_at)
                        VALUES (?,?,?,'Offline fixture',?)''', (path, kind, 'test', database.now()))
            self.assertEqual(documents.import_documents(), (6, 0))
            self.assertEqual(documents.import_documents(), (0, 6))
            with database.connect() as db:
                styles = db.execute("SELECT relative_path,text_content FROM documents WHERE kind='style_example'").fetchall()
                self.assertEqual(sorted(Path(row['relative_path']).name for row in styles), SAMPLES)
                self.assertTrue(all('FIKTIVE STILREFERENZ' in row['text_content'] for row in styles))
                self.assertEqual(db.execute("SELECT count(*) FROM documents WHERE kind='style_pdf_layout'").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM documents WHERE relative_path LIKE '%retained.txt'").fetchone()[0], 1)
            sample = self.samples / SAMPLES[0]
            sample.write_text(sample.read_text(encoding='utf-8') + '\nAktualisierung\n', encoding='utf-8')
            self.assertEqual(documents.import_documents(), (1, 5))
            sample.unlink()
            documents.import_documents()
            with database.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM documents WHERE kind='style_example'").fetchone()[0], 2)

    def test_optional_pdf_sources_and_markdown_are_preserved(self):
        with self.document_context():
            self.assertFalse(any(kind == 'style_pdf_layout' for _, kind in documents.source_files()))
            pdf_dir = self.root / 'data/input/stilreferenzen_pdf'
            pdf_dir.mkdir()
            (pdf_dir / 'local.pdf').write_bytes(b'Offline discovery fixture')
            (self.samples / 'local.md').write_text('Lokale Stilvorlage', encoding='utf-8')
            sources = {(path.name, kind) for path, kind in documents.source_files()}
            self.assertIn(('local.pdf', 'style_pdf_layout'), sources)
            self.assertIn(('local.md', 'style_example'), sources)

    def test_all_samples_work_with_layout_parser(self):
        letters = [parse_reference((self.samples / name).read_text(encoding='utf-8')) for name in SAMPLES]
        self.assertEqual(len({letter['salutation'] for letter in letters}), 3)
        self.assertEqual(len({letter['closing'] for letter in letters}), 3)
        for letter in letters:
            self.assertIn('Bewerbung', letter['subject'])
            self.assertGreater(len(letter['paragraphs']), 50)
            self.assertNotIn('FIKTIVE STILREFERENZ', letter['paragraphs'])
            self.assertNotIn('Fiktive Beispielorganisation', letter['paragraphs'])

    def test_real_agent_prompt_and_tool_bodies_without_sdk_or_network(self):
        # Ausführung der unveränderten Funktionskörper, isoliert vom externen SDK.
        source = ast.parse((ROOT / 'app/agent.py').read_text(encoding='utf-8'))
        selected = [node for node in source.body if isinstance(node, ast.FunctionDef)
                    and node.name in {'cfg', 'stilreferenzen_lesen', 'make_agent'}]
        from app.style_references import available_style_references, read_style_references
        namespace = {
            'ROOT': self.root, 'date': date, 'MODEL': 'offline-test',
            'distance_policy_text': distance_policy_text,
            'function_tool': lambda function: function,
            'Agent': lambda **kwargs: SimpleNamespace(**kwargs),
            'WebSearchTool': lambda **kwargs: SimpleNamespace(**kwargs),
            'excluded_companies': lambda: [],
            'available_style_references': available_style_references,
            'read_style_references': read_style_references,
        }
        for name in ('lies_lebenslauf', 'bekannte_bewerbungen', 'offene_stellen',
                     'stelle_speichern', 'stelle_abrufen', 'anschreiben_pdf_erstellen', 'kurze_email_erstellen'):
            namespace[name] = object()
        for name in ('suchprofil.md', 'projektstand.md', 'bewerbungsregeln.md'):
            (self.root / 'config' / name).write_text('Neutrale Offline-Testkonfiguration', encoding='utf-8')
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'app/agent.py', 'exec'), namespace)
        agent = namespace['make_agent']('draft')
        for name in SAMPLES:
            self.assertIn(name, agent.instructions)
            self.assertIn(name, json.loads(namespace['stilreferenzen_lesen']([name])))
        self.assertIn(namespace['stilreferenzen_lesen'], agent.tools)
        self.assertIn('Leere Referenzen sind erlaubt', agent.instructions)
        self.assertIn('nur_cv', agent.instructions)
        self.assertIn('kurze_email', agent.instructions)
        self.assertIn('Hauptreferenz wählen', agent.instructions)
        self.assertIn('Unternehmensgröße allein entscheidet nicht', agent.instructions)
        self.assertNotIn(namespace['stilreferenzen_lesen'], namespace['make_agent']('search').tools)

    @unittest.skipUnless(shutil.which('git'), 'Git is not installed')
    def test_gitignore_includes_only_public_style_material(self):
        # Temporäres Git-Verzeichnis, keine Initialisierung der Projektkopie.
        environment = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                           GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        environment.pop('GIT_DIR', None)
        environment.pop('GIT_WORK_TREE', None)
        subprocess.run(['git', 'init', '--quiet', '--template=', str(self.root)],
                       env=environment, check=True, capture_output=True)
        public = ['data/input/stilreferenzen/' + name for name in SAMPLES]
        public += ['config/' + name for name in GUIDES]
        public += ['README.md', '.env.example', 'examples/config/entfernung.json',
                   'examples/config/absender.json', 'examples/data/bewerbungen.csv',
                   'examples/data/lebenslauf.txt']
        private = ['config/absender.json', 'config/suchprofil.md',
                   'data/state/bewerbungsagent.sqlite3', 'data/input/bewerbungen.csv',
                   'data/input/lebenslauf/local.txt', 'data/input/stilreferenzen/local.md',
                   'data/input/stilreferenzen_pdf/local.pdf', '.env', '.env.local',
                   '.env.production', 'config/entfernung.json', 'output/local.pdf',
                   'private.sqlite3', 'private.sqlite3-wal', 'private.pdf', 'private.key',
                   '.portfolio-test-leftover/config/private.json']
        result = subprocess.run(
            ['git', '--git-dir=' + str(self.root / '.git'), '--work-tree=' + str(ROOT),
             'check-ignore', '--no-index', '--stdin'],
            input='\n'.join(public + private) + '\n', text=True,
            capture_output=True, env=environment, check=True, cwd=ROOT)
        self.assertEqual(set(result.stdout.splitlines()), set(private))


class ReadOnlyStyleReferenceTests(unittest.TestCase):
    """Diese Prüfungen lesen nur Dateien und erzeugen weder Datenbanken noch PDFs."""

    def test_three_placeholders_are_zero_bytes(self):
        self.assertEqual(available_style_references(root=ROOT), SAMPLES)
        for name in SAMPLES:
            self.assertEqual((ROOT / 'data/input/stilreferenzen' / name).read_bytes(), b'')

    def test_empty_references_return_guidance(self):
        result = json.loads(read_style_references(SAMPLES, root=ROOT))
        self.assertEqual(result, {name: EMPTY_REFERENCE_NOTICE for name in SAMPLES})

    def test_invalid_reference_requests_remain_rejected(self):
        for names in ([], SAMPLES + [SAMPLES[0]], ['../lebenslauf/cv.txt'], ['missing.txt']):
            self.assertTrue(read_style_references(names, root=ROOT).startswith('FEHLER:'))

    def test_import_discovery_includes_empty_references(self):
        styles = sorted(path.name for path, kind in documents.source_files() if kind == 'style_example')
        self.assertEqual(styles, SAMPLES)

    def test_parser_handles_empty_input_and_filled_user_letters(self):
        for empty in ('', ' \n\t'):
            with self.assertRaisesRegex(ValueError, 'Stilreferenz ist leer'):
                parse_reference(empty)
        for letter in TEST_LETTERS.values():
            parsed = parse_reference(letter)
            self.assertIn('Bewerbung', parsed['subject'])
            self.assertTrue(parsed['paragraphs'])

    def test_layout_script_skips_empty_input(self):
        output = io.StringIO()
        with redirect_stdout(output):
            layout_main()
        self.assertIn('übersprungen', output.getvalue())

    def test_prompt_and_tool_use_style_guide_fallback(self):
        source = ast.parse((ROOT / 'app/agent.py').read_text(encoding='utf-8'))
        selected = [node for node in source.body if isinstance(node, ast.FunctionDef)
                    and node.name in {'cfg', 'stilreferenzen_lesen', 'make_agent'}]
        namespace = {
            'ROOT': ROOT, 'date': date, 'MODEL': 'offline-test',
            'distance_policy_text': distance_policy_text,
            'function_tool': lambda function: function,
            'Agent': lambda **kwargs: SimpleNamespace(**kwargs),
            'WebSearchTool': lambda **kwargs: SimpleNamespace(**kwargs),
            'excluded_companies': lambda: [],
            'available_style_references': available_style_references,
            'read_style_references': read_style_references,
        }
        for name in ('lies_lebenslauf', 'bekannte_bewerbungen', 'offene_stellen',
                     'stelle_speichern', 'stelle_abrufen', 'anschreiben_pdf_erstellen', 'kurze_email_erstellen'):
            namespace[name] = object()
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'app/agent.py', 'exec'), namespace)
        agent = namespace['make_agent']('draft')
        self.assertIn('Leere Referenzen sind erlaubt', agent.instructions)
        self.assertIn('Hauptreferenz wählen', agent.instructions)
        self.assertIn(namespace['stilreferenzen_lesen'], agent.tools)
        for name in SAMPLES:
            self.assertIn(name, agent.instructions)
        result = json.loads(namespace['stilreferenzen_lesen'](SAMPLES))
        self.assertEqual(result, {name: EMPTY_REFERENCE_NOTICE for name in SAMPLES})


if __name__ == '__main__':
    unittest.main()
