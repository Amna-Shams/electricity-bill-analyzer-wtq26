"""All arithmetic for Level 2 lives here. The model never calculates; it only copies these values into its answers."""
import re
from calendar import month_name
from typing import Optional


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    if x is None:
        return None
    x = round(x, nd)
    return int(x) if float(x).is_integer() else x


def _pct(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    if part is None or not whole:
        return None
    return _r(part / whole * 100)


def month_label(m: Optional[str]) -> Optional[str]:
    if not m or not re.match(r"^\d{4}-\d{2}$", m):
        return m
    y, mo = m.split("-")
    return f"{month_name[int(mo)]} {y}"


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _previous_usage(rows: list[dict], current_month: Optional[str]) -> list[tuple]:
    out = [(r["month"], _num(r.get("units"))) for r in rows if r.get("month") and r.get("month") != current_month]
    return [(m, u) for m, u in out if u is not None]


def usage_stats(rows: list[dict], current_month: Optional[str], current_units: Optional[float]) -> dict:
    """Stats over PREVIOUS months (the current bill month is excluded from the history list)."""
    prev = _previous_usage(rows, current_month)
    out: dict = {
        "previous_months_count": len(prev),
        "previous_months": [{"month": month_label(m), "units": _r(u)} for m, u in prev],
        "current_month": month_label(current_month), "current_units": _r(current_units),
    }
    if not prev:
        return out
    units = [u for _, u in prev]
    avg = sum(units) / len(units)
    if any(u < 0 for u in units):
        out["has_negative_units"] = True
        out["negative_units_note"] = ("Some previous months show NEGATIVE units as printed on the bill (net-metering export/credit). "
                                      "Averages and percentage comparisons include these negative values, so they are not "
                                      "typical consumption figures.")
    hi, lo = max(prev, key=lambda t: t[1]), min(prev, key=lambda t: t[1])
    out.update(
        average_units_previous_months=_r(avg),
        highest_previous_month={"month": month_label(hi[0]), "units": _r(hi[1])},
        lowest_previous_month={"month": month_label(lo[0]), "units": _r(lo[1])},
        total_units_previous_months=_r(sum(units)),
        most_recent_previous_month={"month": month_label(prev[-1][0]), "units": _r(prev[-1][1])},
    )
    if current_units is not None:
        out["current_vs_average"] = {"difference_units": _r(current_units - avg),
                                     "percent_of_average": _pct(current_units, avg) if avg > 0 else None}
        out["current_vs_highest_previous"] = {"difference_units": _r(current_units - hi[1])}
        out["current_vs_lowest_previous"] = {"difference_units": _r(current_units - lo[1])}
        last = prev[-1][1]
        out["current_vs_most_recent_previous"] = {
            "difference_units": _r(current_units - last),
            # a percentage on a zero/negative base is meaningless, so it is withheld
            "percent_change": _pct(current_units - last, last) if last > 0 else None}
        allm = units + [current_units]
        out["average_units_including_current"] = _r(sum(allm) / len(allm))
        out["current_is_highest_of_all"] = current_units >= max(allm)
        out["current_is_lowest_of_all"] = current_units <= min(allm)
    return out


def billing_stats(rows: list[dict], current_month: Optional[str]) -> dict:
    prev = [r for r in rows if r.get("month") and r.get("month") != current_month]
    billed = [(r["month"], _num(r.get("billed_amount"))) for r in prev if _num(r.get("billed_amount")) is not None]
    out: dict = {"previous_months_count": len(prev),
                 "rows": [{"month": month_label(r["month"]), "billed_amount": _r(_num(r.get("billed_amount"))),
                           "pay_date": r.get("pay_date"), "payment": _r(_num(r.get("payment")))} for r in prev]}
    if billed:
        vals = [b for _, b in billed]
        hi, lo = max(billed, key=lambda t: t[1]), min(billed, key=lambda t: t[1])
        out.update(average_billed_amount=_r(sum(vals) / len(vals)), total_billed_amount=_r(sum(vals)),
                   highest_billed={"month": month_label(hi[0]), "amount": _r(hi[1])},
                   lowest_billed={"month": month_label(lo[0]), "amount": _r(lo[1])})
    paid = [(r["month"], _num(r.get("payment"))) for r in prev if _num(r.get("payment")) not in (None, 0.0)]
    out["payment_note"] = ("A blank payment cell means no payment is printed for that month; a payment printed as 0 means the bill "
                           "shows zero paid. The bill does not say why in either case. Do not guess a reason.")
    out["months_with_recorded_payment"] = [month_label(m) for m, _ in paid]
    out["months_with_payment_printed_as_zero"] = [month_label(r["month"]) for r in prev if _num(r.get("payment")) == 0.0]
    out["months_with_blank_payment"] = [month_label(r["month"]) for r in prev if _num(r.get("payment")) is None]
    if paid:
        out["total_payments_recorded"] = _r(sum(p for _, p in paid))
    return out


def bill_breakdown(bill: dict) -> dict:
    cur, units = _num(bill.get("current_bill")), _num(bill.get("units_consumed"))
    tc, tt = _num(bill.get("total_charges")), _num(bill.get("total_taxes"))
    within, after = _num(bill.get("payable_within_due_date")), _num(bill.get("payable_after_due_date"))
    out = {
        "taxes_percent_of_current_bill": _pct(tt, cur),
        "charges_percent_of_current_bill": _pct(tc, cur),
        "cost_per_unit_current_bill_divided_by_units": _r(cur / units, 2) if cur is not None and units else None,
        "charge_lines": [{"type": c["type"], "amount": c["amount"], "percent_of_current_bill": _pct(c["amount"], cur)}
                         for c in bill.get("charges", [])],
        "tax_lines": [{"type": t["type"], "amount": t["amount"], "percent_of_current_bill": _pct(t["amount"], cur)}
                      for t in bill.get("taxes", [])],
    }
    if within is not None and after is not None:
        out["late_payment_extra_amount"] = _r(after - within)
        out["late_payment_extra_percent_of_on_time_amount"] = _pct(after - within, within)
    fixed_lines = [c["amount"] for c in bill.get("charges", []) if c["type"] == "fixed"]
    if fixed_lines:
        out["fixed_charges_total"] = _r(sum(fixed_lines))
        out["fixed_charges_percent_of_current_bill"] = _pct(sum(fixed_lines), cur)
    return out


_UNIT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:units|kwh)", re.I)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", re.I)


