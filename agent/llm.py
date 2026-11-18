"""One Claude call per account. The call cap is enforced here, before the API is touched."""
from __future__ import annotations

import json
import os
import re

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-5-5")
MAX_CALLS = 2  # one call per account, plus one retry if the reply isn't valid JSON


class CapReached(Exception):
    pass


class Claude:
    def __init__(self, model: str = MODEL, max_calls: int = MAX_CALLS):
        self.model, self.max_calls, self.calls = model, max_calls, 0
        self._client = None

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        if self.calls >= self.max_calls:
            raise CapReached(f"Claude call cap ({self.max_calls}) reached")
        self.calls += 1
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            import anthropic
            self._client = anthropic.Anthropic()
        msg = self._client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def extract_json(text: str, want: type | None = None):
    """First JSON value in a model reply. With `want`, skip values of the other type,
    so a source number like "[3]" mentioned before the answer isn't taken as the answer."""
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    starts = "{" if want is dict else "[" if want is list else "{["
    for i, ch in enumerate(text):
        if ch in starts:
            try:
                val = dec.raw_decode(text[i:])[0]
            except json.JSONDecodeError:
                continue
            if want is None or isinstance(val, want):
                return val
    raise ValueError("no JSON found in model reply")
