import streamlit as st
import os
import json
import subprocess
from pathlib import Path
import transcribe
from datetime import datetime

st.set_page_config(page_title="YouTube Transcriber", page_icon="📺", layout="wide")

# Custom CSS for a better look
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #ef4444;
    }
    .log-container {
        background-color: #1e1e1e;
        color: #00ff00;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        height: 200px;
        overflow-y: auto;
        font-size: 0.8rem;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

def play_success_sound():
    try:
        # macOS native sound
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
    except:
        pass

def get_all_transcripts():
    output_path = Path("./output")
    transcripts = []
    if output_path.exists():
        for md_file in output_path.glob("**/*.md"):
            transcripts.append({
                "path": md_file,
                "name": md_file.stem,
                "topic": md_file.parent.parent.name,
                "channel": md_file.parent.name,
                "mtime": md_file.stat().st_mtime
            })
    return sorted(transcripts, key=lambda x: x['mtime'], reverse=True)

# --- APP LAYOUT ---
st.title("📺 YouTube Transcriber")

tab1, tab2, tab3 = st.tabs(["🚀 Transcribe", "📚 Library", "⚙️ Topics"])

# --- TAB 1: TRANSCRIBE ---
with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("New Transcription")
        url = st.text_input("YouTube URL", placeholder="Video, Playlist, or Channel URL")
        
        c1, c2 = st.columns(2)
        with c1:
            limit = st.number_input("Limit videos", min_value=1, value=5)
        with c2:
            model = st.selectbox("Whisper Model", ["tiny", "base", "small", "medium"], index=1)
        
        force_whisper = st.checkbox("Force local Whisper (slower, but works if auto-subs fail)")
        
        if st.button("🚀 Start Processing", type="primary", use_container_width=True):
            if not url:
                st.error("Please enter a URL")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_container = st.empty()
                logs = []

                def update_logs(msg):
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                    log_container.markdown(f'<div class="log-container">{"<br>".join(logs[::-1])}</div>', unsafe_allow_html=True)

                with st.status("Working...", expanded=True) as status:
                    update_logs("🔍 Analyzing URL...")
                    is_single = 'watch?v=' in url or 'youtu.be/' in url or 'shorts/' in url
                    
                    if is_single:
                        videos = [{'url': url, 'title': '', 'id': ''}]
                    else:
                        videos = transcribe.get_video_list(url, limit)
                    
                    if not videos:
                        st.error("No videos found.")
                    else:
                        success_count = 0
                        for i, vid in enumerate(videos):
                            current_title = vid.get('title', 'Video')
                            status_text.markdown(f"**Processing {i+1}/{len(videos)}:** {current_title}")
                            progress_bar.progress((i) / len(videos))
                            
                            update_logs(f"Starting: {current_title}")
                            
                            ok = transcribe.process_video(
                                vid['url'], 
                                './output', 
                                force_whisper, 
                                model,
                                log_callback=update_logs
                            )
                            if ok:
                                success_count += 1
                        
                        progress_bar.progress(1.0)
                        status.update(label=f"Finished! {success_count}/{len(videos)} processed.", state="complete")
                        play_success_sound()
                        st.balloons()

    with col2:
        st.subheader("Quick Stats")
        all_ts = get_all_transcripts()
        st.metric("Total Transcripts", len(all_ts))
        
        if all_ts:
            st.write("**Latest Additions:**")
            for ts in all_ts[:5]:
                st.caption(f"• {ts['name'][:40]}...")

# --- TAB 2: LIBRARY ---
with tab2:
    st.subheader("Browse Your Transcripts")
    all_ts = get_all_transcripts()
    
    if not all_ts:
        st.info("Your library is empty. Start transcribing to see files here.")
    else:
        # Search and Filter
        search = st.text_input("🔍 Search transcripts...", "")
        
        filtered = [t for t in all_ts if search.lower() in t['name'].lower() or search.lower() in t['channel'].lower()]
        
        for ts in filtered:
            with st.expander(f"📄 {ts['topic']} / {ts['channel']} / {ts['name']}"):
                col_a, col_b = st.columns([4, 1])
                with col_b:
                    if st.button("📋 Copy", key=f"copy_{ts['path']}"):
                        st.write("Copied! (Simulated)") # Streamlit doesn't have native clipboard yet
                
                content = ts['path'].read_text()
                st.markdown(content)

# --- TAB 3: TOPICS ---
with tab3:
    st.subheader("Manage Topics & Channels")
    topics = transcribe.load_topics()
    
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        new_topic = st.text_input("Add New Topic")
        if st.button("Create Topic") and new_topic:
            if new_topic not in topics:
                topics[new_topic] = []
                with open('topics.json', 'w') as f:
                    json.dump(topics, f, indent=2)
                st.success(f"Topic '{new_topic}' added!")
                st.rerun()

    with col_t2:
        st.write("**Current Mappings**")
        for topic, channels in topics.items():
            with st.expander(f"📁 {topic} ({len(channels)} channels)"):
                for chan in channels:
                    st.text(f"• {chan}")
                
                c_add = st.text_input(f"Add channel to {topic}", key=f"add_chan_{topic}")
                if st.button("Add", key=f"btn_add_{topic}"):
                    if c_add and c_add not in topics[topic]:
                        topics[topic].append(c_add)
                        with open('topics.json', 'w') as f:
                            json.dump(topics, f, indent=2)
                        st.success(f"Added {c_add}")
                        st.rerun()
