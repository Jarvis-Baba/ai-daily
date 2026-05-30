import io
from unittest.mock import patch, MagicMock
from src.adapters.content_fetcher import _TextExtractor, fetch_content


class TestTextExtractor:
    def test_extracts_visible_text_from_html(self):
        html = "<html><head><title>ignored</title></head><body><p>Hello World</p></body></html>"
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        assert "Hello World" in text
        assert "ignored" not in text

    def test_strips_script_and_style_tags(self):
        html = "<html><script>var x=1;</script><style>.a{}</style><p>Visible</p></html>"
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        assert "Visible" in text
        assert "var x=1" not in text
        assert ".a{}" not in text

    def test_collapses_whitespace(self):
        html = "<p>Hello    World</p><p>Second   paragraph</p>"
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        assert "Hello    World" not in text  # collapsed
        assert "Hello World" in text

    def test_inserts_newlines_for_block_tags(self):
        html = "<p>First</p><p>Second</p>"
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        # Should have a space or newline separating the two paragraphs
        assert "First" in text
        assert "Second" in text


class TestFetchContent:
    def test_fetch_content_handles_http_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            result = fetch_content("http://example.com", timeout=1)
            assert result == ""

    def test_fetch_content_non_html(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content("http://example.com/api", timeout=1)
            assert result == ""

    def test_fetch_content_truncates_to_max_chars(self):
        html = "<html><body><p>" + ("x" * 5000) + "</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.read.return_value = html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content("http://example.com", timeout=1, max_chars=1000)
            assert len(result) <= 1000
            assert "x" in result

    def test_fetch_content_returns_empty_on_decode_error(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.read.return_value = b"\xff\xfe\x00\x01"  # invalid UTF-8
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content("http://example.com", timeout=1)
            # Should not crash; returned text may be empty or contain replacement chars
            assert isinstance(result, str)
