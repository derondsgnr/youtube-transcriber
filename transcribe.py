#!/usr/bin/env python3
"""
YouTube Transcriber — Pull transcripts from YouTube, output LLM-ready markdown.

Usage:
    python transcribe.py <url> [options]

Options:
    --limit N       Max videos to process (default: all)
    --output DIR    Output directory (default: ./output)
    --whisper       Force local Whisper transcription (requires faster-whisper)
    --model SIZE    Whisper model size: tiny/base/small/medium/large (default: base)
    --force         Reprocess even if already in state or file exists
"""

import subprocess
import json
import sys
import os
import re
import argparse
import time
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "output_dir": "./output",
    "default_whisper_model": "base",
    "default_limit": 5,
    "subtitle_lang_preference": ["en", "en-US", "en-GB"],
}


def load_config():
    p = PROJECT_ROOT / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def state_path():
    d = PROJECT_ROOT / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d / "processed.json"


def load_state():
    p = state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    state_path().write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def record_processed(video_id, title, out_path):
    if not video_id:
        return
    state = load_state()
    try:
        rel = out_path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        rel = out_path.resolve()
    state[video_id] = {
        "title": title,
        "out_path": str(rel),
        "processed_at": datetime.utcnow().isoformat() + "Z",
    }
    save_state(state)


def is_video_processed(video_id):
    if not video_id:
        return False
    return video_id in load_state()


def load_topics():
    topics_path = PROJECT_ROOT / "topics.json"
    if topics_path.exists():
        try:
            return json.loads(topics_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_topic_for_channel(channel_name, topics):
    for topic, channels in topics.items():
        if channel_name in channels:
            return topic
    return "Uncategorized"


def preview_categorization(url: str, is_single: bool, limit):
    """
    Resolve channel + topic folder for the first video in a job.
    Returns (channel_name, topic_name, error_message).
    error_message is set if metadata or list fetch failed.
    """
    topics = load_topics()
    if is_single:
        meta = get_video_metadata(url)
        if not meta:
            return None, None, "Could not fetch video metadata (check URL and network)."
        ch = meta.get("channel") or meta.get("uploader") or "Unknown"
        return ch, get_topic_for_channel(ch, topics), None
    vids = get_video_list(url, limit)
    if not vids:
        return None, None, "No videos found for that URL."
    first_url = vids[0].get("url")
    if not first_url:
        return None, None, "Could not resolve the first video URL."
    meta = get_video_metadata(first_url)
    if not meta:
        return None, None, "Could not fetch metadata for the first video in the list."
    ch = meta.get("channel") or meta.get("uploader") or "Unknown"
    return ch, get_topic_for_channel(ch, topics), None


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120]


