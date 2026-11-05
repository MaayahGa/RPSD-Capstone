#!/usr/bin/env python
"""computes RoBERTa sentiment scores for a text column in a CSV dataset

if you decide to run in a terminal:
    python sentiment.py --input data/reputation_items_all_sources.csv \
        --text-col title --output data/reputation_items_scored.csv

setup:
    pip install -U pandas numpy transformers torch
"""
# import libraries
import argparse
import pandas as pd
from transformers import pipeline

DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

def run_eda(df: pd.DataFrame) -> None:
    '''
    simple EDA of dataset, prints outputs to console
    '''
    print("Shape:", df.shape)
    print(df.head(), "\n")
    print(df.describe(), "\n")
    print(df.isna().sum(), "\n") # title and engagement are the only columns with missing values but will populate w reddit data (probably)
    print(df.dtypes, "\n")
    for cols in (["engagement"], ["title"], ["source", "clinic", "collection_method"]):
        if all(c in df.columns for c in cols):
            print(df[cols].value_counts(), "\n")


def score_sentiment(texts, model_name, batch_size, max_length, device):
    '''
    returns dataframe of labelled sentiments + confidence scores for each review
    '''
    clf = pipeline(
        "text-classification",
        model = model_name,
        top_k = None,  # returns probabilities for every label
        truncation = True,
        max_length = max_length,
        device = device,
    )

    results = clf(texts, batch_size = batch_size)

    rows = []
    for res in results:
        probs = {r["label"].lower(): r["score"] for r in res}
        rows.append(probs)
    out = pd.DataFrame(rows)

    # label of highest-probability class
    out["sentiment_label"] = out[["negative", "neutral", "positive"]].idxmax(axis=1)
    
    # sentiment score from [-1, 1]: P(positive) - P(negative)
    out["sentiment_score"] = out["positive"] - out["negative"]
    return out.rename(
        columns = {
            "negative": "prob_negative",
            "neutral": "prob_neutral",
            "positive": "prob_positive",
        }
    )


def main():
    # setup command line arguments if you prefer terminal
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/reputation_items_all_sources.csv", help="Input CSV path")
    p.add_argument("--output", default="data/reputation_items_scored.csv", help="Output CSV path")
    p.add_argument("--text-col", default="text", help="Column containing the text to score")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model name")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--max-length", type=int, default=512, help="Max tokens per text (longer text is truncated)")
    p.add_argument("--device", type=int, default=-1, help="-1 for CPU, 0 for first GPU")
    p.add_argument("--eda", action="store_true", help="Print the notebook's EDA summary before scoring")
    args = p.parse_args()

    df = pd.read_csv(args.input)
    if args.text_col not in df.columns:
        raise SystemExit(f"Column '{args.text_col}' not found. Available columns: {list(df.columns)}")

    if args.eda:
        run_eda(df)

    # only score rows with text, the rest get NaN scores
    text = df[args.text_col].astype("string").str.strip()
    mask = text.notna() & (text != "")
    if mask.sum() == 0:
        non_null = df.notna().sum().sort_values(ascending=False)
        raise SystemExit(
            f"No non-empty text found in column '{args.text_col}'.\n"
            f"Non-null counts per column (pick the one with your review text):\n{non_null}\n"
            f"Then re-run with --text-col <column>."
        )
    print(f"Scoring {mask.sum()} of {len(df)} rows from '{args.text_col}'...")

    scores = score_sentiment(
        text[mask].tolist(), args.model, args.batch_size, args.max_length, args.device
    )
    scores.index = df.index[mask]

    df = df.join(scores)
    df.to_csv(args.output, index=False)
    print(f"Saved to {args.output}")
    print(df["sentiment_label"].value_counts(dropna=False))

if __name__ == "__main__":
    main()