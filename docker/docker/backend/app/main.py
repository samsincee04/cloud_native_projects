import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models import SummarizeRequest, SummarizeResponse
from app.summarizer import MissingAPIKeyError, UpstreamRequestError, summarize_with_openrouter

# Load .env from lab4/ directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
_env_loaded = load_dotenv(_env_path)

app = FastAPI()
security = HTTPBearer(auto_error=False)
VALID_TOKEN = "dev-token"


def verify_token(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    if credentials.credentials != VALID_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid authorization token")


@app.get("/health")
def health():
    api_key_set = bool(_get_env("OPENROUTER_API_KEY"))
    model_set = bool(_get_env("OPENROUTER_MODEL"))
    return {
        "status": "ok",
        "env": {
            "dotenv_loaded": _env_loaded,
            "openrouter_api_key_set": api_key_set,
            "openrouter_model_set": model_set,
        },
    }


def _get_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    return value if value else ""


@app.post("/summarize", response_model=SummarizeResponse, dependencies=[Depends(verify_token)])
def summarize(body: SummarizeRequest) -> SummarizeResponse:
    api_key = _get_env("OPENROUTER_API_KEY")
    model = _get_env("OPENROUTER_MODEL") or "mistralai/devstral-2512:free"

    try:
        summary, truncated = summarize_with_openrouter(
            text=body.text,
            max_length=body.max_length,
            api_key=api_key,
            model=model,
        )
    except MissingAPIKeyError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except UpstreamRequestError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return SummarizeResponse(
        summary=summary,
        model=model,
        truncated=truncated,
    )
