"""Drive the whole personal-mode flow against a running backend.

Uploads a real video through the API, creates a task, waits for the worker,
then downloads the exported clip and inspects it with ffprobe.

    cd backend
    uv run python scripts/personal_e2e_check.py [--api http://127.0.0.1:8000]

Requires the API, worker, Postgres and Redis to be running (docker compose),
with the same BACKEND_AUTH_SECRET as the API and PERSONAL_USER_ID seeded.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "frontend/public/clips/articles/ton-1.mp4"


def auth_headers(user_id: str, secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), f"{user_id}:{timestamp}".encode(), hashlib.sha256
    ).hexdigest()
    return {
        "x-supoclip-user-id": user_id,
        "x-supoclip-ts": timestamp,
        "x-supoclip-signature": signature,
    }


def probe(path: Path) -> dict:
    data = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "duration": round(float(data["format"]["duration"]), 2),
        "bytes": int(data["format"]["size"]),
        "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--source", default=os.getenv("E2E_SOURCE", str(DEFAULT_SOURCE)))
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    user_id = os.getenv("PERSONAL_USER_ID", "personal-owner")
    secret = os.getenv("BACKEND_AUTH_SECRET", "")
    if not secret:
        print("FAIL: BACKEND_AUTH_SECRET is not set")
        return 2
    headers = auth_headers(user_id, secret)
    source = Path(args.source)
    if not source.is_file():
        print(f"FAIL: source video not found: {source}")
        return 2

    with httpx.Client(base_url=args.api, headers=headers, timeout=120) as client:
        health = client.get("/health")
        print(f"api health: {health.status_code}")

        with source.open("rb") as handle:
            upload = client.post(
                "/upload",
                files={"video": (source.name, handle, "video/mp4")},
            )
        if upload.status_code != 200:
            print(f"FAIL: upload {upload.status_code}: {upload.text[:300]}")
            return 3
        video_path = upload.json()["video_path"]
        print(f"uploaded: {video_path}")

        created = client.post(
            "/tasks/",
            json={
                "source": {"url": video_path},
                "font_options": {"font_family": "TikTokSans-Regular", "font_size": 24, "font_color": "#FFFFFF"},
                "caption_template": "default",
                "clip_length": "short",
                "output_format": "vertical",
                "add_subtitles": True,
                "processing_mode": "fast",
            },
        )
        if created.status_code not in (200, 201, 202):
            print(f"FAIL: create task {created.status_code}: {created.text[:500]}")
            return 4
        task_id = created.json()["task_id"]
        print(f"task: {task_id}")

        deadline = time.time() + args.timeout
        status = "pending"
        while time.time() < deadline:
            time.sleep(5)
            task = client.get(f"/tasks/{task_id}").json()
            status = task.get("status")
            print(f"  {status} {task.get('progress')}% {task.get('progress_message') or ''}")
            if status in {"completed", "failed", "cancelled"}:
                break
        if status != "completed":
            print(f"FAIL: task ended as {status}")
            print(json.dumps(task, indent=2)[:1500])
            return 5

        clips = client.get(f"/tasks/{task_id}/clips").json()
        items = clips.get("clips", clips if isinstance(clips, list) else [])
        print(f"clips: {len(items)}")
        if not items:
            print("FAIL: no clips returned")
            return 6

        out_dir = Path(os.getenv("E2E_OUT_DIR", "/tmp/chunkvex-e2e/downloads"))
        out_dir.mkdir(parents=True, exist_ok=True)
        for clip in items:
            url = clip.get("video_url") or f"/tasks/{task_id}/clips/{clip['id']}/file"
            response = client.get(url)
            if response.status_code != 200:
                print(f"FAIL: download {url} -> {response.status_code}")
                return 7
            target = out_dir / f"{clip.get('id', 'clip')}.mp4"
            target.write_bytes(response.content)
            info = probe(target)
            print(f"downloaded: {target.name} -> {info}")
            if info["height"] != 1920 or info["width"] != 1080:
                print("FAIL: not 1080x1920")
                return 8
            if not info["has_audio"] or info["duration"] < 2:
                print("FAIL: clip has no audio or is too short")
                return 9

    print("PASS: upload -> task -> worker -> 9:16 captioned MP4 downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
