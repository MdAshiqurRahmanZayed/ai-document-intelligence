"""Scoring for the evaluation: pure functions, no network.

Comparison rules: amounts within 0.01, dates as ISO strings, invoice numbers ignoring case, spaces
and punctuation, names ignoring case, punctuation and company forms, currency ignoring case.
Each field is correct, wrong, missing (null returned, truth has a value) or invented (value
returned, truth is null). Two nulls count as correct_null.
"""

import math
import re
from decimal import Decimal, InvalidOperation

FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)
AMOUNTS = {"subtotal", "tax", "total"}
COMPANY_FORMS = {
    "ltd",
    "limited",
    "inc",
    "gmbh",
    "ab",
    "as",
    "co",
    "llc",
    "plc",
    "corp",
    "bv",
    "sarl",
}
SUCCESS = {"COMPLETED", "NEEDS_REVIEW"}
# A failure whose recorded error names one of these is the provider's quota or load, not the system.
PROVIDER_MARKERS = ("RateLimit", "Unavailable", "ServerError", "Timeout", "GoogleAPIError")
TOLERANCE = Decimal("0.01")


def norm_number(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def norm_name(value: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", str(value).lower()).split()
    return " ".join(w for w in words if w not in COMPANY_FORMS)


def money(value: object) -> Decimal | None:
    try:
        return None if value is None else Decimal(str(value))
    except InvalidOperation:
        return None


def same(field: str, expected: object, actual: object) -> bool:
    if field in AMOUNTS:
        a, b = money(expected), money(actual)
        return a is not None and b is not None and abs(a - b) <= TOLERANCE
    if field == "invoice_number":
        return norm_number(str(expected)) == norm_number(str(actual))
    if field in ("supplier_name", "customer_name"):
        return norm_name(str(expected)) == norm_name(str(actual))
    if field == "currency":
        return str(expected).upper() == str(actual).upper()
    return str(expected) == str(actual)


def judge(field: str, expected: object, actual: object) -> str:
    if expected is None:
        return "correct_null" if actual is None else "invented"
    if actual is None:
        return "missing"
    return "correct" if same(field, expected, actual) else "wrong"


def line_items_ok(expected: dict, actual: dict | None) -> bool:
    items = (actual or {}).get("line_items") or []
    total = sum((money(i.get("amount")) or Decimal(0) for i in items), Decimal(0))
    target = money(expected["line_items_sum"]) or Decimal(0)
    return len(items) == expected["line_items_count"] and abs(total - target) <= TOLERANCE


def match_invoices(expected: list[dict], actual: list[dict]) -> list[tuple[dict, dict | None]]:
    """Pair each expected invoice with an extracted one: by number first, then by position."""
    free = list(range(len(actual)))
    pairs: dict[int, int] = {}
    for i, exp in enumerate(expected):
        for j in free:
            if norm_number(actual[j].get("invoice_number") or "") == norm_number(
                exp["invoice_number"]
            ):
                pairs[i] = j
                free.remove(j)
                break
    for i in range(len(expected)):
        if i not in pairs and free:
            pairs[i] = free.pop(0)
    return [(exp, actual[pairs[i]] if i in pairs else None) for i, exp in enumerate(expected)]


def score_document(expected: list[dict], actual: list[dict]) -> dict:
    """Field judgements for every expected invoice, line items, and whether everything is right."""
    judged = []
    for exp, act in match_invoices(expected, actual):
        fields = {f: judge(f, exp[f], None if act is None else act.get(f)) for f in FIELDS}
        judged.append({"fields": fields, "line_items": act is not None and line_items_ok(exp, act)})
    exact = (
        len(actual) == len(expected)
        and all(j["line_items"] for j in judged)
        and all(v in ("correct", "correct_null") for j in judged for v in j["fields"].values())
    )
    return {"invoices": judged, "count_ok": len(actual) == len(expected), "exact": exact}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "median": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values) if values else None,
    }


def provider_limited(record: dict) -> bool:
    """Did this document fail only because the model provider refused (quota, load, outage)?"""
    if record.get("status") != "FAILED":
        return False
    messages = [
        e.get("error_message") or ""
        for e in record.get("events", [])
        if e.get("status") == "failed"
    ]
    return bool(messages) and any(m in x for x in messages[-1:] for m in PROVIDER_MARKERS)


