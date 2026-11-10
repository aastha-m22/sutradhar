"""Render an analysis result as Markdown."""

from __future__ import annotations

ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def to_markdown(result: dict) -> str:
    s = result["stats"]
    out = [
        "# Sutradhar continuity report",
        "",
        f"{s['chapters']} chapters · {s['words']:,} words · {s['characters']} characters · "
        f"**{s['issues']} issue{'s' if s['issues'] != 1 else ''}** · model `{s['model']}`",
        "",
    ]
    if not result["issues"]:
        out += ["No continuity problems found. ✅", ""]
    for it in result["issues"]:
        out += [f"## {ICON[it['severity']]} {it['id']}. {it['title']}", "", it["explanation"], ""]
        for ev in it["evidence"]:
            mark = {True: "✓ verified in text", False: "⚠ quote not found in text", None: ""}[ev.get("verified")]
            q = f" “{ev['quote']}”" if ev["quote"] else ""
            out.append(f"- **Ch {ev['chapter']}** ({ev.get('title', '')}){q} {mark}".rstrip())
        if it["suggested_fix"]:
            out += ["", f"**Fix:** {it['suggested_fix']}"]
        out += [f"", f"*confidence {it['confidence']:.0%}*", ""]
    out += ["## Story bible", ""]
    for name, rec in result["bible"]["characters"].items():
        chs = ", ".join(str(c) for c in rec["appearances"]) or "-"
        out.append(f"### {name}")
        out.append(f"Appears in chapters: {chs}" + (f" · aliases: {', '.join(rec['aliases'])}" if rec["aliases"] else ""))
        for f in rec["facts"]:
            out.append(f"- {f['attr']}: **{f['value']}** (Ch {f['chapter']})")
        for d in rec["deaths"]:
            out.append(f"- dies in Ch {d['chapter']}")
        out.append("")
    for w in result.get("warnings", []):
        out.append(f"> ⚠ {w}")
    return "\n".join(out) + "\n"
