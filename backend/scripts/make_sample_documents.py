"""Writes sample invoices and receipts in every supported format, for trying the app by hand.

Run from backend/:  .venv/bin/python scripts/make_sample_documents.py
Output:             tests/fixtures/samples/  (made-up companies and numbers, safe to share)
"""

import csv
import io
import random
from dataclasses import dataclass, replace
from pathlib import Path

import openpyxl
import xlwt
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "samples"


@dataclass
class Invoice:
    number: str
    date: str
    due: str
    supplier: str
    address: str
    customer: str
    currency: str
    items: list[tuple[str, int, float]]
    tax_rate: float
    total_override: float | None = None  # set to make the total disagree with the lines

    @property
    def subtotal(self) -> float:
        return round(sum(q * p for _, q, p in self.items), 2)

    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return (
            self.total_override
            if self.total_override is not None
            else round(self.subtotal + self.tax, 2)
        )


ACME = Invoice(
    "INV-2026-0142",
    "2026-10-05",
    "2026-11-04",
    "Northwind Supplies Ltd",
    "12 Harbour Road, Dublin, Ireland",
    "Contoso Retail GmbH",
    "EUR",
    [
        ("A4 paper, 80gsm (box of 5 reams)", 12, 24.50),
        ("Toner cartridge black", 3, 89.90),
        ("Delivery", 1, 15.00),
    ],
    0.23,
)
SHOP = Invoice(
    "SB-88231",
    "2026-10-18",
    "2026-10-18",
    "Sunrise Bakery",
    "4 Market Street, Austin, TX, USA",
    "Walk-in customer",
    "USD",
    [("Sourdough loaf", 4, 6.50), ("Croissant", 10, 3.25), ("Coffee, large", 6, 4.00)],
    0.0825,
)
CLOUD = Invoice(
    "CS-7740",
    "2026-09-30",
    "2026-10-30",
    "Cirrus Cloud Services AB",
    "Sveavagen 20, Stockholm, Sweden",
    "Fabrikam Studio",
    "SEK",
    [
        ("Managed hosting, October", 1, 4200.00),
        ("Backup storage 500 GB", 1, 650.00),
        ("Support hours", 5, 900.00),
    ],
    0.25,
)
# Subtotal plus tax is 1,000 + 200 = 1,200, but the document says 1,250: validation must flag it.
BAD_TOTAL = Invoice(
    "ER-5001",
    "2026-10-21",
    "2026-11-20",
    "Orbit Engineering Co",
    "88 Foundry Lane, Leeds, UK",
    "Globex Ltd",
    "GBP",
    [("Consulting day", 2, 500.00)],
    0.20,
    total_override=1250.00,
)


def numbered(inv: Invoice, number: str) -> Invoice:
    """The same invoice under another number, so two files never collide on supplier + number."""
    return replace(inv, number=number)


def lines(inv: Invoice, *, receipt: bool = False) -> list[str]:
    cur = inv.currency
    out = [
        inv.supplier,
        inv.address,
        "",
        "RECEIPT" if receipt else "INVOICE",
        f"Invoice No: {inv.number}",
        f"Date: {inv.date}",
        f"Due date: {inv.due}",
        f"Bill to: {inv.customer}",
        "",
    ]
    out.append(f"{'Description':<38}{'Qty':>4}{'Price':>11}{'Amount':>12}")
    for name, qty, price in inv.items:
        out.append(f"{name[:37]:<38}{qty:>4}{price:>11.2f}{qty * price:>12.2f}")
    out += [
        "",
        f"{'Subtotal':>53} {inv.subtotal:>10.2f}",
        f"{f'Tax ({inv.tax_rate * 100:g}%)':>53} {inv.tax:>10.2f}",
        f"{'TOTAL (' + cur + ')':>53} {inv.total:>10.2f}",
        "",
        "Payment terms: bank transfer, thank you.",
    ]
    return out


