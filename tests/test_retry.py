import socket
import urllib.error
from unittest.mock import MagicMock, patch

from src.retry import retry_call
from src.adapters.rss import RSSAdapter


class TestRetryCall:
    def test_succeeds_first_attempt(self):
        """Mock function returns value, verify called once."""
        mock_fn = MagicMock(return_value="result")
        result = retry_call(mock_fn, max_attempts=3)
        assert result == "result"
        assert mock_fn.call_count == 1

    def test_retries_on_failure(self):
        """Mock function fails twice then succeeds, verify called 3 times."""
        mock_fn = MagicMock(side_effect=[ValueError("fail1"), ValueError("fail2"), "result"])
        result = retry_call(
            mock_fn,
            max_attempts=3,
            retryable_exceptions=(ValueError,),
        )
        assert result == "result"
        assert mock_fn.call_count == 3

    def test_raises_after_max_attempts(self):
        """Mock that always fails, verify raises after max_attempts."""
        mock_fn = MagicMock(side_effect=ValueError("always fail"))
        try:
            retry_call(
                mock_fn,
                max_attempts=3,
                retryable_exceptions=(ValueError,),
            )
            assert False, "Expected ValueError to be raised"
        except ValueError:
            pass
        assert mock_fn.call_count == 3

    def test_exponential_backoff(self):
        """Verify sleep times follow exponential backoff pattern."""
        mock_fn = MagicMock(side_effect=[ValueError("e1"), ValueError("e2"), "ok"])
        with patch("src.retry.time.sleep") as mock_sleep:
            result = retry_call(
                mock_fn,
                max_attempts=4,
                backoff_seconds=2.0,
                retryable_exceptions=(ValueError,),
            )
            assert result == "ok"
            # Called twice: after attempt 0 (wait=2.0*1=2.0) and attempt 1 (wait=2.0*2=4.0)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(2.0)  # 2.0 * 2^0
            mock_sleep.assert_any_call(4.0)  # 2.0 * 2^1

    def test_non_retryable_exception(self):
        """Verify it does NOT retry on non-matching exception type."""
        mock_fn = MagicMock(side_effect=TypeError("not retryable"))
        try:
            retry_call(
                mock_fn,
                max_attempts=3,
                retryable_exceptions=(ValueError,),
            )
            assert False, "Expected TypeError to be raised"
        except TypeError:
            pass
        assert mock_fn.call_count == 1  # no retry, raised immediately


class TestRSSAdapterRetry:
    def test_rss_adapter_retries_on_network_error(self):
        """Verify RSSAdapter.fetch uses retry on network errors."""
        adapter = RSSAdapter(timeout=30, retry_attempts=2, retry_backoff=0.01)

        with patch("src.adapters.rss.feedparser.parse") as mock_parse:
            mock_parse.side_effect = urllib.error.URLError("timeout")
            result = adapter.fetch("http://example.com/rss", "TestSource")
            # Should return empty list after exhausting retries
            assert result == []
            assert mock_parse.call_count == 2  # retry_attempts=2

    def test_rss_adapter_retries_on_os_error(self):
        """OSError is also retryable."""
        adapter = RSSAdapter(timeout=30, retry_attempts=3, retry_backoff=0.01)

        with patch("src.adapters.rss.feedparser.parse") as mock_parse:
            fallback_feed = MagicMock()
            fallback_feed.bozo = True
            fallback_feed.bozo_exception = "parse error"
            fallback_feed.entries = []
            mock_parse.side_effect = [
                OSError("connection reset"),
                OSError("connection reset"),
                fallback_feed,
            ]
            result = adapter.fetch("http://example.com/rss", "TestSource")
            # Should retry twice then get a bozo feed (empty entries)
            assert result == []
            assert mock_parse.call_count == 3

    def test_rss_adapter_retries_on_socket_timeout(self):
        """socket.timeout is also retryable."""
        adapter = RSSAdapter(timeout=30, retry_attempts=2, retry_backoff=0.01)

        with patch("src.adapters.rss.feedparser.parse") as mock_parse:
            mock_parse.side_effect = socket.timeout("timed out")
            result = adapter.fetch("http://example.com/rss", "TestSource")
            assert result == []
            assert mock_parse.call_count == 2

    def test_rss_adapter_returns_articles_when_retry_succeeds(self):
        """After a transient error, the adapter returns articles on retry success."""
        adapter = RSSAdapter(timeout=30, retry_attempts=3, retry_backoff=0.01)

        # feedparser entries are dict-like objects with .get() method
        mock_entry = MagicMock()
        mock_entry.get = MagicMock(side_effect=lambda key, default="": {
            "title": "Test Title",
            "link": "http://example.com/1",
            "summary": "Summary text",
        }.get(key, default))
        mock_entry.published_parsed = None

        good_feed = MagicMock()
        good_feed.bozo = False
        good_feed.entries = [mock_entry]

        with patch("src.adapters.rss.feedparser.parse") as mock_parse:
            mock_parse.side_effect = [
                urllib.error.URLError("transient error"),
                good_feed,
            ]
            result = adapter.fetch("http://example.com/rss", "TestSource")
            assert len(result) == 1
            assert result[0].title == "Test Title"
            assert mock_parse.call_count == 2
