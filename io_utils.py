"""CSV reading/writing and bill discovery."""
import csv
import json
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def find_bills(folder: Path) -> list[Path]:
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def dumps_one_line(obj: dict) -> str:
    """Single-line JSON (csv module doubles the quotes when it quotes the cell)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
