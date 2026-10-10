# Utility Bill Decoder (Women Tech Quest 2026 - Build Track)

A command-line tool that reads electricity bill images (K-Electric, LESCO, IESCO) and

- **Level 1** - extracts each bill into one JSON object (provider, tariff, readings, dates, charges, taxes, payable amounts);
- **Level 2** - answers 12 customer questions per bill in plain English.

It fills the two CSV templates (`level1.csv`, `level2.csv`) and writes the completed files to an output folder.

**Python:** 3.11 or later (developed and tested on Python 3.13).

## Setup

Windows (PowerShell):
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env        # set API_KEY to your Google AI Studio key
```

macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env           # set API_KEY to your Google AI Studio key
```

`.env` contents (free key at https://aistudio.google.com):
```
MODEL_PROVIDER=google
MODEL_NAME=gemini-3.5-flash-lite
API_KEY=your-api-key-here
```
The app refuses to run with any other provider or model. The API key is never logged or printed.
(`GEMINI_API_KEY` is accepted as a fallback name for `API_KEY`.)

## Run

Competition run (test bills and templates; this is the exact command):
```
python main.py --bills test/bills --level1-template test/csv/level1.csv --level2-template test/csv/level2.csv --out output
```
Results: `output/level1.csv` (10 rows) and `output/level2.csv` (120 rows). A run of 10 bills takes roughly 2.5 to 4 minutes.

Quick test on the training bills (no templates: prints each bill's Level 1 JSON and answers 12 built-in sample questions, and
saves `level1.csv` / `level2.csv` to the output folder):
```
python main.py --bills train/bills --out output
```

Check Level 1 against the known-correct answer for KESC_0008 (live call, uses the cache when available):
```
python tests/test_expected.py
```

Offline unit tests (no API calls):
```
python -m unittest discover -s tests -v
```

Build the submission ZIP (refuses if `output/` is not the full 10 x 12 result, or if the key from `.env` appears in any included file):
```
python make_zip.py
```

Options for `main.py`:

| Option | Meaning |
|---|---|
| `--no-cache` | ignore and do not write the disk cache |
| `--expected-bills N` | bills the validator expects when templates are used (default 10) |
| `--expected-questions N` | questions per bill the validator expects (default 12) |

Results are cached in `cache/` per bill and step so re-runs do not repeat model calls. The cache key includes the image bytes and the
prompt text, so changing a prompt refreshes it. Logs go to the console and `logs/run.log`.

### Output checks
After writing the CSVs the tool validates them and prints `RESULT: PASS` or `RESULT: FAIL`. PASS requires: the expected number of rows
(10 in `level1.csv`, 120 in `level2.csv` when templates are used), original column names, `bill_id` / `question_id` / `question`
identical to the templates and in the same order, no empty `json` or `answer` cell, and every `json` cell is valid single-line JSON
containing every schema key.

## Architecture

```
main.py        CLI, per-bill orchestration, error isolation, CSV output
config.py      reads .env, enforces the allowed model
llm.py         Gemini client: image + system prompt -> JSON; throttling (15 req/min); tenacity retries with backoff
prompts.py     all prompts (Level 1 rules, history-table extraction, Level 2 rules)
schemas.py     pydantic models (Level 1 schema, history tables); null-schema fallback
extract.py     Level 1 extraction and history-table extraction, with validation retries
calc.py        every calculation for Level 2 (averages, counts, percentages, differences, estimates)
qa.py          Level 2: one call per bill answers all questions; built-in sample questions
cache.py       disk cache per bill and step
io_utils.py    CSV read/write helpers
validate.py    final output validation
make_zip.py    builds submission.zip
tests/         test_expected.py (KESC_0008 check, live) and test_calc.py (offline)
```

Per bill the app makes 3 model calls (about 30 for 10 bills, inside the free tier):

1. **Level 1** - bill image + system prompt, `response_mime_type=application/json`, validated by pydantic (up to 3 attempts).
2. **History tables** - the usage history and the billing/payment history as structured rows (month, units, billed amount, payment).
3. **Level 2** - one call answering all 12 questions as JSON `Q1..Q12`, given the image, the Level 1 JSON and a statistics pack computed
   by `calc.py`.

## Design choices

- **Image input, no OCR or extraction service.** The original image file is sent to Gemini at full resolution (media resolution HIGH).
  This handles tilted phone photos and Urdu text.
- **Calculations in Python, not in the model.** The model reads the tables; `calc.py` computes averages, differences, counts above a
  threshold, percentages, highest/lowest months and estimates. Numbers mentioned in a question (for example "above 200 units" or "20%")
  are parsed and pre-computed. The model is told to copy these values and never do arithmetic. Estimates are labelled and come with a
  method sentence.
- **Previous months only.** History statistics exclude the current bill month; figures that include it are labelled separately.
- **Multi-register bills (net metering, peak/off-peak):** `previous_reading` and `current_reading` come from the main (first)
  register row; `units_consumed` is the single printed total for the bill if one exists, otherwise the units of that first register.
- **Totals-only bills (typical for LESCO and IESCO):** when only totals are printed, `charges` and `taxes` are `[]` and
  `total_charges` / `total_taxes` hold the printed totals. A single combined "Taxes" line is treated the same way. No line items are
  invented, and a summary line such as "Subsidies" is not turned into a charge entry.
- **Null over guessing.** Blank, grey-boxed or unreadable values are `null`; credits (CR) and subsidies are negative;
  `payable_after_due_date` is the highest late amount, or `null` for "NOT TO BE PAID". A trailing "/ N" after an amount
  (for example `39411 / 2`) is treated as a suffix, not a decimal.
- **Negative history (net metering).** Negative units are used as printed; the stats pack flags them, withholds percentages computed on
  a non-positive base, and withholds average-based estimates, so answers say so instead of presenting nonsense figures.
- **No identifiers.** The schema has no name, address, CNIC, account, reference, consumer or meter fields, and the prompts forbid them.
- **Never an empty cell.** If Level 1 fails after 3 validated attempts, the full schema with `null` values is written (provider is taken
  from the file-name prefix). If Level 2 fails, a short honest fallback answer is written. A bill that fails, or whose image is missing,
  never stops the run.
- **Rate limits.** Calls are spaced 4.5 s apart (about 13 per minute, under the free-tier 15/min); transient errors (429, 5xx,
  network) are retried with exponential backoff.

## Known limitations

- **IESCO summary lines.** Some IESCO bills print "Total Electricity Charges", "Subsidies" and "Net Electricity Charges" without line
  items. This tool returns `total_charges` as the printed, labelled "Total Electricity Charges" amount (for example 6102) with
  `charges: []`; it does not turn the subsidy summary into a line item or use the net amount. A grader that expects the net figure would
  read this differently.
- Quality depends on how legible the photo is; blurry or heavily tilted regions may come back `null` or be misread.
- Small printed artefacts can be misread by the model (for example a stray suffix on a tariff code such as `A-1b(03)T`).
- Questions needing a calculation that `calc.py` does not cover are answered with "the bill does not show it" rather than a guess.
- History-table extraction relies on the model reading small tables; on messy photos a month can be missed.
- Net-metering bills have negative units/credits, so averages are computed on the printed values and no average-based estimate is given.
- The model runs at temperature 0, but outputs can still vary slightly between runs.

## AI usage

- **Models and APIs:** Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) via Google AI Studio (`google-genai` SDK).
- **AI coding tools used to write the code:** Claude (Anthropic) and OpenCode.
- **Other services:** none.
