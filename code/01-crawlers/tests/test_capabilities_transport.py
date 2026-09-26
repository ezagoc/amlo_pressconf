"""Offline regression tests for portable, verified and complete curl responses."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.capabilities import fetch, run_curl  # noqa: E402


URL = "https://example.test/noticia/sample/"
MODULE = "crawler_core.capabilities"


class CurlTransportTests(unittest.TestCase):
    def completed(self, code=0, stdout=None, stderr=""):
        return subprocess.CompletedProcess(
            args=["curl"],
            returncode=code,
            stdout=stdout if stdout is not None else f"200\t{URL}\ttext/html; charset=utf-8",
            stderr=stderr,
        )

    def fake_response(self, body, *, code=0, stdout=None, stderr=""):
        def run(url, body_path, timeout, **kwargs):
            if body is not None:
                body_path.write_bytes(body)
            return self.completed(code, stdout, stderr)

        return run

    def test_portable_executable_and_verified_tls_on_mac_and_windows(self):
        for platform, name, executable in (
            ("darwin", "curl", "/usr/bin/curl"),
            ("win32", "curl.exe", r"C:\Windows\System32\curl.exe"),
        ):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmp:
                with patch(f"{MODULE}.sys.platform", platform), patch(
                    f"{MODULE}.shutil.which", return_value=executable
                ) as which, patch(
                    f"{MODULE}.subprocess.run", return_value=self.completed()
                ) as run:
                    run_curl(URL, Path(tmp) / "body", 3)
                which.assert_called_once_with(name)
                command = run.call_args.args[0]
                self.assertEqual(command[0], executable)
                self.assertEqual(command[1], "--disable")
                self.assertNotIn("--insecure", command)
                self.assertNotIn("-k", command)
                self.assertNotIn("--ssl-no-revoke", command)
                self.assertEqual(command[-2:], ["--url", URL])
                self.assertEqual(run.call_args.kwargs["timeout"], 8)

    def test_missing_curl_is_actionable_without_attempting_a_process(self):
        with patch(f"{MODULE}.shutil.which", return_value=None), patch(
            f"{MODULE}.subprocess.run"
        ) as run:
            result = run_curl(URL, Path("unused-body"), 1)
        self.assertIn("CurlNotFound", result)
        self.assertIn("PATH", result)
        run.assert_not_called()

    def test_disappeared_executable_returns_error(self):
        with patch(f"{MODULE}.shutil.which", return_value="/missing/curl"), patch(
            f"{MODULE}.subprocess.run", side_effect=FileNotFoundError("curl disappeared")
        ):
            result = run_curl(URL, Path("unused-body"), 1)
        self.assertIn("CurlExecutionError: FileNotFoundError", result)

    def test_process_timeout_returns_error(self):
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/curl"), patch(
            f"{MODULE}.subprocess.run", side_effect=subprocess.TimeoutExpired("curl", 6)
        ):
            result = run_curl(URL, Path("unused-body"), 1)
        self.assertIn("TimeoutExpired", result)

    def test_tls_failure_is_not_retried_with_verification_disabled(self):
        with patch(
            f"{MODULE}.run_curl",
            side_effect=self.fake_response(None, code=60, stderr="SSL certificate verification failed"),
        ) as run:
            result = fetch(URL, 1)
        run.assert_called_once()
        self.assertEqual(result["curl_exit_code"], 60)
        self.assertIn("certificate verification failed", result["error"])
        self.assertEqual(result["text"], "")

    def test_http_200_with_timeout_does_not_expose_partial_article(self):
        with patch(
            f"{MODULE}.run_curl",
            side_effect=self.fake_response(b"<article>plausible partial article</article>", code=28, stderr="Operation timed out"),
        ):
            result = fetch(URL, 1)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["curl_exit_code"], 28)
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_complete_response_preserves_metadata_and_accents(self):
        body = "México: información completa."
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response(body.encode())):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], body)
        self.assertEqual(result["final_url"], URL)
        self.assertTrue(pd.isna(result["error"]))
        self.assertFalse(result["body_text_limit_exceeded"])

    def test_limit_counts_decoded_characters_and_accepts_exact_boundary(self):
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response("áéí".encode())):
            result = fetch(URL, 1, body_text_limit=3)
        self.assertEqual(result["text"], "áéí")
        self.assertTrue(pd.isna(result["error"]))

    def test_oversize_response_is_flagged_and_not_silently_truncated(self):
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response("áéíó".encode())):
            result = fetch(URL, 1, body_text_limit=3)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["text"], "")
        self.assertTrue(result["body_text_limit_exceeded"])
        self.assertIn("body_text_limit_exceeded", result["error"])

    def test_declared_charset_is_respected(self):
        body = "México, información"
        with patch(
            f"{MODULE}.run_curl",
            side_effect=self.fake_response(body.encode("iso-8859-1"), stdout=f"200\t{URL}\ttext/html; charset=iso-8859-1"),
        ):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], body)
        self.assertTrue(pd.isna(result["error"]))

    def test_invalid_encoding_does_not_silently_drop_text(self):
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response(b"news\xffcontent")):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], "")
        self.assertIn("UnicodeDecodeError", result["error"])

    def test_unknown_declared_encoding_is_reported(self):
        with patch(
            f"{MODULE}.run_curl",
            side_effect=self.fake_response(b"news", stdout=f"200\t{URL}\ttext/html; charset=unknown-encoding"),
        ):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], "")
        self.assertIn("LookupError", result["error"])

    def test_missing_body_file_is_not_success(self):
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response(None)):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["error"], "missing_response_body_file")

    def test_invalid_http_metadata_is_not_success(self):
        with patch(f"{MODULE}.run_curl", side_effect=self.fake_response(b"news", stdout="not metadata")):
            result = fetch(URL, 1)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["error"], "missing_or_invalid_http_status")

    def test_invalid_limit_rejected_before_network_call(self):
        with patch(f"{MODULE}.run_curl") as run, self.assertRaises(ValueError):
            fetch(URL, 1, body_text_limit=0)
        run.assert_not_called()

    def test_browser_profile_and_explicit_headers_are_preserved(self):
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/curl"), patch(
            f"{MODULE}.subprocess.run", return_value=self.completed()
        ) as run:
            run_curl(URL, Path("unused-body"), 1, profile="browser", headers=["X-Test: value"], referer="https://example.test/")
        command = run.call_args.args[0]
        self.assertIn("X-Test: value", command)
        self.assertIn("https://example.test/", command)
        self.assertIn("Accept-Language: es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6", command)


if __name__ == "__main__":
    unittest.main()
