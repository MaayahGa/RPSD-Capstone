# Track 3: AI responses

Track 3 has two independent workflows:

| Folder | Purpose | Instructions |
| --- | --- | --- |
| `quarter1/` | Current Quarter 1 deliverable: topic-based RPSD/SDFC response collection, independent Siya/Audrey batches, and 10 CSVs for Keilani | [Quarter 1 guide](quarter1/README.md) |
| `pilot/` | Retained Quarter 2 pilot test: original six-question collection, visibility labels, fact checks, and exploratory notebooks | [Pilot guide](pilot/README.md) |

Run terminal commands from `RPSD-Capstone/stream2/`.

```text
track3/
  README.md
  quarter1/
    collect.py
    combine_batches.py
    questions.csv
    tests/
  pilot/
    run.py
    prepare_eda.py
    rpsd_rules.py
    rpsd_tools.py
    notebooks/
    tests/
```

Private Quarter 1 data stays in `stream2/data/track3/quarter1/`. Existing pilot
data stays at its original `stream2/data/track3/` paths so saved batches remain
usable. Both are gitignored. Each workflow has its own `.env.example` template;
keep credentials in its local `.env` or environment variables.
