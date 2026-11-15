"""The trust layer. The model proposes; this code decides what a rep is allowed to see.

A signal or opener survives only if it cites a real source number AND quotes that source's text
word for word (ignoring case, curly quotes and spacing). Anything else is dropped and counted.
If nothing survives, there is no brief: better to say "no verified signals" than to hand a rep
something made up about their prospect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_QUOTE_CHARS = 12
MAX_SIGNALS = 5
MAX_OPENERS = 3
OPENER_MAX_CHARS = 320


def norm(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip(" .\"'")


NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|k\b|m\b|b\b|bn\b|million|billion|trillion|x\b))?", re.I)
UNITS = {"million": "m", "billion": "b", "bn": "b", "trillion": "t"}


def numbers(text: str) -> set[str]:
    """Every figure in a piece of text, normalized: "$40 million" -> "40m", "62%" -> "62%"."""
    out = set()
    for m in NUM.finditer(text or ""):
        tok = m.group(0).lower().replace("$", "").replace(",", "").replace(" ", "")
        for word, short in UNITS.items():
            tok = tok.replace(word, short)
        if re.fullmatch(r"(19|20)\d\d", tok):  # years are context, not claims
            continue
        out.add(tok)
    return out


def unbacked_numbers(text: str, items, ids, extra: set[str] = frozenset()) -> set[str]:
    """Figures in `text` that appear in none of the cited sources (or the code-computed hiring counts)."""
    pool = set(extra)
    for i in ids:
        pool |= numbers(items[i - 1].text)
    return {n for n in numbers(text) if n not in pool and n.rstrip("%kmbtx") not in pool}


@dataclass
class Checked:
    signals: list[dict] = field(default_factory=list)
    openers: list[dict] = field(default_factory=list)
    summary: str = ""
    dropped: list[str] = field(default_factory=list)   # why each rejected claim was rejected

    @property
    def ok(self) -> bool:
        return bool(self.signals)


def _quote_ok(item_ids, quote: str, items) -> tuple[bool, str]:
    if not isinstance(item_ids, list) or not item_ids:
        return False, "no source cited"
    if not all(isinstance(i, int) and 1 <= i <= len(items) for i in item_ids):
        return False, f"cites a source that doesn't exist ({item_ids})"
    q = norm(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return False, "quote too short to check"
    if not any(q in norm(items[i - 1].text) for i in item_ids):
        return False, f"quote not found in cited source {item_ids}: \"{quote[:80]}\""
    return True, ""


def check(reply: dict, items, hiring: dict | None = None) -> Checked:
    """hiring: the code-computed counts, so figures like "165 open roles" can be checked too."""
    out = Checked()
    if not isinstance(reply, dict):
        out.dropped.append("reply was not a JSON object")
        return out
    extra = set()
    if hiring:
        extra = {str(hiring.get("total", ""))} | {str(v) for v in hiring.get("by_team", {}).values()}
    summary = str(reply.get("summary", "")).strip()[:300]
    bad = unbacked_numbers(summary, items, range(1, len(items) + 1), extra)
    if bad:
        out.dropped.append(f"summary: figure(s) not in any source: {sorted(bad)}")
    else:
        out.summary = summary
    for s in reply.get("signals", []) or []:
        if not isinstance(s, dict):
            continue
        ok, why = _quote_ok(s.get("sources"), str(s.get("quote", "")), items)
        if ok:
            bad = unbacked_numbers(f"{s.get('headline', '')} {s.get('why_it_matters', '')}", items, s["sources"], extra)
            if bad:
                ok, why = False, f"figure(s) not in the cited sources: {sorted(bad)}"
        if ok and len(out.signals) < MAX_SIGNALS:
            out.signals.append({k: s.get(k) for k in ("headline", "why_it_matters", "sources", "quote")})
        elif not ok:
            out.dropped.append(f"signal \"{str(s.get('headline', ''))[:60]}\": {why}")
    verified_sources = {i for s in out.signals for i in s["sources"]}
    for o in reply.get("openers", []) or []:
        if not isinstance(o, dict):
            continue
        text = str(o.get("text", "")).strip()
        ok, why = _quote_ok(o.get("sources"), str(o.get("quote", "")), items)
        if ok:
            bad = unbacked_numbers(text, items, o["sources"], extra)
            if bad:
                ok, why = False, f"figure(s) not in the cited sources: {sorted(bad)}"
        if ok and not set(o["sources"]) & verified_sources:
            ok, why = False, "opener isn't backed by a verified signal"
        if ok and len(text) > OPENER_MAX_CHARS:
            ok, why = False, "opener too long for a first message"
        if ok and len(out.openers) < MAX_OPENERS:
            out.openers.append({"text": text, "sources": o["sources"], "quote": o.get("quote")})
        elif not ok:
            out.dropped.append(f"opener: {why}")
    return out
