import unittest
from urllib.parse import parse_qs, urlsplit

from grangerpet.dorks import DorkError, DorkSpec, build_query, google_url, normalize_domain


class DorkTests(unittest.TestCase):
    def test_combined_document_query_and_unicode(self):
        result = build_query(DorkSpec(mode="documents", domain="https://Example.ORG/", text="годовой отчёт",
                                     exact=True, filetype="PDF", title="финансы компании", url="reports",
                                     intext="выручка", exclude='вакансии "старый отчёт"'))
        self.assertEqual(result, 'site:example.org filetype:pdf "годовой отчёт" intitle:"финансы компании" inurl:reports intext:выручка -вакансии -"старый отчёт"')

    def test_unicode_domain(self):
        self.assertEqual(normalize_domain("пример.рф"), "xn--e1afmkfd.xn--p1ai")

    def test_reject_query_injection_into_domain(self):
        for domain in ("example.org OR site:evil.org", "https://u:p@example.org", "example.org/private", "example.org:443", "example.org?x=1", "example", "-bad.example.org", "https://["):
            with self.subTest(domain=domain), self.assertRaises(DorkError):
                normalize_domain(domain)

    def test_mentions_is_phrase_with_optional_domain(self):
        self.assertEqual(build_query(DorkSpec(mode="mentions", text="Рога и копыта")), '"Рога и копыта"')

    def test_custom_syntax_validation(self):
        for query in ('site:', 'site: example.org', '"unclosed', '(one OR two', 'one)'):
            with self.subTest(query=query), self.assertRaises(DorkError):
                build_query(DorkSpec(mode="custom", text=query))

    def test_custom_combination_preserved(self):
        query = 'site:example.org (filetype:pdf OR filetype:docx) "public report" -draft'
        self.assertEqual(build_query(DorkSpec(mode="custom", text=query)), query)

    def test_google_url_roundtrip(self):
        query = 'site:example.org "исследование & наука" -копия'
        url = google_url(query)
        self.assertEqual(urlsplit(url).netloc, "www.google.com")
        self.assertEqual(parse_qs(urlsplit(url).query)["q"], [query])

    def test_required_input_and_invalid_filetype(self):
        for spec in (DorkSpec(), DorkSpec(mode="custom"), DorkSpec(mode="mentions"),
                     DorkSpec(mode="documents", domain="example.org", filetype="exe"),
                     DorkSpec(mode="mentions", text='"x"')):
            with self.assertRaises(DorkError):
                build_query(spec)


if __name__ == "__main__":
    unittest.main()
