import re

import httpx
import pytest
import run_eval
from run_eval import (
    Runner,
    check_empty,
    load_env,
    needs_retry,
    reject_unauthorised,
    rerun_provider_limited,
    run,
    select,
)

DATA = {"invoice_number": "INV-1", "total": "10.00", "line_items": []}


def entry(name, outcome="success", **extra):
    return {
        "file": name,
        "group": "pdf",
        "category": "digital_pdf",
        "expected_outcome": outcome,
        "expected_findings": [],
        "invoices": [],
        **extra,
    }


class FakeApi:
    """Stands in for the API: statuses come from `plan[name]`, a list consumed one GET at a time."""

    def __init__(self, plan, refused=None):
        self.plan, self.refused, self.calls, self.ids = plan, refused or {}, [], {}
        self.statuses: dict[str, list] = {}
        self.fail_message = "GoogleRateLimitError"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        if method == "POST" and path == "/api/v1/documents":
            name = re.search(rb'filename="([^"]+)"', request.content).group(1).decode()
            if name in self.refused:
                item = {"filename": name, "status": "rejected", "reason": self.refused[name]}
            else:
                doc_id = f"id-{name}"
                self.ids[doc_id] = name
                self.statuses[doc_id] = list(self.plan[name])
                item = {"filename": name, "status": "accepted", "document_id": doc_id}
            return httpx.Response(202, json={"results": [item]})
        if method == "POST" and path.endswith("/reprocess"):
            doc_id = path.split("/")[-2]
            self.statuses[doc_id] = list(self.plan[self.ids[doc_id] + ":retry"])
            self.body = request.content
            return httpx.Response(202, json={})
        if path.endswith("/result"):
            return httpx.Response(
                200,
                json={
                    "invoices": [
                        {
                            "data": DATA,
                            "model": "m",
                            "prompt_version": "v1",
                            "validation_errors": [{"code": "x"}],
                        }
                    ],
                    "document_errors": [],
                },
            )
        if path == "/api/v1/documents":
            return httpx.Response(
                200, json={"items": [{"id": i} for i in self.ids], "next_cursor": None}
            )
        doc_id = path.rsplit("/", 1)[1]
        queue = self.statuses[doc_id]
        status = queue.pop(0) if len(queue) > 1 else queue[0]
        events = [{"stage": "ingest", "status": "succeeded", "duration_ms": 100}]
        if status == "FAILED":
            events.append(
                {"stage": "extract", "status": "failed", "error_message": self.fail_message}
            )
        body = {
            "status": status,
            "error_code": "extraction_failed" if status == "FAILED" else None,
            "events": events,
        }
        return httpx.Response(200, json=body)


def runner(api, tmp_path, **kw):
    (tmp_path / "ok.pdf").write_bytes(b"%PDF")
    for name in ("a.pdf", "b.pdf", "empty.pdf", "slow.pdf"):
        (tmp_path / name).write_bytes(b"x")
    client = httpx.Client(transport=httpx.MockTransport(api), base_url="http://test")
    return Runner(client, tmp_path, poll=0, sleep=lambda _: None, **kw)


def test_clean_run_records_outcome_timing_and_invoices(tmp_path):
    api = FakeApi({"ok.pdf": ["PROCESSING", "COMPLETED"]})
    saved = []
    records = run(
        runner(api, tmp_path), [entry("ok.pdf")], concurrency=1, retries=0, save=saved.append
    )
    r = records[0]
    assert r["status"] == "COMPLETED" and r["upload"] == "accepted" and not r["timed_out"]
    assert r["invoices"] == [DATA] and r["finding_codes"] == ["x"] and r["model"] == "m"
    assert r["events"][0]["duration_ms"] == 100 and r["seconds"] is not None
    assert saved == records  # saved as each document finishes


def test_refused_file_is_recorded_without_polling(tmp_path):
    api = FakeApi({}, refused={"empty.pdf": "empty_file"})
    r = run(
        runner(api, tmp_path),
        [entry("empty.pdf", "rejected:empty_file")],
        concurrency=1,
        retries=0,
        save=lambda _: None,
    )[0]
    assert r["upload"] == "rejected" and r["reason"] == "empty_file" and r["status"] is None
    assert all(call[0] == "POST" for call in api.calls)


def test_timeout_counts_as_failure(tmp_path):
    api = FakeApi({"slow.pdf": ["PROCESSING"]})
    r = run(
        runner(api, tmp_path, timeout=0),
        [entry("slow.pdf")],
        concurrency=1,
        retries=0,
        save=lambda _: None,
    )[0]
    assert r["timed_out"] and needs_retry(r)


def test_retry_keeps_first_pass_and_final(tmp_path):
    api = FakeApi({"a.pdf": ["FAILED"], "a.pdf:retry": ["COMPLETED"]})
    r = run(runner(api, tmp_path), [entry("a.pdf")], concurrency=1, retries=1, save=lambda _: None)[
        0
    ]
    assert (
        r["first_pass"]["status"] == "FAILED" and r["status"] == "COMPLETED" and r["retried"] == 1
    )
    assert b'"extract"' in api.body  # extraction_failed restarts from extraction


