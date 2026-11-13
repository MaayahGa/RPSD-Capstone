# Stream 1 – Track 2: Review Sentiment and Severity Scoring

DSC 180A capstone project with Reproductive Partners Fertility Center – San Diego (RPSD).
Track 2 uses data collected from Tracks 1 to perform sentiment analysis and provide overall sentiment scores as well and model confidence scores.

## What's here
``sentiment.py`` reads a CSV, scores one text column with a pretrained RoBERTa sentiment model, and writes a new CSV with the sentiment columns added.

Default model: cardiffnlp/twitter-roberta-base-sentiment-latest (negative / neutral / positive)
Input: any CSV with a column of text
Output: the original CSV plus five sentiment columns

## Setup
Run terminal commands from **`stream2/track2/`**

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

## Data

The script defaults to using `data/reputation_items_all_sources.csv`, which is a file obtained from Track 1 and is not included in this repo for confidentiality reasons. The CSV file requires one column containing review text to score.

## Files

| File | Purpose |
|---|---|
| `sentiment.py` | Sentiment scoring script |
| `requirements.txt` | Pinned library versions |
| `README.md` | This file |

Rows where the text column is empty or missing are kept in the output but get blank (NaN) sentiment values.

## Usage

Basic run:

```bash
python sentiment.py --input data/reputation_items_all_sources.csv --text-col text --output data/reputation_items_scored.csv
```

> **Check your text column.** `--text-col` defaults to `text`. If your review text lives in a different column, pass its name. If the chosen column has no text, the script stops and lists every column with its non-null count so you can pick the right one.

Print EDA (shape, describe, missing values, dtypes, value counts):

```bash
python sentiment.py --text-col title --eda
```

Use a GPU:

```bash
python sentiment.py --text-col title --device 0
```

See all options:

```bash
python sentiment.py --help
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--input` | `data/reputation_items_all_sources.csv` | Path to the input CSV |
| `--output` | `data/reputation_items_scored.csv` | Path for the scored CSV |
| `--text-col` | `title` | Column containing the text to score |
| `--model` | `cardiffnlp/twitter-roberta-base-sentiment-latest` | Hugging Face model name. Must output `negative`, `neutral`, `positive` labels |
| `--batch-size` | `32` | Texts scored per batch. Lower this if you run out of memory |
| `--max-length` | `512` | Max tokens per text. Longer texts are truncated |
| `--device` | `-1` | `-1` for CPU, `0` for the first GPU |
| `--eda` | off | Print the EDA summary before scoring |

## Output

The script saves all original columns plus:

| Column | Meaning |
|---|---|
| `prob_negative` | Model probability the text is negative (0 to 1) |
| `prob_neutral` | Model probability the text is neutral (0 to 1) |
| `prob_positive` | Model probability the text is positive (0 to 1) |
| `sentiment_label` | Class with the highest probability: `negative`, `neutral`, or `positive` |
| `sentiment_score` | `prob_positive - prob_negative`, a single score from -1 (very negative) to +1 (very positive) |

The three probabilities sum to 1 for each row.

## Reproducing results

Inference with a fixed model is deterministic (there is no training or random sampling), so the same inputs should give the same scores as long as the environment matches. To get matching results:

1. **Use the same data file.** Any change to the rows or the text column changes the output.
2. **Use the same text column** and the same `--max-length` (it controls truncation).
3. **Use the same model.** Keep the default unless you intentionally change it. The model is downloaded from Hugging Face, so if its authors publish an update, a fresh download could differ slightly.
4. **Match library versions.** Install from the included `requirements.txt` (`pip install -r requirements.txt`) rather than installing the latest versions. Newer releases of `transformers` or `torch` can change behavior or numeric output.
5. **Use the same Python version** (3.12) where possible.
6. **Expect tiny numeric differences across hardware.** CPU and GPU runs, or different `torch` builds, can differ in the far decimal places of the probabilities. Labels should almost always be identical.

## Troubleshooting

- **`No non-empty text found in column '...'`**: the column you chose is empty. Re-run with `--text-col` set to a column from the list the script prints.
- **`Column '...' not found`**: check the spelling against the column list in the error message.
- **Out of memory:** lower `--batch-size` (for example `8`) or `--max-length`.
- **Slow on CPU:** expected for large datasets. Use `--device 0` if you have a CUDA GPU.

## Limitations

The default RoBERTa model was fine-tuned on tweets. It generally works well on short, informal text such as reviews, which is why we use it here. However, sentiment scores for very long, formal, or domain-specific text (e.g clinical language) should be spot-checked against a sample you have labeled by hand.
