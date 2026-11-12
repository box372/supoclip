"""Deterministic clip selection for installations with no AI provider.

The highlights pipeline normally asks a language model which passages to cut.
When ``AI_ANALYSIS_ENABLED=false`` this module picks the same number of clips
from the transcript itself: line-aligned windows of the requested length,
spread across the source. Nothing here calls a model, downloads a model, or
needs a network connection.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .clip_duration import clip_duration

TRANSCRIPT_LINE_PATTERN = re.compile(
    r"^\[(\d{1,3}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,3}:\d{2}(?::\d{2})?)\]\s*(.*)$"
)
SPEAKER_PREFIX_PATTERN = re.compile(r"^Speaker [^:]+:\s*")

DEFAULT_TARGET_SECONDS = 35
MIN_CLIP_SECONDS = 15
MAX_CLIP_SECONDS = 60


def _seconds(label: str) -> float:
    parts = [int(part) for part in label.split(":")]
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(seconds)


def _stamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_transcript_lines(transcript: str) -> List[Dict[str, Any]]:
    """``[start - end] text`` lines with speaker labels stripped."""
    lines: List[Dict[str, Any]] = []
    for raw_line in (transcript or "").splitlines():
        match = TRANSCRIPT_LINE_PATTERN.match(raw_line.strip())
        if not match:
            continue
        text = SPEAKER_PREFIX_PATTERN.sub("", match.group(3).strip()).strip()
        start, end = _seconds(match.group(1)), _seconds(match.group(2))
        if end <= start:
            continue
        lines.append({"start": start, "end": end, "text": text})
    return lines


def _target_seconds(clip_length: str) -> float:
    try:
        ideal = float(clip_duration(clip_length).ideal_minimum)
    except Exception:
        ideal = DEFAULT_TARGET_SECONDS
    return min(MAX_CLIP_SECONDS, max(MIN_CLIP_SECONDS, ideal or DEFAULT_TARGET_SECONDS))


def _clip_count(duration: float, target: float, max_clips: Optional[int]) -> int:
    if duration <= 0:
        return 1
    # Leave room between clips so a long source is not cut wall to wall.
    available = max(1, int(duration // (target * 1.5)))
    limit = max(1, int(max_clips)) if max_clips else 3
    return max(1, min(limit, available))


def _pick_window(
    lines: List[Dict[str, Any]],
    center: float,
    target: float,
    after: float,
) -> Optional[Dict[str, Any]]:
    """Line-aligned window of about ``target`` seconds around ``center``."""
    candidates = [line for line in lines if line["end"] > after + 1 and line["start"] < center + target]
    if not candidates:
        return None
    first = min(candidates, key=lambda line: abs(line["start"] - max(after, center - target / 2)))
    if first["start"] < after:
        return None
    end_time = first["end"]
    text_parts = [first["text"]]
    for line in lines:
        if line["start"] < first["start"]:
            continue
        if line is not first:
            if line["start"] - end_time > 3:
                break
            text_parts.append(line["text"])
        end_time = max(end_time, line["end"])
        if end_time - first["start"] >= target:
            break
    if end_time <= first["start"]:
        return None
    return {
        "start": first["start"],
        "end": end_time,
        "text": " ".join(part for part in text_parts if part).strip(),
    }


def _segment(window: Dict[str, Any], index: int) -> Dict[str, Any]:
    length = max(1.0, window["end"] - window["start"])
    # A flat, honest score: no model judged this passage.
    score = 50
    words = len(window["text"].split())
    if words:
        score = min(70, 40 + min(30, words // 3))
    return {
        "start_time": _stamp(window["start"]),
        "end_time": _stamp(window["end"]),
        "text": window["text"],
        "relevance_score": round(min(1.0, 0.4 + length / 300), 2),
        "reasoning": (
            "Chosen locally from the transcript because AI analysis is off. "
            "This window is a complete spoken passage of about "
            f"{int(round(length))} seconds."
        ),
        "virality_score": score,
        "hook_score": 0,
        "engagement_score": score,
        "value_score": score,
        "shareability_score": score,
        "hook_type": "local",
        "hook_title": None,
    }


class LocalAnalysis:
    """The subset of the transcript analysis the pipeline reads."""

    def __init__(self, segments: List[Dict[str, Any]], duration: float):
        self.summary = (
            "Local selection: the transcript was split into evenly spaced, "
            "line-aligned passages because no AI model is configured."
        )
        self.key_topics: List[str] = []
        self.most_relevant_segments = segments
        self.duration = duration


def build_local_analysis(
    transcript: str,
    duration_seconds: Optional[float],
    clip_length: str = "auto",
    max_clips: Optional[int] = None,
    server_max_clips: Optional[int] = None,
) -> LocalAnalysis:
    """Evenly spaced, line-aligned clips with no model involved."""
    lines = parse_transcript_lines(transcript)
    duration = float(duration_seconds or 0)
    if duration <= 0 and lines:
        duration = lines[-1]["end"]
    target = _target_seconds(clip_length)
    limit = max_clips or server_max_clips or 3
    count = _clip_count(duration, target, limit)

    if not lines:
        # No timed transcript (e.g. captions unavailable): cut the opening
        # window so a clip can still be produced and checked by hand.
        fallback_end = min(duration or target, target)
        return LocalAnalysis(
            [
                {
                    "start_time": "00:00",
                    "end_time": _stamp(fallback_end),
                    "text": " ".join((transcript or "").split())[:240],
                    "relevance_score": 0.25,
                    "reasoning": "Local selection produced one opening clip; no timed transcript was available.",
                    "virality_score": 0,
                    "hook_score": 0,
                    "engagement_score": 0,
                    "value_score": 0,
                    "shareability_score": 0,
                    "hook_type": "local",
                    "hook_title": None,
                }
            ],
            duration or fallback_end,
        )

    windows: List[Dict[str, Any]] = []
    after = 0.0
    span = max(target, (duration - target) / max(1, count - 1)) if count > 1 else target
    for index in range(count):
        center = target / 2 + span * index
        window = _pick_window(lines, center, target, after)
        if window is None:
            continue
        windows.append(window)
        after = window["end"]

    if not windows:
        windows = [
            {
                "start": lines[0]["start"],
                "end": min(lines[-1]["end"], lines[0]["start"] + target),
                "text": " ".join(line["text"] for line in lines[:6]).strip(),
            }
        ]

    segments = [_segment(window, index) for index, window in enumerate(windows)]
    return LocalAnalysis(segments, duration)
