# Quarter 1: Topic-based AI responses

This workflow is separate from the **Quarter 2 pilot test** in the sibling `pilot/`
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

The shared `models.json` records the models selected for the current study.
If creating a configuration from the example, replace each placeholder with a
search-capable API model ID your account can access. Use exactly the same file for every collector. Remove a
provider entry if the team agrees not to collect it. Model IDs are explicit
rather than inherited from the pilot. Placeholder values are rejected.

Copy the Quarter 1 credential template:

```bash
cp -n track3/quarter1/.env.example track3/quarter1/.env
```

Put keys in `track3/quarter1/.env`, or set environment variables:

```text
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

If your keys were previously in `track3/.env`, copy them to the new file or pass
`--env-file track3/.env`. No tracker sheet or fact-sheet access is needed.
This workflow collects responses;
it does not call a sentiment judge or the pilot fact-checker.

## 2. Plan each independent batch (free, offline)

Collector 1:

```bash
python3 track3/quarter1/collect.py --batch collector1-q1-01 --tester Collector1
```

Collector 2, on a separate computer:

```bash
python3 track3/quarter1/collect.py --batch collector2-q1-01 --tester Collector2
```

These commands create each batch's frozen `manifest.json` and print how many
collection slots remain. They do not contact any API. With three providers and
three trials (the default), each batch has 360 collection slots.

## 3. Collect responses

Collector 1:

```bash
python3 track3/quarter1/collect.py --batch collector1-q1-01 --tester Collector1 --spend
```

Collector 2:

```bash
python3 track3/quarter1/collect.py --batch collector2-q1-01 --tester Collector2 --spend
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

The `--tester` value is a collector identifier; use a stable pseudonym such as
`Collector1`, not a personal name. Add more collectors with unique batch IDs and
include their folders in the same merge command.

The batch manifest freezes the tester, providers/models, trial count, and exact
questions. Changing any of them requires a new batch ID. Use a new ID for an
independent new round, even if the settings are identical. A transport interruption
can leave an upstream request billed without a local success; resuming retries
that slot. A malformed/truncated log is rejected rather than silently discarded.

### Collect one topic at a time

Add `--topics general` to collect only General now:

```bash
python3 track3/quarter1/collect.py --batch collector1-q1-01 --tester Collector1 --topics general --spend
```

With three providers and three trials, this collects 72 responses. The manifest
still freezes all five topics; rerunning without `--topics` later collects the
remaining topics and skips saved answers. You can also choose multiple topics,
for example `--topics billing communication`. The combined handoff remains
incomplete until all planned topics are collected. Topic selection does not
change batch identity or the question-set version. Add `--workers 3` to run up to
three requests concurrently; the default is one. Successful captures are saved
individually under a write lock. Use one collection process per batch, even when
using multiple workers. Total planned response counts are unchanged.

### Defer a provider while its credits are unavailable

Keep all agreed providers in `models.json`. Use a runtime filter instead of
changing the frozen batch design:

```bash
python3 track3/quarter1/collect.py --batch collector1-q1-01 --tester Collector1 --topics safety communication --providers Claude Gemini --spend --workers 3
```

With three trials this collects 96 responses across both clinics and topics.
Only selected providers need keys. OpenAI slots stay pending. After credits are
restored, fill the missing slots with `--providers OpenAI`, or omit the provider
filter to collect all remaining slots. The merger continues to count uncollected
providers as missing; partial handoffs must be labeled incomplete.

## 4. Share the complete batch folders privately

Default location on local `main`:

```text
stream2/data/track3/quarter1/batches/
  collector1-q1-01/
    manifest.json       frozen design and provenance
    attempts.jsonl      original provider payloads, full answers, failures
    responses.csv       successful responses; regenerated from captures
  collector2-q1-01/
    manifest.json
    attempts.jsonl
    responses.csv
```

Each collector shares the complete batch folder with the person doing the merge.
Place the collected batch folders under the same `batches/` directory. No API keys or `.env`
files need to be shared. All real outputs live under gitignored `data/`.
`--data-dir PATH` can select a different private data location for collection.

The merger requires the manifest and attempt log alongside the CSV so it can
check the collection design and rebuild trustworthy rows. It does not treat an
edited `responses.csv` as a new original capture. It never needs API keys.

## 5. Combine and export the 10 CSVs

From `stream2/`:

```bash
python3 track3/quarter1/combine_batches.py --batches data/track3/quarter1/batches/collector1-q1-01 data/track3/quarter1/batches/collector2-q1-01
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

Share the **10 CSVs in `exports/`** with the sentiment analysis team, plus `handoff_summary.json` for counts
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
replaces generated outputs; save scored copies elsewhere. A failed merge
does not update response exports; any previous successful exports remain from the
previous run. Check the exit status and summary before sharing them.

### Combine only groups complete in every batch

While waiting for missing providers, export just the clinic/topic groups with
all planned questions, framings, providers, and trials present in every batch:

```bash
python3 track3/quarter1/combine_batches.py --batches data/track3/quarter1/batches/collector1-q1-01 data/track3/quarter1/batches/collector2-q1-01 --complete-only --output data/track3/quarter1/combined_complete
```

This creates only the complete groups' CSVs and a master table containing those
same rows. `group_coverage.csv` explains which groups were included or excluded.
`selected_scope_complete` in the summary describes the exported subset;
`complete` continues to describe the entire planned study. Source batches and
incomplete responses are preserved. Do not combine this flag with `--allow-partial`.

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

The following columns are intentionally blank for the sentiment analysis team:

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
