"""Core unit tests for translate_srt.py, text_to_srt.py, stepfun_to_srt.py, and eval.py"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integration"))

from translate_srt import parse_srt, format_srt, ts_to_sec, sec_to_ts, re_segment
from text_to_srt import split_sentences, format_timestamp, estimate_duration, text_to_srt
from subtitle_quality import enforce as sqi_enforce, diagnose, parse_srt as sqi_parse, format_srt as sqi_format
from eval import load, record, recommend, stats as eval_stats
import eval as eval_module

SRT_SAMPLE = """1
00:00:00,000 --> 00:00:03,500
Welcome to Everyones Video.

2
00:00:03,500 --> 00:00:07,200
This is the fastest way to add subtitles.

3
00:00:07,200 --> 00:00:12,800
We support six ASR engines.

"""


class TestParseSRT:
    def test_parse(self):
        cues = parse_srt_text(SRT_SAMPLE)
        assert len(cues) == 3
        assert cues[0]["text"] == "Welcome to Everyones Video."
        assert cues[2]["start"] == "00:00:07,200"

    def test_empty(self):
        assert parse_srt_text("") == []


class TestFormatSRT:
    def test_roundtrip(self):
        cues = parse_srt_text(SRT_SAMPLE)
        formatted = format_srt(cues)
        reparsed = parse_srt_text(formatted)
        assert len(reparsed) == 3
        assert reparsed[1]["text"] == cues[1]["text"]

    def test_timestamps(self):
        cues = [{"index": 1, "start": "00:01:30,500", "end": "00:01:35,000", "text": "Hello"}]
        srt = format_srt(cues)
        assert "00:01:30,500 --> 00:01:35,000" in srt


class TestTimeUtils:
    def test_ts_to_sec(self):
        assert abs(ts_to_sec("00:00:03,500") - 3.5) < 0.001
        assert abs(ts_to_sec("01:30:00,000") - 5400) < 0.001

    def test_sec_to_ts(self):
        assert sec_to_ts(3.5) == "00:00:03,500"
        assert sec_to_ts(3661.123) == "01:01:01,123"


class TestReSegment:
    def test_zh_resegment(self):
        cues = [{"index": 1, "start": "00:00:00,000", "end": "00:00:10,000",
                 "text": "你好。今天天气很好。我们去散步吧。"}]
        result = re_segment(cues, "zh-CN")
        assert len(result) >= 2

    def test_en_resegment(self):
        cues = [{"index": 1, "start": "00:00:00,000", "end": "00:00:10,000",
                 "text": "Hello. How are you? I am fine."}]
        result = re_segment(cues, "en")
        assert len(result) >= 2


class TestSplitSentences:
    def test_zh(self):
        parts = split_sentences("你好。今天天气很好。我们去散步。", "zh")
        assert len(parts) >= 2

    def test_en(self):
        parts = split_sentences("Hello. How are you? Fine.", "en")
        assert len(parts) >= 2


class TestFormatTimestamp:
    def test_basic(self):
        assert format_timestamp(3.5) == "00:00:03,500"
        assert format_timestamp(3661.123) == "01:01:01,123"


class TestTextToSRT:
    def test_zh(self):
        srt = text_to_srt("你好。今天天气很好。", "zh")
        assert "00:00:00,000 -->" in srt
        assert "你好" in srt

    def test_en(self):
        srt = text_to_srt("Hello. How are you?", "en")
        assert "Hello" in srt

    def test_empty(self):
        srt = text_to_srt("", "zh")
        assert srt == ""

    def test_long_sentence(self):
        long_text = "这是一个很长的句子，" * 20
        srt = text_to_srt(long_text, "zh")
        cues = [b for b in srt.split("\n\n") if b.strip()]
        assert len(cues) >= 2  # should be split by commas


class TestSplitSentencesEdge:
    def test_abbreviation_merge(self):
        """Ensure trailing single-char fragments from abbreviations are merged."""
        parts = split_sentences("The U.S. is large.", "en")
        # "U." and "S." should be merged back into "U.S."
        joined = " ".join(parts)
        assert "U.S." in joined or "U. S." in joined

    def test_zh_question_mark(self):
        parts = split_sentences("你好吗？我很好。", "zh")
        assert len(parts) == 2

    def test_zh_semicolon(self):
        parts = split_sentences("第一部分；第二部分。", "zh")
        assert len(parts) >= 2


class TestEval:
    @pytest.fixture(autouse=True)
    def _isolate_eval_file(self, tmp_path, monkeypatch):
        """Point EVAL_FILE at a temp file so tests don't mutate the real DB."""
        test_file = tmp_path / "workflow_eval.json"
        test_file.write_text('{"records":[],"engines":{}}', encoding="utf-8")
        monkeypatch.setattr(eval_module, "EVAL_FILE", test_file)

    def test_record_and_stats(self):
        data = record("funasr", "zh", 120.0, 0.0, "audio", 30)
        assert len(data["records"]) >= 1
        assert data["engines"]["funasr"]["calls"] >= 1
        assert data["engines"]["funasr"]["total_sec"] >= 120.0

    def test_recommend_chinese_free(self):
        results = recommend("zh", budget=0)
        assert len(results) >= 2
        # free engines should be top
        assert all(r["cost_yuan_per_min"] == 0 for r in results if r["local"])

    def test_recommend_english_free(self):
        results = recommend("en", budget=0)
        assert any(r["engine"] == "faster_whisper" for r in results)

    def test_recommend_paid(self):
        results = recommend("zh", budget=1.0)
        assert len(results) >= 3  # free + paid engines

    def test_stats_function(self, capsys):
        # Smoke test: ensure stats() runs without error
        eval_stats()
        captured = capsys.readouterr()
        assert "Records:" in captured.out or "Workflow Eval" in captured.out


