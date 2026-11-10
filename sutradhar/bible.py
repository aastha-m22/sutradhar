"""Merge per-chapter extractions into a story bible and find inconsistency candidates."""

from __future__ import annotations

import re


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def build_bible(extractions: list[dict | None], chapters: list[dict]) -> dict:
    chars: dict[str, dict] = {}
    alias_index: dict[str, str] = {}
    events: list[dict] = []

    for ch, ext in zip(chapters, extractions):
        idx = ch["index"]
        ext = ext or {}
        for c in ext.get("characters") or []:
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            aliases = [str(a).strip() for a in (c.get("aliases") or []) if str(a).strip()]
            names = {norm(name)} | {norm(a) for a in aliases}
            canon = next((alias_index[n] for n in names if n in alias_index), None)
            if canon is None:
                canon = name
                chars[canon] = {"name": name, "aliases": [], "facts": [], "appearances": [], "deaths": []}
            rec = chars[canon]
            for n in names:
                alias_index.setdefault(n, canon)
            for a in [name] + aliases:
                if a != canon and a not in rec["aliases"]:
                    rec["aliases"].append(a)
            if c.get("present", True) and idx not in rec["appearances"]:
                rec["appearances"].append(idx)
            for f in c.get("facts") or []:
                attr, val = norm(f.get("attr")), str(f.get("value") or "").strip()
                if attr and val:
                    rec["facts"].append(
                        {"attr": attr, "value": val, "quote": str(f.get("quote") or ""), "chapter": idx}
                    )
            if norm(c.get("status")) == "dead":
                rec["deaths"].append({"chapter": idx, "quote": str(c.get("status_quote") or "")})
        for e in ext.get("events") or []:
            events.append(
                {
                    "chapter": idx,
                    "summary": str(e.get("summary") or ""),
                    "characters": [str(x) for x in (e.get("characters") or [])],
                    "location": str(e.get("location") or ""),
                    "time": str(e.get("time") or ""),
                }
            )
    return {"characters": chars, "events": events}


def find_candidates(bible: dict) -> list[dict]:
    out: list[dict] = []
    for name, rec in bible["characters"].items():
        by_attr: dict[str, list[dict]] = {}
        for f in rec["facts"]:
            if f["attr"].startswith("other:"):
                continue
            by_attr.setdefault(f["attr"], []).append(f)
        for attr, facts in by_attr.items():
            distinct: dict[str, dict] = {}
            for f in facts:
                distinct.setdefault(norm(f["value"]), f)
            if len(distinct) > 1:
                out.append(
                    {
                        "type": "attribute",
                        "character": name,
                        "attr": attr,
                        "evidence": [
                            {"chapter": f["chapter"], "value": f["value"], "quote": f["quote"]}
                            for f in distinct.values()
                        ],
                    }
                )
        if rec["deaths"]:
            death = min(rec["deaths"], key=lambda d: d["chapter"])
            later = sorted(c for c in rec["appearances"] if c > death["chapter"])
            if later:
                out.append(
                    {
                        "type": "posthumous",
                        "character": name,
                        "death": death,
                        "later_chapters": later,
                        "evidence": [{"chapter": death["chapter"], "quote": death["quote"], "value": "dies"}],
                    }
                )
    return out
