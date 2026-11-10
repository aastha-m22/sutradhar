"""Command line interface: sutradhar check | ask | serve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .demo import ScriptedLLM, demo_story
from .llm import BharatCodeLLM, LLMError
from .pipeline import analyze, ask
from .report import to_markdown


def _load(args):
    if args.demo:
        return demo_story(), ScriptedLLM()
    if not args.file:
        sys.exit("Give a manuscript file (.md/.txt) or use --demo.")
    return Path(args.file).read_text(encoding="utf-8"), BharatCodeLLM()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sutradhar", description="Continuity editor for fiction, powered by BharatCode.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="analyse a manuscript for continuity errors")
    c.add_argument("file", nargs="?")
    c.add_argument("--demo", action="store_true", help="use the bundled sample story, no API key needed")
    c.add_argument("--no-deep", action="store_true", help="skip the timeline/travel deep scan")
    c.add_argument("--md", help="write a Markdown report to this path")
    c.add_argument("--json", help="write the raw result as JSON to this path")

    a = sub.add_parser("ask", help="ask a question about the story")
    a.add_argument("question")
    a.add_argument("file", nargs="?")
    a.add_argument("--demo", action="store_true")

    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    args = p.parse_args(argv)
    try:
        if args.cmd == "serve":
            from .server import serve

            serve(args.host, args.port)
            return 0
        text, llm = _load(args)
        last = {"m": ""}

        def prog(f, m):
            if m != last["m"]:
                print(f"  [{int(f * 100):3d}%] {m}", file=sys.stderr)
                last["m"] = m

        result = analyze(text, llm, on_progress=prog, deep=not getattr(args, "no_deep", False))
        if args.cmd == "ask":
            print(ask(args.question, result, text, llm))
            return 0
        md = to_markdown(result)
        if args.md:
            Path(args.md).write_text(md, encoding="utf-8")
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(md)
        return 1 if any(i["severity"] == "high" for i in result["issues"]) else 0
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
