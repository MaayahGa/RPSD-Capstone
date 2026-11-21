# Quarter 1: Topic-based AI responses

This workflow is separate from the **Quarter 2 pilot test** in the parent Track 3
folder. It leaves the pilot's code, notebooks, questions, and saved batches intact.
It uses Python 3.10+ and the standard library only; no installation is necessary.

The shared `questions.csv` contains the proposal's 40 exact prompts:
2 clinics × 5 topics × 2 question framings × 2 questions. RPSD is expanded as
“Reproductive Partners Fertility Center in San Diego”; SDFC as “San Diego Fertility
Center”. Topics are general, billing, scheduling, safety, and communication.
Question framing (`neutral` or `negative`) is not response sentiment.

## 1. Agree on the model configuration

Run all commands below from **`RPSD-Capstone/stream2/`** on local `main`.
On the older `track3` branch, run from the repository root instead.

```bash
cp -n track3/quarter1/models.example.json track3/quarter1/models.json
```

Replace each placeholder in `models.json` with a search-capable API model ID your
account can access. Use exactly the same file for Siya and Audrey. Remove a
provider entry if both of you agree not to collect it. Model IDs are explicit
rather than inherited from the pilot. Placeholder values are rejected.

Put keys in the existing gitignored `track3/.env`, or set environment variables:

```text
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

No tracker sheet or fact-sheet access is needed. This workflow collects responses;
it does not call a sentiment judge or the pilot fact-checker.

## 2. Plan each independent batch (free, offline)

Siya:

```bash
python3 track3/quarter1/collect.py --batch siya-q1-01 --tester Siya
```

Audrey, on her own computer:

```bash
python3 track3/quarter1/collect.py --batch audrey-q1-01 --tester Audrey
```

These commands create each batch's frozen `manifest.json` and print how many
collection slots remain. They do not contact any API. With three providers and
three trials (the default), each batch has 360 collection slots.

## 3. Collect responses

Siya:

```bash
python3 track3/quarter1/collect.py --batch siya-q1-01 --tester Siya --spend
```

Audrey:

```bash
python3 track3/quarter1/collect.py --batch audrey-q1-01 --tester Audrey --spend
```

`--spend` explicitly enables paid generation and provider web-search calls.
For a small first check, append `--limit 2`; this collects up to two remaining
slots, not a complete batch. Omit the limit to finish. `--trials N` changes the
study size and must be agreed before either batch is created.

Rerun the **same command** after an interruption or failure: successful slots are
skipped and missing/failed slots are retried. No automatic paid retries are made
within a slot; Claude may require continuation requests to finish one answer.
Failures make the command exit unsuccessfully and are saved in the private log.
Do not run two collection processes against the same batch simultaneously.

The batch manifest freezes the tester, providers/models, trial count, and exact
questions. Changing any of them requires a new batch ID. Use a new ID for an
independent new round, even if the settings are identical. A transport interruption
can leave an upstream request billed without a local success; resuming retries
that slot. A malformed/truncated log is rejected rather than silently discarded.

## 4. Share the complete batch folders privately

Default location on local `main`:

```text
stream2/data/track3/quarter1/batches/
  siya-q1-01/
    manifest.json       frozen design and provenance
    attempts.jsonl      original provider payloads, full answers, failures
    responses.csv       successful responses; regenerated from captures
  audrey-q1-01/
    manifest.json
    attempts.jsonl
    responses.csv
```

Audrey sends her entire `audrey-q1-01` folder to the person doing the merge.
Place both folders under the same `batches/` directory. No API keys or `.env`
files need to be shared. All real outputs live under gitignored `data/`.
`--data-dir PATH` can select a different private data location for collection.

The merger requires the manifest and attempt log alongside the CSV so it can
check the collection design and rebuild trustworthy rows. It does not treat an
edited `responses.csv` as a new original capture. It never needs API keys.

## 5. Combine and export the 10 CSVs

From `stream2/`:

```bash
python3 track3/quarter1/combine_batches.py --batches data/track3/quarter1/batches/siya-q1-01 data/track3/quarter1/batches/audrey-q1-01
```

You can also pass each folder's `responses.csv` path to `--batches`.
The default output is `data/track3/quarter1/combined/`:

```text
responses_master.csv
coverage_report.csv
handoff_summary.json
exports/
  rpsd_general.csv
  rpsd_billing.csv
  rpsd_scheduling.csv
  rpsd_safety.csv
  rpsd_communication.csv
  sdfc_general.csv
  sdfc_billing.csv
  sdfc_scheduling.csv
  sdfc_safety.csv
  sdfc_communication.csv
```

Send Keilani the **10 CSVs in `exports/`**, plus `handoff_summary.json` for counts
and completeness. Each CSV contains both collectors and both question framings.
For two complete three-provider, three-trial batches, the master has 720 rows and
each topic/clinic file has 72. Independent identical answers remain separate.
Repeated imports of an identical batch are skipped; conflicting copies are rejected.

Missing/failed slots normally block response exports and produce a coverage
report listing every expected slot. Resume collection to fill them. An explicitly
incomplete handoff can be generated with `--allow-partial`; the summary records
`complete: false`, missing counts, and actual per-file counts. All 10 CSVs are
created, including header-only files for empty groups. No fabricated rows are added.

Different question sets always block merging. Model/provider/trial differences
block by default; `--allow-model-differences` permits an intentional mixed design
and records the differences in the summary. Keep these groups separate in analysis.
Actual returned model versions remain in each row even when requested IDs match.

Use `--output PATH` for a separate output directory. Repeating a successful merge
replaces generated outputs; save Keilani's scored copies elsewhere. A failed merge
does not update response exports; any previous successful exports remain from the
previous run. Check the exit status and summary before sharing them.

## CSV contract and sentiment handoff

Each row contains a batch-prefixed `record_id`, source run ID, tester, batch,
question-set version, target clinic, topic, framing, exact prompt, provider,
requested/returned model, trial, UTC timestamps, collection/search modes, full
response text, citation URLs (a JSON array), and search count.

Clinic and topic are assigned by the question definition, not inferred from
mentions. `review_required` and `review_note` ask for target-clinic relevance and
passage review before scoring; a mention of the other study clinic gets a specific
flag. This flag is a text heuristic, not a clinic-identity or accuracy judgment.
Search is enabled but providers may choose not to search; `search_count` retains
the observed count. API outputs should be identified as API outputs in the dashboard.

The following columns are intentionally blank for Keilani:

```text
sentiment_score, sentiment_label, sentiment_method, sentiment_version
```

Full original text, including line breaks, Unicode, quotes, and leading characters,
is preserved in UTF-8 CSV. Import text columns as text when using spreadsheet apps.
No sentiment cutoffs, composite score, recommendation rank, or clinical accuracy
judgment is invented here. Review responses with no relevant clinic information
before deciding whether they are eligible for scoring.

## Offline verification

From `stream2/`:

```bash
python3 -m unittest discover -s track3/quarter1/tests -v
```

Tests use temporary directories, synthetic responses, and mocked adapters. They
cover the complete 720-row handoff, exact response preservation, 10 exports,
resume/deduplication, missing responses, settings changes, conflicts, damaged logs,
and provider parsing. They require no keys, Google access, or paid calls.

API request references: [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search),
[Claude web search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
[Gemini Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search).
Live access to the selected models must be checked using your own accounts.