def test_expected_failures_are_not_retried(tmp_path):
    api = FakeApi({"a.pdf": ["FAILED"]})
    r = run(
        runner(api, tmp_path),
        [entry("a.pdf", "failed:pdf_encrypted")],
        concurrency=1,
        retries=1,
        save=lambda _: None,
    )[0]
    assert r["status"] == "FAILED" and "retried" not in r


def test_a_file_marked_after_waits_for_the_first(tmp_path):
    api = FakeApi({"a.pdf": ["PROCESSING", "COMPLETED"], "b.pdf": ["COMPLETED"]})
    entries = [entry("b.pdf", after="a.pdf"), entry("a.pdf")]
    run(runner(api, tmp_path), entries, concurrency=2, retries=0, save=lambda _: None)
    posts = [p for m, p in api.calls if m == "POST"]
    last_get_a = max(i for i, (m, p) in enumerate(api.calls) if p.endswith("id-a.pdf"))
    post_b = [i for i, (m, p) in enumerate(api.calls) if m == "POST"][1]
    assert len(posts) == 2 and post_b > last_get_a


def test_non_empty_database_stops_the_run(tmp_path):
    api = FakeApi({"a.pdf": ["COMPLETED"]})
    api.ids["stranger"] = "x"
    client = httpx.Client(transport=httpx.MockTransport(api), base_url="http://test")
    with pytest.raises(SystemExit, match="already holds"):
        check_empty(client, set())
    check_empty(client, {"stranger"})  # known documents (a resumed run) are fine


def test_select_by_group_and_resume():
    entries = [
        {"file": "a", "group": "pdf"},
        {"file": "b", "group": "image"},
        {"file": "c", "group": "pdf"},
    ]
    assert [e["file"] for e in select(entries, "pdf", set())] == ["a", "c"]
    assert [e["file"] for e in select(entries, None, {"a"})] == ["b", "c"]


def test_module_has_the_documented_options():
    assert run_eval.FINAL == {"COMPLETED", "NEEDS_REVIEW", "FAILED"}


def test_env_file_is_read_without_exporting(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nAPI_KEY=abc123\nAPI_URL='http://x:1'\n\nBAD LINE\nEMPTY=\n")
    assert load_env(env) == {"API_KEY": "abc123", "API_URL": "http://x:1", "EMPTY": ""}
    assert load_env(tmp_path / "missing") == {}


def test_a_rejected_key_stops_with_a_clear_message():
    with pytest.raises(SystemExit, match="needs its key"):
        reject_unauthorised(httpx.Response(401, json={"detail": "Invalid or missing API key"}))
    reject_unauthorised(httpx.Response(200, json={}))  # other statuses pass through


def test_the_run_stops_after_failures_in_a_row_and_skips_retries(tmp_path):
    names = ["a.pdf", "b.pdf", "ok.pdf", "slow.pdf"]
    api = FakeApi({n: ["FAILED"] for n in names} | {n + ":retry": ["COMPLETED"] for n in names})
    saved = []
    records = run(
        runner(api, tmp_path),
        [entry(n) for n in names],
        concurrency=1,
        retries=1,
        save=saved.append,
        stop_after=2,
    )
    assert [r["file"] for r in records] == ["a.pdf", "b.pdf"]  # the rest were never sent
    assert all(r["status"] == "FAILED" and "retried" not in r for r in records)  # no wasted retries


def test_progress_streak_resets_on_a_success(tmp_path):
    api = FakeApi(
        {
            "a.pdf": ["FAILED"],
            "ok.pdf": ["COMPLETED"],
            "b.pdf": ["FAILED"],
            "slow.pdf": ["COMPLETED"],
        }
    )
    entries = [entry(n) for n in ("a.pdf", "ok.pdf", "b.pdf", "slow.pdf")]
    records = run(
        runner(api, tmp_path), entries, concurrency=1, retries=0, save=lambda _: None, stop_after=2
    )
    assert len(records) == 4


def test_documents_the_provider_refused_are_rerun_and_replace_the_first_pass(tmp_path):
    api = FakeApi(
        {
            "a.pdf": ["FAILED"],
            "a.pdf:retry": ["COMPLETED"],
            "b.pdf": ["FAILED"],
            "b.pdf:retry": ["FAILED"],
        }
    )
    rn = runner(api, tmp_path)
    saved = []
    records = run(rn, [entry("a.pdf"), entry("b.pdf")], concurrency=1, retries=0, save=saved.append)
    assert all(r["status"] == "FAILED" for r in records)
    assert rerun_provider_limited(rn, records, saved.append) is False
    a, b = records
    assert (
        a["status"] == "COMPLETED"
        and a["first_pass"]["status"] == "COMPLETED"
        and a["provider_attempts"] == 1
    )
    assert (
        b["status"] == "FAILED" and b["first_pass"]["status"] == "FAILED"
    )  # still refused: stays not evaluated


def test_rerun_stops_when_the_provider_keeps_refusing(tmp_path):
    names = ["a.pdf", "b.pdf", "ok.pdf"]
    plan = {n: ["FAILED"] for n in names} | {n + ":retry": ["FAILED"] for n in names}
    api = FakeApi(plan)
    rn = runner(api, tmp_path)
    records = run(rn, [entry(n) for n in names], concurrency=1, retries=0, save=lambda _: None)
    assert rerun_provider_limited(rn, records, lambda _: None, stop_after=2) is True
    assert records[2].get("provider_attempts") is None  # the third was never re-run
