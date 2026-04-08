"""Unit tests for Todo2: retries and timeouts. No real network calls."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.retry import retry_async
from app.openrouter_client import OpenRouterClient


# --- Retry behavior: timeouts and transient failures ---


@pytest.mark.asyncio
async def test_retry_async_retries_on_timeout_then_succeeds():
    """Retries when the operation raises asyncio.TimeoutError, then succeeds."""
    call_count = 0

    async def timeout_once() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncio.TimeoutError("simulated timeout")
        return "ok"

    result = await retry_async(timeout_once, retries=3, base_delay_s=0.01)
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_async_exhausted_after_timeouts():
    """Raises TimeoutError when every attempt times out."""
    async def always_timeout() -> str:
        raise asyncio.TimeoutError("slow")

    with pytest.raises(asyncio.TimeoutError, match="slow"):
        await retry_async(always_timeout, retries=2, base_delay_s=0.01)


@pytest.mark.asyncio
async def test_retry_async_backoff_delay_increases():
    """Backoff delay grows between retries (exponential)."""
    attempt_times = []
    call_count = 0

    async def fail_with_timestamp() -> None:
        nonlocal call_count
        attempt_times.append(asyncio.get_event_loop().time())
        call_count += 1
        if call_count <= 3:
            raise OSError("transient")
        return None

    try:
        await retry_async(fail_with_timestamp, retries=3, base_delay_s=0.03)
    except OSError:
        pass

    assert len(attempt_times) == 4
    # Delays between attempts should increase (backoff)
    delays = [attempt_times[i + 1] - attempt_times[i] for i in range(3)]
    assert delays[1] > delays[0]
    assert delays[2] > delays[1]


# --- OpenRouterClient: timeout and retry behavior ---


@pytest.mark.asyncio
async def test_client_generate_respects_timeout():
    """generate() passes the configured timeout to the HTTP client."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"choices": [{"message": {"content": "x"}}]}
    fake_response.raise_for_status = MagicMock()

    with patch("app.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with patch("app.openrouter_client.OPENROUTER_API_KEY", "sk-fake"):
            client = OpenRouterClient(timeout_s=5.0)
            await client.generate("hi")

    call_kwargs = mock_client.post.call_args[1]
    assert call_kwargs["timeout"] == 5.0


@pytest.mark.asyncio
async def test_client_generate_retries_on_timeout():
    """generate() retries when the HTTP request times out, then succeeds."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"choices": [{"message": {"content": "done"}}]}
    fake_response.raise_for_status = MagicMock()

    post_calls = 0

    async def post_side_effect(*args, **kwargs):
        nonlocal post_calls
        post_calls += 1
        if post_calls < 2:
            raise asyncio.TimeoutError("request timeout")
        return fake_response

    with patch("app.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=post_side_effect)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with patch("app.openrouter_client.OPENROUTER_API_KEY", "sk-fake"):
            client = OpenRouterClient(timeout_s=10.0)
            result = await client.generate("hello")

    assert result == "done"
    assert post_calls == 2
