#!/usr/bin/env python3
"""Background worker for local transcription jobs."""

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import transcribe

PROJECT_ROOT = Path(__file__).resolve().parent
JOBS_DIR = PROJECT_ROOT / "jobs"


def now():
    return datetime.utcnow().isoformat() + "Z"


def job_path(job_id):
    return JOBS_DIR / f"{job_id}.json"


def log_path(job_id):
    return JOBS_DIR / f"{job_id}.log"


def read_job(job_id):
    return json.loads(job_path(job_id).read_text(encoding="utf-8"))


def write_job(job):
    job["updated_at"] = now()
    path = job_path(job["id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def append_log(job_id, message):
    line = f"{datetime.now().strftime('%H:%M:%S')}  {message}\n"
    with log_path(job_id).open("a", encoding="utf-8") as f:
        f.write(line)


def videos_from_url(url, limit):
    is_single = "watch?v=" in url or "youtu.be/" in url or "shorts/" in url
    if is_single:
        return [{"url": url, "title": "", "id": ""}]
    return transcribe.get_video_list(url, limit)


def run_transcribe_job(job):
    payload = job["payload"]
    if job["kind"] == "transcribe_url":
        videos = videos_from_url(payload["url"], payload.get("limit"))
    else:
        videos = payload.get("videos", [])

    job["status"] = "running"
    job["total"] = len(videos)
    job["success"] = 0
    job["failed"] = []
    write_job(job)

    if not videos:
        job["status"] = "failed"
        job["error"] = "No videos found for that URL."
        write_job(job)
        append_log(job["id"], "[!] No videos found")
        return

    for idx, vid in enumerate(videos, start=1):
        title = vid.get("title") or vid.get("url") or "Video"
        job["current"] = {"index": idx, "title": title}
        write_job(job)
        append_log(job["id"], f"[{idx}/{len(videos)}] {title}")

        ok = transcribe.process_video(
            vid["url"],
            payload.get("output_dir", str(PROJECT_ROOT / "output")),
            payload.get("force_whisper", False),
            payload.get("model", "base"),
            log_callback=lambda msg: append_log(job["id"], msg),
            force=payload.get("force_reprocess", False),
        )
        if ok:
            job["success"] += 1
        else:
            job["failed"].append(
                {
                    "url": vid.get("url", ""),
                    "title": title,
                    "id": vid.get("id", ""),
                }
            )
        write_job(job)

    job["status"] = "completed_with_errors" if job["failed"] else "completed"
    job["completed_at"] = now()
    write_job(job)


def run_rerun_files_job(job):
    payload = job["payload"]
    files = payload.get("files", [])
    job["status"] = "running"
    job["total"] = len(files)
    job["success"] = 0
    job["failed"] = []
    write_job(job)

    if not files:
        job["status"] = "failed"
        job["error"] = "No files selected."
        write_job(job)
        append_log(job["id"], "[!] No files selected")
        return

    for idx, file_path in enumerate(files, start=1):
        path = Path(file_path)
        job["current"] = {"index": idx, "title": path.name}
        write_job(job)
        append_log(job["id"], f"[{idx}/{len(files)}] {path.name}")

        ok = transcribe.rerun_markdown_file(
            path,
            force_whisper=payload.get("force_whisper", False),
            model_size=payload.get("model", "base"),
            log_callback=lambda msg: append_log(job["id"], msg),
        )
        if ok:
            job["success"] += 1
        else:
            job["failed"].append({"path": str(path), "title": path.name})
        write_job(job)

    job["status"] = "completed_with_errors" if job["failed"] else "completed"
    job["completed_at"] = now()
    write_job(job)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: job_worker.py <job_id>")
    job_id = sys.argv[1]
    job = read_job(job_id)
    append_log(job_id, f"Worker started ({job['kind']})")
    try:
        if job["kind"] in {"transcribe_url", "videos"}:
            run_transcribe_job(job)
        elif job["kind"] == "rerun_files":
            run_rerun_files_job(job)
        else:
            job["status"] = "failed"
            job["error"] = f"Unknown job kind: {job['kind']}"
            write_job(job)
    except Exception as exc:
        job = read_job(job_id)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["traceback"] = traceback.format_exc()
        job["completed_at"] = now()
        write_job(job)
        append_log(job_id, f"[!] Fatal error: {exc}")
    append_log(job_id, "Worker finished")


if __name__ == "__main__":
    main()
