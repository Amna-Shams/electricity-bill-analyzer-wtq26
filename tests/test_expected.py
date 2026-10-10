"""Compare the tool's Level 1 output for KESC_0008 with the known-correct answer.

Run from the project root:   python tests/test_expected.py
(Uses the disk cache, so it costs no extra API calls after a normal run. Add --no-cache to force a fresh call.)
Exit code 0 = all fields match.
"""
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cache import Cache  # noqa: E402
from config import load_settings  # noqa: E402
from extract import extract_level1  # noqa: E402
from llm import GeminiClient  # noqa: E402

TOLERANCE = 0.01  # the competition accepts +-1; we check much tighter


def compare(expected, actual, path="") -> list[str]:
    diffs: list[str] = []
    if isinstance(expected, dict):
        for k in expected:
            diffs += compare(expected[k], (actual or {}).get(k, "<missing>"), f"{path}{k}.")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            diffs.append(f"{path[:-1]}: expected {len(expected)} items, got {actual}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                diffs += compare(e, a, f"{path[:-1]}[{i}].")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or abs(actual - expected) > TOLERANCE:
            diffs.append(f"{path[:-1]}: expected {expected}, got {actual}")
    elif expected != actual:
        diffs.append(f"{path[:-1]}: expected {expected!r}, got {actual!r}")
    return diffs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    expected = json.loads((ROOT / "expected_KESC_0008.json").read_text(encoding="utf-8"))
    settings = load_settings()
    cache = Cache(settings.cache_dir, enabled="--no-cache" not in sys.argv)
    actual = extract_level1(GeminiClient(settings), cache, "KESC_0008", ROOT / "train" / "bills" / "KESC_0008.png")
    diffs = compare(expected, actual)
    if diffs:
        print("FAIL - differences from expected_KESC_0008.json:")
        for d in diffs:
            print("  -", d)
        return 1
    print("PASS - KESC_0008 Level 1 output matches expected_KESC_0008.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
