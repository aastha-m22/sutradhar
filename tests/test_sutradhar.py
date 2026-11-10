from sutradhar.bible import build_bible, find_candidates
from sutradhar.chapters import split_chapters
from sutradhar.demo import ScriptedLLM, demo_story
from sutradhar.llm import extract_json
from sutradhar.pipeline import analyze, ask, quote_in_chapter
from sutradhar.report import to_markdown


def test_split_chapters_headings():
    chs = split_chapters(demo_story())
    assert [c["index"] for c in chs] == [1, 2, 3, 4, 5]
    assert chs[1]["title"].startswith("Chapter 2")


def test_split_chapters_plain_text_chunks():
    text = "\n\n".join("word " * 400 for _ in range(20))
    chs = split_chapters(text, max_words=1000)
    assert len(chs) > 3 and chs[0]["title"] == "Section 1"


def test_extract_json_handles_think_and_fences():
    raw = '<think>hmm {not json}</think>\n```json\n{"a": 1}\n```'
    assert extract_json(raw) == {"a": 1}


def test_alias_merge():
    chs = [{"index": 1, "title": "a", "text": ""}, {"index": 2, "title": "b", "text": ""}]
    ex = [
        {"characters": [{"name": "Meera Sood", "aliases": ["Meera"], "facts": []}]},
        {"characters": [{"name": "Meera", "facts": [{"attr": "Eye_Color", "value": "Brown", "quote": ""}]}]},
    ]
    bible = build_bible(ex, chs)
    assert list(bible["characters"]) == ["Meera Sood"]
    assert bible["characters"]["Meera Sood"]["facts"][0]["attr"] == "eye_color"


def test_candidates_flag_conflict_and_posthumous():
    chs = [{"index": i, "title": str(i), "text": ""} for i in (1, 2, 3)]
    ex = [
        {"characters": [{"name": "A", "facts": [{"attr": "age", "value": "17", "quote": "q"}]}]},
        {"characters": [{"name": "A", "status": "dead", "status_quote": "dead"}]},
        {"characters": [{"name": "A", "facts": [{"attr": "age", "value": "19", "quote": "q"}]}]},
    ]
    kinds = {c["type"] for c in find_candidates(build_bible(ex, chs))}
    assert kinds == {"attribute", "posthumous"}


def test_flashback_is_not_posthumous():
    chs = [{"index": i, "title": str(i), "text": ""} for i in (1, 2)]
    ex = [
        {"characters": [{"name": "A", "status": "dead", "status_quote": "dead"}]},
        {"characters": [{"name": "A", "present": False}]},
    ]
    assert find_candidates(build_bible(ex, chs)) == []


def test_full_demo_pipeline_finds_the_planted_errors():
    text = demo_story()
    res = analyze(text, ScriptedLLM())
    titles = " | ".join(i["title"] for i in res["issues"])
    assert res["stats"]["issues"] == 4
    assert "Dadi appears after dying" in titles
    assert "eye color" in titles and "age" in titles
    assert "Impossible travel" in titles
    assert res["issues"][0]["severity"] == "high"
    for issue in res["issues"]:
        for ev in issue["evidence"]:
            if ev["quote"]:
                assert ev["verified"] is True, ev


def test_hallucinated_quote_is_flagged():
    chs = split_chapters(demo_story())
    assert quote_in_chapter("Her green eyes stung", chs, 1)
    assert not quote_in_chapter("Her violet eyes sparkled", chs, 1)


def test_ask_and_report():
    text = demo_story()
    res = analyze(text, ScriptedLLM(), deep=False)
    assert "[Ch 2]" in ask("When does Dadi die?", res, text, ScriptedLLM())
    md = to_markdown(res)
    assert "Story bible" in md and "Meera Sood" in md
