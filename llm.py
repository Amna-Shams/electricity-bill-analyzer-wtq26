"""Gemini client: the only place the app talks to a model (gemini-3.5-flash-lite)."""
import json
import logging
import mimetypes
import re
import threading
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors, types
from tenacity import (before_sleep_log, retry, retry_if_exception, stop_after_attempt,
                      wait_exponential)

from config import Settings

log = logging.getLogger(__name__)
_RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.APIError):
        return getattr(exc, "code", None) in _RETRYABLE_CODES
    # network hiccups (httpx timeouts / connection resets) are worth retrying
    return type(exc).__module__.startswith(("httpx", "httpcore")) or isinstance(exc, (TimeoutError, ConnectionError))


class GeminiClient:
    def __init__(self, settings: Settings):
        self._model = settings.model
        self._client = genai.Client(api_key=settings.api_key)
        self._min_gap = settings.min_seconds_between_calls
        self._last_call = 0.0
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        """Stay under the free-tier 15 requests/minute limit."""
        with self._lock:
            wait = self._last_call + self._min_gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    @retry(retry=retry_if_exception(_is_retryable), stop=stop_after_attempt(5),
           wait=wait_exponential(multiplier=4, min=4, max=60), reraise=True,
           before_sleep=before_sleep_log(log, logging.WARNING))
    def _call(self, system: str, parts: list) -> str:
        self._throttle()
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.0,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        )
        resp = self._client.models.generate_content(model=self._model, contents=parts, config=config)
        if not resp.text:
            raise ValueError("model returned empty response")
        return resp.text

    def generate_json(self, system: str, user_text: str, image_path: Path | None = None) -> Any:
        """One model call; returns parsed JSON. The image is sent as the original file bytes (full resolution)."""
        parts: list = []
        if image_path is not None:
            mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
            parts.append(types.Part.from_bytes(data=Path(image_path).read_bytes(), mime_type=mime))
        parts.append(user_text)
        return parse_json(self._call(system, parts))


def parse_json(text: str) -> Any:
    """Parse model output as JSON, tolerating markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)
