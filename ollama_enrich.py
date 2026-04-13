#!/usr/bin/env python3
"""
Optional: send a saved Knowledge Asset .md to a local Ollama model to add
structured axioms / summaries (runs on your machine; no API cost).

Prereqs: Ollama installed and running (`ollama serve`), model pulled e.g.:
  ollama pull gemma2:2b

Usage:
  python ollama_enrich.py path/to/file.md
  python ollama_enrich.py path/to/file.md --model gemma2:2b
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def main():
    parser = argparse.ArgumentParser(description="Enrich transcript MD via local Ollama")
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument("--model", default="gemma2:2b", help="Ollama model name")
    args = parser.parse_args()

    path = args.markdown_file
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    prompt = f"""You are helping structure knowledge from a video transcript for LLM ingestion.

From the document below, extract:
1) Five bullet "First principles / axioms" (short, standalone).
2) Five bullet "Mental models or frameworks" named in the talk.
3) Five bullet "Actionable takeaways".

Use clear bullets. Do not repeat the full transcript.

--- DOCUMENT ---
{text[:12000]}
"""

    payload = json.dumps(
        {"model": args.model, "prompt": prompt, "stream": False}
    ).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(
            "Ollama request failed. Is `ollama serve` running and the model pulled?\n",
            e,
            file=sys.stderr,
        )
        sys.exit(1)

    answer = body.get("response", "").strip()
    out = path.with_suffix(".enriched.md")
    header = f"""---
enriched_by: ollama
model: {args.model}
---

## Enrichment (local model)

{answer}

---

## Original file

"""
    out.write_text(header + text, encoding="utf-8")
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
