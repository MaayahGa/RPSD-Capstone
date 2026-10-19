"""
Test for Reddit API (via PRAW) for Track 1.

Searches fertility subreddits for posts mentioning RPSD and the
high-priority competitors, and prints what comes back.
Usernames are never printed or saved.

Setup:
  1. Create a "script" app at https://www.reddit.com/prefs/apps
  2. Put these in a .env file next to this script:
       REDDIT_CLIENT_ID=...
       REDDIT_CLIENT_SECRET=...
       REDDIT_USER_AGENT=rpsd-capstone-test by u/your_username
  3. pip install -r requirements.txt
  4. python reddit_test.py
"""

import os
from datetime import datetime, timezone

import praw
from dotenv import load_dotenv

load_dotenv()

SUBREDDITS = "IVF+infertility+sandiego"

# Quoted phrases so Reddit matches the full name, not each word separately
QUERIES = [
    '"Reproductive Partners"',
    '"RMA San Diego"',
    '"San Diego Fertility Center"',
    '"Shady Grove" "Solana Beach"',
]

RESULTS_PER_QUERY = 10


def main():
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT"),
    )
    reddit.read_only = True

    for query in QUERIES:
        print("=" * 70)
        print(f"Search: {query} in r/{SUBREDDITS}")
        count = 0
        for post in reddit.subreddit(SUBREDDITS).search(
            query, sort="new", time_filter="all", limit=RESULTS_PER_QUERY
        ):
            count += 1
            date = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).date()
            body = (post.selftext or "").replace("\n", " ")
            print(f"  [{count}] r/{post.subreddit.display_name} | {date} | "
                  f"{post.num_comments} comments")
            print(f"      Title: {post.title[:120]}")
            if body:
                print(f"      Text:  {body[:150]}")
            print(f"      Link:  https://www.reddit.com{post.permalink}")
        if count == 0:
            print("  No posts found.")


if __name__ == "__main__":
    main()
