import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from grangerpet.search import SearchError, parse_results, search_google


class SearchTests(unittest.TestCase):
    def test_real_response_fields_and_safe_links(self):
        results = parse_results({"items": [
            {"title": "Public report", "link": "https://example.org/report.pdf", "snippet": "A public report."},
            {"title": "unsafe", "link": "javascript:alert(1)"},
            {"title": "unsafe", "link": "https://user:pass@example.org"},
            {"title": "broken", "link": "https://["},
        ]}, "site:example.org")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Public report")
        self.assertEqual(results[0].snippet, "A public report.")
        self.assertEqual(results[0].query, "site:example.org")

    def test_empty_is_distinct_from_malformed(self):
        self.assertEqual(parse_results({"searchInformation": {"totalResults": "0"}}, "q"), [])
        for payload in (None, {}, {"items": "broken"}, {"error": {"code": 403}}):
            with self.assertRaises(SearchError):
                parse_results(payload, "q")

    def test_request_encoding_and_timeout(self):
        seen = []
        def opener(request, timeout):
            seen.append((request, timeout))
            return io.BytesIO(json.dumps({"searchInformation": {"totalResults": "0"}}).encode())
        self.assertEqual(search_google('"наука & мир"', "secret", "engine", opener=opener), [])
        values = parse_qs(urlsplit(seen[0][0].full_url).query)
        self.assertEqual(values["q"], ['"наука & мир"'])
        self.assertEqual(values["key"], ["secret"])
        self.assertEqual(seen[0][1], 15)

    def test_network_and_http_errors_do_not_leak_secrets(self):
        for error in (URLError("https://secret.example/?key=SECRET"), HTTPError("?key=SECRET", 403, "Forbidden", {}, None)):
            def opener(request, timeout):
                raise error
            with self.assertRaises(SearchError) as caught:
                search_google("query", "SECRET", "cx", opener=opener)
            self.assertNotIn("SECRET", str(caught.exception))

    def test_bad_json_and_oversize(self):
        for data in (b"not json", b" " * 5_000_001):
            with self.assertRaises(SearchError):
                search_google("q", "key", "cx", opener=lambda *a, **k: io.BytesIO(data))


if __name__ == "__main__":
    unittest.main()