def question_specific(question: str, usage_rows: list[dict], current_month, bill: dict) -> dict:
    """Numbers mentioned in a question (unit thresholds, percentages) -> precomputed answers."""
    out: dict = {}
    prev = _previous_usage(usage_rows, current_month)
    cur_units = _num(bill.get("units_consumed"))
    for m in _UNIT_RE.finditer(question):
        t = float(m.group(1).replace(",", ""))
        above = [(mo, u) for mo, u in prev if u > t]
        below = [(mo, u) for mo, u in prev if u < t]
        cur_above = (cur_units > t) if cur_units is not None else None
        out.setdefault("unit_thresholds", []).append({
            "threshold_units": _r(t),
            "previous_months_considered": len(prev),
            "previous_months_above": len(above),
            "months_above": [f"{month_label(mo)} ({_r(u)})" for mo, u in above],
            "previous_months_below": len(below),
            "months_below": [f"{month_label(mo)} ({_r(u)})" for mo, u in below],
            "current_month_units_above": cur_above,
            "count_above_including_current_month": len(above) + (1 if cur_above else 0),
        })
    cur = _num(bill.get("current_bill"))
    for m in _PCT_RE.finditer(question):
        p = float(m.group(1))
        sc: dict = {"percent": _r(p)}
        if cur_units is not None:
            sc["units_if_usage_reduced"] = _r(cur_units * (1 - p / 100))
            sc["units_if_usage_increased"] = _r(cur_units * (1 + p / 100))
        if cur is not None and cur_units:
            rate = cur / cur_units
            sc["ESTIMATE_bill_if_usage_reduced"] = _r(cur_units * (1 - p / 100) * rate)
            sc["ESTIMATE_bill_if_usage_increased"] = _r(cur_units * (1 + p / 100) * rate)
            sc["method"] = ("Estimate: new units multiplied by this month's average cost per unit "
                            f"(current bill {_r(cur)} divided by {_r(cur_units)} units = {_r(rate)}); real bills use "
                            "slabs, fixed charges and taxes, so the actual figure would differ.")
        out.setdefault("percent_scenarios", []).append(sc)
    return out


def estimates(bill: dict, usage: dict, billing: dict) -> dict:
    out: dict = {}
    prev_units = [r["units"] for r in usage.get("previous_months", []) if r.get("units") is not None]
    avg_u = sum(prev_units) / len(prev_units) if prev_units else None   # unrounded, so estimates are not off by rounding
    cur, units = _num(bill.get("current_bill")), _num(bill.get("units_consumed"))
    if usage.get("has_negative_units") or any((_num(r.get("billed_amount")) or 0) < 0 for r in billing.get("rows", [])):
        out["estimates_unavailable"] = ("History contains negative units/amounts (net-metering credits), so an estimate based on "
                                        "average usage or average billed amount would not be meaningful; do not give one.")
        return out
    if avg_u is not None:
        out["ESTIMATE_annual_units_at_average_previous_usage"] = _r(avg_u * 12)
        out["annual_units_method"] = ("Estimate: average monthly units over the previous months on the bill "
                                      "multiplied by 12.")
        if cur is not None and units:
            out["ESTIMATE_bill_at_average_previous_usage"] = _r(avg_u * cur / units)
            out["bill_at_average_method"] = ("Estimate: average previous monthly units multiplied by this month's "
                                             "average cost per unit (current bill divided by units consumed).")
    avg_b = billing.get("average_billed_amount")
    if avg_b is not None:
        out["ESTIMATE_annual_cost_at_average_billed_amount"] = _r(avg_b * 12)
        out["annual_cost_method"] = ("Estimate: average billed amount over the previous months on the bill "
                                     "multiplied by 12.")
    return out


def build_stats(bill: dict, history: dict, questions: dict[str, str]) -> dict:
    cm = bill.get("bill_month")
    usage = usage_stats(history.get("usage_history", []), cm, _num(bill.get("units_consumed")))
    billing = billing_stats(history.get("billing_history", []), cm)
    return {
        "bill_breakdown": bill_breakdown(bill),
        "usage_history_stats": usage,
        "billing_history_stats": billing,
        "estimates": estimates(bill, usage, billing),
        "per_question": {qid: s for qid, q in questions.items()
                         if (s := question_specific(q, history.get("usage_history", []), cm, bill))},
        "notes": "Previous-month statistics exclude the current bill month; values that include it are labelled.",
    }
