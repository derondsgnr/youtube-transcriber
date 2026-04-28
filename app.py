import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st

import transcribe

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def card():
    """Resend-style bordered panel; falls back on older Streamlit without `border=`."""
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


st.set_page_config(
    page_title="Transcriber",
    page_icon="◆",
    layout="wide",
)


def inject_styles():
    st.markdown(
        """
<style>
  :root {
    --bg: #fafafa;
    --surface: #ffffff;
    --text: #0a0a0a;
    --muted: #737373;
    --border: #e5e5e5;
    --ring: rgba(10, 10, 10, 0.08);
    --shadow: 0 1px 2px rgba(10, 10, 10, 0.04), 0 8px 24px rgba(10, 10, 10, 0.06);
    --radius: 10px;
    --radius-sm: 8px;
    --font: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
      Roboto, "Helvetica Neue", Arial, sans-serif;
  }

  .stApp { background: var(--bg); font-family: var(--font); color: var(--text); }
  #MainMenu { visibility: hidden; }
  footer { visibility: hidden; }
  header[data-testid="stHeader"] { background: transparent; border-bottom: 1px solid var(--border); }
  .block-container { padding-top: 2rem !important; padding-bottom: 4rem !important; max-width: 1080px !important; }

  .yt-hero {
    padding: 0 0 1.5rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.75rem;
  }
  .yt-kicker {
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
    margin: 0 0 0.5rem 0;
  }
  .yt-title {
    font-size: 1.75rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    line-height: 1.15;
    margin: 0 0 0.5rem 0;
    color: var(--text);
  }
  .yt-sub {
    font-size: 0.95rem;
    color: var(--muted);
    line-height: 1.55;
    max-width: 52ch;
    margin: 0;
  }

  .yt-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 1.25rem 1.35rem;
    margin-bottom: 1rem;
  }
  .yt-card h3 {
    font-size: 0.8125rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--text);
    margin: 0 0 1rem 0;
  }

  .yt-log {
    background: #0a0a0a;
    color: #e5e5e5;
    border-radius: var(--radius-sm);
    padding: 1rem 1.1rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.78rem;
    line-height: 1.45;
    max-height: 260px;
    overflow-y: auto;
    border: 1px solid #262626;
  }

  div[data-testid="stTabs"] { margin-top: 0.25rem; }
  div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0.25rem;
    background: transparent;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0;
  }
  div[data-testid="stTabs"] button[data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 0.55rem 0.9rem;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--muted);
    border: none;
    background: transparent;
  }
  div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--border);
    border-bottom-color: var(--surface);
    margin-bottom: -1px;
  }

  div[data-testid="stVerticalBlock"] > div > div[data-testid="stMarkdownContainer"] p {
    line-height: 1.55;
  }

  .stTextInput label, .stNumberInput label, .stSelectbox label, .stCheckbox label {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: var(--text) !important;
  }
  div[data-baseweb="input"] > div {
    border-radius: var(--radius-sm) !important;
    border-color: var(--border) !important;
    background: var(--surface) !important;
  }
  div[data-baseweb="select"] > div {
    border-radius: var(--radius-sm) !important;
    border-color: var(--border) !important;
  }

  div[data-testid="stButton"] > button {
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    padding: 0.5rem 1rem !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    color: var(--text) !important;
    transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-testid="stButton"] > button:hover {
    border-color: #d4d4d4 !important;
    box-shadow: 0 1px 2px rgba(10,10,10,0.06) !important;
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: #171717 !important;
    color: #fafafa !important;
    border-color: #171717 !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #262626 !important;
    border-color: #262626 !important;
  }

  div[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1rem;
    box-shadow: 0 1px 2px rgba(10,10,10,0.04);
  }
  div[data-testid="stMetric"] label { color: var(--muted) !important; font-size: 0.75rem !important; }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.35rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em;
  }

  [data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--surface) !important;
    box-shadow: 0 1px 2px rgba(10,10,10,0.03);
  }
  [data-testid="stExpander"] summary {
    font-weight: 500 !important;
    font-size: 0.9rem !important;
  }

  [data-testid="stStatus"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--surface) !important;
  }

  .stProgress > div > div > div > div {
    background: #171717 !important;
    border-radius: 999px;
  }

  div[data-testid="stAlert"] {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
  }

  [data-testid="stSidebar"] {
    border-right: 1px solid var(--border);
    background: var(--surface);
  }

  iframe[title="streamlit dataframe"] { border-radius: var(--radius-sm) !important; }

  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow) !important;
    padding: 1.25rem 1.35rem !important;
    margin-bottom: 1rem !important;
  }

  div[data-testid="stDialog"] > div {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    box-shadow: 0 25px 50px -12px rgba(10, 10, 10, 0.2) !important;
    background: var(--surface) !important;
  }
  div[data-testid="stModal"] {
    backdrop-filter: blur(4px);
  }
</style>
        """,
        unsafe_allow_html=True,
    )