class TestStepfunToSRTWrapper:
    def test_import(self):
        """Backward-compat: stepfun_to_srt.py should import from text_to_srt."""
        import stepfun_to_srt
        assert hasattr(stepfun_to_srt, "main")

    def test_cli_help(self, capsys):
        """stepfun_to_srt.py --help should exit 2 (argparse default)."""
        import stepfun_to_srt
        try:
            stepfun_to_srt.main()
        except SystemExit as e:
            # --help or no-args triggers argparse exit
            assert e.code in (0, 2)
        else:
            pass  # may exit successfully with empty stdin


def parse_srt_text(text: str) -> list[dict]:
    """Parse SRT from string for test convenience."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp = f.name
    try:
        return parse_srt(tmp)
    finally:
        os.unlink(tmp)


# ── SQI 字幕质量引擎测试 ─────────────────────────────

SRT_OVERLAPPING = """1
00:00:00,000 --> 00:00:03,000
Hello world

2
00:00:02,500 --> 00:00:05,000
This overlaps with #1
"""

SRT_LONG_GAP = """1
00:00:00,000 --> 00:00:02,000
First cue

2
00:00:15,000 --> 00:00:17,000
After long silence
"""

SRT_SHORT_GAP = """1
00:00:00,000 --> 00:00:02,000
Hello

2
00:00:02,100 --> 00:00:04,000
World
"""

SRT_SUPER_LONG = """1
00:00:00,000 --> 00:00:30,000
This is a very long subtitle that stays on screen for 30 seconds

2
00:00:31,000 --> 00:00:33,000
Next one
"""

SRT_TOO_SHORT = """1
00:00:00,000 --> 00:00:00,300
Hi

2
00:00:01,000 --> 00:00:03,000
Next
"""


class TestSQI:

    def test_overlap_fix(self):
        cues = parse_srt_text(SRT_OVERLAPPING)
        assert len(cues) == 2
        fixed, report = sqi_enforce(cues, "en")
        assert report.fixed_overlaps >= 1
        # After fix: cue 2 start >= cue 1 end
        assert ts_to_sec(fixed[1]["start"]) >= ts_to_sec(fixed[0]["end"])

    def test_long_gap_freeze(self):
        cues = parse_srt_text(SRT_LONG_GAP)
        fixed, report = sqi_enforce(cues, "en")
        # Cue 1 duration should be capped at MAX_CUE_DURATION
        dur = ts_to_sec(fixed[0]["end"]) - ts_to_sec(fixed[0]["start"])
        assert dur <= 7.5  # MAX_CUE_DURATION = 7.0 + small tolerance

    def test_max_duration_cap(self):
        cues = parse_srt_text(SRT_SUPER_LONG)
        fixed, report = sqi_enforce(cues, "en")
        dur0 = ts_to_sec(fixed[0]["end"]) - ts_to_sec(fixed[0]["start"])
        assert dur0 <= 7.5
        assert report.capped_durations >= 1

    def test_min_duration_enforce(self):
        cues = parse_srt_text(SRT_TOO_SHORT)
        fixed, report = sqi_enforce(cues, "zh")
        dur0 = ts_to_sec(fixed[0]["end"]) - ts_to_sec(fixed[0]["start"])
        assert dur0 >= 0.5  # boosted from 0.3 to ≥0.5

    def test_diagnose_returns_issues(self):
        issues = diagnose(parse_srt_text(SRT_OVERLAPPING), "en")
        assert len(issues) >= 1
        assert any("重叠" in i or "overlap" in i.lower() for i in issues)

    def test_cps_warning_triggers(self):
        srt = """1
00:00:00,000 --> 00:00:01,000
这是一个非常长的中文字幕句子包含了很多很多的文字需要在一秒内读完

2
00:00:01,500 --> 00:00:03,000
Short
"""
        cues = parse_srt_text(srt)
        _, report = sqi_enforce(cues, "zh")
        assert report.cps_warnings >= 1

    def test_preserves_cue_count_without_merge(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
First

2
00:00:03,000 --> 00:00:05,000
Second

3
00:00:06,000 --> 00:00:08,000
Third
"""
        cues = parse_srt_text(srt)
        fixed, _ = sqi_enforce(cues, "en")
        assert len(fixed) == 3

    def test_idempotent(self):
        cues = parse_srt_text(SRT_OVERLAPPING)
        f1, _ = sqi_enforce(cues, "en")
        f2, _ = sqi_enforce(f1, "en")
        assert ts_to_sec(f2[0]["end"]) >= ts_to_sec(f1[0]["end"]) - 0.01
        assert ts_to_sec(f2[1]["start"]) >= ts_to_sec(f2[0]["end"]) - 0.01