def pdf_text(invoices: list[Invoice], path: Path) -> None:
    """A digital PDF with a real text layer; one invoice per page."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for inv in invoices:
        y = 790
        for i, line in enumerate(lines(inv)):
            pdf.setFont("Courier-Bold" if i in (0, 3) else "Courier", 15 if i == 0 else 10)
            pdf.drawString(50, y, line)
            y -= 20 if i == 0 else 15
        pdf.showPage()
    pdf.save()


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/Courier.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def scan(inv: Invoice, *, receipt: bool = False, tilt: float = 0.0, seed: int = 1) -> Image.Image:
    """Text on paper, slightly rotated, blurred and noisy, like a phone photo or a scan."""
    rng = random.Random(seed)
    text = lines(inv, receipt=receipt)
    f = font(26)
    img = Image.new("RGB", (1240, 120 + 38 * len(text)), (250, 249, 245))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(text):
        draw.text((70, 60 + i * 38), line, fill=(25, 25, 25), font=f)
    if tilt:
        img = img.rotate(
            tilt, expand=True, fillcolor=(250, 249, 245), resample=Image.Resampling.BICUBIC
        )
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    for _ in range(img.width * img.height // 60):
        x, y, d = rng.randrange(img.width), rng.randrange(img.height), rng.randint(-25, 25)
        r, g, b = px[x, y]
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))
    return img


def rows(invoices: list[Invoice]) -> list[list[object]]:
    head = [
        "invoice_number",
        "date",
        "supplier",
        "customer",
        "description",
        "quantity",
        "unit_price",
        "currency",
        "line_total",
        "tax_rate",
        "invoice_total",
    ]
    body = [
        [
            i.number,
            i.date,
            i.supplier,
            i.customer,
            n,
            q,
            p,
            i.currency,
            round(q * p, 2),
            i.tax_rate,
            i.total,
        ]
        for i in invoices
        for n, q, p in i.items
    ]
    return [head, *body]


# (supplier, address, currency, tax rate, catalogue of (item, typical unit price)).
# Different words per supplier so keyword and semantic search have something to tell apart
# ("freight", "laptop", "catering", "legal advice", ...).
SUPPLIERS = [
    (
        "Northwind Supplies Ltd",
        "12 Harbour Road, Dublin, Ireland",
        "EUR",
        0.23,
        [
            ("A4 paper box", 24.5),
            ("Toner cartridge", 89.9),
            ("Stapler heavy duty", 18.0),
            ("Whiteboard markers", 9.4),
        ],
    ),
    (
        "Sunrise Bakery",
        "4 Market Street, Austin, TX, USA",
        "USD",
        0.0825,
        [
            ("Sourdough loaf", 6.5),
            ("Croissant", 3.25),
            ("Catering platter", 120.0),
            ("Birthday cake", 45.0),
        ],
    ),
    (
        "Cirrus Cloud Services AB",
        "Sveavagen 20, Stockholm, Sweden",
        "SEK",
        0.25,
        [
            ("Managed hosting", 4200.0),
            ("Backup storage", 650.0),
            ("Support hours", 900.0),
            ("Domain renewal", 190.0),
        ],
    ),
    (
        "Orbit Engineering Co",
        "88 Foundry Lane, Leeds, UK",
        "GBP",
        0.20,
        [
            ("Consulting day", 500.0),
            ("Site inspection", 320.0),
            ("CAD drawing", 210.0),
            ("Structural report", 780.0),
        ],
    ),
    (
        "Meridian Freight GmbH",
        "Hafenstrasse 5, Hamburg, Germany",
        "EUR",
        0.19,
        [
            ("Sea freight container", 2350.0),
            ("Customs clearance", 180.0),
            ("Pallet storage per week", 36.0),
            ("Courier parcel", 14.5),
        ],
    ),
    (
        "Pixel Forge Studio",
        "27 Spring Street, Melbourne, Australia",
        "AUD",
        0.10,
        [
            ("Logo design", 900.0),
            ("Website redesign", 4800.0),
            ("Photography half day", 650.0),
            ("Stock images pack", 75.0),
        ],
    ),
    (
        "Harlow & Finch Solicitors",
        "3 Chancery Row, London, UK",
        "GBP",
        0.20,
        [
            ("Legal advice per hour", 275.0),
            ("Contract review", 600.0),
            ("Company filing fee", 85.0),
            ("Notary signature", 60.0),
        ],
    ),
    (
        "TechMart Electronics Inc",
        "901 Mission Street, San Francisco, CA, USA",
        "USD",
        0.0875,
        [
            ("Laptop 14 inch", 1299.0),
            ("Wireless mouse", 29.99),
            ("USB-C dock", 149.0),
            ("Monitor 27 inch", 329.0),
        ],
    ),
    (
        "Fjord Catering AS",
        "Karl Johans gate 14, Oslo, Norway",
        "NOK",
        0.25,
        [
            ("Lunch buffet per person", 245.0),
            ("Coffee service", 1200.0),
            ("Waiter per hour", 410.0),
            ("Dessert table", 2100.0),
        ],
    ),
    (
        "GreenLeaf Cleaning Services",
        "17 Elm Avenue, Toronto, Canada",
        "CAD",
        0.13,
        [
            ("Office cleaning weekly", 340.0),
            ("Carpet shampoo", 190.0),
            ("Window cleaning", 120.0),
            ("Sanitiser refill", 42.0),
        ],
    ),
]
CUSTOMERS = [
    "Contoso Retail GmbH",
    "Fabrikam Studio",
    "Globex Ltd",
    "Initech Solutions",
    "Umbrella Logistics",
    "Wayne Holdings",
    "Stark Components",
    "Hooli Media",
    "Vandelay Imports",
    "Soylent Foods",
]


def bulk_invoices(count: int, seed: int = 7, prefix: str | None = None) -> list[Invoice]:
    rng = random.Random(seed)
    out = []
    for n in range(count):
        name, address, currency, tax, catalogue = SUPPLIERS[n % len(SUPPLIERS)]
        items = [
            (item, rng.randint(1, 8), round(price * rng.uniform(0.9, 1.15), 2))
            for item, price in rng.sample(catalogue, rng.randint(1, 4))
        ]
        issued = f"2026-{rng.randint(7, 10):02d}-{rng.randint(1, 28):02d}"
        due = f"2026-{rng.randint(11, 12):02d}-{rng.randint(1, 28):02d}"
        inv = Invoice(
            f"{prefix}-{1000 + n}" if prefix else f"{name.split()[0][:3].upper()}-{3000 + n}",
            issued,
            due,
            name,
            address,
            rng.choice(CUSTOMERS),
            currency,
            items,
            tax,
        )
        if n % 13 == 12:  # an occasional wrong total for the review queue
            inv.total_override = round(inv.total * 1.1, 2)
        out.append(inv)
    return out


def write_bulk(count: int = 40) -> None:
    folder = OUT / "bulk"
    folder.mkdir(exist_ok=True)
    invoices = bulk_invoices(count)
    for n, inv in enumerate(invoices):
        stem = f"{inv.number.lower()}-{inv.supplier.split()[0].lower()}"
        kind = (
            n + n // len(SUPPLIERS)
        ) % 5  # shifts each round so a supplier shows up in several formats
        if kind in (0, 1, 2):
            pdf_text([inv], folder / f"{stem}.pdf")
        elif kind == 3:
            scan(inv, tilt=random.Random(n).uniform(-1.5, 1.5), seed=n).convert("RGB").save(
                folder / f"{stem}.jpg", quality=80
            )
        else:
            scan(inv, receipt=True, seed=n).save(folder / f"{stem}.png")
    # Two big ledgers: many invoices per file.
    ledger = bulk_invoices(count, seed=21, prefix="LED")
    half = count // 2
    data = rows(ledger[:half])
    with (folder / "ledger-q3.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(data)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ledger Q4"
    for row in rows(ledger[half:]):
        ws.append(row)
    wb.save(folder / "ledger-q4.xlsx")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_bulk()
    # One PDF with a lot of data: 60 pages, one invoice per page, ten suppliers.
    pdf_text(bulk_invoices(60, seed=11, prefix="BIG"), OUT / "invoices-big-60-pages.pdf")
    # Every file gets its own supplier + number pairs, except the one deliberate duplicate below.
    everyone = [numbered(ACME, "SHT-1001"), numbered(SHOP, "SHT-1002"), numbered(CLOUD, "SHT-1003")]
    pdf_text(
        [replace(ACME, date="2026-10-06")], OUT / "invoice-duplicate-number.pdf"
    )  # same supplier + number as invoice-digital.pdf

    pdf_text([ACME], OUT / "invoice-digital.pdf")
    pdf_text(
        [numbered(ACME, "INV-2026-0201"), numbered(SHOP, "SB-90001"), numbered(CLOUD, "CS-8001")],
        OUT / "invoices-three-in-one.pdf",
    )  # several invoices in one file
    pdf_text([BAD_TOTAL], OUT / "invoice-total-mismatch.pdf")  # should end as "Needs review"

    scan(SHOP, receipt=True, tilt=1.2, seed=2).convert("RGB").save(
        OUT / "receipt-photo.jpg", quality=82
    )
    scan(CLOUD, tilt=-0.8, seed=3).save(OUT / "invoice-scan.png")
    scan(numbered(ACME, "INV-2026-0143"), seed=4).convert("L").save(
        OUT / "invoice-scan.tiff", compression="tiff_lzw"
    )

    # A PDF with no text layer: only a picture, so it has to go through OCR.
    buf = io.BytesIO()
    scan(numbered(ACME, "INV-2026-0144"), tilt=0.6, seed=5).save(buf, "JPEG", quality=85)
    pdf = canvas.Canvas(str(OUT / "invoice-scanned.pdf"), pagesize=A4)
    from reportlab.lib.utils import ImageReader

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

    data = rows(everyone)
    with (OUT / "invoices.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(data)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoices"
    for row in rows([numbered(i, i.number.replace("SHT", "SHX")) for i in everyone]):
        ws.append(row)
    ws2 = wb.create_sheet("Single invoice")
    for row in rows([numbered(BAD_TOTAL, "ER-5002")]):
        ws2.append(row)
    wb.save(OUT / "invoices.xlsx")

    xls = xlwt.Workbook()
    sheet = xls.add_sheet("Invoices")
    for r, row in enumerate(rows([numbered(i, i.number.replace("SHT", "SHL")) for i in everyone])):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    xls.save(str(OUT / "invoices.xls"))

    for path in sorted(OUT.iterdir()):
        print(f"{path.stat().st_size:>8}  {path.name}")


if __name__ == "__main__":
    main()
