"""Unit tests for app.runner async orchestration (run_many, run_many_with_limit)."""

import asyncio
import pytest

from app.runner import run_many, run_many_with_limit


# --- Simulated async function (no real network) ---


async def echo_after_delay(prompt: str, delay: float = 0.01) -> str:
    """Simulated I/O: sleep then return the prompt. Used to verify order and concurrency."""
    await asyncio.sleep(delay)
    return prompt


async def echo_with_id(prompt: str) -> str:
    """Return prompt unchanged; no delay. For fast order checks."""
    return prompt


# --- run_many ---


@pytest.mark.asyncio
async def test_run_many_empty_prompts():
    """run_many with no prompts returns empty list."""
    result = await run_many(echo_with_id, [])
    assert result == []


@pytest.mark.asyncio
async def test_run_many_single_prompt():
    """run_many with one prompt returns one result in order."""
    result = await run_many(echo_with_id, ["only"])
    assert result == ["only"]


@pytest.mark.asyncio
async def test_run_many_preserves_order():
    """run_many returns results in the same order as prompts."""
    prompts = ["a", "b", "c", "d", "e"]
    result = await run_many(echo_after_delay, prompts)
    assert result == prompts


@pytest.mark.asyncio
async def test_run_many_concurrent_execution():
    """run_many runs tasks concurrently (faster than sequential)."""
    async def slow_echo(prompt: str) -> str:
        await asyncio.sleep(0.05)
        return prompt

    prompts = ["x", "y", "z"]
    # If run concurrently, total time ~0.05s; if sequential, ~0.15s
    import time
    t0 = time.perf_counter()
    result = await run_many(slow_echo, prompts)
    elapsed = time.perf_counter() - t0
    assert result == prompts
    assert elapsed < 0.12, "Should complete in ~0.05s (concurrent), not ~0.15s (sequential)"


# --- run_many_with_limit ---


@pytest.mark.asyncio
async def test_run_many_with_limit_empty_prompts():
    """run_many_with_limit with no prompts returns empty list."""
    result = await run_many_with_limit(echo_with_id, [], limit=2)
    assert result == []


@pytest.mark.asyncio
async def test_run_many_with_limit_preserves_order():
    """run_many_with_limit returns results in the same order as prompts."""
    prompts = ["first", "second", "third", "fourth", "fifth"]
    result = await run_many_with_limit(echo_after_delay, prompts, limit=2)
    assert result == prompts


@pytest.mark.asyncio
async def test_run_many_with_limit_1_is_serial():
    """With limit=1, only one task runs at a time (order preserved)."""
    result = await run_many_with_limit(echo_after_delay, ["a", "b", "c"], limit=1)
    assert result == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_run_many_with_limit_respects_cap():
    """With limit=2, at most 2 tasks run concurrently."""
    in_flight = 0
    max_in_flight = 0

    async def track_concurrency(prompt: str) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return prompt

    result = await run_many_with_limit(
        track_concurrency, ["p1", "p2", "p3", "p4", "p5"], limit=2
    )
    assert result == ["p1", "p2", "p3", "p4", "p5"]
    assert max_in_flight <= 2, "Semaphore should cap in-flight tasks at 2"


@pytest.mark.asyncio
async def test_run_many_with_limit_larger_than_prompts():
    """limit greater than number of prompts runs all concurrently."""
    prompts = ["a", "b"]
    result = await run_many_with_limit(echo_after_delay, prompts, limit=10)
    assert result == prompts
