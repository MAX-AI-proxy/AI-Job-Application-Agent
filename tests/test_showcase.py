"""Regression checks for the isolated fictional showcase."""
import hashlib
import importlib.util
import re
import socket
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('showcase', ROOT / 'scripts/run_showcase.py')
showcase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(showcase)


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='.portfolio-test-demo-test-', dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / 'artifacts'
        self.before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (ROOT / 'app').glob('*.py')}
        self.results, self.transcript = showcase.run_showcase(self.output)

    def test_three_real_policy_decisions_and_storage(self):
        self.assertEqual([j['decision'] for j in self.results['jobs']], ['bereit','pruefen','gesperrt'])
        self.assertEqual([j['stored'] for j in self.results['jobs']], [True,True,False])
        self.assertEqual(self.results['stored_jobs'], 2)
        self.assertIn('180 km', self.results['jobs'][2]['rule_reason'])

    def test_draft_transition_and_duplicate_prevention(self):
        self.assertEqual(self.results['application_status'], 'entwurf')
        self.assertEqual(self.results['draft_status'], 'pruefen')
        self.assertEqual(self.results['draft_count'], 1)
        self.assertTrue(self.results['duplicate_draft_rejected'])
        self.assertEqual(self.results['jobs'][0]['final_workflow_status'], 'entwurf')

    def test_pdf_text_and_metadata_are_fictional(self):
        pdf = PdfReader(self.output / 'cover_letter.pdf')
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text()
        self.assertIn('Robin Muster (fiktiv)', text)
        self.assertIn('robin.muster@example.invalid', text)
        self.assertIn('Beispielbetrieb A', text)
        self.assertIn('15.01.2026', text)
        self.assertEqual(pdf.metadata.author, 'Robin Muster (fiktiv)')
        self.assertIn('Fiktives Beispiel', pdf.metadata.title)
        self.assertNotIn('/EmbeddedFiles', pdf.trailer['/Root'])

    def test_outputs_are_reproducible(self):
        second = Path(self.temporary.name) / 'second'
        results, text = showcase.run_showcase(second)
        self.assertEqual(results, self.results)
        self.assertEqual(text, self.transcript)
        for name in ('cover_letter.pdf','cover_letter.txt','results.json','terminal.txt'):
            self.assertEqual((second / name).read_bytes(), (self.output / name).read_bytes())

    def test_no_productive_state_or_application_code_changed(self):
        self.assertEqual(self.before, {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROOT / 'app').glob('*.py')})
        self.assertFalse((ROOT / 'data/state/showcase.sqlite3').exists())
        self.assertFalse((ROOT / '.env').exists())
        self.assertFalse(self.results['database_published'])
        self.assertEqual(self.results['live_api_calls'], 0)
        self.assertIn('prepared inputs', self.transcript)
        self.assertNotIn(str(ROOT), self.transcript)

    def test_readme_links_resolve_to_public_files(self):
        for document in (ROOT / 'README.md', ROOT / 'docs/demo/README.md'):
            for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', document.read_text()):
                if link.startswith(('https://', 'http://', '#')):
                    continue
                target = (document.parent / link.split('#')[0]).resolve()
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.exists(), link)

    def test_network_attempts_are_rejected(self):
        import json
        scenario = json.loads((ROOT / 'docs/demo/scenario.json').read_text())
        with showcase.isolated_application(Path(self.temporary.name), scenario):
            with self.assertRaisesRegex(RuntimeError, 'Network is disabled'):
                socket.getaddrinfo('employer-a.example.invalid', 443)
            with socket.socket() as client:
                with self.assertRaisesRegex(RuntimeError, 'Network is disabled'):
                    client.connect(('127.0.0.1', 1))

    def test_public_domains_and_empty_style_files(self):
        self.assertTrue(all('.example.invalid/' in j['url'] for j in self.results['jobs']))
        self.assertTrue(self.results['style_fallback_used'])
        for name in ('startup_sample.txt','corporate_sample.txt','tech_sample.txt'):
            self.assertEqual((ROOT / 'data/input/stilreferenzen' / name).read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
