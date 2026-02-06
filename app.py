import streamlit as st
import os
import json
from pathlib import Path
import transcribe
from datetime import datetime

st.set_page_config(page_title="YouTube Transcriber", page_icon="📺", layout="wide")

st.title("📺 YouTube Transcriber")
st.markdown("Download, transcribe, and organize YouTube videos for your LLM knowledge base.")

# Sidebar for Topic Management
with st.sidebar:
    st.header("Topic Management")
    topics = transcribe.load_topics()
    
    new_topic = st.text_input("Add New Topic")
    if st.button("Create Topic") and new_topic:
        if new_topic not in topics:
            topics[new_topic] = []
            with open('topics.json', 'w') as f:
                json.dump(topics, f, indent=2)
            st.success(f"Topic '{new_topic}' added!")
            st.rerun()

    st.divider()
    st.subheader("Current Mappings")
    for topic, channels in topics.items():
        with st.expander(f"{topic} ({len(channels)})"):
            for channel in channels:
                st.text(f"• {channel}")
            
            chan_to_add = st.text_input(f"Add channel to {topic}", key=f"add_{topic}")
            if st.button("Add", key=f"btn_{topic}"):
                if chan_to_add and chan_to_add not in topics[topic]:
                    topics[topic].append(chan_to_add)
                    with open('topics.json', 'w') as f:
                        json.dump(topics, f, indent=2)
                    st.success(f"Added {chan_to_add}")
                    st.rerun()

# Main Interface
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Transcribe New Content")
    url = st.text_input("YouTube URL", placeholder="Video, Playlist, or Channel URL")
    
    c1, c2 = st.columns(2)
    with c1:
        limit = st.number_input("Limit videos (for playlists/channels)", min_value=1, value=5)
    with c2:
        model = st.selectbox("Whisper Model (Fallback)", ["tiny", "base", "small", "medium"], index=1)
    
    force_whisper = st.checkbox("Force local Whisper transcription")
    
    if st.button("🚀 Start Processing", type="primary"):
        if not url:
            st.error("Please enter a URL")
        else:
            output_area = st.empty()
            log_area = st.empty()
            
            with st.status("Processing...", expanded=True) as status:
                # Determine if single video or collection
                is_single = 'watch?v=' in url or 'youtu.be/' in url or 'shorts/' in url
                
                if is_single:
                    videos = [{'url': url, 'title': '', 'id': ''}]
                else:
                    st.write("🔍 Fetching video list...")
                    videos = transcribe.get_video_list(url, limit)
                
                if not videos:
                    st.error("No videos found.")
                else:
                    success_count = 0
                    for i, vid in enumerate(videos):
                        st.write(f"Processing [{i+1}/{len(videos)}]: {vid.get('title', vid['url'])}")
                        try:
                            # We'll call the process_video function from transcribe.py
                            # Note: In a real app, we'd want to capture stdout, but for now we just run it
                            ok = transcribe.process_video(vid['url'], './output', force_whisper, model)
                            if ok:
                                success_count += 1
                        except Exception as e:
                            st.error(f"Error: {e}")
                    
                    status.update(label=f"Finished! {success_count}/{len(videos)} videos processed.", state="complete")
                    st.balloons()

with col2:
    st.subheader("Recent Outputs")
    output_path = Path("./output")
    if output_path.exists():
        for topic_dir in sorted(output_path.iterdir()):
            if topic_dir.is_dir():
                with st.expander(f"📁 {topic_dir.name}"):
                    for channel_dir in sorted(topic_dir.iterdir()):
                        if channel_dir.is_dir():
                            st.markdown(f"**{channel_dir.name}**")
                            for md_file in sorted(channel_dir.glob("*.md")):
                                st.text(f"📄 {md_file.name}")
    else:
        st.info("No outputs yet. Start transcribing to see files here.")
