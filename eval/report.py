"""Renders eval/results/report.md from results.json. Every number comes from the saved records."""

# ruff: noqa: E501  (long lines are report text)

from pathlib import Path

from scoring import FIELDS, judge, match_invoices, outcome_ok, provider_limited, summarize, timing

COMMENTARY = Path(__file__).resolve().parent / "results" / "commentary.md"
LIMITS = """\
- **The data is synthetic.** The documents are drawn by code from known values, in English, with clean
  layouts. Scores are an upper bound for real invoices; this report makes no claim about real-world accuracy.
- **The set is small** (see the counts above). A difference of one document moves a rate by several points.
- **The generator and the system share an author.** The extractor was not tested on layouts it was never
  shown, and the set was not used to tune the prompt, model or rules.
- **One run.** The model is not deterministic and reruns can differ by a point or two. No averaging was done.
- **Provider limits affect failures and times.** A rate limit or a busy model ends a document as failed for
  a reason that is not the extractor's; first-pass and after-retry results are shown separately.
- **Spreadsheets carry a tax rate and a total, not a subtotal or tax amount**, so those fields are expected
  to be null there and anything returned counts as invented."""


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def secs(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def problems(records: list[dict]) -> list[list]:
    """Each field that was wrong, missing or invented, with the expected and returned value."""
    out = []
    for r in records:
        if r.get("status") not in ("COMPLETED", "NEEDS_REVIEW"):
            continue
        for exp, act in match_invoices(r["invoices_expected"], r.get("invoices", [])):
            for f in FIELDS:
                got = None if act is None else act.get(f)
                verdict = judge(f, exp[f], got)
                if verdict in ("wrong", "missing", "invented"):
                    out.append([r["file"], exp["invoice_number"], f, verdict, exp[f], got])
    return out


def by_model(records: list[dict]) -> list[list]:
    """Documents, exact match and wrong fields per extraction model (a run can span models)."""
    groups: dict[str, list[dict]] = {}
    for r in records:
        if r.get("model") and not provider_limited(r):
            groups.setdefault(r["model"], []).append(r)
    return [
        [m, len(rs), pct(summarize(rs, "final")["exact_match"]), len(problems(rs))]
        for m, rs in sorted(groups.items())
    ]


def render(results: dict) -> str:
    meta, records = results["meta"], results["records"]
    first, final = summarize(records, "first_pass"), summarize(records, "final")
    manifest = meta.get("manifest", {})
    wall = meta.get("wall_seconds") or 0
    accepted = final["accepted"]
    out = ["# Evaluation report", ""]
    out += ["## Conditions", ""]
    out.append(
        table(
            ["Item", "Value"],
            [
                ["Run date", meta.get("date")],
                ["Git commit", meta.get("commit")],
                ["Extraction model(s)", ", ".join(meta.get("models", [])) or "n/a"],
                ["Prompt version(s)", ", ".join(meta.get("prompt_versions", [])) or "n/a"],
                ["Embedding model", meta.get("embedding_model")],
                [
                    "Documents",
                    f"{len(records)} ({accepted} accepted, {final['not_evaluated']} not evaluated)",
                ],
                [
                    "Re-run after a provider limit",
                    sum(1 for r in records if r.get("provider_attempts")),
                ],
                [
                    "By category",
                    ", ".join(f"{k} {v}" for k, v in sorted(manifest.get("category", {}).items())),
                ],
                [
                    "By file type",
                    ", ".join(f"{k} {v}" for k, v in sorted(manifest.get("type", {}).items())),
                ],
                ["Runner settings", meta.get("settings")],
            ],
        )
    )
    out += ["", "## Results", ""]
    rows = [
        ("Document success rate", "success_rate"),
        ("Document failure rate", "failure_rate"),
        ("Expected failures and refusals handled as expected", "expected_failures_matched"),
        ("Documents with every field correct", "exact_match"),
        ("Invoice count correct", "invoice_count_accuracy"),
        ("Line items correct (count and sum)", "line_items_accuracy"),
        (f"Seeded validation errors flagged (of {final['seeded']})", "validation_recall"),
        (f"Clean documents sent to review (of {final['clean']})", "false_review_rate"),
    ]
    out.append(
        table(
            ["Metric", "First pass", "After retry"],
            [[n, pct(first[k]), pct(final[k])] for n, k in rows],
        )
    )
    out += [
        "",
        "Success rate is measured on documents expected to succeed (status completed or needs review);",
    ]
    out += [
        "failure rate on all accepted documents (failed or timed out). After retry equals first pass if no retry ran.",
        "",
    ]
    out += ["## Field accuracy (after retry)", ""]
    fields = final["fields"]
    out.append(
        table(
            ["Field", "Correct", "Wrong", "Missing", "Invented", "Accuracy", "Invented rate"],
            [
                [
                    f,
                    c["correct"],
                    c["wrong"],
                    c["missing"],
                    c["invented"],
                    pct(c["accuracy"]),
                    pct(c["invented_rate"]),
                ]
                for f, c in fields.items()
            ],
        )
    )
    out += [
        "",
        "Accuracy is correct over (correct + wrong + missing); invented rate is invented over fields whose truth is null.",
        "",
    ]
    models = by_model(records)
    if models:
        out += ["## By extraction model", ""]
        out.append(
            table(["Model", "Documents", "Every field correct", "Fields not correct"], models)
        )
        out += [
            "",
            "The model recorded on each document's extraction. More than one row means the run spanned models.",
            "",
        ]
    times = timing(records)
    out += ["## Processing time (seconds)", ""]
    out.append(
        table(
            ["File type", "Documents", "Median", "95th pct", "Max"],
            [
                [t, s["n"], secs(s["median"]), secs(s["p95"]), secs(s["max"])]
                for t, s in times["by_type"].items()
            ],
        )
    )
    out += [""]
    out.append(
        table(
            ["Stage", "Documents", "Median", "95th pct", "Max"],
            [
                [t, s["n"], secs(s["median"]), secs(s["p95"]), secs(s["max"])]
                for t, s in times["by_stage"].items()
            ],
        )
    )
    per_min = f"{accepted / (wall / 60):.1f}" if wall else "n/a"
    out += [
        "",
        f"Total wall time {wall:.0f} s for {accepted} accepted documents: {per_min} documents per minute.",
        "",
    ]
    out += ["## Failure analysis", ""]
    limited = [r for r in records if provider_limited(r)]
    if limited:
        out += [
            f"**{len(limited)} documents are not evaluated:** the model provider refused them (quota or rate limit), "
            'which says nothing about the system. They are left out of every figure above; run `make eval ARGS="--resume"` '
            "again once the provider allows it.",
            "",
            ", ".join(r["file"] for r in limited),
            "",
        ]
    bad = [r for r in records if not provider_limited(r) and not outcome_ok(r, r)]
    if bad:
        out.append(
            table(
                ["File", "Expected", "Got", "Error code", "Retried"],
                [
                    [
                        r["file"],
                        r["expected_outcome"],
                        r.get("status") or r.get("upload"),
                        r.get("error_code") or r.get("reason") or "",
                        r.get("retried", 0),
                    ]
                    for r in bad
                ],
            )
        )
    else:
        out.append("Every document ended as its ground truth says.")
    wrong = problems(records)
    out += ["", f"Fields not correct: {len(wrong)}", ""]
    if wrong:
        out.append(
            table(["File", "Invoice", "Field", "Result", "Expected", "Returned"], wrong[:25])
        )
        if len(wrong) > 25:
            out.append(f"\n({len(wrong) - 25} more in results.json.)")
    if COMMENTARY.exists():
        out += ["", "## Commentary", "", COMMENTARY.read_text().strip()]
    out += ["", "## Limits of this evaluation", "", LIMITS, ""]
    return "\n".join(out)
