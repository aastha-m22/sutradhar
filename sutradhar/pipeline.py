"""The analysis pipeline: extract -> merge -> flag -> verify -> deep scan."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import prompts
from .bible import build_bible, find_candidates, norm
from .chapters import split_chapters

SEV = {"high": 0, "medium": 1, "low": 2}


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def quote_in_chapter(quote: str, chapters: list[dict], chapter: int) -> bool:
    if not quote or not (1 <= chapter <= len(chapters)):
        return False
    q = _squash(quote)
    return bool(q) and q in _squash(chapters[chapter - 1]["text"])


def _excerpt(chapters, idx, limit=3500):
    return chapters[idx - 1]["text"][:limit]


def _extract_one(llm, ch):
    user = f"CHAPTER_TITLE: {ch['title']}\n\n{ch['text'][:14000]}"
    return llm.json(prompts.EXTRACT, user, max_tokens=3000)


def _verify_one(llm, cand, chapters):
    needed = {e["chapter"] for e in cand["evidence"]} | set(cand.get("later_chapters", []))
    excerpts = "\n\n".join(
        f"--- Chapter {i}: {chapters[i - 1]['title']} ---\n{_excerpt(chapters, i)}" for i in sorted(needed)
    )
    user = "CANDIDATE:\n" + json.dumps(cand, ensure_ascii=False) + "\n\nTEXT:\n" + excerpts
    return llm.json(prompts.VERIFY, user, max_tokens=1200)


def _title_for(cand):
    if cand["type"] == "posthumous":
        return f"{cand['character']} appears after dying"
    return f"{cand['character']}: conflicting {cand['attr'].replace('_', ' ')}"


def _condense(bible, chapters):
    lines = []
    for ch in chapters:
        lines.append(f"## Chapter {ch['index']}: {ch['title']}")
        for e in bible["events"]:
            if e["chapter"] == ch["index"]:
                lines.append(
                    f"- [{e['time'] or '?'} @ {e['location'] or '?'}] {e['summary']} ({', '.join(e['characters'])})"
                )
    lines.append("\n## Characters")
    for name, rec in bible["characters"].items():
        facts = "; ".join(f"{f['attr']}={f['value']} (ch{f['chapter']})" for f in rec["facts"][:12])
        lines.append(f"- {name}: {facts}")
    return "\n".join(lines)[:14000]


def analyze(text: str, llm, on_progress=None, deep: bool = True, workers: int = 4) -> dict:
    def progress(frac, msg):
        if on_progress:
            on_progress(frac, msg)

    chapters = split_chapters(text)
    if not chapters:
        raise ValueError("The manuscript is empty.")
    warnings: list[str] = []
    progress(0.02, f"Reading {len(chapters)} chapters")

    done = 0

    def run(ch):
        nonlocal done
        try:
            return _extract_one(llm, ch)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Chapter {ch['index']} could not be analysed: {e}")
            return {"characters": [], "events": []}
        finally:
            done += 1
            progress(0.05 + 0.5 * done / len(chapters), f"Extracted chapter {done} of {len(chapters)}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        extractions = list(pool.map(run, chapters))

    progress(0.58, "Building the story bible")
    bible = build_bible(extractions, chapters)
    candidates = find_candidates(bible)

    progress(0.62, f"Verifying {len(candidates)} suspicious spots")

    def verify(cand):
        try:
            return _verify_one(llm, cand, chapters)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Could not verify {_title_for(cand)}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        verdicts = list(pool.map(verify, candidates))

    issues: list[dict] = []
    for cand, v in zip(candidates, verdicts):
        if not v or not v.get("is_contradiction"):
            continue
        conf = float(v.get("confidence") or 0)
        if conf < 0.5:
            continue
        evidence = [
            {"chapter": int(e.get("chapter") or 0), "quote": str(e.get("quote") or "")}
            for e in (v.get("evidence") or [])
        ] or [{"chapter": e["chapter"], "quote": e["quote"]} for e in cand["evidence"]]
        issues.append(
            {
                "type": cand["type"],
                "title": _title_for(cand),
                "character": cand["character"],
                "severity": v.get("severity") if v.get("severity") in SEV else "medium",
                "confidence": round(conf, 2),
                "explanation": str(v.get("explanation") or ""),
                "suggested_fix": str(v.get("suggested_fix") or ""),
                "evidence": evidence,
            }
        )

    if deep:
        progress(0.8, "Deep scan: timeline, travel and knowledge")
        try:
            scan = llm.json(prompts.SCAN, _condense(bible, chapters), max_tokens=2000)
            for it in scan.get("issues") or []:
                conf = float(it.get("confidence") or 0.6)
                if conf < 0.6:
                    continue
                issues.append(
                    {
                        "type": "timeline",
                        "title": str(it.get("title") or "Possible timeline issue"),
                        "character": "",
                        "severity": it.get("severity") if it.get("severity") in SEV else "medium",
                        "confidence": round(conf, 2),
                        "explanation": str(it.get("explanation") or ""),
                        "suggested_fix": str(it.get("suggested_fix") or ""),
                        "evidence": [{"chapter": int(c), "quote": ""} for c in (it.get("chapters") or []) if str(c).isdigit()],
                    }
                )
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Deep scan skipped: {e}")

    for it in issues:
        for ev in it["evidence"]:
            ev["title"] = chapters[ev["chapter"] - 1]["title"] if 1 <= ev["chapter"] <= len(chapters) else ""
            ev["verified"] = quote_in_chapter(ev["quote"], chapters, ev["chapter"]) if ev["quote"] else None
    issues.sort(key=lambda i: (SEV[i["severity"]], -i["confidence"]))
    for n, it in enumerate(issues, 1):
        it["id"] = n

    progress(1.0, "Done")
    return {
        "chapters": [{k: c[k] for k in ("index", "title", "words")} for c in chapters],
        "bible": bible,
        "issues": issues,
        "warnings": warnings,
        "stats": {
            "chapters": len(chapters),
            "words": sum(c["words"] for c in chapters),
            "characters": len(bible["characters"]),
            "issues": len(issues),
            "model": getattr(llm, "model", getattr(llm, "name", "unknown")),
        },
    }


def ask(question: str, result: dict, text: str, llm) -> str:
    chapters = split_chapters(text)
    q = norm(question)
    scored = []
    for ch in chapters:
        body = norm(ch["text"])
        score = sum(1 for w in set(q.split()) if len(w) > 3 and w in body)
        for name in result["bible"]["characters"]:
            if norm(name) in q and norm(name) in body:
                score += 3
        scored.append((score, ch["index"]))
    top = [i for s, i in sorted(scored, reverse=True)[:3] if s > 0] or [1]
    excerpts = "\n\n".join(f"--- Chapter {i}: {chapters[i - 1]['title']} ---\n{_excerpt(chapters, i, 4500)}" for i in sorted(top))
    user = f"QUESTION: {question}\n\nBIBLE:\n{_condense(result['bible'], chapters)}\n\nEXCERPTS:\n{excerpts}"
    return str(llm.json(prompts.ASK, user, max_tokens=700).get("answer") or "No answer.")
