"""Prove the free pipeline renders and exports a real MP4.

Uses a bundled sample video, local Whisper, the model-free selector and the
same FFmpeg renderer the worker uses. No database, Redis, queue or AI key is
involved, so it can run on a fresh machine.

    cd backend
    TRANSCRIPTION_PROVIDER=whisper WHISPER_MODEL=tiny AI_ANALYSIS_ENABLED=false \
    TEMP_DIR=/tmp/chunkvex-check MEDIA_STORAGE=local \
    uv run python scripts/personal_pipeline_check.py [source.mp4]

Exit code 0 means: a vertical, captioned clip was written and its MP4 stream
properties were verified with ffprobe.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.local_selection import build_local_analysis  # noqa: E402
from src.services.video_service import VideoService  # noqa: E402
from src.video_utils import get_video_transcript  # noqa: E402

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "frontend/public/clips/articles/ton-1.mp4"


def probe(path: Path) -> dict:
    """Width, height, duration and audio presence from ffprobe."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "duration": float(data["format"]["duration"]),
        "has_audio": audio is not None,
        "codec": video.get("codec_name"),
        "bytes": int(data["format"]["size"]),
    }


async def main() -> int:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        print(f"FAIL: sample source not found: {source}")
        return 2

    temp_dir = Path(os.environ.get("TEMP_DIR", "/tmp/chunkvex-check"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    work = temp_dir / "personal-check-source.mp4"
    shutil.copy2(source, work)
    print(f"source: {source.name} -> {probe(work)}")

    # 1. Free local transcription (Whisper, CPU).
    transcript = await asyncio.to_thread(get_video_transcript, work, "best", None)
    timed_lines = transcript.strip().splitlines()
    print(f"transcript: {len(transcript)} chars, first line: {timed_lines[0] if timed_lines else '(empty)'}")
    if not timed_lines:
        print("FAIL: Whisper returned no transcript")
        return 3

    # 2. Model-free selection.
    duration = probe(work)["duration"]
    analysis = build_local_analysis(transcript, duration, clip_length="short", max_clips=2)
    segments = analysis.most_relevant_segments
    print(f"local selection: {len(segments)} clip(s)")
    for segment in segments:
        print(f"  {segment['start_time']}-{segment['end_time']} {segment['text'][:70]!r}")

    # 3. Real vertical render with burned-in captions.
    clips = await VideoService.create_video_clips(
        work,
        segments,
        caption_template="default",
        output_format="vertical",
        add_subtitles=True,
    )
    if not clips:
        print("FAIL: the renderer produced no clips")
        return 4

    for clip in clips:
        info = probe(Path(clip["path"]))
        print(f"clip: {clip['filename']} -> {info}")
        if info["width"] != 1080 or info["height"] != 1920:
            print("FAIL: clip is not 9:16 1080x1920")
            return 5
        if info["duration"] < 2 or info["bytes"] < 10_000 or not info["has_audio"]:
            print("FAIL: clip looks empty")
            return 6

    print("PASS: transcribed, selected, reframed to 9:16, captioned and exported MP4")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
