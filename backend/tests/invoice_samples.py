"""Demo invoices with known values, built in memory.

The same invoice exists as a digital PDF, a scanned image and a spreadsheet, so extraction and
cross-verification can be tried end to end. They also seed the evaluation dataset later.
"""

import io

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

SUPPLIER = "Acme Industries Ltd"
CUSTOMER = "Globex Corporation"
# description, quantity, unit price, amount: they add up to 100.00
LINES = [
    ("Widget", "2", "25.00", "50.00"),
    ("Gadget", "1", "30.00", "30.00"),
    ("Service", "4", "5.00", "20.00"),
]


def invoice_lines(
    number: str = "INV-1042",
    subtotal: str = "100.00",
    tax: str = "20.00",
    total: str = "120.00",
    supplier: str = SUPPLIER,
) -> list[str]:
    """The text of the invoice, line by line. The defaults are consistent: 100 + 20 = 120."""
    lines = [
        f"INVOICE {number}",
        f"Supplier: {supplier}",
        f"Bill to: {CUSTOMER}",
        "Date: 5 January 2026",
        "",
        "Description    Qty    Unit price    Amount",
    ]
    lines += [f"{name}    {qty}    {price}    {amount}" for name, qty, price, amount in LINES]
    lines += ["", f"Subtotal {subtotal}", f"Tax (20%) {tax}", f"Total {total} EUR"]
    return lines


def invoice_pdf(**values: str) -> bytes:
    """A digital PDF: the text is a real text layer."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    top = 780
    for row, line in enumerate(invoice_lines(**values)):
        pdf.drawString(60, top - row * 18, line)
    pdf.save()
    return buffer.getvalue()


def invoice_png(**values: str) -> bytes:
    """A scanned-looking image of the invoice: pixels only, so OCR has to read it."""
    lines = invoice_lines(**values)
    font = ImageFont.load_default(size=34)
    image = Image.new("RGB", (1500, 80 + 56 * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        draw.text((50, 40 + row * 56), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def invoice_xlsx(
    number: str = "INV-1042",
    subtotal: str = "100.00",
    tax: str = "20.00",
    total: str = "120.00",
) -> bytes:
    """The same invoice as a spreadsheet: a line-item table, then the totals below it."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Invoice"
    sheet.append(["Invoice No", "Date", "Supplier", "Customer"])
    sheet.append([number, "5 January 2026", SUPPLIER, CUSTOMER])
    sheet.append([])
    sheet.append(["Description", "Qty", "Unit price", "Amount"])
    for name, qty, price, amount in LINES:
        sheet.append([name, qty, price, amount])
    sheet.append([])
    sheet.append(["Subtotal", subtotal])
    sheet.append(["Tax (20%)", tax])
    sheet.append(["Total", total])
    sheet.append(["Currency", "EUR"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def wrong_total_pdf() -> bytes:
    """An invoice whose total is not subtotal plus tax: validation must flag it."""
    return invoice_pdf(number="INV-2001", total="130.00")


def duplicate_pdf() -> bytes:
    """Reuses the number and supplier of the default invoice with different amounts."""
    return invoice_pdf(subtotal="50.00", tax="10.00", total="60.00")


def letter_pdf() -> bytes:
    """A document that is not an invoice."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for row, line in enumerate(
        [
            "Dear customer,",
            "",
            "Thank you for your order. We will contact you shortly.",
            "Kind regards",
        ]
    ):
        pdf.drawString(60, 780 - row * 18, line)
    pdf.save()
    return buffer.getvalue()
