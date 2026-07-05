"""Tests for dashpublish.sentry.parse — the most fragile surface in the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from dashpublish.sentry.parse import parse_last_search, parse_stdout, ts_to_seconds

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# --- ts_to_seconds ----------------------------------------------------------
def test_ts_mm_ss():
    assert ts_to_seconds("02:15") == 135.0


def test_ts_hh_mm_ss():
    assert ts_to_seconds("1:02:03") == 3723.0


def test_ts_numeric_passthrough():
    assert ts_to_seconds(42) == 42.0
    assert ts_to_seconds(12.5) == 12.5
    assert ts_to_seconds("90.25") == 90.25


def test_ts_fractional_seconds():
    assert ts_to_seconds("02:15.5") == 135.5


def test_ts_garbage_is_none():
    assert ts_to_seconds(None) is None
    assert ts_to_seconds("") is None
    assert ts_to_seconds("not-a-time") is None


# --- parse_last_search ------------------------------------------------------
def test_last_search_top_level_list():
    matches = parse_last_search(FIXTURES / "last_search_list.json")
    assert len(matches) == 2
    first = matches[0]
    assert first.score == 0.87
    assert first.source_file == "front_2024-01-15_14-30.mp4"
    assert first.start_s == 135.0
    assert first.end_s == 165.0
    assert first.saved_clip_path == "./match_front_2024-01-15_14-30_02m15s-02m45s.mp4"
    assert matches[1].saved_clip_path is None
    assert matches[1].start_s == 12.5


def test_last_search_dict_form_with_alt_keys_and_mm_ss():
    matches = parse_last_search(FIXTURES / "last_search_dict.json")
    # The entry with no timestamps is skipped.
    assert len(matches) == 2
    assert matches[0].score == 0.91
    assert matches[0].source_file == "front_2024-01-15_14-30.mp4"
    assert matches[0].start_s == 135.0
    assert matches[0].end_s == 165.0
    assert matches[1].start_s == 3723.0
    assert matches[1].end_s == 3753.0
    assert matches[1].saved_clip_path is None


def test_last_search_matches_key(tmp_path: Path):
    payload = {
        "matches": [
            {"score": 0.5, "source": "a.mp4", "start_time": 1.0, "end_time": 2.0}
        ]
    }
    p = tmp_path / "last_search.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    matches = parse_last_search(p)
    assert len(matches) == 1
    assert matches[0].source_file == "a.mp4"


def test_last_search_missing_file_returns_empty(tmp_path: Path):
    assert parse_last_search(tmp_path / "nope.json") == []


def test_last_search_invalid_json_returns_empty(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert parse_last_search(p) == []


def test_last_search_unexpected_shape_returns_empty(tmp_path: Path):
    p = tmp_path / "weird.json"
    p.write_text('"just a string"', encoding="utf-8")
    assert parse_last_search(p) == []


def test_last_search_single_match_dict(tmp_path: Path):
    p = tmp_path / "single.json"
    p.write_text(
        json.dumps({"score": 0.7, "file": "solo.mp4", "start": "00:05", "end": "00:10"}),
        encoding="utf-8",
    )
    matches = parse_last_search(p)
    assert len(matches) == 1
    assert matches[0].start_s == 5.0
    assert matches[0].end_s == 10.0


# --- parse_stdout -----------------------------------------------------------
STDOUT_MULTI = """\
Searching for: a car overtaking another vehicle

  #1 [0.87] front_2024-01-15_14-30.mp4 @ 02:15-02:45
Saved clip: ./match_front_2024-01-15_14-30_02m15s-02m45s.mp4
  #2 [0.71] road_trip.mp4 @ 1:02:03-1:02:33
Saved clip: ./match_road_trip_1h02m.mp4
  #3 [0.55] dusk_drive.mov @ 00:05-00:12

3 results.
"""


def test_stdout_multi_match_with_saved_clips():
    matches = parse_stdout(STDOUT_MULTI)
    assert len(matches) == 3

    assert matches[0].score == 0.87
    assert matches[0].source_file == "front_2024-01-15_14-30.mp4"
    assert matches[0].start_s == 135.0
    assert matches[0].end_s == 165.0
    assert matches[0].saved_clip_path == (
        "./match_front_2024-01-15_14-30_02m15s-02m45s.mp4"
    )

    # HH:MM:SS timestamps.
    assert matches[1].start_s == 3723.0
    assert matches[1].end_s == 3753.0
    assert matches[1].saved_clip_path == "./match_road_trip_1h02m.mp4"

    # Third match has no Saved clip line.
    assert matches[2].saved_clip_path is None
    assert matches[2].source_file == "dusk_drive.mov"


def test_stdout_no_matches():
    assert parse_stdout("No results found.\n") == []
    assert parse_stdout("") == []


def test_stdout_saved_clip_association_order():
    text = (
        "  #1 [0.9] a.mp4 @ 00:01-00:02\n"
        "  #2 [0.8] b.mp4 @ 00:03-00:04\n"
        "Saved clip: /tmp/first.mp4\n"
        "Saved clip: /tmp/second.mp4\n"
    )
    matches = parse_stdout(text)
    assert matches[0].saved_clip_path == "/tmp/first.mp4"
    assert matches[1].saved_clip_path == "/tmp/second.mp4"


def test_stdout_orphan_saved_clip_line_ignored():
    assert parse_stdout("Saved clip: /tmp/orphan.mp4\n") == []


def test_stdout_filename_with_spaces():
    matches = parse_stdout("  #1 [0.80] my road trip.mp4 @ 00:10-00:20\n")
    assert len(matches) == 1
    assert matches[0].source_file == "my road trip.mp4"
