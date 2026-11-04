#!/usr/bin/env python
"""Track 3 build script: what AI assistants say about RPSD.

    python track3/run.py test                 # offline + free: runs the full pipeline on the synthetic sample
    python track3/run.py collect [--spend]    # ask the 6 questions to each AI (paid only with --spend)
    python track3/run.py label   [--spend]    # auto-label + fact-check every answer (paid only with --spend)
    python track3/run.py export               # tracker CSVs + comparison with hand labels (free)
    python track3/run.py all     [--spend]    # collect, label, export

Without --spend every target is free: paid steps only report what they would send.
Real runs need RPSD-Capstone/.env (see .env.example). Results go to data/track3/ (gitignored).
"""
import argparse, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rpsd_rules as R          # noqa: E402
import rpsd_tools as T          # noqa: E402

TESTDATA = HERE / 'test' / 'testdata'


def run_test():
    """Full pipeline on made-up data, with all network access blocked. Exit code 1 on any failure."""
    out = T.REPO / 'data' / 'track3-test'            # gitignored scratch folder, rebuilt every run
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(TESTDATA / 'data_seed', out)

    def offline(*a, **k):
        raise AssertionError('The test tried to use the network; it must run offline.')
    T.configure(DATA_DIR=out, TESTER='Test', BATCH_ID='sample', ALLOW_SPENDING=False,
                FACT_SHEET_FILE=str(TESTDATA / 'fact_sheet_sample.html'),
                SHEET_FILES={'Sample': str(TESTDATA / 'tracker_sample.csv')}, SHEET_TABS={'Sample': ''},
                LABEL_API_RESULTS=True, LABEL_SHEET_TABS=['Sample'], MAX_ANSWERS=None,
                ACCURACY_REFERENCE_TABS=['Sample'])
    T.http_json = T.fetch_text = offline

    print('== collect (no keys, so nothing is sent)'); T.collect()
    print('\n== saved answers'); print(T.results_table().to_string(index=False))
    print('\n== fact sheet'); T.load_fact_sheet()
    print('\n== answers to label'); print(T.gather_items().to_string())
    print('\n== label + fact-check (from the saved sample judge results)'); T.run_labels()
    print('\n== export + compare'); T.export_and_compare()

    rows = {row['Run ID']: row for _, row, _ in T.RESULTS}
    checks = [
        ('every answer labeled from the cache (nothing paid, nothing skipped)', not T.SKIPPED and not T.FAILED and len(rows) == 4),
        ('hedged numbered list: no explicit rank, list position 2',
         rows['T01']['Explicit recommendation rank'] == '' and rows['T01']['Numbered-list position'] == 2),
        ('competitor names normalized (SDFC -> San Diego Fertility Center)',
         rows['T01']['Competitors mentioned'] == 'San Diego Fertility Center; Hanabusa IVF'),
        ('donor programs flagged as needs qualification', rows['T01']['Accuracy assessment'] == 'Needs qualification - review'),
        ('invented fact ID F99 removed from the evidence', 'F99' not in rows['T01']['Evidence / fact-sheet reference']),
        ('RPSD absent -> N/A values', rows['T02']['RPSD mentioned'] == 'No' and rows['T02']['First mention order'] == R.NA_ABSENT),
        ('priority competitor detected (RMA San Diego / Pearl)', 'RMA San Diego' in rows['T02']['Notes / deviations']),
        ('branded prompt -> rank N/A', rows['T03']['Explicit recommendation rank'] == R.NA_BRANDED),
        ('claim with a made-up quote dropped', '1 claim(s) dropped' in rows['T03']['Notes / deviations']),
        ('star rating = not documented', rows['T03']['Accuracy assessment'] == 'Supported + not documented'),
        ('"Best overall" keeps explicit rank 1', rows['API-OpenAI-P01-1']['Explicit recommendation rank'] == 1),
    ]
    print('\n== checks')
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    if failed and T.SKIPPED:
        print('\nThe sample judge results no longer match the rules (RULES_VERSION changed?). '
              'Rebuild them with: python track3/test/make_testdata.py')
    print(f'\n{len(checks) - len(failed)}/{len(checks)} checks passed. Outputs: {out}')
    return 1 if failed else 0


def configure_real(args):
    env = T.load_env()
    T.configure(TESTER=args.tester, ALLOW_SPENDING=args.spend, SMOKE_TEST=args.smoke,
                SHEET_ID=env.get('RPSD_TRACKER_SHEET_ID', ''),
                SHEET_TABS=T.sheet_tabs_from_env(env.get('RPSD_TRACKER_TAB_GIDS')),
                FACT_DOC_ID=env.get('RPSD_FACT_SHEET_DOC_ID', ''),
                LABEL_SHEET_TABS=[t for t in args.tabs.split(',') if t], MAX_ANSWERS=args.max)
    if args.target in ('collect', 'label', 'all'):
        T.keys_from_env(env)
        if not T.KEYS:
            print('No API keys in .env; asking instead (Enter to skip a provider).')
            T.enter_keys()
    T.status()
    missing = [n for n, v in [('RPSD_TRACKER_SHEET_ID', T.SHEET_ID), ('RPSD_FACT_SHEET_DOC_ID', T.FACT_DOC_ID)] if not v]
    if missing and args.target in ('label', 'export', 'all'):
        sys.exit(f'Missing {", ".join(missing)} in RPSD-Capstone/.env (copy .env.example).')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('target', choices=['test', 'collect', 'label', 'export', 'all'])
    ap.add_argument('--spend', action='store_true', help='allow paid API calls (otherwise free mode)')
    ap.add_argument('--smoke', action='store_true', help='collect: only P01 trial 1 per provider')
    ap.add_argument('--tester', default=T.TESTER, help='name used in result file names (default: %(default)s)')
    ap.add_argument('--tabs', default='Siya,Audrey', help='tracker tabs to label, comma-separated')
    ap.add_argument('--max', type=int, default=None, help='label at most N answers')
    args = ap.parse_args()

    if args.target == 'test':
        sys.exit(run_test())
    configure_real(args)
    if args.target in ('collect', 'all'):
        print('\n== collect'); T.collect()
    if args.target in ('label', 'export', 'all'):
        print('\n== fact sheet + answers'); T.load_fact_sheet(); print(T.gather_items())
        print('\n== label + fact-check'); T.run_labels()
        print('\n== export + compare'); T.export_and_compare()
    print(f'\nResults in {T.DATA}')


if __name__ == '__main__':
    main()
