"""Unit tests for app.retry (retry_async with exponential backoff)."""

import asyncio

import pytest

from app.retry import retry_async


@pytest.mark.asyncio
async def test_retry_async_success_first_try():
    """Returns result when the async call succeeds on first attempt."""
    call_count = 0

    async def succeed() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(succeed, retries=3)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_success_after_failures():
    """Retries on failure and returns result when a later attempt succeeds."""
    call_count = 0

    async def fail_twice_then_succeed() -> int:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temp")
        return 42

    result = await retry_async(fail_twice_then_succeed, retries=5, base_delay_s=0.01)
    assert result == 42
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausted_raises():
    """Raises the last exception when all retries are exhausted."""
    async def always_fail() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await retry_async(always_fail, retries=3, base_delay_s=0.01)


@pytest.mark.asyncio
async def test_retry_async_zero_retries_raises_immediately():
    """With retries=0, fails immediately without retrying."""
    call_count = 0

    async def fail() -> None:
        nonlocal call_count
        call_count += 1
        raise OSError("err")

    with pytest.raises(OSError, match="err"):
        await retry_async(fail, retries=0)

    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_calls_up_to_retries_plus_one():
    """Attempts at most retries+1 times (initial try + retries)."""
    call_count = 0

    async def always_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("again")

    with pytest.raises(ValueError, match="again"):
        await retry_async(always_fail, retries=3, base_delay_s=0.01)

    assert call_count == 4  # 1 initial + 3 retries
