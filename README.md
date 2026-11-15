# Account Research Agent

Type in a company name. Get back what changed there recently, why it matters for outreach, and two or three first lines a sales rep could actually send. Every claim links to its source and quotes it word for word, or it doesn't make it into the brief.

I built this because the first hour of a sales development rep's day is research: which accounts matter, what happened at them this week, and what's worth saying. That's the part an agent can do well, as long as the rep can trust it. A made-up fact in a cold email is worse than no email.

## What it reads

| Source | What it adds |
| --- | --- |
| Google News (last 30 days) | Funding, launches, leadership changes, incidents |
| The company's own site (home, blog, newsroom, changelog, customers) | What they're shipping and how they describe themselves |
| Their public job board (Ashby, Greenhouse, or Lever) | Where they're investing. Hiring counts by team are computed in code, not by the model |

All public. No logins, no scraping behind paywalls, no paid data APIs.

## How it stays honest

1. **Sources are numbered.** The model gets the text it's allowed to use and nothing else.
2. **One Claude call per account** (hard cap of 2 in code, for one retry). A brief costs pennies.
3. **Everything is checked in code.** Each signal and opener must cite real source numbers and include a quote that appears in that source, word for word. Wrong number, wrong source, or a quote that isn't there: dropped, and the brief says what was dropped and why.
4. **Openers must rest on a verified signal.** No "saw you're crushing it" lines with nothing behind them.
5. **It fails closed.** If nothing verifies, the brief says "No verified brief today" instead of guessing.
6. **Source text is treated as untrusted.** An instruction hidden in a web page can't add a claim, because the claim still has to quote a real source.

The tests include deliberately fabricated quotes, made-up source numbers, a right quote cited to the wrong source, and a prompt-injection page. All have to be caught.

## Run it

**From GitHub (no setup):** Actions → *Research an account* → *Run workflow*. Enter a company and, ideally, its website. The brief appears in the run summary and is saved to [`briefs/`](briefs).

**Locally:**

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or put it in .env
python research.py "Notion" --domain notion.com
python research.py "Linear" --domain linear.app --news-query '"Linear" ("linear.app" OR "issue tracking")'
python research.py "Acme" --pitch "We sell spend management to finance teams."
```

`--pitch` tells it what you sell, which shapes "why it matters" and the openers. `--news-query` helps with company names that are also everyday words.

## What's in a brief

- One-line summary of the company right now
- **What changed:** up to 5 signals, each with why it matters, a source link, and the quote it rests on
- **Openers:** 2–3 first lines, each tied to a verified signal
- **Hiring:** open roles by team, counted in code
- **Checks:** how many claims were verified, how many were dropped, and why

## Tests

```bash
python -m pytest -q
```

17 tests, no network and no API key needed.

## How it was built

Built in a day with Claude Code, in Python. It reuses the approach from my [market intelligence agent](https://github.com/Nashmahler/ai-infra-intel-brief): source-quoted claims, fail-closed output, and hard caps on model calls. More builds at [nashmahler.github.io/builds](https://nashmahler.github.io/builds).
