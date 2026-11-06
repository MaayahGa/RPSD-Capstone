"""
Collect Reddit posts and comments that mention RPSD or a competitor and save
them as reputation_items. Requires an approved Reddit API app (see README).

What it does:
  1. Searches fertility subreddits for each clinic's aliases (from clinics.json)
  2. Saves each matching post (title + body)
  3. Opens those posts and saves any comment that names a clinic, which is
     where most "which San Diego clinic?" recommendations live
Usernames are never read into the saved records.

Run:
    python reddit/reddit_collector.py       # saves to data/reputation.db
    python reputation_item.py export
"""

# Let this script (in a source subfolder) import shared code from the repo root.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
import json
import os
import re
from datetime import datetime, timezone

from reputation_item import DB_PATH, make_item, save_items

SUBREDDITS = "IVF+infertility+sandiego+TryingForABaby+eggfreezing"
RESULTS_PER_QUERY = 50
CLINICS_FILE = ROOT / "clinics.json"


def alias_patterns(clinics):
    """Whole-word, case-insensitive pattern for each clinic's aliases."""
    patterns = {}
    for clinic in clinics:
        names = clinic.get("aliases") or [clinic["name"]]
        joined = "|".join(re.escape(n) for n in names)
        patterns[clinic["name"]] = re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)
    return patterns


def clinics_mentioned(text, patterns):
    return [name for name, pat in patterns.items() if pat.search(text or "")]


def to_date(created_utc):
    return datetime.fromtimestamp(created_utc, tz=timezone.utc).date().isoformat()


def post_items(post, patterns):
    text = f"{post.title}\n{post.selftext or ''}"
    return [make_item(
        source="reddit", clinic=clinic, text=post.selftext or "", title=post.title,
        posted_at=to_date(post.created_utc),
        url=f"https://www.reddit.com{post.permalink}",
        native_id=f"{post.id}_{i}" if i else post.id,  # one item per clinic named
        engagement=post.score, collection_method="reddit_api",
    ) for i, clinic in enumerate(clinics_mentioned(text, patterns))]


def comment_items(comment, patterns):
    return [make_item(
        source="reddit", clinic=clinic, text=comment.body,
        posted_at=to_date(comment.created_utc),
        url=f"https://www.reddit.com{comment.permalink}",
        native_id=f"{comment.id}_{i}" if i else comment.id,
        engagement=comment.score, collection_method="reddit_api",
    ) for i, clinic in enumerate(clinics_mentioned(comment.body, patterns))]


def collect(reddit, clinics):
    patterns = alias_patterns(clinics)
    sub = reddit.subreddit(SUBREDDITS)
    seen_posts, items = set(), []
    for clinic in clinics:
        for alias in clinic.get("aliases") or [clinic["name"]]:
            for post in sub.search(f'"{alias}"', sort="new", time_filter="all",
                                   limit=RESULTS_PER_QUERY):
                if post.id in seen_posts:
                    continue
                seen_posts.add(post.id)
                items += post_items(post, patterns)
                post.comments.replace_more(limit=0)
                for comment in post.comments.list():
                    items += comment_items(comment, patterns)
    return items, len(seen_posts)


def main():
    import praw
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT"),
    )
    reddit.read_only = True
    clinics = json.loads(CLINICS_FILE.read_text())
    items, n_posts = collect(reddit, clinics)
    added, skipped = save_items(items, args.db)
    print(f"Checked {n_posts} posts. Added {added} new items, skipped {skipped}.")


if __name__ == "__main__":
    main()
