"""Local selection: clips without an AI provider."""

from src.local_selection import build_local_analysis, parse_transcript_lines

TRANSCRIPT = "\n".join(
    f"[{second // 60:02d}:{second % 60:02d} - {(second + 10) // 60:02d}:{(second + 10) % 60:02d}] "
    f"Speaker 1: sentence number {second // 10 + 1} about the topic"
    for second in range(0, 600, 10)
)


def test_parses_timed_lines_and_strips_speaker_labels():
    lines = parse_transcript_lines(TRANSCRIPT)
    assert len(lines) == 60
    assert lines[0]["start"] == 0
    assert lines[0]["text"].startswith("sentence number")


def test_picks_several_line_aligned_windows_of_the_requested_length():
    analysis = build_local_analysis(
        TRANSCRIPT, duration_seconds=600, clip_length="medium", max_clips=3
    )
    segments = analysis.most_relevant_segments
    assert len(segments) == 3
    for segment in segments:
        start = segment["start_time"]
        assert start != segment["end_time"]
        assert segment["hook_title"] is None
        assert segment["reasoning"].startswith("Chosen locally")
        # Windows never overlap and stay inside the source.
        assert segment["start_time"] < segment["end_time"] <= "10:00"


def test_windows_do_not_overlap():
    analysis = build_local_analysis(TRANSCRIPT, 600, clip_length="auto", max_clips=6)
    stops = [segment["end_time"] for segment in analysis.most_relevant_segments]
    starts = [segment["start_time"] for segment in analysis.most_relevant_segments]
    assert all(later >= earlier for later, earlier in zip(starts[1:], stops[:-1]))


def test_without_a_timed_transcript_it_still_returns_one_clip():
    analysis = build_local_analysis("just some untimed words", duration_seconds=90)
    segments = analysis.most_relevant_segments
    assert len(segments) == 1
    assert segments[0]["start_time"] == "00:00"
    # The auto clip length's ideal minimum is 25 seconds.
    assert segments[0]["end_time"] == "00:25"
    assert segments[0]["hook_title"] is None


def test_respects_the_requested_clip_count_cap():
    analysis = build_local_analysis(TRANSCRIPT, 600, max_clips=2)
    assert len(analysis.most_relevant_segments) == 2
