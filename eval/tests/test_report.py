from report import render

EXP = {
    "invoice_number": "INV-1",
    "invoice_date": "2026-01-05",
    "supplier_name": "Acme",
    "customer_name": None,
    "subtotal": "100.00",
    "tax": None,
    "total": "100.00",
    "currency": "EUR",
    "line_items_count": 1,
    "line_items_sum": "100.00",
}


def rec(name, total="100.00", status="COMPLETED", **extra):
    got = {k: v for k, v in EXP.items() if not k.startswith("line_")} | {
        "total": total,
        "line_items": [{"amount": "100.00"}],
    }
    base = {
        "file": name,
        "type": "digital_pdf",
        "expected_outcome": "success",
        "invoices_expected": [EXP],
        "expected_findings": [],
        "upload": "accepted",
        "status": status,
        "error_code": None,
        "reason": None,
        "timed_out": False,
        "invoices": [got],
        "finding_codes": [],
        "seconds": 2.0,
        "first_pass": {"status": status, "error_code": None},
        "events": [{"stage": "extract", "status": "succeeded", "duration_ms": 1500}],
    }
    return base | extra


def test_report_has_conditions_numbers_and_limits():
    results = {
        "meta": {
            "date": "2026-11-04",
            "commit": "abc1234",
            "models": ["gemini-3.5-flash"],
            "prompt_versions": ["v1"],
            "wall_seconds": 60,
            "manifest": {"category": {"digital_pdf": 2}, "type": {"pdf": 2}},
            "settings": {"concurrency": 2},
        },
        "records": [rec("a.pdf"), rec("b.pdf", total="90.00")],
    }
    text = render(results)
    for part in (
        "## Conditions",
        "gemini-3.5-flash",
        "abc1234",
        "## Results",
        "## Field accuracy",
        "## Processing time",
        "## Failure analysis",
        "## Limits of this evaluation",
        "synthetic",
    ):
        assert part in text
    assert "Document success rate | 100.0% | 100.0%" in text
    assert "Documents with every field correct | 50.0% | 50.0%" in text
    assert (
        "| b.pdf | INV-1 | total | wrong | 100.00 | 90.00 |" in text
    )  # the wrong field is listed with both values
    assert "2.0 documents per minute" in text


def test_report_lists_a_failed_document():
    failed = rec(
        "x.pdf",
        status="FAILED",
        error_code="llm_error",
        invoices=[],
        first_pass={"status": "FAILED", "error_code": "llm_error"},
    )
    failed["error_code"] = "llm_error"
    text = render({"meta": {"manifest": {}}, "records": [rec("a.pdf"), failed]})
    assert "| x.pdf | success | FAILED | llm_error |" in text


def test_report_splits_results_by_extraction_model():
    records = [
        rec("a.pdf", model="model-a"),
        rec("b.pdf", total="90.00", model="model-b"),
        rec("c.pdf", model="model-b"),
    ]
    text = render({"meta": {"manifest": {}}, "records": records})
    assert "## By extraction model" in text
    assert "| model-a | 1 | 100.0% | 0 |" in text
    assert "| model-b | 2 | 50.0% | 1 |" in text
