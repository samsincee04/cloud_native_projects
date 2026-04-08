import asyncio
from typing import Awaitable, Callable, TypeVar
T = TypeVar("T")

async def retry_async(
    fn: Callable[[], Awaitable[T]],
    retries: int = 3,
    base_delay_s: float = 0.5,
) -> T:
    """Retry an async operation with exponential backoff."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                delay = base_delay_s * (2 ** attempt)
                await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc