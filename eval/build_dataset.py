"""Builds the labelled evaluation dataset: documents (git-ignored) and ground truth (committed).

Run from backend/ (it needs the backend's packages):  uv run python ../eval/build_dataset.py
Same inputs, same files: PDFs and XLSX carry no timestamps and all randomness is seeded.
"""

import csv
import io
import json
import re
import sys
import zipfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import openpyxl
import xlwt
from PIL import ImageFilter
from reportlab.lib import pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
# The generator is in backend/scripts; in the test container that folder is the working directory.
for scripts in (ROOT.parent / "backend" / "scripts", Path.cwd() / "scripts"):
    if scripts.is_dir():
        sys.path.insert(0, str(scripts))
        break
import make_sample_documents as gen  # noqa: E402

DOCUMENTS = ROOT / "dataset" / "documents"
GROUND_TRUTH = ROOT / "dataset" / "ground_truth"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def truth(inv: gen.Invoice, *, sheet: bool = False) -> dict:
    """What the document states. A spreadsheet has a tax rate and total, no subtotal or tax."""
    subtotal = f"{inv.subtotal:.2f}"
    return {
        "invoice_number": inv.number,
        "invoice_date": inv.date,
        "supplier_name": inv.supplier,
        "customer_name": inv.customer or None,
        "subtotal": None if sheet else subtotal,
        "tax": None if sheet or not inv.tax_rate else f"{inv.tax:.2f}",
        "total": f"{inv.total:.2f}",
        "currency": inv.currency,
        "line_items_count": len(inv.items),
        "line_items_sum": subtotal,
    }


def picture(
    inv: gen.Invoice, *, tilt: float = 0.0, seed: int = 1, blur: float = 0.0, scale: float = 1.0
):
    img = gen.scan(inv, tilt=tilt, seed=seed)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return img


def scanned_pdf(inv: gen.Invoice, path: Path, **kw) -> None:
    buf = io.BytesIO()
    picture(inv, **kw).convert("RGB").save(buf, "JPEG", quality=85)
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.drawImage(
        ImageReader(io.BytesIO(buf.getvalue())),
        20,
        150,
        width=555,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()


def save_xlsx(book: openpyxl.Workbook, path: Path) -> None:
    book.properties.created = book.properties.modified = datetime(*FIXED_TIME)
    raw = io.BytesIO()
    book.save(raw)
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(path, "w") as out:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = src.read(item.filename)
            if item.filename == "docProps/core.xml":  # openpyxl stamps the save time here
                data = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*",
                    rb"\g<1>2026-01-01T00:00:00Z",
                    data,
                )
            out.writestr(info, data)


def save_xls(invoices: list[gen.Invoice], path: Path) -> None:
    sheet = (book := xlwt.Workbook()).add_sheet("Invoices")
    for r, row in enumerate(gen.rows(invoices)):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    book.save(str(path))