def get_video_list(url, limit=None):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--ignore-errors",
        url,
    ]
    if limit:
        cmd.extend(["--playlist-end", str(limit)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            vid_url = data.get("url") or data.get("webpage_url") or data.get("original_url")
            if vid_url and not vid_url.startswith("http"):
                vid_url = f"https://www.youtube.com/watch?v={vid_url}"
            videos.append(
                {
                    "url": vid_url,
                    "title": data.get("title", "Untitled"),
                    "id": data.get("id", ""),
                }
            )
        except json.JSONDecodeError:
            continue
    return videos


def list_unprocessed_videos(channel_url, limit=20):
    """Return list of dicts with id, title, url, processed for UI."""
    state_ids = set(load_state().keys())
    vids = get_video_list(channel_url, limit)
    out = []
    for v in vids:
        vid = v.get("id") or ""
        out.append(
            {
                "id": vid,
                "title": v.get("title", "Untitled"),
                "url": v["url"],
                "processed": vid in state_ids if vid else False,
            }
        )
    return out


def get_video_metadata(url):
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--skip-download",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def ts_to_seconds(ts):
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def parse_vtt_to_segments(vtt_text):
    segments = []
    lines = vtt_text.splitlines()
    i = 0
    time_line_re = re.compile(
        r"^\s*(\d{1,2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}\.\d{3})"
    )
    while i < len(lines):
        line = lines[i]
        m = time_line_re.match(line.strip())
        if m:
            start = ts_to_seconds(m.group(1))
            end = ts_to_seconds(m.group(2))
            i += 1
            buf = []
            while i < len(lines) and lines[i].strip() != "":
                if time_line_re.match(lines[i].strip()):
                    break
                t = re.sub(r"<[^>]+>", "", lines[i]).strip()
                if t:
                    buf.append(t)
                i += 1
            txt = " ".join(buf).strip()
            if txt:
                segments.append({"start": start, "end": end, "text": txt})
            continue
        i += 1
    return segments


def clean_paragraphs_from_text(full):
    sentences = re.split(r"(?<=[.!?])\s+", full)
    paragraphs = []
    for i in range(0, len(sentences), 5):
        chunk = " ".join(sentences[i : i + 5])
        if chunk.strip():
            paragraphs.append(chunk.strip())
    return "\n\n".join(paragraphs)


def merge_segments_to_paragraphs(segments):
    if not segments:
        return ""
    texts = [s["text"] for s in segments]
    full = " ".join(texts)
    full = re.sub(r"\s+", " ", full).strip()
    return clean_paragraphs_from_text(full)


def build_chapter_transcript(metadata, segments):
    chapters = metadata.get("chapters") or []
    if not chapters or not segments:
        return None
    chapters = sorted(chapters, key=lambda c: c.get("start_time", 0))
    blocks = []
    for idx, ch in enumerate(chapters):
        t0 = ch.get("start_time", 0)
        t1 = chapters[idx + 1]["start_time"] if idx + 1 < len(chapters) else float("inf")
        title = ch.get("title") or f"Section {idx + 1}"
        texts = []
        for seg in segments:
            mid = (seg["start"] + seg["end"]) / 2
            if t0 <= mid < t1:
                texts.append(seg["text"])
        if not texts:
            for seg in segments:
                if seg["start"] >= t0 and seg["start"] < t1:
                    texts.append(seg["text"])
        body = clean_paragraphs_from_text(" ".join(texts)) if texts else ""
        if body.strip():
            blocks.append(f"## {title}\n\n{body}")
    if not blocks:
        return None
    return "\n\n".join(blocks)


def build_chapters_toc_only(metadata):
    chapters = metadata.get("chapters") or []
    if not chapters:
        return ""
    lines = ["## 📑 Video chapters (YouTube)", ""]
    for ch in sorted(chapters, key=lambda c: c.get("start_time", 0)):
        t0 = ch.get("start_time", 0)
        title = ch.get("title", "")
        lines.append(f"- **{format_duration(int(t0))}** — {title}")
    return "\n".join(lines)


def pick_best_subtitle_file(tmp_dir):
    files = list(tmp_dir.glob("*.vtt")) + list(tmp_dir.glob("*.srt"))
    if not files:
        return None

    def score(p):
        n = p.name.lower()
        s = 0
        if "auto" in n or "live" in n:
            s -= 3
        if ".en." in n or "english" in n:
            s += 2
        if "en" in n:
            s += 1
        try:
            s += min(p.stat().st_size / 100000, 5)
        except Exception:
            pass
        return s

    return max(files, key=score)


def fetch_youtube_subtitles(url):
    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    for f in tmp_dir.iterdir():
        if f.suffix in (".vtt", ".srt"):
            try:
                f.unlink()
            except Exception:
                pass

    cmd = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "en.*,en",
        "--sub-format",
        "vtt",
        "--skip-download",
        "--no-warnings",
        "-o",
        str(tmp_dir / "sub_%(id)s"),
        url,
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    sub_file = pick_best_subtitle_file(tmp_dir)
    if not sub_file:
        for f in list(tmp_dir.iterdir()):
            if f.suffix in (".vtt", ".srt"):
                try:
                    f.unlink()
                except Exception:
                    pass
        return None

    raw = sub_file.read_text(encoding="utf-8", errors="replace")
    for f in list(tmp_dir.iterdir()):
        if f.suffix in (".vtt", ".srt"):
            try:
                f.unlink()
            except Exception:
                pass

    segments = parse_vtt_to_segments(raw)
    if segments:
        plain = merge_segments_to_paragraphs(segments)
    else:
        plain = clean_vtt(raw)
        segments = None

    if not plain or not plain.strip():
        return None

    return plain, segments


def clean_vtt(vtt_text):
    noise_patterns = re.compile(
        r"\[(?:Music|Applause|Laughter|Silence|Crowd)[^\]]*\]|"
        r"\((?:music|applause|laughs?)\)",
        re.IGNORECASE,
    )
    lines = vtt_text.split("\n")
    texts = []
    seen = set()

    for line in lines:
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line or line.strip() == "":
            continue
        if re.match(r"^\d+$", line.strip()):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        clean = noise_patterns.sub("", clean).strip()
        if not clean:
            continue
        if clean not in seen:
            seen.add(clean)
            texts.append(clean)

    full = " ".join(texts)
    full = re.sub(r"\s+", " ", full).strip()
    return clean_paragraphs_from_text(full)


def whisper_transcribe(url, model_size="base", log_callback=None):
    def log(msg):
        print(f"  {msg}")
        if log_callback:
            log_callback(msg)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("[!] faster-whisper not installed. pip install faster-whisper")
        return None

    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    audio_path = tmp_dir / "audio.mp3"

    t0 = time.time()
    log("Downloading audio for Whisper...")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "5",
        "--no-warnings",
        "-o",
        str(audio_path),
        url,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    log(f"Audio step done in {time.time() - t0:.1f}s")

    if not audio_path.exists():
        for f in tmp_dir.iterdir():
            if f.suffix in (".mp3", ".m4a", ".wav", ".webm"):
                audio_path = f
                break

    if not audio_path.exists():
        return None

    log(f"Transcribing with Whisper ({model_size})...")
    t1 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    seg_iter, _info = model.transcribe(str(audio_path), beam_size=5)

    segments = []
    texts = []
    for segment in seg_iter:
        texts.append(segment.text.strip())
        segments.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
            }
        )
    log(f"Whisper done in {time.time() - t1:.1f}s")

    for f in tmp_dir.iterdir():
        try:
            f.unlink()
        except Exception:
            pass

    full = " ".join(texts)
    plain = clean_paragraphs_from_text(full)
    return plain, segments


