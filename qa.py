"""Level 2: one model call per bill answers all questions; numbers come from calc.py."""
import json
import logging
from pathlib import Path

from cache import Cache, digest
from calc import build_stats
from llm import GeminiClient
from prompts import QA_SYSTEM

log = logging.getLogger(__name__)

# Used only when no level2 template is given (local testing on train/bills).
SAMPLE_QUESTIONS = [
    "How much of my bill is taxes?",
    "How many months in my history went above 200 units?",
    "What is my average monthly usage over the previous months shown on the bill?",
    "Which month had the highest usage, and how does this month compare with it?",
    "What is the difference between this month's units and last month's units?",
    "What are the main charges on my bill, and which one is the largest?",
    "By how much does my bill increase if I pay after the due date?",
    "What is my due date and how much do I need to pay by then?",
    "Do I have any arrears or credit carried forward from previous months?",
    "What is my average cost per unit this month?",
    "Roughly what would my bill be if I used the average number of units from my history? (estimate)",
    "Were there any months in the billing history with no recorded payment?",
]


def fallback_answer(question: str, reason: str) -> str:
    return ("I could not produce a reliable answer to this question from the bill automatically "
            f"({reason}). Please check the printed bill for this information.")


def answer_bill(client: GeminiClient, cache: Cache, bill_id: str, image: Path, bill: dict, history: dict,
                questions: dict[str, str], attempts: int = 3) -> dict[str, str]:
    """Returns {question_id: answer}; every id always gets a non-empty string."""
    stats = build_stats(bill, history, questions)
    payload = {"bill_json": bill, "computed_stats": stats, "questions": questions}
    user = ("Answer all questions using the bill image, bill_json and computed_stats below. Return JSON with keys "
            f"{', '.join(questions)}.\n\n" + json.dumps(payload, ensure_ascii=False, indent=1))
    key = digest(image.read_bytes(), QA_SYSTEM, user)
    cached = cache.get(bill_id, "qa", key)
    if cached is not None:
        return cached

    answers: dict[str, str] = {}
    reason = "model call failed"
    for attempt in range(1, attempts + 1):
        try:
            raw = client.generate_json(QA_SYSTEM, user, image)
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON is not an object")
            for qid in questions:
                v = raw.get(qid)
                if isinstance(v, str) and v.strip() and qid not in answers:
                    answers[qid] = v.strip()
            if len(answers) == len(questions):
                break
            reason = "model returned incomplete answers"
            log.warning("[%s] qa attempt %d/%d: missing %s", bill_id, attempt, attempts,
                        [q for q in questions if q not in answers])
        except Exception as e:
            reason = "model call failed"
            log.warning("[%s] qa attempt %d/%d failed: %s", bill_id, attempt, attempts, str(e)[:200])

    complete = len(answers) == len(questions)
    for qid, q in questions.items():
        answers.setdefault(qid, fallback_answer(q, reason))
    if complete:
        cache.put(bill_id, "qa", key, answers)
    else:
        log.error("[%s] qa incomplete; used fallback answers for %s", bill_id,
                  [q for q in questions if answers[q].startswith("I could not produce")])
    return answers
