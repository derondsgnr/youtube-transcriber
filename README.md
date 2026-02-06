# YouTube Transcriber

Pull YouTube videos (single, channel, or playlist) → transcribe → output LLM-ready markdown files.

## How It Works

1. **yt-dlp** fetches video metadata and YouTube's own subtitles (auto-generated or manual)
2. If no subtitles exist, **faster-whisper** transcribes locally on your CPU (optional)
3. Output: one clean `.md` file per video, organized by channel — ready to drop into any LLM

## Requirements

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — `brew install yt-dlp` or `pip install yt-dlp`
- [ffmpeg](https://ffmpeg.org/) — `brew install ffmpeg`
- (Optional) [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — `pip install faster-whisper` (only needed if YouTube subtitles unavailable)

## Usage

```bash
# Single video
python transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Entire channel (last 20 videos)
python transcribe.py "https://www.youtube.com/@ChannelName" --limit 20

# Playlist
python transcribe.py "https://www.youtube.com/playlist?list=PLAYLIST_ID"

# Force local Whisper (when subtitles exist but you want better quality)
python transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID" --whisper --model small
```

## Output Structure

```
output/
  Channel Name/
    Video Title.md
    Another Video.md
  Other Channel/
    Some Video.md
```

Each `.md` file contains YAML frontmatter + clean transcript:

```markdown
---
title: "Video Title"
channel: "Channel Name"
url: "https://youtube.com/watch?v=..."
date: 2024-01-15
duration: 1:23:45
tags: [tag1, tag2]
---

# Video Title

**Channel:** Channel Name
**Date:** 2024-01-15
**Duration:** 1:23:45

## Description
...

## Transcript
Full clean transcript text here...
```

## Plug Into LLMs

| Target | How |
|--------|-----|
| **Claude Projects** | Upload `.md` files to Project Knowledge |
| **Cursor Skills** | Copy to `.cursor/skills/` as `SKILL.md` |
| **NotebookLM** | Upload `.md` files as sources |
| **ChatGPT** | Upload to conversation or GPT knowledge |
| **RAG / Vector DB** | Ingest `.md` files directly |

## Options

| Flag | Description |
|------|-------------|
| `--limit N` | Max number of videos to process |
| `--output DIR` | Output directory (default: `./output`) |
| `--whisper` | Force local Whisper instead of YouTube subs |
| `--model SIZE` | Whisper model: tiny/base/small/medium/large |