def format_duration(seconds):
    if not seconds:
        return "Unknown"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_markdown(metadata, transcript, chapter_body=None, chapters_toc=""):
    title = metadata.get("title", "Untitled")
    channel = metadata.get("channel", metadata.get("uploader", "Unknown"))
    url = metadata.get("webpage_url", metadata.get("original_url", ""))
    upload_date = metadata.get("upload_date", "")
    if upload_date:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    duration = format_duration(metadata.get("duration"))
    tags = metadata.get("tags", [])

    axioms = []
    mental_models = []
    patterns = {
        "axiom": r"(?i)(the core idea is|at the fundamental level|the first principle is|the basic truth is|it boils down to)([^.!?]+[.!?])",
        "model": r"(?i)(we use a framework called|the mental model is|think of it as a|concept of)([^.!?]+[.!?])",
    }
    body_for_regex = chapter_body or transcript
    for match in re.finditer(patterns["axiom"], body_for_regex):
        axioms.append(match.group(2).strip())
    for match in re.finditer(patterns["model"], body_for_regex):
        mental_models.append(match.group(2).strip())

    axioms = list(dict.fromkeys(axioms))[:5]
    mental_models = list(dict.fromkeys(mental_models))[:5]

    toc_block = (chapters_toc + "\n\n") if chapters_toc else ""
    knowledge_body = chapter_body if chapter_body else transcript

    md = f"""---
title: "{title}"
channel: "{channel}"
url: "{url}"
date: {upload_date}
type: "Knowledge Asset"
---

# [KNOWLEDGE ASSET] {title}

> **LLM INSTRUCTION:** You are assuming the reasoning state of the experts in this transcript (Channel: {channel}). Use the First Principles and Mental Models defined below to inform your logic and problem-solving.

## 🧩 First Principles & Core Axioms
{chr(10).join([f"- {a}" for a in axioms]) if axioms else "- [Heuristic extraction: expand from transcript below]"}

## ⚡ Mental Models & Frameworks
{chr(10).join([f"- {m}" for m in mental_models]) if mental_models else "- [Heuristic extraction: expand from transcript below]"}

## 📝 Metadata & Context
- **Expert/Source:** {channel}
- **Original URL:** {url}
- **Duration:** {duration}
- **Key Tags:** {", ".join(tags[:10]) if tags else "N/A"}

{toc_block}---

## 📖 Structured Knowledge (Transcript)

{knowledge_body}

---
**End of Knowledge Asset**
"""
    return md.strip() + "\n"


