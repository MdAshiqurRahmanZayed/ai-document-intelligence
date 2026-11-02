"""Builds test PDFs in memory so no binary fixtures are committed and page counts are adjustable."""

import io

from PIL import Image
from reportlab.lib import pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Long enough to clear the scanned-page threshold (20 non-whitespace characters).
SENTENCE = "Invoice number 1042 total due 250.00 USD"


def build_pdf(
    pages: list[str | None], *, password: str | None = None, size: tuple[float, float] = A4
) -> bytes:
    """One page per entry: a string is drawn as text, None is an image with no text layer."""
    buffer = io.BytesIO()
    encrypt = pdfencrypt.StandardEncryption(password, canPrint=0) if password else None
    pdf = canvas.Canvas(buffer, pagesize=size, encrypt=encrypt)
    for content in pages:
        if content is None:
            # A flat grey picture stands in for a scan: pixels only, nothing to extract.
            image = Image.new("RGB", (200, 200), "lightgrey")
            pdf.drawImage(ImageReader(image), 50, 50, width=200, height=200)
        else:
            pdf.drawString(72, 720, content)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def text_pdf(count: int = 3) -> bytes:
    return build_pdf([f"{SENTENCE} page {n}" for n in range(1, count + 1)])


def scanned_pdf() -> bytes:
    return build_pdf([None])


def mixed_pdf() -> bytes:
    """Page 1 and 3 have text, page 2 is image-only."""
    return build_pdf([f"{SENTENCE} page 1", None, f"{SENTENCE} page 3"])


def encrypted_pdf() -> bytes:
    return build_pdf([SENTENCE], password="secret")


def corrupt_pdf() -> bytes:
    # Starts with a valid header (so upload accepts it) but the body is cut off.
    return text_pdf()[:120]


def empty_pdf() -> bytes:
    """A syntactically valid PDF whose page tree has no pages."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [] /Count 0 >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 3\n0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return out
