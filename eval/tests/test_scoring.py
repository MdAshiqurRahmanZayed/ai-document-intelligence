import pytest
from scoring import (
    judge,
    match_invoices,
    outcome_ok,
    percentile,
    provider_limited,
    score_document,
    stats,
    summarize,
    timing,
)

EXP = {
    "invoice_number": "INV-1",
    "invoice_date": "2026-01-05",
    "supplier_name": "Acme Ltd",
    "customer_name": "Globex",
    "subtotal": "100.00",
    "tax": "20.00",
    "total": "120.00",
    "currency": "EUR",
    "line_items_count": 2,
    "line_items_sum": "100.00",
}
ITEMS = [{"amount": "60.00"}, {"amount": "40.00"}]


def actual(**changes):
    return {
        **{k: v for k, v in EXP.items() if not k.startswith("line_")},
        "line_items": ITEMS,
        **changes,
    }


@pytest.mark.parametrize(
    ("field", "expected", "got", "verdict"),
    [
        ("total", "120.00", "120.01", "correct"),  # within the 0.01 tolerance
        ("total", "120.00", "120.02", "wrong"),
        ("invoice_number", "INV-1", "inv 1", "correct"),  # case, spaces and punctuation ignored
        ("supplier_name", "Acme Ltd", "ACME, Limited", "correct"),  # company forms ignored
        ("supplier_name", "Acme Ltd", "Globex", "wrong"),
        ("invoice_date", "2026-01-05", "2026-05-01", "wrong"),
        ("currency", "EUR", "eur", "correct"),
        ("customer_name", "Globex", None, "missing"),
        ("tax", None, "5.00", "invented"),
        ("tax", None, None, "correct_null"),
    ],
)
def test_judge(field, expected, got, verdict):
    assert judge(field, expected, got) == verdict


def test_wrong_is_not_missing():
    scored = score_document([EXP], [actual(supplier_name="Initech")])
    assert scored["invoices"][0]["fields"]["supplier_name"] == "wrong"
    assert not scored["exact"]


def test_exact_match_and_line_items():
    assert score_document([EXP], [actual()])["exact"]
    bad = score_document([EXP], [actual(line_items=[{"amount": "60.00"}])])
    assert bad["invoices"][0]["line_items"] is False and not bad["exact"]


def test_invoices_matched_by_number_then_position():
    second = {**EXP, "invoice_number": "INV-2"}
    pairs = match_invoices([EXP, second], [actual(invoice_number="inv-2"), actual()])
    assert pairs[0][1]["invoice_number"] == "INV-1" and pairs[1][1]["invoice_number"] == "inv-2"


def test_missing_invoice_and_extra_invoice():
    assert score_document([EXP], [])["invoices"][0]["fields"]["total"] == "missing"
    assert not score_document([EXP], [actual(), actual()])["count_ok"]


def test_percentiles():
    assert percentile([], 50) is None
    assert percentile([5.0], 95) == 5.0
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert stats([]) == {"n": 0, "median": None, "p95": None, "max": None}


def record(file="a.pdf", outcome="success", **extra):
    base = {
        "file": file,
        "type": "pdf",
        "expected_outcome": outcome,
        "invoices_expected": [EXP],
        "expected_findings": [],
        "upload": "accepted",
        "status": "COMPLETED",
        "error_code": None,
        "reason": None,
        "timed_out": False,
        "invoices": [actual()],
        "finding_codes": [],
        "first_pass": {"status": "COMPLETED", "error_code": None},
        "events": [],
        "seconds": 4.0,
    }
    return {**base, **extra}


def test_outcome_rules():
    ok = {"status": "NEEDS_REVIEW"}
    assert outcome_ok({"expected_outcome": "success"}, ok)
    assert not outcome_ok({"expected_outcome": "success"}, {"status": "FAILED"})
    enc = {"expected_outcome": "failed:pdf_encrypted"}
    assert outcome_ok(enc, {"status": "FAILED", "error_code": "pdf_encrypted"})
    assert not outcome_ok(enc, {"status": "FAILED", "error_code": "pdf_corrupt"})
    empty = {"expected_outcome": "rejected:empty_file"}
    assert outcome_ok(empty, {"upload": "rejected", "reason": "empty_file"})
    assert not outcome_ok(empty, {"upload": "accepted", "status": "COMPLETED"})


def test_summary_rates_and_validation():
    seeded = record(
        "e.pdf",
        expected_findings=["total_mismatch"],
        finding_codes=["total_mismatch"],
        status="NEEDS_REVIEW",
    )
    missed = record("m.pdf", expected_findings=["total_mismatch"], finding_codes=[])
    flagged = record("f.pdf", status="NEEDS_REVIEW")  # a clean document sent to review
    failed = record(
        "x.pdf",
        status="FAILED",
        error_code="llm_error",
        invoices=[],
        first_pass={"status": "FAILED", "error_code": "llm_error"},
    )
    refused = record(
        "r.pdf",
        "rejected:empty_file",
        upload="rejected",
        reason="empty_file",
        status=None,
        invoices=[],
        invoices_expected=[],
    )
    out = summarize([record(), seeded, missed, flagged, failed, refused])
    assert out["documents"] == 6 and out["accepted"] == 5
    assert out["failure_rate"] == 1 / 5
    assert out["success_rate"] == 4 / 5  # 5 expected successes, the failed one does not count
    assert out["validation_recall"] == 1 / 2 and out["seeded"] == 2
    assert out["expected_failures_matched"] == 1.0
    assert out["fields"]["total"]["accuracy"] is not None


def test_first_pass_differs_from_final_after_retry():
    retried = record(status="COMPLETED", first_pass={"status": "FAILED", "error_code": "llm_error"})
    assert summarize([retried], "final")["failure_rate"] == 0
    assert summarize([retried], "first_pass")["failure_rate"] == 1


def test_timing_by_type_and_stage():
    events = [
        {"stage": "ingest", "status": "succeeded", "duration_ms": 500},
        {
            "stage": "extract",
            "status": "failed",
            "duration_ms": 9000,
        },  # failed attempts are not counted
        {"stage": "extract", "status": "succeeded", "duration_ms": 2000},
    ]
    out = timing([record(events=events, seconds=3.0), record("b.pdf", seconds=5.0)])
    assert out["by_type"]["pdf"]["n"] == 2 and out["by_type"]["pdf"]["max"] == 5.0
    assert out["by_stage"]["extract"]["median"] == 2.0
    assert out["overall"]["median"] == 3.0


def test_provider_limit_failures_are_not_evaluated():
    failed_event = {"stage": "extract", "status": "failed", "error_message": "GoogleRateLimitError"}
    limited = record(
        "l.pdf", status="FAILED", error_code="extraction_failed", invoices=[], events=[failed_event]
    )
    own_fault = record(
        "o.pdf",
        status="FAILED",
        error_code="extraction_failed",
        invoices=[],
        events=[{"stage": "extract", "status": "failed", "error_message": "ValidationError"}],
    )
    assert (
        provider_limited(limited)
        and not provider_limited(own_fault)
        and not provider_limited(record())
    )
    out = summarize([record(), limited, own_fault])
    api_error = record(
        "p.pdf",
        status="FAILED",
        invoices=[],
        events=[{"stage": "extract", "status": "failed", "error_message": "GoogleAPIError"}],
    )
    assert provider_limited(api_error)  # the provider's generic API error counts too
    assert out["not_evaluated"] == 1 and out["documents"] == 2
    assert out["failure_rate"] == 1 / 2  # only the document that failed for its own reasons counts
    assert timing([limited])["by_type"] == {}
