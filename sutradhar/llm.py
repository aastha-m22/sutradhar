"""Minimal OpenAI-compatible client for the BharatCode model API (stdlib only)."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://bharatcode.ai/api/model/v1"
DEFAULT_MODEL = "qwen-3.8-27b"


class LLMError(Exception):
    pass


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (handles <think> and code fences)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?", "", text)
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    raise LLMError("Model did not return valid JSON")


class BharatCodeLLM:
    name = "bharatcode"

    def __init__(self, api_key=None, base_url=None, model=None, timeout=180):
        self.api_key = api_key or os.environ.get("BHARATCODE_API_KEY")
        self.base_url = (base_url or os.environ.get("BHARATCODE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("BHARATCODE_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        if not self.api_key:
            raise LLMError("BHARATCODE_API_KEY is not set. Get a key at https://bharatcode.ai")

    def chat(self, system: str, user: str, max_tokens: int = 3000) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        last = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                last = LLMError(f"HTTP {e.code}: {detail}")
                if e.code not in (429, 500, 502, 503, 504):
                    raise last
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last = LLMError(f"Request failed: {e}")
            time.sleep(1.5 * (attempt + 1))
        raise last or LLMError("Request failed")

    def json(self, system: str, user: str, max_tokens: int = 3000) -> dict:
        reply = self.chat(system, user, max_tokens)
        try:
            return extract_json(reply)
        except LLMError:
            reply = self.chat(system + "\nReturn ONLY one valid JSON object, nothing else.", user, max_tokens)
            return extract_json(reply)
