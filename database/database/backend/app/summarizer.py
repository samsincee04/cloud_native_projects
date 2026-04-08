import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class SummarizerError(Exception):
    """Base exception for summarizer failures."""

    pass


class MissingAPIKeyError(SummarizerError):
    """Raised when OPENROUTER_API_KEY is not set."""

    pass


class UpstreamRequestError(SummarizerError):
    """Raised when the OpenRouter API request fails."""

    pass


def summarize_with_openrouter(
    text: str,
    max_length: int,
    api_key: str,
    model: str,
) -> tuple[str, bool]:
    """
    Call OpenRouter to summarize text.

    Returns:
        Tuple of (summary, truncated) where truncated is True if the output
        exceeded max_length words and was truncated.
    """
    if not api_key or api_key.strip() == "" or api_key == "your_api_key_here":
        raise MissingAPIKeyError("OPENROUTER_API_KEY is missing or invalid")

    prompt = (
        f"Summarize the following text in at most {max_length} words. "
        "Be concise. Output only the summary, no preamble.\n\n"
        f"{text}"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max(max_length * 2, 100),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise UpstreamRequestError(f"OpenRouter API error: {e.response.status_code} - {e.response.text}") from e
    except httpx.RequestError as e:
        raise UpstreamRequestError(f"OpenRouter request failed: {e}") from e

    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise UpstreamRequestError("OpenRouter returned no choices")

    content = choices[0].get("message", {}).get("content", "")
    if content is None:
        content = ""

    summary = content.strip()
    words = summary.split()
    truncated = len(words) > max_length
    if truncated:
        summary = " ".join(words[:max_length])

    return summary, truncated
