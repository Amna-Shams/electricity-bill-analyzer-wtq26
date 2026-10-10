"""Build submission.zip:  python make_zip.py [--out submission.zip]

Layout:  output/level1.csv, output/level2.csv | source/<code, README.md, .env.example, requirements.txt, tests> | demo/demo.mp4 (if present)
Refuses to build if the API key from .env appears in any included file. Never includes .env, venv/, cache/, logs/,
__pycache__/, app.py, llm_example.py, bill image folders, or PDFs.
"""
import argparse
import os
import sys
import zipfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 15 * 1024 * 1024
EXCLUDED_NAMES = {"app.py", "llm_example.py", ".env"}
EXCLUDED_DIRS = {"venv", "cache", "logs", "__pycache__", "train", "test", ".git", "output", "demo"}
SOURCE_FILES = ["README.md", ".env.example", "requirements.txt", ".gitignore", "expected_KESC_0008.json"]


def collect() -> list[tuple[Path, str]]:
    """Returns (file on disk, path inside the zip)."""
    items: list[tuple[Path, str]] = []
    for name in ("level1.csv", "level2.csv"):
        items.append((ROOT / "output" / name, f"output/{name}"))
    for p in sorted(ROOT.glob("*.py")):                       # top-level code only (no recursion into venv etc.)
        if p.name not in EXCLUDED_NAMES:
            items.append((p, f"source/{p.name}"))
    for name in SOURCE_FILES:
        if (ROOT / name).exists():
            items.append((ROOT / name, f"source/{name}"))
    for p in sorted((ROOT / "tests").rglob("*.py")):
        if "__pycache__" not in p.parts:
            items.append((p, f"source/tests/{p.relative_to(ROOT / 'tests').as_posix()}"))
    demo = ROOT / "demo" / "demo.mp4"
    if demo.exists():
        items.append((demo, "demo/demo.mp4"))
    for other in ("demo.mov", "demo.webm"):
        if (ROOT / "demo" / other).exists():
            print(f"NOTE: demo/{other} exists but only demo.mp4 is packaged by this helper.")
    return items


def forbidden(arcname: str) -> bool:
    parts = arcname.split("/")
    return (parts[-1] in EXCLUDED_NAMES or arcname.lower().endswith(".pdf")
            or any(d in EXCLUDED_DIRS for d in parts[1:-1] if parts[0] == "source"))


def secrets_to_check() -> list[str]:
    vals = dotenv_values(ROOT / ".env")
    keys = [v.strip() for k, v in vals.items() if v and ("KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper())]
    keys += [os.environ[k].strip() for k in ("API_KEY", "GEMINI_API_KEY") if os.environ.get(k)]
    return [k for k in set(keys) if len(k) >= 8 and k != "your-api-key-here"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "submission.zip")
    ap.add_argument("--allow-partial", action="store_true", help="skip the 10-row / 120-row check on the output CSVs")
    args = ap.parse_args()

    items = collect()
    missing = [a for p, a in items if not p.exists()]
    if missing:
        print("ERROR: required files missing (run main.py first):", ", ".join(missing))
        return 1
    if not args.allow_partial:  # stops training-run output (5 bills) from being submitted by mistake
        from validate import validate_outputs
        if not validate_outputs(ROOT / "output/level1.csv", ROOT / "output/level2.csv", 10, 12):
            print("ERROR: output CSVs are not the full 10 x 12 test result - refusing to build (use --allow-partial to override).")
            return 1
    bad = [a for _, a in items if forbidden(a)]
    if bad:
        print("ERROR: forbidden files selected:", bad)
        return 1

    secrets = secrets_to_check()
    leaks = [a for p, a in items if any(s.encode() in p.read_bytes() for s in secrets)]
    if leaks:
        print("ERROR: the API key from .env appears in these files - refusing to build:")
        for a in leaks:
            print("  -", a)
        return 1
    if not secrets:
        print("WARNING: no API key found in .env, so the key scan could not check anything.")

    if args.out.exists():
        args.out.unlink()
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, a in items:
            z.write(p, a)

    # Re-check the finished archive itself.
    with zipfile.ZipFile(args.out) as z:
        if any(s.encode() in z.read(n) for n in z.namelist() for s in secrets):
            args.out.unlink()
            print("ERROR: key found inside the built archive; archive deleted.")
            return 1
        names = z.namelist()
    print(f"\n{args.out.name} contents ({len(names)} files):")
    for n in names:
        print("  ", n)
    size = args.out.stat().st_size
    print(f"\nSize: {size / 1024 / 1024:.2f} MB")
    if size > MAX_BYTES:
        print("WARNING: ZIP is over 15 MB - the portal will reject it (probably a large demo video).")
    if not any(n.startswith("demo/") for n in names):
        print("Note: no demo/demo.mp4 included (optional, up to +5 bonus points).")
    print("Key scan: OK (key not found in any included file)." if secrets else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
