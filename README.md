# YouTube Transcriber

Pull YouTube videos (single, channel, or playlist) → transcribe → LLM-ready markdown, organized by **topic** (from `topics.json`) and **channel**.

## Setup

```bash
cd youtube-transcriber
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy optional settings: `cp config.example.json config.json`

## CLI

```bash
python transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID"
python transcribe.py "https://www.youtube.com/@ChannelName" --limit 20
python transcribe.py "URL" --whisper --model small
python transcribe.py "URL" --force   # reprocess even if already saved
```

## UI

```bash
streamlit run app.py
# or double-click start.command
```

Tabs: **Transcribe**, **Library**, **Topics**, **Diagnostics & catch-up** (health checks + list new videos on a channel/playlist).

## Output

```
output/
  <Topic>/
    <Channel>/
      <Video title>.md
state/processed.json   # YouTube video IDs already saved (skip / resume)
```

Markdown includes Knowledge Asset sections, optional **YouTube chapter** TOC, and chapter-bucketed transcript when timed subs or Whisper segments exist.

## Optional: local enrichment (Ollama)

If [Ollama](https://ollama.com) is installed and running (`ollama serve`), you can add a second-pass summary/axioms with a local model (e.g. Gemma):

```bash
ollama pull gemma2:2b
python ollama_enrich.py "output/Product Strategy/Some Channel/Some Video.md"
```

Writes `*.enriched.md` next to the original.

## Plug into LLMs

| Target | How |
|--------|-----|
| Claude Projects / NotebookLM | Upload `.md` files |
| Cursor | Point rules/skills at `output/...` or copy excerpts into project docs |