def build(documents: Path = DOCUMENTS, ground_truth: Path = GROUND_TRUTH) -> dict:
    documents.mkdir(parents=True, exist_ok=True)
    ground_truth.mkdir(parents=True, exist_ok=True)
    for old in ground_truth.glob("*.json"):
        if not old.name.startswith("real-"):  # labels added by hand for real documents are kept
            old.unlink()
    manifest: dict[str, dict[str, int]] = {"category": {}, "type": {}}
    # Clean invoices: the generator's own wrong totals are removed; only the seeded ones are wrong.
    pool = iter(
        replace(i, total_override=None) for i in gen.bulk_invoices(60, seed=101, prefix="EV")
    )

    def invoice(**changes) -> gen.Invoice:
        return replace(next(pool), **changes)

    def record(
        file: str,
        category: str,
        group: str,
        invoices: list[dict],
        *,
        outcome="success",
        findings=(),
        after=None,
    ):
        entry = {
            "file": file,
            "category": category,
            "group": group,
            "expected_outcome": outcome,
            "invoices": invoices,
            "expected_findings": list(findings),
            **({"after": after} if after else {}),
        }
        (ground_truth / f"{file}.json").write_text(
            json.dumps(entry, indent=2, sort_keys=True) + "\n"
        )
        suffix = file.rsplit(".", 1)[1]
        manifest["category"][category] = manifest["category"].get(category, 0) + 1
        manifest["type"][suffix] = manifest["type"].get(suffix, 0) + 1

    # Digital PDFs (6): four plain, one without a customer, one holding three invoices.
    for n in range(1, 5):
        inv = invoice()
        gen.pdf_text([inv], documents / f"digital-{n:02d}.pdf")
        record(f"digital-{n:02d}.pdf", "digital_pdf", "pdf", [truth(inv)])
    inv = invoice(customer="")
    gen.pdf_text([inv], documents / "digital-05.pdf")
    record("digital-05.pdf", "digital_pdf", "pdf", [truth(inv)])
    three = [invoice() for _ in range(3)]
    gen.pdf_text(three, documents / "digital-06.pdf")
    record("digital-06.pdf", "digital_pdf", "pdf", [truth(i) for i in three])

    # Scanned PDFs (3): clean, tilted, tilted without a customer.
    for n, (tilt, customer) in enumerate([(0.0, None), (2.0, None), (1.0, "")], start=1):
        inv = invoice(**({} if customer is None else {"customer": customer}))
        scanned_pdf(inv, documents / f"scanned-{n:02d}.pdf", tilt=tilt, seed=n)
        record(f"scanned-{n:02d}.pdf", "scanned_pdf", "pdf", [truth(inv)])

    # Images: JPG (clean, tilted, low-res without tax), PNG (clean, blurred, tilted), TIFF (2).
    jpg = [
        ("clean", {}, {}),
        ("tilted", {"tilt": -1.5}, {}),
        ("lowres", {"scale": 0.55}, {"tax_rate": 0.0}),
    ]
    for n, (_, kw, changes) in enumerate(jpg, start=1):
        inv = invoice(**changes)
        quality = 35 if kw.get("scale") else 85
        picture(inv, seed=10 + n, **kw).convert("RGB").save(
            documents / f"image-jpg-{n:02d}.jpg", quality=quality
        )
        record(f"image-jpg-{n:02d}.jpg", "jpg", "image", [truth(inv)])
    for n, kw in enumerate([{}, {"blur": 1.2}, {"tilt": 2.0}], start=1):
        inv = invoice()
        picture(inv, seed=20 + n, **kw).save(documents / f"image-png-{n:02d}.png")
        record(f"image-png-{n:02d}.png", "png", "image", [truth(inv)])
    for n, kw in enumerate([{}, {"tilt": -1.0}], start=1):
        inv = invoice()
        picture(inv, seed=30 + n, **kw).convert("L").save(
            documents / f"image-tiff-{n:02d}.tiff", compression="tiff_lzw"
        )
        record(f"image-tiff-{n:02d}.tiff", "tiff", "image", [truth(inv)])

    # Spreadsheets: CSV 3 (last without a customer), XLSX 3 (last with two sheets), XLS 2.
    for n, (count, customer) in enumerate([(2, None), (1, None), (2, "")], start=1):
        invs = [
            invoice(**({} if customer is None else {"customer": customer})) for _ in range(count)
        ]
        with (documents / f"sheet-csv-{n:02d}.csv").open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, lineterminator="\n").writerows(gen.rows(invs))
        record(f"sheet-csv-{n:02d}.csv", "csv", "spreadsheet", [truth(i, sheet=True) for i in invs])
    for n, sheets in enumerate([[2], [1], [1, 1]], start=1):
        book = openpyxl.Workbook()
        all_invs: list[gen.Invoice] = []
        for s, count in enumerate(sheets):
            ws = book.active if s == 0 else book.create_sheet()
            ws.title = f"Sheet{s + 1}"
            invs = [invoice() for _ in range(count)]
            all_invs += invs
            for row in gen.rows(invs):
                ws.append(row)
        save_xlsx(book, documents / f"sheet-xlsx-{n:02d}.xlsx")
        record(
            f"sheet-xlsx-{n:02d}.xlsx",
            "xlsx",
            "spreadsheet",
            [truth(i, sheet=True) for i in all_invs],
        )
    for n, count in enumerate([2, 1], start=1):
        invs = [invoice() for _ in range(count)]
        save_xls(invs, documents / f"sheet-xls-{n:02d}.xls")
        record(f"sheet-xls-{n:02d}.xls", "xls", "spreadsheet", [truth(i, sheet=True) for i in invs])

    # Seeded errors (4): two totals 10% too high, and a duplicate pair (same supplier and number).
    for n in (1, 2):
        base = invoice()
        inv = replace(base, total_override=round(base.total * 1.1, 2))
        gen.pdf_text([inv], documents / f"error-total-{n:02d}.pdf")
        record(
            f"error-total-{n:02d}.pdf",
            "seeded_error",
            "pdf",
            [truth(inv)],
            findings=["total_mismatch"],
        )
    first = invoice()
    second = replace(first, date="2026-12-01")
    gen.pdf_text([first], documents / "duplicate-a.pdf")
    gen.pdf_text([second], documents / "duplicate-b.pdf")
    record("duplicate-a.pdf", "seeded_error", "pdf", [truth(first)])
    record(
        "duplicate-b.pdf",
        "seeded_error",
        "pdf",
        [truth(second)],
        findings=["duplicate_invoice"],
        after="duplicate-a.pdf",
    )

    # Files that must be refused at upload or fail while processing: no model call is spent on them.
    valid = documents / "_valid.pdf"
    gen.pdf_text([invoice()], valid)
    (documents / "failure-corrupt.pdf").write_bytes(
        valid.read_bytes()[: int(valid.stat().st_size * 0.6)]
    )
    valid.unlink()
    locked = canvas.Canvas(
        str(documents / "failure-encrypted.pdf"),
        pagesize=A4,
        invariant=1,
        encrypt=pdfencrypt.StandardEncryption("user-pass", ownerPassword="owner-pass", canPrint=0),
    )
    locked.drawString(72, 720, "Invoice number EV-LOCKED total due 100.00 USD")
    locked.showPage()
    locked.save()
    (documents / "failure-empty.pdf").write_bytes(b"")
    (documents / "failure-renamed.pdf").write_bytes(b"This is plain text, not a PDF.\n")
    record("failure-corrupt.pdf", "failure", "failures", [], outcome="failed:pdf_corrupt")
    record("failure-encrypted.pdf", "failure", "failures", [], outcome="failed:pdf_encrypted")
    record("failure-empty.pdf", "failure", "failures", [], outcome="rejected:empty_file")
    record("failure-renamed.pdf", "failure", "failures", [], outcome="rejected:unsupported_type")

    manifest["total"] = sum(manifest["category"].values())
    (ground_truth.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


if __name__ == "__main__":
    result = build()
    print(f"{result['total']} documents")
    for kind in ("category", "type"):
        print(kind, dict(sorted(result[kind].items())))
