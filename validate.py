"""Final validation of the generated CSV files. Prints a clear PASS/FAIL (PASS only if every check succeeds)."""
import json
from pathlib import Path

from io_utils import read_csv
from schemas import Bill

L1_COLS = ["bill_id", "json"]
L2_COLS = ["bill_id", "question_id", "question", "answer"]


def validate_outputs(level1: Path, level2: Path, expected_bills: int, questions_per_bill: int,
                     template1: Path | None = None, template2: Path | None = None) -> bool:
    problems: list[str] = []

    cols1, rows1 = read_csv(level1)
    if cols1 != L1_COLS:
        problems.append(f"level1 columns are {cols1}, expected {L1_COLS}")
    if len(rows1) != expected_bills:
        problems.append(f"level1 has {len(rows1)} rows, expected {expected_bills}")
    for r in rows1:
        cell = (r.get("json") or "").strip()
        if not cell:
            problems.append(f"level1 {r.get('bill_id')}: empty json cell")
            continue
        try:
            obj = json.loads(cell)
            Bill.model_validate(obj)
            if "\n" in cell or "\r" in cell:
                problems.append(f"level1 {r['bill_id']}: JSON spans several lines")
            missing = set(Bill.model_fields) - set(obj)
            if missing:
                problems.append(f"level1 {r['bill_id']}: missing keys {sorted(missing)}")
        except Exception as e:
            problems.append(f"level1 {r.get('bill_id')}: invalid JSON/schema ({str(e)[:80]})")

    cols2, rows2 = read_csv(level2)
    if cols2 != L2_COLS:
        problems.append(f"level2 columns are {cols2}, expected {L2_COLS}")
    expected_rows = expected_bills * questions_per_bill
    if len(rows2) != expected_rows:
        problems.append(f"level2 has {len(rows2)} rows, expected {expected_rows}")
    for r in rows2:
        if not (r.get("answer") or "").strip():
            problems.append(f"level2 {r.get('bill_id')} {r.get('question_id')}: empty answer")

    # Template fidelity: same column names, row order and untouched key columns.
    if template1 and template2:
        for name, out_rows, tpl, keys in (("level1", rows1, template1, ["bill_id"]),
                                          ("level2", rows2, template2, ["bill_id", "question_id", "question"])):
            tcols, trows = read_csv(tpl)
            if len(trows) != len(out_rows):
                problems.append(f"{name}: {len(out_rows)} rows but template has {len(trows)}")
                continue
            for i, (t, o) in enumerate(zip(trows, out_rows), 1):
                if any(t[k] != o.get(k) for k in keys):
                    problems.append(f"{name} row {i}: {keys} differ from the template")
                    break

    print("\n=== VALIDATION ===")
    print(f"level1 rows: {len(rows1)} (expected {expected_bills}) | level2 rows: {len(rows2)} (expected {expected_rows})")
    if problems:
        for p in problems[:30]:
            print(f"  - {p}")
        print("RESULT: FAIL")
        return False
    print("RESULT: PASS")
    return True
