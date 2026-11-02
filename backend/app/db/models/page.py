import uuid

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_pages_document_id_page_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(String(20))  # native | ocr | vision
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    image_key: Mapped[str | None] = mapped_column(String(255))
