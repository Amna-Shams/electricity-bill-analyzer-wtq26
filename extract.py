"""Level 1 extraction (plus the history-table extraction that feeds Level 2 calculations)."""
import logging
from pathlib import Path

from pydantic import ValidationError

from cache import Cache, digest
from llm import GeminiClient
from prompts import HISTORY_SYSTEM, HISTORY_USER, LEVEL1_SYSTEM, LEVEL1_USER
from schemas import Bill, History, null_bill

log = logging.getLogger(__name__)

_PREFIX_TO_PROVIDER = {"KESC": "KE", "KE": "KE", "LESCO": "LESCO", "IESCO": "IESCO"}


def provider_from_bill_id(bill_id: str) -> str | None:
    """File names carry the provider (KESC_0008 -> KE); used only for the null fallback."""
    return _PREFIX_TO_PROVIDER.get(bill_id.split("_")[0].upper())


def _validated(client: GeminiClient, system: str, user: str, image: Path, model_cls, attempts: int, label: str):
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            raw = client.generate_json(system, user, image)
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON is not an object")
            return model_cls.model_validate(raw)
        except (ValidationError, ValueError) as e:  # json.JSONDecodeError is a ValueError
            last_err = e
            log.warning("%s: invalid output (attempt %d/%d): %s", label, attempt, attempts, str(e)[:200])
    raise RuntimeError(f"{label}: invalid after {attempts} attempts: {last_err}")


def extract_level1(client: GeminiClient, cache: Cache, bill_id: str, image: Path, attempts: int = 3) -> dict:
    key = digest(image.read_bytes(), LEVEL1_SYSTEM, LEVEL1_USER)
    cached = cache.get(bill_id, "level1", key)
    if cached is not None:
        return cached
    try:
        bill = _validated(client, LEVEL1_SYSTEM, LEVEL1_USER, image, Bill, attempts, f"[{bill_id}] level1")
        result = bill.to_json_dict()
    except Exception as e:  # network/auth/validation: keep the run going with a full-schema null row
        log.error("[%s] level1 failed, writing null schema: %s", bill_id, e)
        return null_bill(provider_from_bill_id(bill_id))  # not cached, so a re-run retries
    cache.put(bill_id, "level1", key, result)
    return result


def extract_history(client: GeminiClient, cache: Cache, bill_id: str, image: Path, attempts: int = 3) -> dict:
    key = digest(image.read_bytes(), HISTORY_SYSTEM, HISTORY_USER)
    cached = cache.get(bill_id, "history", key)
    if cached is not None:
        return cached
    try:
        hist = _validated(client, HISTORY_SYSTEM, HISTORY_USER, image, History, attempts, f"[{bill_id}] history")
        result = hist.model_dump()
    except Exception as e:
        log.error("[%s] history extraction failed, continuing without history: %s", bill_id, e)
        return {"usage_history": [], "billing_history": [], "failed": True}
    cache.put(bill_id, "history", key, result)
    return result
