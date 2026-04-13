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

Theme: light, Resend-inspired typography and spacing (see `.streamlit/config.toml` + CSS in `app.py`). The sidebar can **open your output folder in Finder** so you rarely need the terminal.

Tabs: **Transcribe**, **Library**, **Topics**, **System** (health + catch-up on new channel/playlist videos).

## Output (folders)

**Topic** names are your top-level folders. **Channel** is the subfolder (exact YouTube channel display name). You add topics and channel mappings on the **Topics** tab (or edit `topics.json`). The app creates `output/<Topic>/<Channel>/` when you run a job—you do not need to create folders by hand.

If a channel is not listed under any topic, files go to **`Uncategorized`**. The UI blocks that by default until you enable **Allow Uncategorized** in the sidebar (or use `python transcribe.py URL --allow-uncategorized`).

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
