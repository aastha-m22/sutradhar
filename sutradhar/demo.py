"""Offline demo: a scripted stand-in for the model so anyone can try Sutradhar without an API key.

It only knows the bundled sample story ("The Cellar Key"), but it runs the *real* pipeline
(chapter splitting, bible merging, candidate detection, quote verification, reporting).
"""

from __future__ import annotations

import json
from pathlib import Path

STORY_PATH = Path(__file__).with_name("demo_story.md")


def demo_story() -> str:
    return STORY_PATH.read_text(encoding="utf-8")


def _c(name, aliases=(), facts=(), status="alive", status_quote="", present=True):
    return {
        "name": name,
        "aliases": list(aliases),
        "facts": [{"attr": a, "value": v, "quote": q} for a, v, q in facts],
        "status": status,
        "status_quote": status_quote,
        "present": present,
    }


def _e(summary, chars, loc, time):
    return {"summary": summary, "characters": chars, "location": loc, "time": time}


EXTRACTIONS = {
    "Chapter 1": {
        "characters": [
            _c("Meera Sood", ["Meera"], [
                ("eye_color", "green", "Her green eyes stung from the smoke of the wood stove."),
                ("occupation", "crime reporter", "She had been a crime reporter for six years"),
                ("relationship:arjun", "brother", "Her little brother Arjun, seventeen and restless"),
            ]),
            _c("Arjun", [], [("age", "seventeen", "Her little brother Arjun, seventeen and restless, paced behind her.")]),
            _c("Dadi", [], [], present=False),
        ],
        "events": [
            _e("Meera reads Dadi's letter summoning the family home", ["Meera Sood", "Arjun"], "Shimla guesthouse", "Monday evening"),
        ],
    },
    "Chapter 2": {
        "characters": [
            _c("Meera Sood", ["Meera"]),
            _c("Arjun"),
            _c("Dadi", [], [("hair_color", "silver", "her silver braid over one shoulder")], "dead", "By midnight Dadi was dead."),
            _c("Inspector Rawat", ["Rawat"]),
        ],
        "events": [
            _e("The siblings reach the old house; Dadi gives Meera a brass key", ["Meera Sood", "Dadi"], "Kasauli house", "Wednesday"),
            _e("Dadi dies; Rawat takes notes", ["Dadi", "Inspector Rawat", "Arjun"], "Kasauli house", "Wednesday midnight"),
        ],
    },
    "Chapter 3": {
        "characters": [
            _c("Meera Sood", ["Meera"]),
            _c("Arjun", [], [("age", "nineteen", "Arjun, who was nineteen and still pretending he did not need her")]),
            _c("Inspector Rawat", ["Rawat"]),
        ],
        "events": [
            _e("Meera and Arjun force open the cellar and find a tin box of photographs", ["Meera Sood", "Arjun", "Inspector Rawat"], "Kasauli cellar", "Thursday morning"),
            _e("Meera takes the six o'clock train to Delhi with the photographs", ["Meera Sood"], "Kasauli to Delhi", "Thursday dawn"),
        ],
    },
    "Chapter 4": {
        "characters": [
            _c("Meera Sood", ["Meera"], [("eye_color", "brown", "Meera's brown eyes widened")]),
            _c("Dadi", [], [], "alive"),
        ],
        "events": [
            _e("Dadi serves Meera tea and says her grandfather never went to Delhi", ["Meera Sood", "Dadi"], "Kasauli kitchen", "nine that same morning"),
        ],
    },
    "Chapter 5": {
        "characters": [
            _c("Meera Sood", ["Meera"]),
            _c("Arjun"),
            _c("Inspector Rawat", ["Rawat"]),
        ],
        "events": [
            _e("Rawat says some secrets stay in the cellar; the monsoon begins", ["Inspector Rawat", "Meera Sood", "Arjun"], "Kasauli", "afterwards"),
        ],
    },
}


class ScriptedLLM:
    name = "offline-demo"
    model = "offline-demo (scripted)"

    def json(self, system: str, user: str, max_tokens: int = 0) -> dict:
        if "TASK:EXTRACT" in system:
            for key, data in EXTRACTIONS.items():
                if user.startswith(f"CHAPTER_TITLE: {key}"):
                    return json.loads(json.dumps(data))
            return {"characters": [], "events": []}
        if "TASK:VERIFY" in system:
            cand = json.loads(user.split("CANDIDATE:\n", 1)[1].split("\n\nTEXT:", 1)[0])
            if cand["type"] == "posthumous":
                return {
                    "is_contradiction": True, "confidence": 0.95, "severity": "high",
                    "explanation": f"{cand['character']} dies in Chapter {cand['death']['chapter']}, yet acts and speaks in Chapter {cand['later_chapters'][0]} with no flashback, dream or supernatural framing.",
                    "suggested_fix": "Make the Chapter 4 scene a memory or dream, or give the death scene an ambiguity that allows it.",
                    "evidence": [
                        {"chapter": cand["death"]["chapter"], "quote": cand["death"]["quote"]},
                        {"chapter": cand["later_chapters"][0], "quote": "Dadi set a cup of tea in front of her, humming an old film song."},
                    ],
                }
            ev = cand["evidence"]
            a, b = ev[0], ev[-1]
            what = cand["attr"].replace("_", " ")
            return {
                "is_contradiction": True, "confidence": 0.9, "severity": "medium" if cand["attr"] == "age" else "high",
                "explanation": f"{cand['character']}'s {what} is '{a['value']}' in Chapter {a['chapter']} but '{b['value']}' in Chapter {b['chapter']}, and the story covers only a few days.",
                "suggested_fix": f"Pick one {what} and update the other chapter.",
                "evidence": [{"chapter": e["chapter"], "quote": e["quote"]} for e in ev],
            }
        if "TASK:SCAN" in system:
            return {
                "issues": [{
                    "title": "Impossible travel: on a train to Delhi and back in Kasauli by nine",
                    "explanation": "In Chapter 3 Meera boards the six o'clock train to Delhi at dawn. Chapter 4 places her back in the Kasauli kitchen at nine 'that same morning', which the journey makes impossible.",
                    "severity": "high", "confidence": 0.85, "chapters": [3, 4],
                    "suggested_fix": "Move the Delhi trip to a later day or change the time in Chapter 4.",
                }]
            }
        if "TASK:ASK" in system:
            q = user.split("QUESTION:", 1)[1].split("\n", 1)[0].lower()
            if "dadi" in q and any(w in q for w in ("die", "death", "dead")):
                return {"answer": "Dadi dies at midnight on Wednesday, shortly after pressing the brass key into Meera's hand and whispering 'Cellar' [Ch 2]."}
            if "rawat" in q:
                return {"answer": "Inspector Rawat is the police officer who watches the family: he takes notes at Dadi's deathbed [Ch 2], observes the cellar search [Ch 3] and closes the story with a warning about secrets [Ch 5]."}
            if "key" in q:
                return {"answer": "Dadi gives Meera a brass key and whispers 'Cellar' [Ch 2]. Meera uses it for the cellar door [Ch 3] and keeps it at the end [Ch 5]."}
            return {"answer": "Demo mode only knows the sample story. Try: 'When does Dadi die?', 'Who is Rawat?' or 'What does the key open?'. With a BharatCode API key you can ask anything about your own manuscript."}
        return {}
