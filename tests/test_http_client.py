"""Tests for HttpClient resiliency, rate limiting, headers, and retry backoff."""

import asyncio
import time

import httpx
import pytest
import respx

from src.tools.http_client import USER_AGENTS, HttpClient


class TestHttpClientHeaders:
    def test_headers_include_browser_fingerprints(self):
        client = HttpClient()
        headers = client._get_headers()
        assert "User-Agent" in headers
        assert headers["User-Agent"] in USER_AGENTS
        assert headers["Sec-Fetch-Dest"] == "document"
        assert "pt-BR" in headers["Accept-Language"]
        assert "gzip" in headers["Accept-Encoding"]

    def test_custom_headers_override_defaults(self):
        client = HttpClient()
        headers = client._get_headers({"X-Custom-Header": "custom-val"})
        assert headers["X-Custom-Header"] == "custom-val"


class TestHttpClientRetriesAndResilience:
    @respx.mock
    async def test_successful_fetch(self):
        respx.get("https://example.com/item").mock(
            return_value=httpx.Response(200, text="<html>Product Page</html>")
        )
        client = HttpClient()
        html = await client.fetch("https://example.com/item")
        assert "Product Page" in html

    @respx.mock
    async def test_retry_on_503_and_eventual_success(self, monkeypatch):
        # Patch sleep to not slow down tests
        async def noop_sleep(_):
            pass

        monkeypatch.setattr(asyncio, "sleep", noop_sleep)

        route = respx.get("https://example.com/item").mock(
            side_effect=[
                httpx.Response(503, text="Service Unavailable"),
                httpx.Response(200, text="<html>Recovered</html>"),
            ]
        )
        client = HttpClient()
        html = await client.fetch("https://example.com/item")
        assert "Recovered" in html
        assert route.call_count == 2

    @respx.mock
    async def test_retry_on_429_rate_limit(self, monkeypatch):
        async def noop_sleep(_):
            pass

        monkeypatch.setattr(asyncio, "sleep", noop_sleep)

        route = respx.get("https://example.com/rate-limited").mock(
            side_effect=[
                httpx.Response(429, text="Too Many Requests"),
                httpx.Response(200, text="<html>Success after 429</html>"),
            ]
        )
        client = HttpClient()
        html = await client.fetch("https://example.com/rate-limited")
        assert "Success after 429" in html
        assert route.call_count == 2

    @respx.mock
    async def test_max_retries_exhausted_raises_runtime_error(self, monkeypatch):
        async def noop_sleep(_):
            pass

        monkeypatch.setattr(asyncio, "sleep", noop_sleep)

        respx.get("https://example.com/always-down").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = HttpClient()
        with pytest.raises(RuntimeError) as exc_info:
            await client.fetch("https://example.com/always-down")
        assert "após 3 tentativas" in str(exc_info.value)

    @respx.mock
    async def test_connection_error_retries_and_raises(self, monkeypatch):
        async def noop_sleep(_):
            pass

        monkeypatch.setattr(asyncio, "sleep", noop_sleep)

        respx.get("https://example.com/timeout").mock(
            side_effect=httpx.ConnectTimeout("Connection timed out")
        )
        client = HttpClient()
        with pytest.raises(RuntimeError) as exc_info:
            await client.fetch("https://example.com/timeout")
        assert "Connection timed out" in str(exc_info.value)


class TestHttpClientRateLimiting:
    @respx.mock
    async def test_rate_limit_delays_consecutive_calls_to_same_domain(self, monkeypatch):
        respx.get("https://loja.com/p1").mock(return_value=httpx.Response(200, text="Page 1"))
        respx.get("https://loja.com/p2").mock(return_value=httpx.Response(200, text="Page 2"))

        client = HttpClient()
        client._min_domain_delay = 0.05  # 50ms para teste ágil

        t0 = time.time()
        await client.fetch("https://loja.com/p1")
        await client.fetch("https://loja.com/p2")
        elapsed = time.time() - t0

        assert elapsed >= 0.04
