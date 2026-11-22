"""Offline integration checks: independent collection, resume, validation, and handoff."""
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_questions, planned_rows
from collect import collect_batch, prepare_batch
from combine_batches import combine
from providers import ask


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.questions = load_questions()
        self.calls = 0

    def fake(self, provider, model, prompt, key):
        self.calls += 1
        return {'response_text': '=Original, "answer"\nSecond line — preserved.',
                'citation_urls': '["https://example.org/review"]', 'model_returned': model + '-resolved',
                'search_count': 1, 'raw_response': {'original': 'provider payload'}}

    def batch(self, batch='collector1-q1-01', tester='Collector1', models=None, trials=1, complete=True):
        d = self.root / 'batches' / batch
        m = prepare_batch(d, batch, tester, models or {'OpenAI': 'test-model'}, trials, self.questions)
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, {p: 'fake-key' for p in m['models']}, spend=complete, delay=0, ask_fn=self.fake)
        return d, m

    def test_grid_matches_proposal(self):
        self.assertEqual(len(self.questions), 40)
        self.assertEqual(len({q['question_id'] for q in self.questions}), 40)
        self.assertIn('What is Reproductive Partners Fertility Center in San Diego known for?',
                      [q['prompt_text'] for q in self.questions])
        self.assertEqual(sum(q['question_framing'] == 'negative' for q in self.questions), 20)

    def test_two_full_batches_ten_files_and_resume(self):
        models = {'OpenAI': 'test-openai', 'Claude': 'test-claude', 'Gemini': 'test-gemini'}
        a, ma = self.batch(models=models, trials=3)
        b, _ = self.batch('collector2-q1-01', 'Collector2', models, trials=3)
        self.assertEqual(self.calls, 720)
        with redirect_stdout(io.StringIO()):
            collect_batch(a, ma, {'OpenAI': 'x'}, spend=True, delay=0, ask_fn=self.fake)
            rows = combine([a, b, a], self.root / 'out')
        self.assertEqual(self.calls, 720)
        self.assertEqual(len(rows), 720)
        self.assertEqual(len({r['record_id'] for r in rows}), 720)
        exports = sorted((self.root / 'out' / 'exports').glob('*.csv'))
        self.assertEqual(len(exports), 10)
        for path in exports:
            with path.open(encoding='utf-8-sig', newline='') as f:
                data = list(csv.DictReader(f))
            self.assertEqual(len(data), 72)
            self.assertEqual({r['tester'] for r in data}, {'Collector1', 'Collector2'})
            self.assertEqual({r['question_framing'] for r in data}, {'neutral', 'negative'})
            self.assertEqual(data[0]['response_text'], '=Original, "answer"\nSecond line — preserved.')
            self.assertEqual(data[0]['sentiment_label'], '')
        self.assertTrue(json.loads((self.root / 'out' / 'handoff_summary.json').read_text())['complete'])

    def test_dry_run_no_network(self):
        d, m = self.batch(complete=False)
        self.assertEqual(self.calls, 0)
        self.assertFalse((d / 'attempts.jsonl').exists())
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, '40 missing'):
            combine([d], self.root / 'out')
        self.assertTrue((self.root / 'out' / 'coverage_report.csv').exists())
        self.assertFalse((self.root / 'out' / 'exports').exists())

    def test_fail_retry_limit_and_partial(self):
        d, m = self.batch(complete=False)
        with redirect_stdout(io.StringIO()):
            errors = collect_batch(d, m, {'OpenAI': 'secret'}, True, limit=1, delay=0,
                                   ask_fn=lambda *a: (_ for _ in ()).throw(RuntimeError('bad secret')))
        self.assertEqual(errors, 1)
        self.assertNotIn('bad secret', (d / 'attempts.jsonl').read_text())
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, {'OpenAI': 'x'}, True, limit=1, delay=0, ask_fn=self.fake)
            rows = combine([d / 'responses.csv'], self.root / 'out', allow_partial=True)
        self.assertEqual(len(rows), 1)
        summary = json.loads((self.root / 'out' / 'handoff_summary.json').read_text())
        self.assertEqual(summary['missing_or_failed_slots'], 39)
        self.assertFalse(summary['complete'])
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, {'OpenAI': 'x'}, True, delay=0, ask_fn=self.fake)
        self.assertEqual(self.calls, 40)

    def test_changed_settings_refused(self):
        d, m = self.batch(complete=False)
        with self.assertRaisesRegex(ValueError, 'changed'):
            prepare_batch(d, m['batch_id'], 'Collector2', m['models'], 1, self.questions)
        changed = [dict(q) for q in self.questions]
        changed[0]['prompt_text'] += ' Changed.'
        with self.assertRaisesRegex(ValueError, 'changed'):
            prepare_batch(d, m['batch_id'], 'Collector1', m['models'], 1, changed)

    def test_changed_question_set_and_models_refused(self):
        a, _ = self.batch()
        b, _ = self.batch('collector2-q1-01', 'Collector2', {'OpenAI': 'different-model'})
        with self.assertRaisesRegex(ValueError, 'Models'):
            combine([a, b], self.root / 'out')
        from common import fingerprint
        manifest_path = b / 'manifest.json'
        m = json.loads(manifest_path.read_text())
        m['questions'][0]['prompt_text'] += ' Changed.'
        m['question_set_sha256'] = fingerprint(m['questions'])
        manifest_path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'metadata'):
            combine([a, b], self.root / 'out', allow_model_differences=True)

    def test_duplicate_conflicts_and_damaged_log(self):
        a, _ = self.batch()
        path = a / 'attempts.jsonl'
        first = json.loads(path.read_text().splitlines()[0])
        first['record']['response_text'] = 'Conflicting answer'
        first['capture']['response_text'] = 'Conflicting answer'
        with path.open('a') as f:
            f.write(json.dumps(first) + '\n')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            combine([a], self.root / 'out')
        path.write_text('{unfinished')
        with self.assertRaisesRegex(ValueError, 'damaged'):
            combine([a], self.root / 'out')

    def test_output_cannot_overwrite_batch(self):
        a, _ = self.batch()
        with self.assertRaisesRegex(ValueError, 'separate'):
            combine([a], a)

    def test_topic_filter_resumes_without_changing_full_design(self):
        models = {'OpenAI': 'test-openai', 'Claude': 'test-claude', 'Gemini': 'test-gemini'}
        d, m = self.batch(models=models, trials=3, complete=False)
        keys = {p: 'fake-key' for p in models}
        manifest_before = (d / 'manifest.json').read_bytes()
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake, topics=['general'])
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake, topics=['general'])
        self.assertEqual(self.calls, 72)
        self.assertEqual((d / 'manifest.json').read_bytes(), manifest_before)
        with (d / 'responses.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 72)
        self.assertEqual({r['topic'] for r in rows}, {'general'})
        self.assertEqual(len(list(planned_rows(m))), 360)
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake)
        self.assertEqual(self.calls, 360)

    def test_concurrent_topic_capture_is_durable_and_resumable(self):
        models = {'OpenAI': 'test-openai', 'Claude': 'test-claude', 'Gemini': 'test-gemini'}
        d, m = self.batch(models=models, trials=3, complete=False)
        keys = {p: 'fake-key' for p in models}
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake, topics=['general'], workers=3)
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake, topics=['general'], workers=3)
        captures = [json.loads(line) for line in (d / 'attempts.jsonl').read_text().splitlines()]
        self.assertEqual(len(captures), 72)
        self.assertEqual(len({a['record']['record_id'] for a in captures}), 72)
        self.assertTrue(all(a['record']['status'] == 'success' for a in captures))

    def test_provider_filter_preserves_manifest_and_defers_openai(self):
        models = {'OpenAI': 'test-openai', 'Claude': 'test-claude', 'Gemini': 'test-gemini'}
        d, m = self.batch(models=models, trials=3, complete=False)
        frozen = (d / 'manifest.json').read_bytes()
        keys = {'Claude': 'fake-key', 'Gemini': 'fake-key'}
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake,
                          topics=['safety', 'communication'], providers=['Claude', 'Gemini'], workers=3)
            collect_batch(d, m, keys, True, delay=0, ask_fn=self.fake,
                          topics=['safety', 'communication'], providers=['Claude', 'Gemini'], workers=3)
        captures = [json.loads(line)['record'] for line in (d / 'attempts.jsonl').read_text().splitlines()]
        self.assertEqual(len(captures), 96)
        self.assertEqual({r['provider'] for r in captures}, {'Claude', 'Gemini'})
        self.assertEqual((d / 'manifest.json').read_bytes(), frozen)
        self.assertEqual(self.calls, 96)
        with redirect_stdout(io.StringIO()):
            collect_batch(d, m, {'OpenAI': 'fake-key'}, True, delay=0, ask_fn=self.fake,
                          topics=['safety', 'communication'], providers=['OpenAI'])
        self.assertEqual(self.calls, 144)
        self.assertEqual((d / 'manifest.json').read_bytes(), frozen)

    def test_provider_filter_rejects_unconfigured_provider(self):
        d, m = self.batch(complete=False)
        with self.assertRaisesRegex(ValueError, 'providers present'):
            collect_batch(d, m, {}, True, ask_fn=self.fake, providers=['Claude'])
        self.assertEqual(self.calls, 0)

    def test_cli_offline_plan_and_missing_config(self):
        import subprocess
        script = Path(__file__).resolve().parents[1] / 'collect.py'
        config = self.root / 'models.json'
        config.write_text(json.dumps({'OpenAI': 'offline-test-model'}))
        command = [sys.executable, str(script), '--batch', 'cli-test', '--tester', 'Collector1',
                   '--config', str(config), '--data-dir', str(self.root / 'cli-data')]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('120 remaining', run.stdout)
        self.assertIn('no API calls', run.stdout)
        self.assertTrue((self.root / 'cli-data/batches/cli-test/manifest.json').exists())
        config.write_text(json.dumps({'OpenAI': 'REPLACE_WITH_MODEL'}))
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Invalid provider/model', run.stderr)

    def test_question_mismatch_even_when_version_unchanged(self):
        a, _ = self.batch()
        changed = [dict(q) for q in self.questions]
        changed[0]['prompt_text'] += ' Different wording.'
        b = self.root / 'batches' / 'changed'
        m = prepare_batch(b, 'changed', 'Collector2', {'OpenAI': 'test-model'}, 1, changed)
        with redirect_stdout(io.StringIO()):
            collect_batch(b, m, {'OpenAI': 'x'}, True, delay=0, ask_fn=self.fake)
        with self.assertRaisesRegex(ValueError, 'Question sets differ'):
            combine([a, b], self.root / 'out')

    def test_model_difference_override_is_recorded(self):
        a, _ = self.batch()
        b, _ = self.batch('collector2-q1-01', 'Collector2', {'OpenAI': 'different-model'})
        with redirect_stdout(io.StringIO()):
            rows = combine([a, b], self.root / 'out', allow_model_differences=True)
        self.assertEqual(len(rows), 80)
        self.assertTrue(json.loads((self.root / 'out/handoff_summary.json').read_text())['collection_settings_differ'])

    def test_complete_only_keeps_groups_complete_in_both_batches(self):
        models = {'OpenAI': 'test-openai', 'Claude': 'test-claude', 'Gemini': 'test-gemini'}
        a, _ = self.batch(models=models, trials=3)
        b, _ = self.batch('collector2-q1-01', 'Collector2', models, trials=3)
        keep = {('rpsd', 'general'), ('rpsd', 'billing'), ('rpsd', 'scheduling'), ('sdfc', 'general')}
        for directory in (a, b):
            log = directory / 'attempts.jsonl'
            captures = [json.loads(line) for line in log.read_text().splitlines()]
            retained = [x for x in captures if (x['record']['clinic_id'], x['record']['topic']) in keep]
            if directory == a:
                retained += [next(x for x in captures if x['record']['topic'] == 'safety')]
            log.write_text(''.join(json.dumps(x) + '\n' for x in retained))
        with redirect_stdout(io.StringIO()):
            rows = combine([a, b], self.root / 'out', complete_only=True)
        self.assertEqual(len(rows), 288)
        exports = list((self.root / 'out/exports').glob('*.csv'))
        self.assertEqual(len(exports), 4)
        self.assertEqual({(r['clinic_id'], r['topic']) for r in rows}, keep)
        for file in exports:
            with file.open(encoding='utf-8-sig', newline='') as stream:
                group = list(csv.DictReader(stream))
            self.assertEqual(len(group), 72)
            self.assertEqual({r['tester'] for r in group}, {'Collector1', 'Collector2'})
        summary = json.loads((self.root / 'out/handoff_summary.json').read_text())
        self.assertTrue(summary['selected_scope_complete'])
        self.assertFalse(summary['complete'])
        self.assertEqual(summary['expected_exported_response_count'], 288)
        self.assertEqual(summary['available_response_count_all_groups'], 289)
        self.assertEqual(len(summary['excluded_groups']), 6)

    def test_complete_only_rejects_no_complete_groups_and_mixed_flags(self):
        a, m = self.batch(complete=False)
        with redirect_stdout(io.StringIO()):
            collect_batch(a, m, {'OpenAI': 'fake-key'}, True, limit=1, delay=0, ask_fn=self.fake)
        with self.assertRaisesRegex(ValueError, 'No clinic/topic groups'):
            combine([a], self.root / 'out', complete_only=True)
        with self.assertRaisesRegex(ValueError, 'cannot be used together'):
            combine([a], self.root / 'out', complete_only=True, allow_partial=True)

    def test_provider_error_codes_do_not_expose_response_body(self):
        from urllib.error import HTTPError
        from providers import post
        body = io.BytesIO(json.dumps({'error': {'type': 'insufficient_quota',
                                              'code': 'insufficient_quota',
                                              'message': 'private body'}}).encode())
        error = HTTPError('https://example.org', 429, 'limit', {}, body)
        with patch('providers.urlopen', side_effect=error), self.assertRaises(RuntimeError) as raised:
            post('https://example.org', {}, {})
        self.assertIn('insufficient_quota', str(raised.exception))
        self.assertNotIn('private body', str(raised.exception))

    def test_provider_parsing_and_incomplete_exclusion(self):
        cases = {
            'OpenAI': {'status': 'completed', 'model': 'resolved', 'output': [
                {'type': 'web_search_call'}, {'type': 'message', 'content': [
                    {'type': 'output_text', 'text': 'Answer', 'annotations': [
                        {'type': 'url_citation', 'url': 'https://example.org'}]}]}]},
            'Claude': {'stop_reason': 'end_turn', 'model': 'resolved', 'content': [
                {'type': 'text', 'text': 'Answer', 'citations': [{'url': 'https://example.org'}]}]},
            'Gemini': {'modelVersion': 'resolved', 'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': 'Answer'}]}, 'groundingMetadata': {
                    'webSearchQueries': ['query'], 'groundingChunks': [{'web': {'uri': 'https://example.org'}}]}}]}}
        for provider, payload in cases.items():
            with self.subTest(provider=provider), patch('providers.post', return_value=payload) as request:
                r = ask(provider, 'requested', 'prompt', 'fake-key')
                self.assertEqual(r['response_text'], 'Answer')
                self.assertEqual(json.loads(r['citation_urls']), ['https://example.org'])
                self.assertEqual(r['model_returned'], 'resolved')
                self.assertEqual(request.call_count, 1)
        with patch('providers.post', return_value={'status': 'incomplete'}), self.assertRaises(ValueError):
            ask('OpenAI', 'requested', 'prompt', 'fake-key')
        with patch('providers.post', return_value={'candidates': [{'finishReason': 'MAX_TOKENS'}]}), self.assertRaises(ValueError):
            ask('Gemini', 'requested', 'prompt', 'fake-key')


if __name__ == '__main__':
    unittest.main()
