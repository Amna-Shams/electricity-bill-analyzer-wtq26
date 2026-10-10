"""Configuration: reads .env. The API key is never logged or printed."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ALLOWED_MODEL = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str = ""
    # Free tier is 15 requests/min -> one request every 4 s; 4.5 s leaves headroom.
    min_seconds_between_calls: float = 4.5
    max_validation_attempts: int = 3
    cache_dir: Path = ROOT / "cache"
    log_dir: Path = ROOT / "logs"

    def __repr__(self) -> str:  # never leak the key through repr/logging
        return f"Settings(provider={self.provider!r}, model={self.model!r}, api_key=<hidden>)"


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    provider = os.getenv("MODEL_PROVIDER", "google").strip().lower()
    model = os.getenv("MODEL_NAME", ALLOWED_MODEL).strip()
    api_key = (os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if provider != "google":
        raise SystemExit("MODEL_PROVIDER must be 'google' (this app only uses Gemini).")
    if model != ALLOWED_MODEL:
        raise SystemExit(f"MODEL_NAME must be '{ALLOWED_MODEL}' (the only model this app may call).")
    if not api_key or api_key == "your-api-key-here":
        raise SystemExit("API_KEY is missing. Copy .env.example to .env and set API_KEY.")
    return Settings(provider=provider, model=model, api_key=api_key)