def outcome_ok(record: dict, state: dict) -> bool:
    """Did the document end as its ground truth says? `state` has upload, status, error_code."""
    expected = record["expected_outcome"]
    if expected == "success":
        return state.get("status") in SUCCESS
    kind, _, code = expected.partition(":")
    if kind == "rejected":
        return state.get("upload") == "rejected" and state.get("reason") == code
    return state.get("status") == "FAILED" and state.get("error_code") == code


def summarize(records: list[dict], which: str = "final") -> dict:
    """All metrics from the saved per-document records. `which` is 'first_pass' or 'final'."""

    def state(r: dict) -> dict:
        return r if which == "final" else {**r, **r.get("first_pass", {})}

    not_evaluated = [r for r in records if provider_limited(r)]
    records = [r for r in records if not provider_limited(r)]

    expected_ok = [r for r in records if r["expected_outcome"] == "success"]
    expected_bad = [r for r in records if r["expected_outcome"] != "success"]
    accepted = [r for r in records if r.get("upload") == "accepted"]
    failed = [r for r in accepted if state(r).get("status") == "FAILED" or r.get("timed_out")]
    fields = {
        f: {k: 0 for k in ("correct", "wrong", "missing", "invented", "correct_null")}
        for f in FIELDS
    }
    docs = exact = counts_ok = line_ok = line_total = 0
    for r in expected_ok:
        if state(r).get("status") not in SUCCESS:
            for inv in r["invoices_expected"]:
                for f in FIELDS:
                    fields[f]["missing" if inv[f] is not None else "correct_null"] += 1
            line_total += len(r["invoices_expected"])
            docs += 1
            continue
        scored = score_document(r["invoices_expected"], r.get("invoices", []))
        docs += 1
        exact += scored["exact"]
        counts_ok += scored["count_ok"]
        for inv in scored["invoices"]:
            line_total += 1
            line_ok += inv["line_items"]
            for f, verdict in inv["fields"].items():
                fields[f][verdict] += 1
    seeded = [r for r in records if r["expected_findings"]]
    caught = [r for r in seeded if set(r["expected_findings"]) <= set(r.get("finding_codes", []))]
    clean = [r for r in expected_ok if not r["expected_findings"]]
    flagged = [r for r in clean if state(r).get("status") == "NEEDS_REVIEW"]
    return {
        "documents": len(records),
        "not_evaluated": len(not_evaluated),
        "accepted": len(accepted),
        "success_rate": ratio(sum(outcome_ok(r, state(r)) for r in expected_ok), len(expected_ok)),
        "failure_rate": ratio(len(failed), len(accepted)),
        "expected_failures_matched": ratio(
            sum(outcome_ok(r, state(r)) for r in expected_bad), len(expected_bad)
        ),
        "exact_match": ratio(exact, docs),
        "invoice_count_accuracy": ratio(counts_ok, docs),
        "line_items_accuracy": ratio(line_ok, line_total),
        "fields": {
            f: {
                **c,
                "accuracy": ratio(c["correct"], c["correct"] + c["wrong"] + c["missing"]),
                "invented_rate": ratio(c["invented"], c["invented"] + c["correct_null"]),
            }
            for f, c in fields.items()
        },
        "validation_recall": ratio(len(caught), len(seeded)),
        "seeded": len(seeded),
        "false_review_rate": ratio(len(flagged), len(clean)),
        "clean": len(clean),
    }


def ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else part / whole


def timing(records: list[dict]) -> dict:
    """Seconds end to end by file type, and stage durations (events) by stage."""
    by_type: dict[str, list[float]] = {}
    by_stage: dict[str, list[float]] = {}
    for r in (r for r in records if not provider_limited(r)):
        if r.get("seconds") is not None:
            by_type.setdefault(r["type"], []).append(r["seconds"])
        per_stage: dict[str, float] = {}
        for e in r.get("events", []):
            if e.get("status") == "succeeded" and e.get("duration_ms") is not None:
                per_stage[e["stage"]] = per_stage.get(e["stage"], 0) + e["duration_ms"] / 1000
        for stage, seconds in per_stage.items():
            by_stage.setdefault(stage, []).append(seconds)
    return {
        "by_type": {t: stats(v) for t, v in sorted(by_type.items())},
        "by_stage": {s: stats(v) for s, v in sorted(by_stage.items())},
        "overall": stats([s for v in by_type.values() for s in v]),
    }
