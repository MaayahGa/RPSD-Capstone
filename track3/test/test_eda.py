"""Offline checks for EDA preparation and the notebook competitor-position function."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

TRACK3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK3))
from prepare_eda import build_input


class PrepareEDATest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(TRACK3 / 'run.py'), 'test'],
                       cwd=TRACK3.parent, stdout=subprocess.DEVNULL, check=True)
        cls.seed = TRACK3.parent / 'data/track3-test'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.answers = self.folder / 'sample-answers.csv'
        self.labels = self.folder / 'labels.csv'
        self.output = self.folder / 'responses_input.csv'
        shutil.copy2(self.seed / 'sample-answers.csv', self.answers)
        shutil.copy2(next(self.seed.glob('autolabels-api-*.csv')), self.labels)
        shutil.copy2(self.seed / 'sample-openai-raw.jsonl', self.folder)

    def build(self):
        return build_input('sample', 'Demo', self.answers, self.labels, self.folder, self.output)

    def test_preserves_text_and_reproduces_output(self):
        table = self.build()
        original = pd.read_csv(self.answers, keep_default_na=False)
        self.assertEqual(table.response_text.tolist(), original.Answer.tolist())
        self.assertEqual(table.record_id.tolist(), ['sample:API-OpenAI-P01-1'])
        self.assertIn('auto_first_mention_order', table)
        self.assertNotIn('sentiment_label', table)
        first = self.output.read_bytes()
        self.build()
        self.assertEqual(first, self.output.read_bytes())

    def test_rejects_labels_from_another_answer(self):
        labels = pd.read_csv(self.labels, keep_default_na=False)
        labels.loc[0, 'Full response verbatim'] = 'A different batch answer.'
        labels.to_csv(self.labels, index=False)
        with self.assertRaisesRegex(ValueError, 'text mismatch'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_duplicate_response_ids(self):
        answers = pd.read_csv(self.answers, keep_default_na=False)
        pd.concat([answers, answers]).to_csv(self.answers, index=False)
        with self.assertRaisesRegex(ValueError, 'duplicate Run IDs'):
            self.build()

    def test_cannot_overwrite_source_answers(self):
        original = self.answers.read_bytes()
        with self.assertRaisesRegex(ValueError, 'overwrite a source'):
            build_input('sample', 'Demo', self.answers, self.labels, self.folder, self.answers)
        self.assertEqual(original, self.answers.read_bytes())

    def test_rejects_mismatched_raw_capture(self):
        path = self.folder / 'sample-openai-raw.jsonl'
        row = json.loads(path.read_text().splitlines()[0])
        row['answer'] = 'Different original capture.'
        path.write_text(json.dumps(row) + '\n')
        with self.assertRaisesRegex(ValueError, 'mismatched original capture'):
            self.build()
        self.assertFalse(self.output.exists())


# Execute only the tagged function-definition cell, not the data/API workflow.
NOTEBOOK = TRACK3 / 'notebooks/02_explore_responses.ipynb'
notebook = json.loads(NOTEBOOK.read_text(encoding='utf-8'))
helper_cells = [cell for cell in notebook['cells']
                if 'competitor-position-helper' in cell.get('metadata', {}).get('tags', [])]
if len(helper_cells) != 1:
    raise ValueError('Expected one competitor-position helper cell.')
namespace = {'REPO': TRACK3.parent}
exec(compile(''.join(helper_cells[0]['source']), str(NOTEBOOK), 'exec'), namespace)
estimate_positions = namespace['estimate_positions']


class CompetitorPositionsTest(unittest.TestCase):
    def test_order_uses_text_not_saved_list(self):
        result = estimate_positions('SDFC first. RPSD next. RMA last. SDFC again.',
                                    'RMA San Diego; San Diego Fertility Center', 'Yes')
        self.assertEqual(json.loads(result['auto_competitor_positions']),
                         {'RMA San Diego': 3, 'San Diego Fertility Center': 1})

    def test_nested_alias_not_double_counted(self):
        result = estimate_positions('Southern California Center for Reproductive Medicine. RPSD.',
             'California Center for Reproductive Medicine; Southern California Center for Reproductive Medicine', 'Yes')
        positions = json.loads(result['auto_competitor_positions'])
        self.assertIsNone(positions['California Center for Reproductive Medicine'])
        self.assertEqual(result['auto_rpsd_position_from_text'], 2)

    def test_url_only_name_is_not_a_visible_mention(self):
        result = estimate_positions('Visit https://example.com/hanabusa', 'Hanabusa IVF', 'No')
        self.assertIsNone(json.loads(result['auto_competitor_positions'])['Hanabusa IVF'])
        self.assertIn('Unmatched', result['auto_competitor_position_review'])


if __name__ == '__main__':
    unittest.main()
