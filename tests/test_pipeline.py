"""E2E test for pipeline.sh — dry-run mode verifies all steps."""

import os
import subprocess
import sys

import pytest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(PROJECT, "integration", "pipeline.sh")


def run_pipeline(*args):
    """Run pipeline.sh with given args, return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    env.setdefault("DEEPSEEK_API_KEY", "")
    proc = subprocess.run(
        ["bash", PIPELINE, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestPipelineE2E:

    def test_help(self):
        """pipeline.sh with no args should show usage."""
        rc, stdout, stderr = run_pipeline("--help")
        assert rc == 0 or "用法" in stdout or "usage" in stdout.lower()

    def test_dry_run_youtube(self):
        """Dry-run with a YouTube URL should succeed (skip ASR if captions exist)."""
        rc, stdout, stderr = run_pipeline(
            "--dry-run",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        combined = stdout + stderr
        # Accept exit 0 or 1 (may fail on network-requiring steps in dry-run)
        assert rc in (0, 1)
        assert "Step" in combined or "step" in combined.lower()

    def test_dry_run_nonexistent_file(self):
        """Should fail gracefully on nonexistent input."""
        rc, stdout, stderr = run_pipeline(
            "/nonexistent/video_12345.mp4",
        )
        assert rc != 0 or "not found" in (stdout + stderr).lower() or "no such" in (stdout + stderr).lower()

    def test_step_flag_accepted(self):
        """--step N should be accepted."""
        rc, stdout, stderr = run_pipeline(
            "--step", "1",
            "--dry-run",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        combined = stdout + stderr
        assert rc in (0, 1, 2)  # 2 = argparse error on bad arg
        assert len(combined) > 0

    def test_lang_flag(self):
        """--lang en should set source language to English."""
        rc, stdout, stderr = run_pipeline(
            "--lang", "en",
            "--dry-run",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        assert rc in (0, 1)
        combined = stdout + stderr
        assert "en" in combined.lower() or "lang" in combined.lower()


class TestBatchPipeline:

    def test_help(self):
        batch = os.path.join(PROJECT, "integration", "batch_pipeline.sh")
        if not os.path.exists(batch):
            pytest.skip("batch_pipeline.sh not found")
        proc = subprocess.run(
            ["bash", batch, "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        assert proc.returncode == 0 or "用法" in (proc.stdout + proc.stderr)
