import hashlib
import json
from pathlib import Path

import build_dataset


def checksums(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_dataset_is_complete_and_reproducible(tmp_path):
    first = build_dataset.build(tmp_path / "d1", tmp_path / "t1")
    build_dataset.build(tmp_path / "d2", tmp_path / "t2")
    assert checksums(tmp_path / "d1") == checksums(tmp_path / "d2")  # same bytes every build
    assert checksums(tmp_path / "t1") == checksums(tmp_path / "t2")

    entries = [json.loads(p.read_text()) for p in (tmp_path / "t1").glob("*.json")]
    assert first["total"] == len(entries) >= 30
    assert {e["file"] for e in entries} == {
        p.name for p in (tmp_path / "d1").iterdir()
    }  # every file has a label
    assert set(first["type"]) == {"pdf", "jpg", "png", "tiff", "csv", "xlsx", "xls"}
    assert {"digital_pdf", "scanned_pdf", "seeded_error", "failure"} <= set(first["category"])


def test_labels_for_absent_fields_errors_and_failures(tmp_path):
    build_dataset.build(tmp_path / "d", tmp_path / "t")
    by_file = {
        p.name.removesuffix(".json"): json.loads(p.read_text())
        for p in (tmp_path / "t").glob("*.json")
    }
    assert by_file["digital-05.pdf"]["invoices"][0]["customer_name"] is None  # not stated, so null
    assert by_file["image-jpg-03.jpg"]["invoices"][0]["tax"] is None
    assert (
        by_file["sheet-csv-01.csv"]["invoices"][0]["subtotal"] is None
    )  # a sheet has no subtotal column
    assert len(by_file["digital-06.pdf"]["invoices"]) == 3
    assert by_file["error-total-01.pdf"]["expected_findings"] == ["total_mismatch"]
    assert by_file["duplicate-b.pdf"]["after"] == "duplicate-a.pdf"
    outcomes = {n: e["expected_outcome"] for n, e in by_file.items() if n.startswith("failure")}
    assert outcomes == {
        "failure-corrupt.pdf": "failed:pdf_corrupt",
        "failure-encrypted.pdf": "failed:pdf_encrypted",
        "failure-empty.pdf": "rejected:empty_file",
        "failure-renamed.pdf": "rejected:unsupported_type",
    }
