"""Split a manuscript into chapters."""

from __future__ import annotations

import re

HEADING = re.compile(
    r"^(?:#{1,3}\s+.+|(?:chapter|part|prologue|epilogue)\b.*|\*\*(?:chapter|part)\b.+\*\*)$",
    re.I | re.M,
)


def _words(s: str) -> int:
    return len(s.split())


def _chunk(text: str, max_words: int) -> list[str]:
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, n = [], [], 0
    for p in paras:
        w = _words(p)
        if cur and n + w > max_words:
            chunks.append("\n\n".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def split_chapters(text: str, max_words: int = 3000) -> list[dict]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    raw: list[tuple[str, str]] = []
    matches = list(HEADING.finditer(text))
    if matches:
        pre = text[: matches[0].start()].strip()
        if _words(pre) > 50:
            raw.append(("Prologue", pre))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            title = m.group(0).strip().lstrip("#").strip().strip("*").strip()
            body = text[m.end() : end].strip()
            if body:
                raw.append((title, body))
    else:
        for i, c in enumerate(_chunk(text, max_words), 1):
            raw.append((f"Section {i}", c))

    out: list[dict] = []
    for title, body in raw:
        parts = _chunk(body, max_words * 2) if _words(body) > max_words * 2 else [body]
        for k, part in enumerate(parts, 1):
            t = title if len(parts) == 1 else f"{title} (part {k})"
            out.append({"index": len(out) + 1, "title": t, "text": part, "words": _words(part)})
    return out
