import asyncio
from typing import Awaitable, Callable, List

AsyncStrFn = Callable[[str], Awaitable[str]]


async def run_many(fn: AsyncStrFn, prompts: List[str]) -> List[str]:
    """
    Run fn(prompt) concurrently for all prompts and return results in the same order.
    Requirements:
    - Use asyncio.gather
    - Do NOT run sequentially in a for-loop with await inside the loop
    """
    coros = [fn(p) for p in prompts]
    return list(await asyncio.gather(*coros))


async def _run_one_with_semaphore(sem: asyncio.Semaphore, fn: AsyncStrFn, prompt: str) -> str:
    """Run fn(prompt) while holding semaphore; used to limit concurrency."""
    async with sem:
        return await fn(prompt)


async def run_many_with_limit(fn: AsyncStrFn, prompts: List[str], limit: int) -> List[str]:
    """
    Run fn(prompt) concurrently but limit the number of in-flight tasks to 'limit'.
    Hint:
    - Use asyncio.Semaphore
    - Preserve output order
    """
    sem = asyncio.Semaphore(limit)
    tasks = [_run_one_with_semaphore(sem, fn, p) for p in prompts]
    return list(await asyncio.gather(*tasks))
