# Track 3: What AI assistants say about RPSD

Asks ChatGPT, Claude and Gemini (through their APIs, with web search on) the same 6 patient questions as the browser pilot. It then labels each answer for RPSD visibility and checks every RPSD claim against the clinic's fact sheet.

```
track3/
├── RPSD_Pilot.ipynb   the control panel: settings, then 9 short steps
├── rpsd_rules.py      study rules: questions, labeling + fact-check instructions, clinic names
├── rpsd_tools.py      the code (API calls, fact-sheet parsing, caching, normalization, export)
└── requirements.txt   pandas
data/track3/           results: raw answers, label cache, CSV exports (gitignored, never committed)
```

## Setup (once)
1. In the repo root, copy `.env.example` to `.env` and fill in the three `RPSD_*` lines (ask a teammate for the IDs).
2. Use any Python 3.10+ with pandas. The python.org installer on macOS needs its "Install Certificates" step first, or you'll get "Could not connect".
3. Open `track3/RPSD_Pilot.ipynb` and set `TESTER` in step 1.

## Money
`ALLOW_SPENDING = False` (the default) is free mode. Every step runs, and paid steps only report what they would send. Saved answers and labels are cached in `data/track3/` and never paid for twice. API keys are typed into a hidden prompt each session and are never saved.

## What to edit
| To change… | Edit |
|---|---|
| Questions | `QUESTIONS` in `rpsd_rules.py` |
| Labeling / fact-check instructions | `LABEL_SYSTEM` / `CHECK_SYSTEM`, then bump `RULES_VERSION` |
| Clinic name merging | `CANONICAL_CLINICS` |
| What counts as an explicit rank | `RANK_LANGUAGE` |
| Models, judge, tabs, how many answers | step 1 of the notebook |

## Method notes
- **API vs apps:** results are API results and may differ from the consumer apps. No user location is sent.
- **Models:** each provider's everyday free-tier default (ChatGPT `chat-latest`, Claude Sonnet, Gemini Flash). Exact model versions are recorded per answer.
- **Fact-checking:** claims are checked against the fact sheet only. "Not documented" means the claim can't be confirmed, not that it's false.
- **Judge:** one fixed judge model (`gpt-4.1`) labels every platform's answers. All auto-labels are drafts for human review.
- **Browser runs:** logged-out ChatGPT runs are still collected with the separate Playwright notebook and pasted into the tracker sheet. Step 7 labels them.
