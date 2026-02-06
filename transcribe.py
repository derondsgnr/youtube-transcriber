#!/usr/bin/env python3
"""
YouTube Transcriber — Pull transcripts from YouTube, output LLM-ready markdown.

Usage:
    python transcribe.py <url> [options]

    url: YouTube video URL, channel URL, or playlist URL

Options:
    --limit N       Max videos to process (default: all)
    --output DIR    Output directory (default: ./output)
    --whisper       Force local Whisper transcription (requires faster-whisper)
    --model SIZE    Whisper model size: tiny/base/small/medium/large (default: base)
"""

import subprocess
import json
import sys
import os
import re
import argparse
from pathlib import Path
from datetime import datetime


def load_topics():
    """Load channel-to-topic mapping."""
    topics_path = Path('topics.json')
    if topics_path.exists():
        try:
            return json.loads(topics_path.read_text())
        except:
            return {}
    return {}


def get_topic_for_channel(channel_name, topics):
    """Find which topic a channel belongs to."""
    for topic, channels in topics.items():
        if channel_name in channels:
            return topic
    return "Uncategorized"


def sanitize_filename(name):
    """Clean string for use as filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120]


def get_video_list(url, limit=None):
    """Extract video URLs and metadata from a URL (video, playlist, or channel)."""
    cmd = [
        'yt-dlp',
        '--flat-playlist',
        '--dump-json',
        '--no-warnings',
        '--ignore-errors',
        url
    ]
    if limit:
        cmd.extend(['--playlist-end', str(limit)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            data = json.loads(line)
            vid_url = data.get('url') or data.get('webpage_url') or data.get('original_url')
            if vid_url and not vid_url.startswith('http'):
                vid_url = f"https://www.youtube.com/watch?v={vid_url}"
            videos.append({
                'url': vid_url,
                'title': data.get('title', 'Untitled'),
                'id': data.get('id', ''),
            })
        except json.JSONDecodeError:
            continue
    return videos


def get_video_metadata(url):
    """Get full metadata for a single video."""
    cmd = [
        'yt-dlp',
        '--dump-json',
        '--no-warnings',
        '--skip-download',
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def fetch_youtube_subtitles(url):
    """Pull existing YouTube subtitles (auto-generated or manual)."""
    tmp_dir = Path('tmp')
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / 'sub'

    # Try manual subs first, then auto-generated
    cmd = [
        'yt-dlp',
        '--write-subs',
        '--write-auto-subs',
        '--sub-langs', 'en.*,en',
        '--sub-format', 'vtt',
        '--skip-download',
        '--no-warnings',
        '-o', str(tmp_path),
        url
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    # Find the subtitle file
    sub_file = None
    for f in tmp_dir.iterdir():
        if f.suffix in ('.vtt', '.srt'):
            sub_file = f
            break

    if not sub_file:
        return None

    text = sub_file.read_text(encoding='utf-8', errors='replace')
    # Clean up tmp
    for f in tmp_dir.iterdir():
        f.unlink()

    return clean_vtt(text)


def clean_vtt(vtt_text):
    """Convert VTT subtitle format to clean paragraph text."""
    lines = vtt_text.split('\n')
    texts = []
    seen = set()

    for line in lines:
        # Skip headers, timestamps, positioning
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line or line.strip() == '':
            continue
        if re.match(r'^\d+$', line.strip()):
            continue
        # Remove VTT tags
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if not clean:
            continue
        # Deduplicate repeated lines (common in auto-subs)
        if clean not in seen:
            seen.add(clean)
            texts.append(clean)

    # Join into paragraphs — split roughly every 5 sentences
    full = ' '.join(texts)
    sentences = re.split(r'(?<=[.!?])\s+', full)

    paragraphs = []
    for i in range(0, len(sentences), 5):
        chunk = ' '.join(sentences[i:i+5])
        if chunk.strip():
            paragraphs.append(chunk.strip())

    return '\n\n'.join(paragraphs)


def whisper_transcribe(url, model_size='base'):
    """Fallback: download audio and transcribe with faster-whisper locally."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  [!] faster-whisper not installed. Install with: pip3 install faster-whisper")
        print("  [!] Skipping local transcription.")
        return None

    tmp_dir = Path('tmp')
    tmp_dir.mkdir(exist_ok=True)
    audio_path = tmp_dir / 'audio.mp3'

    # Download audio only
    cmd = [
        'yt-dlp',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '5',
        '--no-warnings',
        '-o', str(audio_path),
        url
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    if not audio_path.exists():
        # yt-dlp might add extension
        for f in tmp_dir.iterdir():
            if f.suffix in ('.mp3', '.m4a', '.wav', '.webm'):
                audio_path = f
                break

    if not audio_path.exists():
        return None

    print(f"  Transcribing with Whisper ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), beam_size=5)

    texts = []
    for segment in segments:
        texts.append(segment.text.strip())

    # Clean up
    for f in tmp_dir.iterdir():
        f.unlink()

    full = ' '.join(texts)
    sentences = re.split(r'(?<=[.!?])\s+', full)
    paragraphs = []
    for i in range(0, len(sentences), 5):
        chunk = ' '.join(sentences[i:i+5])
        if chunk.strip():
            paragraphs.append(chunk.strip())

    return '\n\n'.join(paragraphs)


def format_duration(seconds):
    """Convert seconds to H:MM:SS or M:SS."""
    if not seconds:
        return "Unknown"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_markdown(metadata, transcript):
    """Build LLM-ready markdown document."""
    title = metadata.get('title', 'Untitled')
    channel = metadata.get('channel', metadata.get('uploader', 'Unknown'))
    url = metadata.get('webpage_url', metadata.get('original_url', ''))
    upload_date = metadata.get('upload_date', '')
    if upload_date:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    duration = format_duration(metadata.get('duration'))
    description = metadata.get('description', '')
    tags = metadata.get('tags', [])

    md = f"""---
title: "{title}"
channel: "{channel}"
url: "{url}"
date: {upload_date}
duration: {duration}
tags: [{', '.join(tags[:10]) if tags else ''}]
---

# {title}

**Channel:** {channel}
**Date:** {upload_date}
**Duration:** {duration}
**URL:** {url}

## Description

{description[:500] if description else 'N/A'}

## Transcript

{transcript}
"""
    return md.strip() + '\n'


def process_video(url, output_dir, force_whisper=False, model_size='base'):
    """Process a single video: get metadata, get transcript, write markdown."""
    print(f"\n  Fetching metadata...")
    metadata = get_video_metadata(url)
    if not metadata:
        print(f"  [!] Could not fetch metadata for {url}")
        return False

    title = metadata.get('title', 'Untitled')
    channel = metadata.get('channel', metadata.get('uploader', 'Unknown'))
    print(f"  Title: {title}")
    print(f"  Channel: {channel}")

    # Determine Topic (Layer A)
    topics = load_topics()
    topic = get_topic_for_channel(channel, topics)
    print(f"  Categorized as: {topic}")

    # Create nested directory: output/Topic/Channel/
    channel_dir = Path(output_dir) / sanitize_filename(topic) / sanitize_filename(channel)
    channel_dir.mkdir(parents=True, exist_ok=True)

    # Check if already processed
    out_file = channel_dir / f"{sanitize_filename(title)}.md"
    if out_file.exists():
        print(f"  [skip] Already exists: {out_file}")
        return True

    # Get transcript
    transcript = None
    if not force_whisper:
        print(f"  Pulling YouTube subtitles...")
        transcript = fetch_youtube_subtitles(url)
        if transcript:
            print(f"  Got subtitles ({len(transcript)} chars)")

    if not transcript:
        print(f"  No YouTube subtitles. Trying Whisper...")
        transcript = whisper_transcribe(url, model_size)

    if not transcript:
        print(f"  [!] No transcript available for: {title}")
        return False

    # Build and write markdown
    md = build_markdown(metadata, transcript)
    out_file.write_text(md, encoding='utf-8')
    print(f"  Saved: {out_file}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='YouTube Transcriber — Pull transcripts, output LLM-ready markdown.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single video
  python transcribe.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  # Channel (last 10 videos)
  python transcribe.py "https://www.youtube.com/@channel" --limit 10

  # Playlist
  python transcribe.py "https://www.youtube.com/playlist?list=PLxxx"

  # Force local Whisper transcription
  python transcribe.py "https://www.youtube.com/watch?v=xxx" --whisper
        """
    )
    parser.add_argument('url', help='YouTube video, channel, or playlist URL')
    parser.add_argument('--limit', type=int, default=None, help='Max videos to process')
    parser.add_argument('--output', default='./output', help='Output directory (default: ./output)')
    parser.add_argument('--whisper', action='store_true', help='Force local Whisper transcription')
    parser.add_argument('--model', default='base', choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper model size (default: base)')

    args = parser.parse_args()

    print(f"YouTube Transcriber")
    print(f"{'=' * 40}")
    print(f"URL: {args.url}")
    print(f"Output: {args.output}")

    # Determine if single video or collection
    is_single = 'watch?v=' in args.url or 'youtu.be/' in args.url or 'shorts/' in args.url

    if is_single:
        videos = [{'url': args.url, 'title': '', 'id': ''}]
    else:
        print(f"\nFetching video list...")
        videos = get_video_list(args.url, args.limit)
        print(f"Found {len(videos)} videos")

    if not videos:
        print("No videos found.")
        sys.exit(1)

    success = 0
    failed = 0
    for i, vid in enumerate(videos):
        print(f"\n[{i+1}/{len(videos)}] {vid.get('title', vid['url'])}")
        try:
            ok = process_video(vid['url'], args.output, args.whisper, args.model)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [!] Error: {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Done. {success} transcribed, {failed} failed.")
    print(f"Output: {os.path.abspath(args.output)}")


if __name__ == '__main__':
    main()