def process_video(
    url,
    output_dir,
    force_whisper=False,
    model_size="base",
    log_callback=None,
    force=False,
):
    def log(msg):
        print(f"  {msg}")
        if log_callback:
            log_callback(msg)

    t_meta = time.time()
    log("Phase: metadata — fetching...")
    metadata = get_video_metadata(url)
    log(f"Phase: metadata — done in {time.time() - t_meta:.1f}s")
    if not metadata:
        log(f"[!] Could not fetch metadata for {url}")
        return False

    title = metadata.get("title", "Untitled")
    channel = metadata.get("channel", metadata.get("uploader", "Unknown"))
    video_id = metadata.get("id") or ""
    log(f"Title: {title}")
    log(f"Channel: {channel}")
    if video_id:
        log(f"Video ID: {video_id}")

    topics = load_topics()
    topic = get_topic_for_channel(channel, topics)
    log(f"Categorized as: {topic}")

    channel_dir = Path(output_dir) / sanitize_filename(topic) / sanitize_filename(channel)
    channel_dir.mkdir(parents=True, exist_ok=True)

    out_file = channel_dir / f"{sanitize_filename(title)}.md"

    if not force and video_id and is_video_processed(video_id):
        log(f"[skip] Already in library (state): {video_id}")
        return True

    if not force and out_file.exists():
        log(f"[skip] File exists: {out_file}")
        if video_id:
            record_processed(video_id, title, out_file)
        return True

    transcript = None
    segments = None

    if force_whisper:
        t_tr = time.time()
        log("Phase: transcription — Whisper only (forced)")
        res = whisper_transcribe(url, model_size, log_callback)
        if res:
            transcript, segments = res
        log(f"Phase: transcription — done in {time.time() - t_tr:.1f}s")
    else:
        t_tr = time.time()
        log("Phase: transcription — YouTube subtitles (prefer manual)")
        fetched = fetch_youtube_subtitles(url)
        if fetched:
            transcript, segments = fetched
        if transcript and transcript.strip():
            log(f"Phase: subtitles — done in {time.time() - t_tr:.1f}s ({len(transcript)} chars)")
        else:
            transcript = None
            segments = None

        if not transcript:
            log("Phase: transcription — Whisper fallback (no usable subtitles)")
            t_w = time.time()
            res = whisper_transcribe(url, model_size, log_callback)
            if res:
                transcript, segments = res
            log(f"Phase: Whisper fallback — done in {time.time() - t_w:.1f}s")

    if not transcript or not transcript.strip():
        log(f"[!] No transcript available for: {title}")
        return False

    chapters_toc = build_chapters_toc_only(metadata)
    chapter_body = None
    if segments:
        chapter_body = build_chapter_transcript(metadata, segments)
    if not chapter_body:
        chapter_body = None

    md = build_markdown(metadata, transcript, chapter_body=chapter_body, chapters_toc=chapters_toc)
    out_file.write_text(md, encoding="utf-8")
    log(f"Saved: {out_file}")
    if video_id:
        record_processed(video_id, title, out_file)
    return True


