"""Utility Bill Decoder CLI.

python main.py --bills <folder> --level1-template <csv> --level2-template <csv> --out <folder>
python main.py --bills train/bills            (no templates: prints results, uses 12 built-in sample questions)
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from cache import Cache
from config import load_settings
from extract import extract_history, extract_level1, provider_from_bill_id
from io_utils import dumps_one_line, find_bills, read_csv, write_csv
from llm import GeminiClient
from qa import SAMPLE_QUESTIONS, answer_bill, fallback_answer
from schemas import null_bill
from validate import L1_COLS, L2_COLS, validate_outputs

log = logging.getLogger("main")


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / "run.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # their URLs can carry request details


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Decode electricity bills (Level 1 extraction + Level 2 Q&A).")
    p.add_argument("--bills", required=True, type=Path, help="folder with bill images (.png/.jpg)")
    p.add_argument("--level1-template", type=Path, help="level1.csv template (bill_id,json)")
    p.add_argument("--level2-template", type=Path, help="level2.csv template (bill_id,question_id,question,answer)")
    p.add_argument("--out", type=Path, default=Path("output"), help="output folder (default: output)")
    p.add_argument("--no-cache", action="store_true", help="ignore and do not write the disk cache")
    p.add_argument("--expected-bills", type=int, default=10,
                   help="bills the validator expects when templates are used (default 10 = competition test set)")
    p.add_argument("--expected-questions", type=int, default=12, help="questions per bill expected (default 12)")
    args = p.parse_args()
    if bool(args.level1_template) != bool(args.level2_template):
        p.error("give both --level1-template and --level2-template, or neither")
    return args


def build_plan(args) -> tuple[list[dict], list[dict], dict[str, Path]]:
    """Returns (level1 rows, level2 rows, bill_id -> image path), in template order when templates are given."""
    images = {p.stem: p for p in find_bills(args.bills)}
    if args.level1_template:
        cols1, rows1 = read_csv(args.level1_template)
        cols2, rows2 = read_csv(args.level2_template)
        if cols1 != L1_COLS or cols2 != L2_COLS:
            raise SystemExit(f"Unexpected template columns: {cols1} / {cols2}")
        return rows1, rows2, images
    if not images:
        raise SystemExit(f"No .png/.jpg bills found in {args.bills}")
    rows1 = [{"bill_id": b, "json": ""} for b in images]
    rows2 = [{"bill_id": b, "question_id": f"Q{i}", "question": q, "answer": ""}
             for b in images for i, q in enumerate(SAMPLE_QUESTIONS, 1)]
    return rows1, rows2, images


def process_bill(client, cache, bill_id: str, image: Path | None, questions: dict[str, str]) -> tuple[dict, dict]:
    """Never raises: any failure degrades to a null-schema row and honest fallback answers."""
    if image is None:
        log.error("[%s] no image found in --bills folder", bill_id)
        return null_bill(provider_from_bill_id(bill_id)), {q: fallback_answer(t, "bill image not found") for q, t in questions.items()}
    try:
        bill = extract_level1(client, cache, bill_id, image)
        history = extract_history(client, cache, bill_id, image)
        answers = answer_bill(client, cache, bill_id, image, bill, history, questions)
        return bill, answers
    except Exception as e:  # last-resort guard so one bill can't stop the run
        log.exception("[%s] unexpected failure: %s", bill_id, e)
        return null_bill(provider_from_bill_id(bill_id)), {q: fallback_answer(t, "processing error") for q, t in questions.items()}


def main() -> int:
    args = parse_args()
    settings = load_settings()
    setup_logging(settings.log_dir)
    log.info("Starting with %r", settings)
    client = GeminiClient(settings)
    cache = Cache(settings.cache_dir, enabled=not args.no_cache)

    rows1, rows2, images = build_plan(args)
    questions_by_bill: dict[str, dict[str, str]] = {}
    for r in rows2:
        questions_by_bill.setdefault(r["bill_id"], {})[r["question_id"]] = r["question"]

    verbose = not args.level1_template
    results: dict[str, tuple[dict, dict]] = {}
    for i, row in enumerate(rows1, 1):
        bid = row["bill_id"]
        log.info("=== Bill %d/%d: %s ===", i, len(rows1), bid)
        results[bid] = process_bill(client, cache, bid, images.get(bid), questions_by_bill.get(bid, {}))
        if verbose:
            bill, answers = results[bid]
            print(f"\n--- {bid} Level 1 ---\n{json.dumps(bill, indent=2, ensure_ascii=False)}")
            for qid, ans in answers.items():
                print(f"{qid}: {questions_by_bill[bid][qid]}\n    {ans}")

    for row in rows1:
        row["json"] = dumps_one_line(results[row["bill_id"]][0])
    for row in rows2:
        row["answer"] = results[row["bill_id"]][1][row["question_id"]]

    out = args.out
    write_csv(out / "level1.csv", L1_COLS, rows1)
    write_csv(out / "level2.csv", L2_COLS, rows2)
    log.info("Wrote %s and %s", out / "level1.csv", out / "level2.csv")

    if args.level1_template:  # competition mode: PASS requires the full 10 x 12 shape
        ok = validate_outputs(out / "level1.csv", out / "level2.csv", args.expected_bills, args.expected_questions,
                              args.level1_template, args.level2_template)
    else:                     # local mode: whatever is in the bills folder
        n_bills = len(rows1)
        ok = validate_outputs(out / "level1.csv", out / "level2.csv", n_bills, len(SAMPLE_QUESTIONS))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
