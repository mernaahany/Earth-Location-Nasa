import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from analog_validation.retrieval import SearchError
from analog_validation.serper import SerperSearch, _NoRedirect


class SerperTests(unittest.TestCase):
    def response(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        return response

    @patch("analog_validation.serper.build_opener")
    def test_official_wire_format_and_pending_status(self, opener):
        opener.return_value.open.return_value = self.response({"organic": [
            {"title": "Lunar rover", "link": "https://www.nasa.gov/rover", "snippet": "Navigation research", "position": 1}]})
        result = SerperSearch("test-secret", timeout=7).search("moon navigation", limit=5)
        call = opener.return_value.open.call_args
        req = call.args[0]
        self.assertEqual(req.full_url, "https://google.serper.dev/search")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("X-api-key"), "test-secret")
        self.assertEqual(json.loads(req.data), {"q": "moon navigation", "num": 5})
        self.assertEqual(call.kwargs["timeout"], 7)
        self.assertEqual(result[0].verification_status, "pending_review")
        self.assertNotIn("test-secret", repr(result))

    @patch("analog_validation.serper.build_opener")
    def test_http_error_does_not_echo_body_or_key(self, opener):
        for status in (401, 403, 429, 500):
            opener.return_value.open.side_effect = HTTPError("https://google.serper.dev/search", status,
                                                           "test-secret", {}, io.BytesIO(b"test-secret"))
            with self.assertRaises(SearchError) as caught:
                SerperSearch("test-secret").search("query")
            self.assertIn(str(status), str(caught.exception))
            self.assertNotIn("test-secret", str(caught.exception))

    @patch("analog_validation.serper.build_opener")
    def test_network_errors_are_redacted(self, opener):
        for error in (URLError("test-secret"), TimeoutError("test-secret")):
            opener.return_value.open.side_effect = error
            with self.assertRaises(SearchError) as caught:
                SerperSearch("test-secret").search("query")
            self.assertNotIn("test-secret", str(caught.exception))

    @patch("analog_validation.serper.build_opener")
    def test_invalid_responses(self, opener):
        for payload in (b"not json", [], {}, {"organic": {}}, {"error": "test-secret"},
                        {"message": "test-secret"}, b"x" * 2_000_001):
            opener.return_value.open.return_value = self.response(payload)
            with self.subTest(payload=type(payload)), self.assertRaises(SearchError) as caught:
                SerperSearch("test-secret").search("query")
            self.assertNotIn("test-secret", str(caught.exception))

    @patch("analog_validation.serper.build_opener")
    def test_malformed_items_skipped_and_empty_results_valid(self, opener):
        opener.return_value.open.return_value = self.response({"organic": [None, {},
            {"title": "a", "link": "b", "snippet": "c", "position": True}]})
        self.assertEqual(SerperSearch("key").search("query"), [])
        opener.return_value.open.return_value = self.response({"organic": []})
        self.assertEqual(SerperSearch("key").search("query"), [])

    def test_redirects_disabled(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.org"))

    def test_configuration_validation(self):
        for key in ("", " "):
            with self.assertRaises(ValueError):
                SerperSearch(key)
        for timeout in (0, -1, 61, float("nan")):
            with self.assertRaises(ValueError):
                SerperSearch("key", timeout=timeout)
        for limit in (0, 11, True, 1.5):
            with self.assertRaises(ValueError):
                SerperSearch("key").search("query", limit=limit)

    @patch.dict(os.environ, {}, clear=True)
    def test_env_file_alias_and_environment_precedence(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / ".env"
            file.write_text("SEARCH_API='file-key'\nUNRELATED=ignore\n", encoding="utf-8")
            self.assertEqual(SerperSearch.from_env(file)._api_key, "file-key")
            with patch.dict(os.environ, {"SERPER_API_KEY": "env-key"}):
                self.assertEqual(SerperSearch.from_env(file)._api_key, "env-key")
            self.assertNotIn("SEARCH_API", os.environ)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_fails_explicitly(self):
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            SerperSearch.from_env(Path(directory) / "absent.env")


if __name__ == "__main__":
    unittest.main()
