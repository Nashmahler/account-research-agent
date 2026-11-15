"""Collect what a sales rep would research before reaching out: recent news, the company's own
pages, and what it's hiring for. Public sources only, no logins, no API keys.

Every item gets a number. The model may only cite items by number, and every quote it uses is
checked word for word against the item's text (see verify.py). A source that fails is skipped;
collect() never raises.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin

import requests

log = logging.getLogger(__name__)

TIMEOUT = 20
HEADERS = {"User-Agent": "account-research-agent/0.1 (+https://github.com/Nashmahler/account-research-agent)"}
NEWS_DAYS = 30
MAX_NEWS = 15
PAGE_CHARS = 2500
SITE_PATHS = ["", "/blog", "/news", "/newsroom", "/press", "/changelog", "/customers"]


@dataclass
class Item:
    kind: str          # news | page | hiring
    title: str
    url: str
    text: str          # exactly what the model sees; quotes must come from here
    date: str = ""     # YYYY-MM-DD when known


@dataclass
class Research:
    company: str
    items: list[Item] = field(default_factory=list)
    hiring: dict = field(default_factory=dict)   # computed in code, never by the model
    errors: list[str] = field(default_factory=list)


def clean(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# ---- news -----------------------------------------------------------------

NEWS_CONTEXT = "(startup OR software OR AI OR funding OR launches OR customers OR app)"


def parse_news_rss(xml_text: str, now: datetime, days: int = NEWS_DAYS, name: str | None = None) -> list[Item]:
    """name: keep only headlines that contain the company name with its exact capitalization,
    which drops most same-word noise ("a linear path", "the notion that...")."""
    name_rx = re.compile(rf"(?<![\w.-]){re.escape(name)}(?![\w-])") if name else None
    items = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        title = clean(it.findtext("title") or "")
        if name_rx and not name_rx.search(title):
            continue
        link = (it.findtext("link") or "").strip()
        source = clean(it.findtext("source") or "")
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            pub = None
        if pub and pub < now - timedelta(days=days):
            continue
        desc = clean(it.findtext("description") or "")
        text = title if not desc or desc.startswith(title[:40]) else f"{title}. {desc}"
        if source:
            text += f" (via {source})"
        items.append(Item("news", title, link, text, pub.date().isoformat() if pub else ""))
    items.sort(key=lambda i: i.date, reverse=True)
    return items[:MAX_NEWS]


def fetch_news(company: str, http, now: datetime, query: str | None = None) -> list[Item]:
    q = query or f'"{company}" {NEWS_CONTEXT}'
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}+when:{NEWS_DAYS}d&hl=en-US&gl=US&ceid=US:en"
    r = http.get(url, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    return parse_news_rss(r.text, now, name=None if query else company)


# ---- company site -----------------------------------------------------------

def fetch_pages(domain: str, http) -> list[Item]:
    base = domain if domain.startswith("http") else f"https://{domain}"
    items, seen = [], set()
    for path in SITE_PATHS:
        url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
        try:
            r = http.get(url, timeout=TIMEOUT, headers=HEADERS)
        except Exception as e:  # one bad page never stops the run
            log.info("skip %s: %s", url, e)
            continue
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
            continue
        title = clean((re.search(r"(?is)<title[^>]*>(.*?)</title>", r.text) or [None, path or "Home"])[1])
        text = clean(r.text)[:PAGE_CHARS]
        if len(text) < 200 or text[:300] in seen:  # empty shells and redirects back to the homepage
            continue
        seen.add(text[:300])
        items.append(Item("page", title or url, r.url or url, text))
    return items


# ---- hiring -----------------------------------------------------------------

BUCKETS = [  # first match wins; order matters
    ("Sales", r"\b(account executive|sales|sdr|bdr|business development|partnerships?)\b"),
    ("Revenue & GTM ops", r"\b(revops|revenue operations|sales operations|gtm|go-to-market|enablement)\b"),
    ("Customer", r"\b(customer success|support|implementation|onboarding|solutions|deployment|account manager)\b"),
    ("Marketing", r"\b(marketing|brand|content|growth|communications|pr)\b"),
    ("AI & data", r"\b(ai|ml|machine learning|data scien\w*|llm|research)\b"),
    ("Engineering", r"\b(engineer\w*|developer|sre|security|infrastructure|platform)\b"),
    ("Product & design", r"\b(product|design\w*|ux)\b"),
    ("Finance, legal & ops", r"\b(finance|accounting|legal|counsel|people|recruit\w*|operations|talent)\b"),
]
BOARD_URLS = {
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
}


def bucket(title: str) -> str:
    low = title.lower()
    for name, rx in BUCKETS:
        if re.search(rx, low):
            return name
    return "Other"


def _titles(board: str, payload) -> list[tuple[str, str]]:
    if board == "ashby":
        return [(j.get("title", ""), j.get("jobUrl", "")) for j in payload.get("jobs", [])]
    if board == "greenhouse":
        return [(j.get("title", ""), j.get("absolute_url", "")) for j in payload.get("jobs", [])]
    return [(j.get("text", ""), j.get("hostedUrl", "")) for j in payload] if isinstance(payload, list) else []


def slug_guesses(company: str) -> list[str]:
    low = company.lower().strip()
    out = [re.sub(r"[^a-z0-9]", "", low), re.sub(r"[^a-z0-9]+", "-", low).strip("-")]
    return list(dict.fromkeys(s for s in out if s))


def fetch_hiring(company: str, http, board: str | None = None) -> tuple[dict, list[Item]]:
    """Find the company's public job board (or use board='ashby:slug'), then count roles in code."""
    tries = [tuple(board.split(":", 1))] if board else [(b, s) for s in slug_guesses(company) for b in BOARD_URLS]
    for b, slug in tries:
        try:
            r = http.get(BOARD_URLS[b].format(slug=slug), timeout=TIMEOUT, headers=HEADERS)
            if r.status_code != 200:
                continue
            roles = [(t.strip(), u) for t, u in _titles(b, r.json()) if t.strip()]
        except Exception:
            continue
        if not roles:
            continue
        counts: dict[str, int] = {}
        for t, _ in roles:
            counts[bucket(t)] = counts.get(bucket(t), 0) + 1
        hiring = {"board": f"{b}:{slug}", "total": len(roles),
                  "by_team": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}
        # Go-to-market roles are the most useful outreach signal, so they become citable items.
        gtm = [(t, u) for t, u in roles if bucket(t) in ("Sales", "Revenue & GTM ops", "Customer", "Marketing")]
        items = [Item("hiring", t, u, f"Open role: {t}") for t, u in gtm[:12]]
        return hiring, items
    return {}, []


# ---- all together -------------------------------------------------------------

def collect(company: str, domain: str | None = None, board: str | None = None,
            http=None, now: datetime | None = None, news_query: str | None = None) -> Research:
    http = http or requests.Session()
    now = now or datetime.now(timezone.utc)
    res = Research(company)
    steps = [("news", lambda: fetch_news(company, http, now, news_query))]
    if domain:
        steps.append(("site", lambda: fetch_pages(domain, http)))
    for name, step in steps:
        try:
            res.items += step()
        except Exception as e:
            res.errors.append(f"{name}: {type(e).__name__}: {e}")
    try:
        res.hiring, hiring_items = fetch_hiring(company, http, board)
        res.items += hiring_items
    except Exception as e:
        res.errors.append(f"hiring: {type(e).__name__}: {e}")
    return res
