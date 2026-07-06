"""Regression tests against the *real* sentrysearch output formats, captured from
a live run (sentrysearch 0.1.0, 2026-07-06) rather than the guessed schema the
parsers were originally written for."""

from __future__ import annotations

import json
import subprocess

from dashpublish.sentry.client import SentrySearchClient
from dashpublish.sentry.parse import merge_saved_clip_paths, parse_last_search, parse_stdout

REAL_LAST_SEARCH = {
    "version": 1,
    "saved_at": "2026-07-06T17:43:07Z",
    "saved_by": "sentrysearch",
    "query": "a funny, unusual, or amusing moment caught while driving",
    "image_path": None,
    "results": [
        {
            "source_file": "/data/footage/5382495-uhd_3840_2160_24fps.mp4",
            "start_time": 25.0,
            "end_time": 34.09,
            "similarity_score": 0.5700080990791321,
        },
        {
            "source_file": "/data/footage/5921059-uhd_3840_2160_30fps.mp4",
            "start_time": 0.0,
            "end_time": 11.277933,
            "similarity_score": 0.5301097631454468,
        },
        {
            "source_file": "/data/footage/4608285-uhd_3840_2160_24fps.mp4",
            "start_time": 0.0,
            "end_time": 29.76,
            "similarity_score": 0.45082080364227295,
        },
    ],
}

REAL_STDOUT = """Model loaded on cpu
Search results cached for sentrymerge --last
  #1 [0.57] 5382495-uhd_3840_2160_24fps.mp4 @ 00:25-00:34
  #2 [0.53] 5921059-uhd_3840_2160_30fps.mp4 @ 00:00-00:11

Saved clip: /root/sentrysearch_clips/match_5382495-uhd_3840_2160_24fps_00m25s-00m34s.mp4

Saved clip: /root/sentrysearch_clips/match_5921059-uhd_3840_2160_30fps_00m00s-00m11s.mp4
Saved clip path cached for sentryblur --last
"""


def test_parse_real_last_search_scores(tmp_path):
    f = tmp_path / "last_search.json"
    f.write_text(json.dumps(REAL_LAST_SEARCH))
    matches = parse_last_search(f)
    assert [round(m.score, 2) for m in matches] == [0.57, 0.53, 0.45]
    assert matches[0].start_s == 25.0 and matches[0].end_s == 34.09
    assert matches[0].source_file.endswith("5382495-uhd_3840_2160_24fps.mp4")


def test_merge_saved_paths_from_stdout(tmp_path):
    f = tmp_path / "last_search.json"
    f.write_text(json.dumps(REAL_LAST_SEARCH))
    matches = parse_last_search(f)
    merge_saved_clip_paths(matches, parse_stdout(REAL_STDOUT))
    assert matches[0].saved_clip_path.endswith("match_5382495-uhd_3840_2160_24fps_00m25s-00m34s.mp4")
    assert matches[1].saved_clip_path.endswith("match_5921059-uhd_3840_2160_30fps_00m00s-00m11s.mp4")
    assert matches[2].saved_clip_path is None  # below save-top, no clip saved


def test_search_filters_below_threshold(tmp_path, monkeypatch):
    """The JSON cache is unfiltered — client.search must apply the threshold."""
    home = tmp_path / ".sentrysearch"
    home.mkdir()
    (home / "last_search.json").write_text(json.dumps(REAL_LAST_SEARCH))

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout=REAL_STDOUT, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = SentrySearchClient(backend="local", home=home)
    matches = client.search("anything", threshold=0.5, save_top=2)
    assert [round(m.score, 2) for m in matches] == [0.57, 0.53]  # 0.45 filtered out
    assert all(m.saved_clip_path for m in matches)