def extract_source_url_from_markdown(markdown_path):
    """Read the original YouTube URL from a saved markdown file."""
    try:
        text = Path(markdown_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r'^url:\s*"([^"\n]+)"\s*$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def rerun_markdown_file(markdown_path, force_whisper=False, model_size="base", log_callback=None):
    """
    Rebuild an existing markdown file in place from its saved source URL.
    This preserves the current file location instead of re-categorizing it.
    """
    def log(msg):
        print(f"  {msg}")
        if log_callback:
            log_callback(msg)

    markdown_path = Path(markdown_path)
    source_url = extract_source_url_from_markdown(markdown_path)
    if not source_url:
        log("[!] Could not find source URL in saved markdown file")
        return False

    log(f"Re-running from source URL: {source_url}")
    metadata = get_video_metadata(source_url)
    if not metadata:
        log("[!] Could not fetch metadata for saved source URL")
        return False

    title = metadata.get("title", "Untitled")
    video_id = metadata.get("id") or ""
    transcript = None
    segments = None

    if force_whisper:
        log("Phase: transcription — Whisper only (forced)")
        res = whisper_transcribe(source_url, model_size, log_callback)
        if res:
            transcript, segments = res
    else:
        log("Phase: transcription — YouTube subtitles (prefer manual)")
        fetched = fetch_youtube_subtitles(source_url)
        if fetched:
            transcript, segments = fetched
        if not transcript:
            log("Phase: transcription — Whisper fallback (no usable subtitles)")
            res = whisper_transcribe(source_url, model_size, log_callback)
            if res:
                transcript, segments = res

    if not transcript or not transcript.strip():
        log(f"[!] No transcript available for: {title}")
        return False

    chapters_toc = build_chapters_toc_only(metadata)
    chapter_body = build_chapter_transcript(metadata, segments) if segments else None
    md = build_markdown(metadata, transcript, chapter_body=chapter_body, chapters_toc=chapters_toc)
    markdown_path.write_text(md, encoding="utf-8")
    log(f"Overwrote: {markdown_path}")
    if video_id:
        record_processed(video_id, title, markdown_path)
    return True


def health_check():
    """Return list of dicts name, ok, detail for UI."""
    checks = []

    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        ver = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=10
        )
        checks.append(
            {
                "name": "yt-dlp",
                "ok": True,
                "detail": (ver.stdout or "").strip()[:100],
            }
        )
    else:
        checks.append({"name": "yt-dlp", "ok": False, "detail": "not in PATH"})

    ff = shutil.which("ffmpeg")
    checks.append(
        {
            "name": "ffmpeg",
            "ok": ff is not None,
            "detail": ff or "not in PATH",
        }
    )

    venv = sys.prefix != sys.base_prefix
    checks.append(
        {
            "name": "Python venv",
            "ok": venv,
            "detail": "active" if venv else "not active (recommended: source venv/bin/activate)",
        }
    )

    try:
        import faster_whisper  # noqa: F401

        checks.append({"name": "faster-whisper", "ok": True, "detail": "import ok"})
    except ImportError:
        checks.append(
            {
                "name": "faster-whisper",
                "ok": False,
                "detail": "pip install faster-whisper (optional until Whisper fallback)",
            }
        )

    return checks


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Transcriber — Pull transcripts, output LLM-ready markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="YouTube video, channel, or playlist URL")
    parser.add_argument("--limit", type=int, default=None, help="Max videos to process")
    parser.add_argument("--output", default="./output", help="Output directory")
    parser.add_argument("--whisper", action="store_true", help="Force local Whisper")
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even if file exists or video is in state",
    )
    parser.add_argument(
        "--allow-uncategorized",
        action="store_true",
        help="Allow saving when the channel is not listed under any topic (Uncategorized folder)",
    )

    args = parser.parse_args()

    print("YouTube Transcriber")
    print("=" * 40)
    print(f"URL: {args.url}")
    print(f"Output: {args.output}")

    is_single = "watch?v=" in args.url or "youtu.be/" in args.url or "shorts/" in args.url

    if is_single:
        videos = [{"url": args.url, "title": "", "id": ""}]
    else:
        print("\nFetching video list...")
        videos = get_video_list(args.url, args.limit)
        print(f"Found {len(videos)} videos")

    if not videos:
        print("No videos found.")
        sys.exit(1)

    ch, topic, err = preview_categorization(args.url, is_single, args.limit)
    if err:
        print(err)
        sys.exit(1)
    if topic == "Uncategorized" and not args.allow_uncategorized:
        print(
            f"Channel “{ch}” is not mapped to any topic. "
            "Add the exact channel name under a topic in topics.json, "
            "or pass --allow-uncategorized to save under Uncategorized."
        )
        sys.exit(1)
    if topic != "Uncategorized":
        print(f"Topic folder: {topic} (channel: {ch})")

    success = 0
    failed = 0
    failed_titles = []
    for i, vid in enumerate(videos):
        print(f"\n[{i+1}/{len(videos)}] {vid.get('title', vid['url'])}")
        try:
            ok = process_video(
                vid["url"], args.output, args.whisper, args.model, force=args.force
            )
            if ok:
                success += 1
            else:
                failed += 1
                failed_titles.append(vid.get("title", vid["url"]))
        except Exception as e:
            print(f"  [!] Error: {e}")
            failed += 1
            failed_titles.append(vid.get("title", vid["url"]))

    print(f"\n{'=' * 40}")
    print(f"Done. {success} transcribed, {failed} failed.")
    if failed_titles:
        print("Failed videos:")
        for title in failed_titles:
            print(f"  - {title}")
    print(f"Output: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