def play_success_sound():
    try:
        subprocess.run(
            ["afplay", "/System/Library/Sounds/Glass.aiff"], check=False
        )
    except Exception:
        pass


def open_in_finder(path: Path):
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def get_all_transcripts():
    transcripts = []
    if OUTPUT_DIR.exists():
        for md_file in OUTPUT_DIR.glob("**/*.md"):
            transcripts.append(
                {
                    "path": md_file,
                    "name": md_file.stem,
                    "topic": md_file.parent.parent.name,
                    "channel": md_file.parent.name,
                    "mtime": md_file.stat().st_mtime,
                }
            )
    return sorted(transcripts, key=lambda x: x["mtime"], reverse=True)


TOPICS_PATH = PROJECT_ROOT / "topics.json"


def save_topics_dict(topics: dict) -> None:
    TOPICS_PATH.write_text(
        json.dumps(topics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_output_topic_folders() -> list[str]:
    if not OUTPUT_DIR.is_dir():
        return []
    return sorted(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir())


def list_channels_in_topic_folder(topic: str) -> list[str]:
    p = OUTPUT_DIR / topic
    if not p.is_dir():
        return []
    return sorted(d.name for d in p.iterdir() if d.is_dir())


def list_transcripts_in_channel_folder(topic: str, channel_folder: str) -> list[Path]:
    p = OUTPUT_DIR / topic / channel_folder
    if not p.is_dir():
        return []
    return sorted(p.glob("*.md"))


def channel_name_for_topics_from_folder(channel_dir: Path) -> str:
    """Use YAML `channel` from a transcript if present; else folder name."""
    for md in sorted(channel_dir.glob("*.md")):
        try:
            head = md.read_text(encoding="utf-8", errors="replace")[:6000]
        except OSError:
            continue
        m = re.search(
            r'^\s*channel:\s*["\']?([^"\'\n#]+?)\s*["\']?\s*$',
            head,
            re.MULTILINE,
        )
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return channel_dir.name


def move_channel_to_topic(
    from_topic: str, channel_folder: str, to_topic_label: str
) -> tuple[bool, str]:
    """
    Move output/from_topic/channel_folder/ → output/<sanitized to_topic>/channel_folder/
    and update topics.json (remove channel from old lists, add to new).
    """
    to_topic_label = to_topic_label.strip()
    if not to_topic_label:
        return False, "Enter a target topic"
    if from_topic == to_topic_label:
        return False, "Source and target topic are the same"

    src = OUTPUT_DIR / from_topic / channel_folder
    if not src.is_dir():
        return False, f"Not found: {from_topic}/{channel_folder}"

    dst_parent = OUTPUT_DIR / transcribe.sanitize_filename(to_topic_label)
    dst = dst_parent / channel_folder
    dst_parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        mds = list(src.glob("*.md"))
        if not mds:
            return False, "Source has no .md files"
        for f in mds:
            if (dst / f.name).exists():
                return (
                    False,
                    f"Target already contains {f.name} — move or delete one copy first.",
                )
        for f in mds:
            shutil.move(str(f), str(dst / f.name))
        try:
            if not any(src.iterdir()):
                src.rmdir()
        except OSError:
            pass
    else:
        shutil.move(str(src), str(dst))

    try:
        old_root = OUTPUT_DIR / from_topic
        if old_root.is_dir() and not any(old_root.iterdir()):
            old_root.rmdir()
    except OSError:
        pass

    ch_json = channel_name_for_topics_from_folder(dst)
    topics = transcribe.load_topics()
    for t, chs in list(topics.items()):
        if chs:
            topics[t] = [c for c in chs if c not in (ch_json, channel_folder)]
    if to_topic_label not in topics:
        topics[to_topic_label] = []
    if ch_json not in topics[to_topic_label]:
        topics[to_topic_label].append(ch_json)
    save_topics_dict(topics)
    return True, f"Moved to **{to_topic_label}** / **{channel_folder}** ({len(list(dst.glob('*.md')))} files)."


def move_selected_transcripts_to_topic(
    from_topic: str,
    channel_folder: str,
    filenames: list[str],
    to_topic_label: str,
) -> tuple[bool, str]:
    """
    Move selected markdown files only.
    This reorganizes existing transcripts but does not change future channel mapping
    in topics.json, because mapping is channel-level.
    """
    to_topic_label = to_topic_label.strip()
    if not to_topic_label:
        return False, "Enter a target topic"
    if not filenames:
        return False, "Select at least one transcript"

    src_dir = OUTPUT_DIR / from_topic / channel_folder
    if not src_dir.is_dir():
        return False, f"Not found: {from_topic}/{channel_folder}"

    dst_parent = OUTPUT_DIR / transcribe.sanitize_filename(to_topic_label)
    dst_dir = dst_parent / channel_folder
    dst_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for name in filenames:
        src = src_dir / name
        dst = dst_dir / name
        if not src.is_file():
            return False, f"Missing file: {name}"
        if dst.exists():
            return False, f"Target already contains {name}"
    for name in filenames:
        shutil.move(str(src_dir / name), str(dst_dir / name))
        moved += 1

    try:
        if src_dir.is_dir() and not any(src_dir.iterdir()):
            src_dir.rmdir()
    except OSError:
        pass
    try:
        old_root = OUTPUT_DIR / from_topic
        if old_root.is_dir() and not any(old_root.iterdir()):
            old_root.rmdir()
    except OSError:
        pass

    return (
        True,
        f"Moved **{moved}** selected transcript(s) to **{to_topic_label}** / **{channel_folder}**. "
        "Future uploads from this channel still follow its current topic mapping.",
    )


def run_transcription_pipeline(
    url: str,
    limit: int,
    model: str,
    force_whisper: bool,
    force_reprocess: bool,
) -> dict:
    """Run yt-dlp + process loop with progress UI (expects URL already allowed)."""
    url = url.strip()
    is_single = "watch?v=" in url or "youtu.be/" in url or "shorts/" in url
    if is_single:
        videos = [{"url": url, "title": "", "id": ""}]
    else:
        videos = transcribe.get_video_list(url, limit)
    return run_video_batch(
        videos=videos,
        model=model,
        force_whisper=force_whisper,
        force_reprocess=force_reprocess,
        source_url=url,
    )


def run_video_batch(
    videos: list[dict],
    model: str,
    force_whisper: bool,
    force_reprocess: bool,
    source_url: str = "",
) -> dict:
    """Run a specific batch of videos and return a retryable summary."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_container = st.empty()
    logs = []

    def update_logs(msg):
        logs.append(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")
        log_container.markdown(
            '<div class="yt-log">' + "<br>".join(logs[::-1]) + "</div>",
            unsafe_allow_html=True,
        )

    with st.status("Running…", expanded=True) as status:
        update_logs("Analyzing URL…")
        if not videos:
            st.error("No videos found for that URL.")
            summary = {
                "total": 0,
                "success": 0,
                "failed": [],
                "model": model,
                "force_whisper": force_whisper,
                "force_reprocess": force_reprocess,
                "source_url": source_url,
            }
            st.session_state["last_run_summary"] = summary
            return summary

        success_count = 0
        failed_videos = []
        for i, vid in enumerate(videos):
            current_title = vid.get("title", "Video")
            status_text.markdown(
                f"**Step {i + 1} of {len(videos)}** · {current_title}"
            )
            progress_bar.progress((i) / max(len(videos), 1))
            update_logs(f"Starting: {current_title}")
            ok = transcribe.process_video(
                vid["url"],
                str(OUTPUT_DIR),
                force_whisper,
                model,
                log_callback=update_logs,
                force=force_reprocess,
            )
            if ok:
                success_count += 1
            else:
                failed_videos.append(
                    {
                        "url": vid.get("url", ""),
                        "title": current_title,
                        "id": vid.get("id", ""),
                    }
                )

        progress_bar.progress(1.0)
        if failed_videos:
            status.update(
                label=f"Finished with issues · {success_count} saved, {len(failed_videos)} failed",
                state="error",
            )
        else:
            status.update(
                label=f"Complete · {success_count} of {len(videos)} saved",
                state="complete",
            )
            play_success_sound()
            st.balloons()

    summary = {
        "total": len(videos),
        "success": success_count,
        "failed": failed_videos,
        "model": model,
        "force_whisper": force_whisper,
        "force_reprocess": force_reprocess,
        "source_url": source_url,
    }
    st.session_state["last_run_summary"] = summary
    return summary


@st.dialog("Map this channel")
def map_channel_modal(pm: dict):
    """Modal: assign YouTube channel to a topic, then auto-run the pending job."""
    st.markdown(
        f"**{pm['channel']}** isn’t in any topic yet. "
        "Choose where to file it — we’ll save `topics.json` and start the job."
    )
    topics_dict = transcribe.load_topics()
    topic_names = sorted(topics_dict.keys())
    map_mode = st.radio(
        "How do you want to map it?",
        ["Add to existing topic", "Create new topic"],
        horizontal=True,
        key="modal_map_mode",
    )
    target_topic = None
    new_topic_txt = ""
    if map_mode == "Add to existing topic":
        if topic_names:
            target_topic = st.selectbox(
                "Topic folder",
                topic_names,
                key="modal_map_select",
            )
        else:
            st.info("No topics yet — use **Create new topic**.")
    else:
        new_topic_txt = st.text_input(
            "New topic name",
            placeholder="e.g. DevOps, Product strategy",
            key="modal_map_new",
        )

    b1, b2 = st.columns(2)
    with b1:
        save_run = st.button(
            "Save & run job",
            type="primary",
            use_container_width=True,
            key="modal_save_run",
        )
    with b2:
        dismiss = st.button("Cancel", use_container_width=True, key="modal_dismiss")

    if dismiss:
        st.session_state.pop("pending_topic_map", None)
        st.rerun()

    if save_run:
        ch = pm["channel"]
        t = dict(transcribe.load_topics())
        if map_mode == "Create new topic":
            nt = (new_topic_txt or "").strip()
            if not nt:
                st.error("Enter a name for the new topic.")
            else:
                if nt not in t:
                    t[nt] = []
                if ch not in t[nt]:
                    t[nt].append(ch)
                save_topics_dict(t)
                st.session_state.pop("pending_topic_map", None)
                st.session_state["auto_run_job"] = pm
                st.rerun()
        else:
            if not topic_names:
                st.error("Create a topic first (use **Create new topic**).")
            elif not target_topic:
                st.error("Select a topic folder.")
            else:
                if ch not in t[target_topic]:
                    t[target_topic].append(ch)
                save_topics_dict(t)
                st.session_state.pop("pending_topic_map", None)
                st.session_state["auto_run_job"] = pm
                st.rerun()


inject_styles()

with st.sidebar:
    st.markdown(
        '<p class="yt-kicker" style="margin-top:0">Workspace</p>',
        unsafe_allow_html=True,
    )
    st.markdown("**Transcriber**")
    st.caption("Runs locally · no API keys for capture")

    st.divider()

    if st.button("Open output folder", use_container_width=True):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        open_in_finder(OUTPUT_DIR)

    if st.button("Open project folder", use_container_width=True):
        open_in_finder(PROJECT_ROOT)

    st.caption(
        f"Output: `{OUTPUT_DIR.relative_to(PROJECT_ROOT)}` — Markdown files appear here automatically."
    )

    st.divider()
    st.markdown("**Folders**")
    st.caption(
        "Topic = top folder · Channel = subfolder · one `.md` per video. "
        "You create **topics** on the Topics tab; the app creates folders when you run a job."
    )
    allow_uncategorized = st.checkbox(
        "Allow Uncategorized",
        value=False,
        help="When off, transcription will not start if the channel is not listed under any topic.",
        key="allow_uncategorized",
    )

st.markdown(
    """
<div class="yt-hero">
  <p class="yt-kicker">Local · LLM-ready</p>
  <h1 class="yt-title">Turn YouTube into knowledge</h1>
  <p class="yt-sub">Paste a link, pull subtitles or Whisper, and save structured markdown—organized by topic—without touching the terminal for day-to-day use.</p>
</div>
""",
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["Transcribe", "Library", "Topics", "System"]
)

with tab1:
    if st.session_state.get("pending_topic_map"):
        map_channel_modal(st.session_state["pending_topic_map"])

    col_main, col_side = st.columns([1.65, 1], gap="large")

    with col_main:
        auto_job = st.session_state.pop("auto_run_job", None)
        if auto_job:
            st.success(
                f"Saved **{auto_job['channel']}** to a topic — running your job…"
            )
            run_transcription_pipeline(
                auto_job["url"],
                auto_job["limit"],
                auto_job["model"],
                auto_job["force_whisper"],
                auto_job["force_reprocess"],
            )

        last_run_summary = st.session_state.get("last_run_summary")
        if last_run_summary and last_run_summary.get("total", 0) > 0:
            with card():
                failed = last_run_summary.get("failed", [])
                failed_count = len(failed)
                success_count = last_run_summary.get("success", 0)
                total_count = last_run_summary.get("total", 0)
                st.markdown("### Last run")
                if failed_count:
                    st.warning(
                        f"{success_count} saved, {failed_count} failed out of {total_count}."
                    )
                    st.caption("Failed videos")
                    for item in failed[:10]:
                        st.caption(f"• {item.get('title', 'Video')}")
                    if failed_count > 10:
                        st.caption(f"+ {failed_count - 10} more")
                    if st.button(
                        "Retry failed",
                        type="primary",
                        use_container_width=True,
                        key="retry_failed_videos",
                    ):
                        run_video_batch(
                            videos=failed,
                            model=last_run_summary.get("model", "base"),
                            force_whisper=last_run_summary.get("force_whisper", False),
                            force_reprocess=last_run_summary.get("force_reprocess", False),
                            source_url=last_run_summary.get("source_url", ""),
                        )
                else:
                    st.success(f"All {total_count} video(s) saved successfully.")

        with card():
            st.markdown("### New job")
            st.caption(
                "Saves to **output / Topic / Channel / title.md**. "
                "If the channel is new, a **modal** will ask you to pick a topic (or use the **Topics** tab)."
            )
            url = st.text_input(
                "YouTube URL",
                placeholder="Video, playlist, or channel URL",
                label_visibility="visible",
            )
            r1, r2 = st.columns(2)
            with r1:
                limit = st.number_input(
                    "Max videos", min_value=1, value=5, step=1
                )
            with r2:
                model = st.selectbox(
                    "Whisper model (fallback)",
                    ["tiny", "base", "small", "medium"],
                    index=1,
                )
            opt1, opt2 = st.columns(2)
            with opt1:
                force_whisper = st.checkbox(
                    "Force Whisper",
                    help="Skip YouTube captions and transcribe locally (slower).",
                )
            with opt2:
                force_reprocess = st.checkbox(
                    "Reprocess saved",
                    help="Ignore skip rules and overwrite when possible.",
                )

            run = st.button(
                "Start processing", type="primary", use_container_width=True
            )

        if run:
            if not url or not url.strip():
                st.error("Add a URL to continue.")
            else:
                url = url.strip()
                is_single = (
                    "watch?v=" in url
                    or "youtu.be/" in url
                    or "shorts/" in url
                )
                ch, topic, prev_err = transcribe.preview_categorization(
                    url, is_single, limit
                )
                if prev_err:
                    st.error(prev_err)
                    st.stop()
                if topic == "Uncategorized" and not allow_uncategorized:
                    st.session_state["pending_topic_map"] = {
                        "channel": ch,
                        "url": url.strip(),
                        "limit": int(limit),
                        "model": model,
                        "force_whisper": force_whisper,
                        "force_reprocess": force_reprocess,
                    }
                    st.rerun()
                if topic != "Uncategorized":
                    st.success(f"Will save under **{topic}** → **{ch}**")
                elif allow_uncategorized:
                    st.info(
                        "Will save under **Uncategorized** (no topic mapping for this channel)."
                    )
                run_transcription_pipeline(
                    url=url,
                    limit=int(limit),
                    model=model,
                    force_whisper=force_whisper,
                    force_reprocess=force_reprocess,
                )

    with col_side:
        with card():
            st.markdown("### At a glance")
            all_ts = get_all_transcripts()
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Transcripts", len(all_ts))
            with m2:
                st.metric("In library DB", len(transcribe.load_state()))
            if all_ts:
                st.markdown("**Recent**")
                for ts in all_ts[:5]:
                    st.caption(f"{ts['name'][:48]}…")
            else:
                st.caption("Nothing yet—run a job to populate your library.")

        with card():
            st.markdown("### Files")
            st.caption(
                "Saved as topic → channel → title. Use the sidebar to open the folder."
            )

with tab2:
    with card():
        st.markdown("### Recategorize")
        st.caption(
            "Move either a whole **channel** folder or only the **selected transcripts**. "
            "Whole-channel moves update future mapping in `topics.json`; selected-file moves only reorganize existing files."
        )
        topic_dirs = list_output_topic_folders()
        if not topic_dirs:
            st.info("Nothing in `output/` yet.")
        else:
            rc1, rc2 = st.columns(2)
            with rc1:
                from_rec = st.selectbox(
                    "From topic",
                    topic_dirs,
                    key="recat_from_topic",
                )
            chans = list_channels_in_topic_folder(from_rec)
            with rc2:
                channel_pick = st.selectbox(
                    "Channel folder",
                    chans if chans else ["(empty)"],
                    disabled=not chans,
                    key="recat_channel",
                )
            files_in_channel = (
                list_transcripts_in_channel_folder(from_rec, channel_pick)
                if chans and channel_pick != "(empty)"
                else []
            )
            move_scope = st.radio(
                "What do you want to move?",
                ["Entire channel", "Selected transcripts"],
                horizontal=True,
                key="recat_scope",
            )
            if move_scope == "Selected transcripts":
                st.multiselect(
                    "Transcripts",
                    [p.name for p in files_in_channel],
                    format_func=lambda name: Path(name).stem,
                    key="recat_selected_files",
                    placeholder="Choose one or more transcripts",
                )
            existing_topics = sorted(transcribe.load_topics().keys())
            how = st.radio(
                "Move to",
                ["Existing topic", "New topic"],
                horizontal=True,
                key="recat_how",
            )
            if how == "Existing topic":
                if existing_topics:
                    st.selectbox(
                        "Target topic",
                        existing_topics,
                        key="recat_target_existing",
                    )
                else:
                    st.warning("No topics in `topics.json` — choose **New topic** above.")
            else:
                st.text_input(
                    "New topic name",
                    placeholder="e.g. Stanford HCI, AI & Learning",
                    key="recat_target_new",
                )
            if st.button(
                "Apply recategorization",
                type="primary",
                key="recat_btn",
            ):
                if not chans or channel_pick == "(empty)":
                    st.error("Pick a channel folder that has files.")
                else:
                    mode = st.session_state.get("recat_how", "Existing topic")
                    if mode == "Existing topic":
                        tl = (st.session_state.get("recat_target_existing") or "").strip()
                    else:
                        tl = (st.session_state.get("recat_target_new") or "").strip()
                    if not tl:
                        st.error("Choose or enter a target topic.")
                    else:
                        from_f = st.session_state.get("recat_from_topic", from_rec)
                        chn = st.session_state.get("recat_channel", channel_pick)
                        scope = st.session_state.get("recat_scope", "Entire channel")
                        if scope == "Entire channel":
                            ok_rec, msg_rec = move_channel_to_topic(from_f, chn, tl)
                        else:
                            selected = st.session_state.get("recat_selected_files", [])
                            ok_rec, msg_rec = move_selected_transcripts_to_topic(
                                from_f, chn, selected, tl
                            )
                        if ok_rec:
                            st.success(msg_rec)
                            st.rerun()
                        else:
                            st.error(msg_rec)

    with card():
        st.markdown("### Library")
        all_ts = get_all_transcripts()
        if not all_ts:
            st.info("No transcripts yet. Run a job on the Transcribe tab.")
        else:
            search = st.text_input(
                "Search", placeholder="Filter by title or channel…"
            )
            q = (search or "").lower()
            filtered = (
                all_ts
                if not q
                else [
                    t
                    for t in all_ts
                    if q in t["name"].lower() or q in t["channel"].lower()
                ]
            )
            st.caption(f"{len(filtered)} file(s)")

            if filtered:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for ts in filtered:
                        arc = (
                            f"{ts['topic']}/{ts['channel']}/{ts['path'].name}"
                        )
                        zf.write(ts["path"], arcname=arc)
                zip_buf.seek(0)
                st.download_button(
                    label="Download all shown as ZIP",
                    data=zip_buf.getvalue(),
                    file_name="transcripts.zip",
                    mime="application/zip",
                    use_container_width=False,
                    key="download_zip_filtered",
                )

            for ts in filtered:
                title = f"{ts['topic']} · {ts['channel']} · {ts['name']}"
                with st.expander(title[:120]):
                    path_key = hashlib.md5(
                        str(ts["path"]).encode(), usedforsecurity=False
                    ).hexdigest()[:20]
                    st.download_button(
                        label="Download this file (.md)",
                        data=ts["path"].read_bytes(),
                        file_name=ts["path"].name,
                        mime="text/markdown; charset=utf-8",
                        key=f"dl_md_{path_key}",
                        use_container_width=True,
                    )
                    content = ts["path"].read_text(encoding="utf-8")
                    st.markdown(content)

with tab3:
    with card():
        st.markdown("### Topics")
        st.caption(
            "Map exact YouTube channel display names to folders. "
            "Unlisted channels land in **Uncategorized**."
        )
        topics = transcribe.load_topics()
        new_topic = st.text_input("New topic name")
        if st.button("Add topic", use_container_width=False):
            nt = (new_topic or "").strip()
            if nt and nt not in topics:
                topics[nt] = []
                (PROJECT_ROOT / "topics.json").write_text(
                    json.dumps(topics, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                st.success("Topic added.")
                st.rerun()
            elif not nt:
                st.warning("Enter a topic name.")

        for topic_name, channels in sorted(topics.items()):
            with st.expander(f"{topic_name} · {len(channels)} channels"):
                for chan in channels:
                    st.text(chan)
                add_key = f"add_{topic_name}".replace(" ", "_")[:40]
                c_add = st.text_input(
                    "Add channel (exact name on YouTube)",
                    key=add_key,
                    label_visibility="collapsed",
                    placeholder=f"Channel display name → {topic_name}",
                )
                if st.button("Add to topic", key=f"btn_{add_key}"):
                    if c_add and c_add not in topics[topic_name]:
                        topics[topic_name].append(c_add)
                        (PROJECT_ROOT / "topics.json").write_text(
                            json.dumps(topics, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        st.rerun()

with tab4:
    with card():
        st.markdown("### Environment")
        for row in transcribe.health_check():
            icon = "●" if row["ok"] else "○"
            color = "#171717" if row["ok"] else "#b45309"
            st.markdown(
                f'<p style="margin:0.35rem 0;font-size:0.9rem;color:{color}">'
                f"<strong>{icon}</strong> &nbsp;{row['name']} — "
                f'<span style="color:#737373">{row["detail"]}</span></p>',
                unsafe_allow_html=True,
            )

    with card():
        st.markdown("### Catch up on a channel or playlist")
        st.caption(
            "List recent uploads and transcribe one that is not in your library yet."
        )
        catch_url = st.text_input("Channel or playlist URL", key="catch_url")
        catch_limit = st.number_input("How many recent", min_value=1, value=15)

        if st.button("List recent videos"):
            if not catch_url or not str(catch_url).strip():
                st.warning("Enter a URL first.")
            else:
                with st.spinner("Fetching…"):
                    try:
                        st.session_state["catch_list"] = (
                            transcribe.list_unprocessed_videos(
                                str(catch_url).strip(), int(catch_limit)
                            )
                        )
                    except Exception as e:
                        st.error(str(e))

        rows = st.session_state.get("catch_list") or []
        if rows:
            st.dataframe(
                [
                    {
                        "New": "No" if r["processed"] else "Yes",
                        "Title": (r.get("title") or "")[:120],
                        "ID": r.get("id") or "",
                    }
                    for r in rows
                ],
                use_container_width=True,
                hide_index=True,
            )
            pending = [r for r in rows if not r["processed"] and r.get("url")]
            if pending:
                labels = [
                    f"{(r.get('title') or '')[:65]}… ({r.get('id', '')})"
                    for r in pending
                ]
                pick = st.selectbox(
                    "Choose a video",
                    range(len(pending)),
                    format_func=lambda i: labels[i],
                )
                whisper_model = st.selectbox(
                    "Whisper model (fallback)",
                    ["tiny", "base", "small"],
                    index=1,
                    key="catch_whisper",
                )
                log_box = st.empty()
                if st.button("Transcribe selection", type="primary"):
                    one_url = pending[pick]["url"]
                    ch, topic, prev_err = transcribe.preview_categorization(
                        one_url, True, 1
                    )
                    if prev_err:
                        st.error(prev_err)
                    elif topic == "Uncategorized" and not allow_uncategorized:
                        st.error(
                            f"**{ch}** is not mapped to any topic. "
                            "Add it under **Topics** or enable **Allow Uncategorized** in the sidebar."
                        )
                    else:

                        def log_cb(msg):
                            log_box.code(msg)

                        ok = transcribe.process_video(
                            one_url,
                            str(OUTPUT_DIR),
                            False,
                            whisper_model,
                            log_callback=log_cb,
                            force=False,
                        )
                        if ok:
                            st.success("Saved to your library.")
                            play_success_sound()
                            st.session_state["catch_list"] = None
                            st.rerun()
                        else:
                            st.error("Could not complete. See log above.")
