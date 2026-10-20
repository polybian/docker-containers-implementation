"""Unit tests for scripts/collect-logs.py (standard library only)."""
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock


def _load_script():
    # The script file is named collect-logs.py (dash), which is not a valid
    # Python module name, so it cannot be imported with a plain `import`.
    # Load it from its file path instead -- still the real module under test.
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(here, "..", "scripts", "collect-logs.py"))
    spec = importlib.util.spec_from_file_location("collect_logs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cl = _load_script()

SAMPLE = [
    ("app.log", 1, "2026-10-20 08:01:11 INFO server starting on :8000"),
    ("app.log", 2, "2026-10-20 08:01:12 INFO listening"),
    ("app.log", 3, "2026-10-20 08:02:01 ERROR db connection refused: dial tcp 10.0.0.5:5432"),
    ("app.log", 4, "2026-10-20 08:02:01 ERROR db connection refused: dial tcp 10.0.0.5:5432"),
    ("app.log", 5, "2026-10-20 08:03:00 WARNING slow query: 1203ms"),
    ("app.log", 6, "2026-10-20 08:04:44 Traceback (most recent call last):"),
    ("db.log", 1, "2026-10-20 08:01:10 LOG database system is ready"),
    ("db.log", 2, "2026-10-20 08:02:01 FATAL password authentication failed for user app"),
    ("db.log", 3, "2026-10-20 08:02:01 FATAL password authentication failed for user app"),
]


class TestSummarize(unittest.TestCase):
    def test_counts(self):
        s = cl.summarize(SAMPLE)
        self.assertEqual(s["total"], 9)
        self.assertEqual(s["errors"], 5)   # 2x ERROR + 1x Traceback + 2x FATAL
        self.assertEqual(s["warnings"], 1)

    def test_top_errors_ranking(self):
        s = cl.summarize(SAMPLE, top_n=10)
        counts = {text: n for n, text in s["top_errors"]}
        self.assertEqual(
            counts["2026-10-20 08:02:01 ERROR db connection refused: dial tcp 10.0.0.5:5432"], 2
        )
        self.assertEqual(
            counts["2026-10-20 08:02:01 FATAL password authentication failed for user app"], 2
        )
        self.assertEqual(counts["2026-10-20 08:04:44 Traceback (most recent call last):"], 1)
        # ties broken by first-seen order
        self.assertEqual(s["top_errors"][0][1],
                         "2026-10-20 08:02:01 ERROR db connection refused: dial tcp 10.0.0.5:5432")

    def test_per_file_breakdown(self):
        s = cl.summarize(SAMPLE)
        self.assertEqual(s["per_file"]["app.log"], {"lines": 6, "errors": 3})
        self.assertEqual(s["per_file"]["db.log"], {"lines": 3, "errors": 2})

    def test_time_range(self):
        s = cl.summarize(SAMPLE)
        self.assertEqual(s["first_ts"], "2026-10-20 08:01:10")
        self.assertEqual(s["last_ts"], "2026-10-20 08:04:44")

    def test_empty_entries(self):
        s = cl.summarize([])
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["errors"], 0)
        self.assertEqual(s["top_errors"], [])
        self.assertIsNone(s["first_ts"])
        report = cl.format_report(s, "empty", generated_at="2026-10-20 00:00:00 UTC")
        self.assertIn("Error lines  : 0 (0.0%)", report)
        self.assertIn("Time range   : n/a", report)

    def test_error_regex_word_boundaries(self):
        # "errors" as a substring of a longer word must NOT match; whole words must.
        s = cl.summarize([("x.log", 1, "terrorists win"), ("x.log", 2, "an error occurred")])
        self.assertEqual(s["errors"], 1)

    def test_report_sections(self):
        report = cl.format_report(cl.summarize(SAMPLE), "unit-test",
                                  generated_at="2026-10-20 00:00:00 UTC")
        for section in ("LOG COLLECTION REPORT (LAB)", "Total lines  : 9",
                        "Error lines  : 5", "Top 3 error lines", "Per-file breakdown:",
                        "app.log: 6 lines, 3 errors"):
            self.assertIn(section, report)


class TestReadEntries(unittest.TestCase):
    def test_reads_only_dot_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.log"), "w") as fh:
                fh.write("line one\nline two ERROR boom\n")
            with open(os.path.join(tmp, "b.log"), "w") as fh:
                fh.write("just info\n")
            with open(os.path.join(tmp, "notes.txt"), "w") as fh:
                fh.write("ERROR should be ignored\n")
            entries = cl.read_entries(tmp)
            self.assertEqual(len(entries), 3)
            self.assertEqual([e[0] for e in entries], ["a.log", "a.log", "b.log"])
            s = cl.summarize(entries)
            self.assertEqual(s["errors"], 1)

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cl.read_entries(tmp), [])


class TestDockerMode(unittest.TestCase):
    def test_missing_docker_cli_raises(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                cl.docker_log_text("whatever")
        self.assertIn("docker CLI not found", str(ctx.exception))

    def test_failed_docker_logs_raises(self):
        fake = mock.Mock(returncode=1, stdout="", stderr="Error: no such container")
        with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
             mock.patch("subprocess.run", return_value=fake):
            with self.assertRaises(RuntimeError) as ctx:
                cl.docker_log_text("nope")
        self.assertIn("no such container", str(ctx.exception))

    def test_successful_docker_logs(self):
        fake = mock.Mock(returncode=0, stdout="a\nb ERROR x\n", stderr="")
        with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
             mock.patch("subprocess.run", return_value=fake) as run:
            text = cl.docker_log_text("lab-app", tail=50)
        self.assertEqual(text, "a\nb ERROR x\n")
        self.assertIn("--tail", run.call_args.args[0])


class TestMain(unittest.TestCase):
    def test_dir_mode_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "app.log"), "w") as fh:
                fh.write("2026-10-20 08:00:00 INFO up\n2026-10-20 08:01:00 ERROR down\n")
            out = os.path.join(tmp, "report.txt")
            rc = cl.main(["--dir", tmp, "--output", out, "--top", "5"])
            self.assertEqual(rc, 0)
            with open(out) as fh:
                content = fh.read()
            self.assertIn("LOG COLLECTION REPORT (LAB)", content)
            self.assertIn("Total lines  : 2", content)
            self.assertIn("Error lines  : 1", content)

    def test_missing_dir_exits_2(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(cl.main(["--dir", "/nonexistent-xyz"]), 2)

    def test_mutually_exclusive_sources(self):
        with self.assertRaises(SystemExit) as ctx:
            with mock.patch("sys.stderr"):
                cl.main(["--dir", "/tmp", "--container", "x"])
        self.assertEqual(ctx.exception.code, 2)

    def test_container_mode_without_docker_exits_1(self):
        with mock.patch("shutil.which", return_value=None), \
             mock.patch("sys.stderr"):
            self.assertEqual(cl.main(["--container", "lab-app"]), 1)


if __name__ == "__main__":
    unittest.main()
