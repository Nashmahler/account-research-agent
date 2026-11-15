"""Research one account and write a verified brief.

    python research.py "Ramp" --domain ramp.com
    python research.py "Notion" --domain notion.com --pitch "We sell payments infrastructure to software companies."
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

from agent import brief, sources
from agent.llm import Claude

DEFAULT_PITCH = "Financial infrastructure for internet businesses: payments, billing, and revenue tools."


def main(argv=None, llm=None, http=None) -> int:
    ap = argparse.ArgumentParser(description="Research an account and draft verified outreach openers.")
    ap.add_argument("company")
    ap.add_argument("--domain", help="company website, e.g. notion.com (adds the company's own pages)")
    ap.add_argument("--board", help="job board override, e.g. ashby:notion or greenhouse:stripe")
    ap.add_argument("--news-query", help="custom news search for names that are common words, "
                    "e.g. '\"Linear\" (\"linear.app\" OR \"issue tracking\")'")
    ap.add_argument("--pitch", default=os.environ.get("RESEARCH_PITCH", DEFAULT_PITCH),
                    help="what you sell, in one sentence (shapes 'why it matters' and the openers)")
    ap.add_argument("--out", default="briefs")
    args = ap.parse_args(argv)

    research = sources.collect(args.company, args.domain or None, args.board or None, http=http,
                               news_query=args.news_query or None)
    print(f"read {len(research.items)} sources; hiring: {research.hiring.get('total', 'n/a')} roles")
    checked, error = brief.run(research, llm or Claude(), args.pitch)
    text = brief.render(research, checked, error, date.today())

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.company.lower()).strip("-")
    path = out / f"{date.today().isoformat()}-{slug}.md"
    path.write_text(text)
    print(f"wrote {path}")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(text)
    return 0 if checked.ok else 1


if __name__ == "__main__":
    sys.exit(main())
