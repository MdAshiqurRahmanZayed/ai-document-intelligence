"""Runs the labelled dataset through the real API and saves what happened.

Run from backend/:  uv run python ../eval/run_eval.py [--only pdf] [--resume] [--retries 1]
Needs the stack running, GOOGLE_API_KEY set (extraction), and an empty database.
`--rescore` rebuilds report.md from the saved results.json without the API.
"""

import argparse
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import report
from scoring import provider_limited

ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "dataset" / "documents"
GROUND_TRUTH = ROOT / "dataset" / "ground_truth"
RESULTS = ROOT / "results" / "results.json"
REPORT = ROOT / "results" / "report.md"
FINAL = {"COMPLETED", "NEEDS_REVIEW", "FAILED"}
SUCCESS = {"COMPLETED", "NEEDS_REVIEW"}
API = "/api/v1/documents"


def load_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of a .env file (make does not export them); real env variables win."""
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                values[key.strip()] = value.strip().strip("'\"")
    return values


def reject_unauthorised(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise SystemExit(
            f"The API answered {response.status_code}: it needs its key. "
            "Set API_KEY in .env (or the environment) to the value the API uses."
        )


def load_truth(folder: Path = GROUND_TRUTH) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]


def codes(items: list) -> list[str]:
    return [i["code"] if isinstance(i, dict) else str(i) for i in items]


class Runner:
    def __init__(
        self,
        client: httpx.Client,
        documents: Path = DOCUMENTS,
        poll=1.0,
        timeout=300.0,
        sleep=time.sleep,
    ):
        self.client, self.documents, self.poll, self.timeout, self.sleep = (
            client,
            documents,
            poll,
            timeout,
            sleep,
        )

    def wait(self, document_id: str, started: float) -> tuple[dict, bool]:
        while True:
            doc = self.client.get(f"{API}/{document_id}").json()
            if doc["status"] in FINAL:
                return doc, False
            if time.monotonic() - started > self.timeout:
                return doc, True
            self.sleep(self.poll)

    def finish(self, record: dict, started: float) -> None:
        """Wait for the document, then store its status, timings and extracted invoices."""
        doc, timed_out = self.wait(record["document_id"], started)
        record.update(status=doc["status"], error_code=doc.get("error_code"), timed_out=timed_out)
        record.update(seconds=round(time.monotonic() - started, 2), events=doc.get("events", []))
        record.update(invoices=[], finding_codes=[])
        if doc["status"] in SUCCESS:
            result = self.client.get(f"{API}/{record['document_id']}/result").json()
            invoices = result.get("invoices", [])
            record["invoices"] = [i["data"] for i in invoices]
            record["finding_codes"] = codes(
                [e for i in invoices for e in i.get("validation_errors", [])]
                + result.get("document_errors", [])
            )
            if invoices:
                record["model"], record["prompt_version"] = (
                    invoices[0].get("model"),
                    invoices[0].get("prompt_version"),
                )

    def run_one(self, entry: dict) -> dict:
        name = entry["file"]
        started = time.monotonic()
        category = entry["category"]
        record = {
            "file": name,
            "group": entry["group"],
            "category": category,
            "type": {"seeded_error": "digital_pdf"}.get(category, category),
            "expected_outcome": entry["expected_outcome"],
            "expected_findings": entry["expected_findings"],
            "invoices_expected": entry["invoices"],
        }
        body = (self.documents / name).read_bytes()
        item = self.client.post(API, files={"files": (name, body)}).json()["results"][0]
        record.update(
            upload=item["status"], reason=item.get("reason"), document_id=item.get("document_id")
        )
        record.update(
            status=None, error_code=None, timed_out=False, seconds=None, events=[], invoices=[]
        )
        if item["status"] == "accepted":
            self.finish(record, started)
        record["first_pass"] = {"status": record["status"], "error_code": record["error_code"]}
        return record

    def retry(self, record: dict) -> None:
        """Reprocess a document that failed although it should have worked, from the failed step."""
        stage = "extract" if record["error_code"] == "extraction_failed" else "ingest"
        started = time.monotonic()
        response = self.client.post(
            f"{API}/{record['document_id']}/reprocess", json={"from_stage": stage}
        )
        if response.status_code == 202:
            self.finish(record, started)
            record["retried"] = record.get("retried", 0) + 1


def needs_retry(record: dict) -> bool:
    failed = record["status"] == "FAILED" or record["timed_out"]
    return (
        failed and record["expected_outcome"] == "success" and record.get("document_id") is not None
    )


def rerun_provider_limited(runner: Runner, records: list[dict], save, stop_after: int = 0) -> bool:
    """Reprocess documents that only failed because the provider refused. True if it still refuses.

    The earlier outcome was the provider's, not the system's: the new one becomes the first pass.
    """
    streak = 0
    for record in [r for r in records if provider_limited(r)]:
        retried = record.get("retried", 0)
        runner.retry(record)
        record["retried"] = retried
        record["provider_attempts"] = record.get("provider_attempts", 0) + 1
        limited = provider_limited(record)
        if not limited:
            record["first_pass"] = {"status": record["status"], "error_code": record["error_code"]}
        save(record)
        print(
            f"re-run {record['file']}: {'provider limit again' if limited else record['status']}",
            flush=True,
        )
        streak = streak + 1 if limited else 0
        if stop_after and streak >= stop_after:
            print("Stopping: the provider still refuses. Try again later.", flush=True)
            return True
    return False


def select(entries: list[dict], only: str | None, done: set[str]) -> list[dict]:
    """The entries still to run: in the chosen group, and not already in the saved results."""
    return [e for e in entries if (not only or e["group"] == only) and e["file"] not in done]


def check_empty(client: httpx.Client, known: set[str]) -> None:
    """Stop if the database holds documents this run does not know (they would skew duplicates)."""
    cursor = None
    while True:
        page = client.get(
            API, params={"limit": 100, **({"cursor": cursor} if cursor else {})}
        ).json()
        unknown = [i["id"] for i in page["items"] if i["id"] not in known]
        if unknown:
            raise SystemExit(
                f"The database already holds {len(unknown)}+ documents this run did not upload.\n"
                "Start from an empty one (docker compose down -v && make up && make migrate) "
                "or pass --allow-nonempty."
            )
        cursor = page.get("next_cursor")
        if not cursor:
            return


def run(
    runner: Runner,
    entries: list[dict],
    *,
    concurrency: int,
    retries: int,
    save,
    stop_after: int = 0,
) -> list[dict]:
    """Upload and follow every entry. A file marked `after` waits for the file it follows."""
    records: list[dict] = []
    lock = threading.Lock()
    stop = threading.Event()
    streak = 0

    def one(entry: dict) -> None:
        nonlocal streak
        if stop.is_set():
            return
        record = runner.run_one(entry)
        with lock:
            records.append(record)
            save(record)
            if record["expected_outcome"] == "success":
                streak = streak + 1 if needs_retry(record) else 0
            shown = record["status"] or f"{record['upload']} {record['reason'] or ''}"
            print(
                f"[{len(records)}/{len(entries)}] {record['file']}: {shown.strip()}",
                flush=True,
            )
            if stop_after and streak >= stop_after and not stop.is_set():
                stop.set()
                print(
                    f"Stopping: {streak} documents in a row failed. See docker compose logs worker "
                    "(a provider quota or rate limit is the usual cause), then run again.",
                    flush=True,
                )

    first = [e for e in entries if "after" not in e]
    later = [e for e in entries if "after" in e]
    for batch in (first, later):
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(one, batch))
    for _ in range(0 if stop.is_set() else retries):
        for record in [r for r in records if needs_retry(r)]:
            runner.retry(record)
            with lock:
                save(record)
    return records


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--only", choices=["pdf", "image", "spreadsheet", "failures"])
    parser.add_argument(
        "--resume", action="store_true", help="skip documents already in results.json"
    )
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--stop-after", type=int, default=3, help="stop after N failures in a row (0 = never)"
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--allow-nonempty", action="store_true")
    parser.add_argument(
        "--rescore", action="store_true", help="rebuild report.md from results.json"
    )
    args = parser.parse_args()

    saved = json.loads(RESULTS.read_text()) if RESULTS.exists() else {"meta": {}, "records": []}
    if args.rescore:
        if not saved["records"]:
            raise SystemExit("No results to score yet. Run make eval first.")
        REPORT.write_text(report.render(saved))
        print(f"wrote {REPORT}")
        return

    by_file = {r["file"]: r for r in saved["records"]} if args.resume else {}
    entries = select(load_truth(), args.only, set(by_file))
    env = {**load_env(ROOT.parent / ".env"), **os.environ}
    headers = {"X-API-Key": env["API_KEY"]} if env.get("API_KEY") else {}
    client = httpx.Client(
        base_url=env.get("API_URL", "http://localhost:8000"),
        headers=headers,
        timeout=60,
        event_hooks={"response": [reject_unauthorised]},
    )
    try:
        client.get("/healthz")
    except httpx.TransportError:
        raise SystemExit(f"Cannot reach the API at {client.base_url}. Run make up first.") from None
    if not args.allow_nonempty:
        check_empty(client, {r["document_id"] for r in by_file.values() if r.get("document_id")})

    def save(record: dict) -> None:
        by_file[record["file"]] = record
        RESULTS.parent.mkdir(exist_ok=True)
        meta = {
            **saved["meta"],
            "commit": git_commit(),
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        }
        RESULTS.write_text(
            json.dumps(
                {"meta": meta, "records": sorted(by_file.values(), key=lambda r: r["file"])},
                indent=1,
            )
        )

    started = time.monotonic()
    runner = Runner(client, timeout=args.timeout)
    pending = [r for r in by_file.values() if not args.only or r["group"] == args.only]
    if rerun_provider_limited(runner, pending, save, args.stop_after):
        entries = []
    run(
        runner,
        entries,
        concurrency=args.concurrency,
        retries=args.retries,
        save=save,
        stop_after=args.stop_after,
    )
    final = json.loads(RESULTS.read_text())
    records = final["records"]
    final["meta"].update(
        wall_seconds=round(saved["meta"].get("wall_seconds", 0) + time.monotonic() - started, 1),
        settings={
            "concurrency": args.concurrency,
            "retries": args.retries,
            "timeout": args.timeout,
        },
        models=sorted({r["model"] for r in records if r.get("model")}),
        prompt_versions=sorted({r["prompt_version"] for r in records if r.get("prompt_version")}),
        embedding_model=env.get("EMBEDDING_MODEL", "models/gemini-embedding-001 (default)"),
        manifest=json.loads((ROOT / "dataset" / "manifest.json").read_text()),
    )
    RESULTS.write_text(json.dumps(final, indent=1))
    REPORT.write_text(report.render(final))
    print(f"{len(records)} documents; wrote {RESULTS.name} and {REPORT.name}")


if __name__ == "__main__":
    main()
