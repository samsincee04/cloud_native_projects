"""
POST /summarize tests with OpenRouter integration.

Mocking strategy:
- Mock httpx.Client in app.summarizer so client.post() returns a fake response.
  No real network calls; response shape matches OpenRouter: {choices: [{message: {content: "..."}}]}
- For missing API key: patch app.main._get_env to return empty string for OPENROUTER_API_KEY,
  which causes summarize_with_openrouter to raise MissingAPIKeyError -> 500.
- For upstream failure: mock post() to raise httpx.HTTPStatusError -> 502.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app, VALID_TOKEN


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    """Authorization: Bearer dev-token (required for /summarize success)."""
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _mock_openrouter_response(content: str):
    """Build a mock response that mimics OpenRouter's chat completion shape."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": content,
                }
            }
        ]
    }
    return mock_response


@patch("app.summarizer.httpx.Client")
def test_valid_request_with_truncation(mock_client_class, client):
    """Valid request where OpenRouter returns more than max_length words; summary is truncated."""
    mock_post = MagicMock(return_value=_mock_openrouter_response("One two three four five six seven"))
    mock_client_instance = MagicMock()
    mock_client_instance.post = mock_post
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client_instance

    with patch("app.main._get_env") as mock_get_env:
        mock_get_env.side_effect = lambda k: {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test-model"}.get(k, "")

        response = client.post(
            "/summarize",
            json={"text": "Some long input", "max_length": 4},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "model" in data
    assert "truncated" in data
    assert data["summary"] == "One two three four"
    assert data["model"] == "test-model"
    assert data["truncated"] is True


@patch("app.summarizer.httpx.Client")
def test_valid_request_without_truncation(mock_client_class, client):
    """Valid request where OpenRouter returns summary within max_length."""
    mock_post = MagicMock(return_value=_mock_openrouter_response("Hello world"))
    mock_client_instance = MagicMock()
    mock_client_instance.post = mock_post
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client_instance

    with patch("app.main._get_env") as mock_get_env:
        mock_get_env.side_effect = lambda k: {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test-model"}.get(k, "")

        response = client.post(
            "/summarize",
            json={"text": "Hello world", "max_length": 100},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "model" in data
    assert "truncated" in data
    assert data["summary"] == "Hello world"
    assert data["model"] == "test-model"
    assert data["truncated"] is False


def test_missing_openrouter_api_key_returns_500(client):
    """When OPENROUTER_API_KEY is missing, returns 500."""
    with patch("app.main._get_env") as mock_get_env:
        mock_get_env.return_value = ""

        response = client.post(
            "/summarize",
            json={"text": "Hello world", "max_length": 5},
            headers=_auth_headers(),
        )

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


@patch("app.summarizer.httpx.Client")
def test_openrouter_upstream_failure_returns_502(mock_client_class, client):
    """When OpenRouter request fails, returns 502."""
    import httpx

    mock_post = MagicMock(side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404, text="Not found")))
    mock_client_instance = MagicMock()
    mock_client_instance.post = mock_post
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client_instance

    with patch("app.main._get_env") as mock_get_env:
        mock_get_env.side_effect = lambda k: {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test-model"}.get(k, "")

        response = client.post(
            "/summarize",
            json={"text": "Hello world", "max_length": 5},
            headers=_auth_headers(),
        )

    assert response.status_code == 502
    data = response.json()
    assert "detail" in data


def test_missing_text_returns_422(client):
    """Request without text field returns 422 validation error."""
    response = client.post(
        "/summarize",
        json={"max_length": 5},
        headers=_auth_headers(),
    )
    assert response.status_code == 422


def test_empty_text_returns_422(client):
    """Request with empty text returns 422 validation error."""
    response = client.post(
        "/summarize",
        json={"text": "", "max_length": 5},
        headers=_auth_headers(),
    )
    assert response.status_code == 422


def test_missing_authorization_returns_401(client):
    """Request without Authorization header returns 401 with clear JSON error."""
    response = client.post(
        "/summarize",
        json={"text": "Hello world", "max_length": 5},
    )
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "missing" in data["detail"].lower() or "authorization" in data["detail"].lower()


def test_invalid_authorization_token_returns_401(client):
    """Request with invalid Bearer token returns 401 with clear JSON error."""
    response = client.post(
        "/summarize",
        json={"text": "Hello world", "max_length": 5},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower() or "token" in data["detail"].lower()


@patch("app.summarizer.httpx.Client")
def test_response_schema_preserves_api_contract(mock_client_class, client):
    """Response has required fields: summary (string), model (string), truncated (boolean)."""
    mock_post = MagicMock(return_value=_mock_openrouter_response("Brief summary"))
    mock_client_instance = MagicMock()
    mock_client_instance.post = mock_post
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client_instance

    with patch("app.main._get_env") as mock_get_env:
        mock_get_env.side_effect = lambda k: {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test-model"}.get(k, "")

        response = client.post(
            "/summarize",
            json={"text": "Some text", "max_length": 50},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["summary"], str)
    assert isinstance(data["model"], str)
    assert isinstance(data["truncated"], bool)
    assert set(data.keys()) == {"summary", "model", "truncated"}
