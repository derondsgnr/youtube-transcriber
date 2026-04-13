import streamlit as st
import json
import subprocess
from pathlib import Path
import transcribe
from datetime import datetime

st.set_page_config(page_title="YouTube Transcriber", page_icon="📺", layout="wide")

st.markdown(
    """
    <style>
    .stProgress > div > div > div > div { background-color: #ef4444; }
    .log-container {
        background-color: #1e1e1e;
        color: #00ff00;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        height: 240px;
        overflow-y: auto;
        font-size: 0.8rem;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def play_success_sound():
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
    except Exception:
        pass


def get_all_transcripts():
    output_path = Path("./output")
    transcripts = []
    if output_path.exists():
        for md_file in output_path.glob("**/*.md"):
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


st.title("📺 YouTube Transcriber")

tab1, tab2, tab3, tab4 = st.tabs(
    ["🚀 Transcribe", "📚 Library", "⚙️ Topics", "🔧 Diagnostics & catch-up"]
)

with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("New transcription")
        url = st.text_input(
            "YouTube URL", placeholder="Video, playlist, or channel URL"
        )

        c1, c2 = st.columns(2)
        with c1:
            limit = st.number_input("Limit videos", min_value=1, value=5)
        with c2:
            model = st.selectbox(
                "Whisper model", ["tiny", "base", "small", "medium"], index=1
            )

        force_whisper = st.checkbox(
            "Force local Whisper (slower; use if subtitles missing or wrong)"
        )
        force_reprocess = st.checkbox(
            "Reprocess even if already saved (ignore skip / state)"
        )

        if st.button("🚀 Start processing", type="primary", use_container_width=True):
            if not url:
                st.error("Please enter a URL")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_container = st.empty()
                logs = []

                def update_logs(msg):
                    logs.append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
                    )
                    log_container.markdown(
                        '<div class="log-container">'
                        + "<br>".join(logs[::-1])
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                with st.status("Working...", expanded=True) as status:
                    update_logs("Analyzing URL…")
                    is_single = (
                        "watch?v=" in url
                        or "youtu.be/" in url
                        or "shorts/" in url
                    )

                    if is_single:
                        videos = [{"url": url, "title": "", "id": ""}]
                    else:
                        videos = transcribe.get_video_list(url, limit)

                    if not videos:
                        st.error("No videos found.")
                    else:
                        success_count = 0
                        for i, vid in enumerate(videos):
                            current_title = vid.get("title", "Video")
                            status_text.markdown(
                                f"**Processing {i+1}/{len(videos)}:** {current_title}"
                            )
                            progress_bar.progress((i) / max(len(videos), 1))

                            update_logs(f"Starting: {current_title}")

                            ok = transcribe.process_video(
                                vid["url"],
                                "./output",
                                force_whisper,
                                model,
                                log_callback=update_logs,
                                force=force_reprocess,
                            )
                            if ok:
                                success_count += 1

                        progress_bar.progress(1.0)
                        status.update(
                            label=f"Finished: {success_count}/{len(videos)} processed.",
                            state="complete",
                        )
                        play_success_sound()
                        st.balloons()

    with col2:
        st.subheader("Quick stats")
        all_ts = get_all_transcripts()
        st.metric("Total transcripts", len(all_ts))

        processed_n = len(transcribe.load_state())
        st.metric("Videos in state DB", processed_n)

        if all_ts:
            st.write("**Latest additions:**")
            for ts in all_ts[:5]:
                st.caption(f"• {ts['name'][:40]}…")

with tab2:
    st.subheader("Browse your transcripts")
    all_ts = get_all_transcripts()

    if not all_ts:
        st.info("Your library is empty. Start transcribing to see files here.")
    else:
        search = st.text_input("Search transcripts…", "")
        filtered = [
            t
            for t in all_ts
            if search.lower() in t["name"].lower()
            or search.lower() in t["channel"].lower()
        ]

        for ts in filtered:
            with st.expander(f"📄 {ts['topic']} / {ts['channel']} / {ts['name']}"):
                content = ts["path"].read_text(encoding="utf-8")
                st.markdown(content)

with tab3:
    st.subheader("Manage topics & channels")
    topics = transcribe.load_topics()

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        new_topic = st.text_input("Add new topic")
        if st.button("Create topic") and new_topic:
            if new_topic not in topics:
                topics[new_topic] = []
                with open("topics.json", "w", encoding="utf-8") as f:
                    json.dump(topics, f, indent=2, ensure_ascii=False)
                st.success(f"Topic “{new_topic}” added.")
                st.rerun()

    with col_t2:
        st.write("**Current mappings**")
        for topic, channels in topics.items():
            with st.expander(f"📁 {topic} ({len(channels)} channels)"):
                for chan in channels:
                    st.text(f"• {chan}")

                c_add = st.text_input(
                    f"Add channel to {topic}", key=f"add_chan_{topic}"
                )
                if st.button("Add", key=f"btn_add_{topic}"):
                    if c_add and c_add not in topics[topic]:
                        topics[topic].append(c_add)
                        with open("topics.json", "w", encoding="utf-8") as f:
                            json.dump(topics, f, indent=2, ensure_ascii=False)
                        st.success(f"Added {c_add}")
                        st.rerun()

with tab4:
    st.subheader("Environment checks")
    for row in transcribe.health_check():
        icon = "✅" if row["ok"] else "❌"
        st.markdown(f"{icon} **{row['name']}** — `{row['detail']}`")

    st.divider()
    st.subheader("Catch up: new videos on a channel or playlist")
    st.caption(
        "Paste a channel (`@handle` or `/channel/…`) or playlist URL. "
        "Lists recent uploads and whether each video ID is already in `state/processed.json`."
    )
    catch_url = st.text_input("Channel or playlist URL", key="catch_url")
    catch_limit = st.number_input("How many recent to list", min_value=1, value=15)

    if st.button("List recent videos"):
        if not catch_url.strip():
            st.warning("Enter a URL first.")
        else:
            with st.spinner("Fetching…"):
                try:
                    st.session_state["catch_list"] = transcribe.list_unprocessed_videos(
                        catch_url.strip(), int(catch_limit)
                    )
                except Exception as e:
                    st.error(str(e))

    rows = st.session_state.get("catch_list") or []
    if rows:
        st.dataframe(
            [
                {
                    "New?": "no" if r["processed"] else "yes",
                    "Title": (r.get("title") or "")[:100],
                    "Video ID": r.get("id") or "",
                }
                for r in rows
            ],
            use_container_width=True,
            hide_index=True,
        )
        pending = [r for r in rows if not r["processed"] and r.get("url")]
        if pending:
            labels = [f"{r.get('title', '')[:70]}… ({r.get('id', '')})" for r in pending]
            pick = st.selectbox("Transcribe one new video", range(len(pending)), format_func=lambda i: labels[i])
            whisper_model = st.selectbox("Whisper model (fallback)", ["tiny", "base", "small"], index=1, key="catch_whisper")
            log_box = st.empty()
            if st.button("Run transcription for selection"):
                def log_cb(msg):
                    log_box.code(msg)

                ok = transcribe.process_video(
                    pending[pick]["url"],
                    "./output",
                    False,
                    whisper_model,
                    log_callback=log_cb,
                    force=False,
                )
                if ok:
                    st.success("Done.")
                    play_success_sound()
                    st.session_state["catch_list"] = None
                    st.rerun()
                else:
                    st.error("Failed — see log above.")

    st.caption(
        "Transcripts: `output/<Topic>/<Channel>/<Title>.md`. "
        "Optional: copy `config.example.json` → `config.json` to tweak defaults."
    )
