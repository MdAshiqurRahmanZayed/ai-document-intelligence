"""Extracts the invoices of one document, saves them, validates them and routes the document."""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import delete, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Extraction, Page, ValidationIssue
from app.llm.extract import PROMPT_VERSION, ExtractedInvoice, InvoiceExtractor
from app.normalize.invoice import normalize_invoice
from app.normalize.values import normalize_name
from app.pipeline.grounding import ground_invoice
from app.schemas.invoice import SCALAR_FIELDS, InvoiceData
from app.validation.findings import ERROR, WARNING, Finding
from app.validation.rules import route, validate_invoice


@dataclass
class ExtractedRecord:
    extraction: Extraction
    data: InvoiceData
    confidence: dict[str, float]
    # Warnings from grounding and normalization: they belong with the other findings.
    findings: list[Finding]


def lookup_columns(data: InvoiceData) -> dict[str, Any]:
    """The copies of key fields kept as columns on `extractions` for indexed lookups."""
    return {
        "invoice_number": data.invoice_number,
        "supplier_norm": normalize_name(data.supplier_name),
        "invoice_date": data.invoice_date,
        "total": data.total,
        "currency": data.currency,
    }


def _to_record(
    document_id: uuid.UUID, index: int, version: int, item: ExtractedInvoice
) -> ExtractedRecord:
    grounded, grounding_findings = ground_invoice(item.draft, item.text)
    data, normalizing_findings = normalize_invoice(grounded)
    # Keep notes only for values that survived grounding and parsing.
    notes = [
        note
        for note in grounded.notes
        if note.field in SCALAR_FIELDS and getattr(data, note.field) is not None
    ]
    extraction = Extraction(
        document_id=document_id,
        invoice_index=index,
        version=version,
        is_current=True,
        data=data.to_jsonable(),
        field_confidence={note.field: note.confidence for note in notes},
        grounding={note.field: note.quote for note in notes if note.quote},
        model=item.model,
        prompt_version=PROMPT_VERSION,
        **lookup_columns(data),
    )
    return ExtractedRecord(
        extraction=extraction,
        data=data,
        confidence={note.field: note.confidence for note in notes},
        findings=[*grounding_findings, *normalizing_findings],
    )


async def extract_document_invoices(
    session: AsyncSession, document: Document, extractor: InvoiceExtractor
) -> list[ExtractedRecord]:
    """Run the model over the document's pages and save what it found as a new version.

    Earlier versions stay in the table but stop being current. Safe to run again.
    """
    rows = await session.execute(
        select(Page.page_no, Page.text)
        .where(Page.document_id == document.id)
        .order_by(Page.page_no)
    )
    pages = [(number, text or "") for number, text in rows]
    # The model call is blocking network I/O, so it runs in a thread, off the event loop.
    items = await asyncio.to_thread(extractor.extract, pages)

    latest = await session.scalar(
        select(func.max(Extraction.version)).where(Extraction.document_id == document.id)
    )
    version = (latest or 0) + 1
    await session.execute(
        update(Extraction)
        .where(Extraction.document_id == document.id, Extraction.is_current)
        .values(is_current=False)
    )
    records = [_to_record(document.id, index, version, item) for index, item in enumerate(items)]
    session.add_all(record.extraction for record in records)
    await session.commit()
    return records


async def _duplicate_findings(
    session: AsyncSession, document_id: uuid.UUID, extraction: Extraction
) -> list[Finding]:
    """Find the same invoice in another document (current extractions only)."""
    if extraction.supplier_norm is None:
        return []
    others = (
        Extraction.is_current,
        Extraction.document_id != document_id,
        Extraction.supplier_norm == extraction.supplier_norm,
    )
    findings = []
    if extraction.invoice_number is not None:
        same_number = await session.scalar(
            select(Extraction.document_id)
            .where(*others, Extraction.invoice_number == extraction.invoice_number)
            .order_by(Extraction.created_at)
            .limit(1)
        )
        if same_number is not None:
            message = (
                f"invoice {extraction.invoice_number} of this supplier is also in {same_number}"
            )
            findings.append(
                Finding("duplicate_invoice", ERROR, message, "invoice_number", same_number)
            )
    if extraction.total is not None and extraction.invoice_date is not None:
        number_differs = (
            or_(
                Extraction.invoice_number.is_(None),
                Extraction.invoice_number != extraction.invoice_number,
            )
            if extraction.invoice_number is not None
            else true()
        )
        same_amounts = await session.scalar(
            select(Extraction.document_id)
            .where(
                *others,
                Extraction.total == extraction.total,
                Extraction.invoice_date == extraction.invoice_date,
                number_differs,
            )
            .order_by(Extraction.created_at)
            .limit(1)
        )
        if same_amounts is not None:
            message = f"same supplier, total and date as an invoice in {same_amounts}"
            findings.append(Finding("possible_duplicate", WARNING, message, None, same_amounts))
    return findings


def _issue(document_id: uuid.UUID, extraction_id: uuid.UUID | None, f: Finding) -> ValidationIssue:
    return ValidationIssue(
        document_id=document_id,
        extraction_id=extraction_id,
        code=f.code,
        field=f.field,
        severity=f.severity,
        message=f.message,
        related_document_id=f.related_document_id,
    )


async def validate_invoice_findings(
    session: AsyncSession,
    document_id: uuid.UUID,
    record: ExtractedRecord,
    today: date,
    threshold: float,
) -> None:
    """Replace the findings of one invoice: rules, warnings from reading it, and duplicates.

    Findings of the document's other invoices are left alone.
    """
    await session.execute(
        delete(ValidationIssue).where(ValidationIssue.extraction_id == record.extraction.id)
    )
    findings = [
        *record.findings,
        *validate_invoice(record.data, record.confidence, today, threshold),
        *await _duplicate_findings(session, document_id, record.extraction),
    ]
    session.add_all(_issue(document_id, record.extraction.id, f) for f in findings)


async def document_status(session: AsyncSession, document_id: uuid.UUID) -> str:
    """`NEEDS_REVIEW` or `COMPLETED`, from every current finding of the document."""
    await session.flush()  # findings added in this transaction must be visible to the queries
    current = select(Extraction.id).where(
        Extraction.document_id == document_id, Extraction.is_current
    )
    rows = await session.execute(
        select(ValidationIssue.code, ValidationIssue.severity, ValidationIssue.message).where(
            ValidationIssue.document_id == document_id,
            # Findings of earlier versions describe values that are no longer current.
            or_(
                ValidationIssue.extraction_id.is_(None), ValidationIssue.extraction_id.in_(current)
            ),
        )
    )
    findings = [Finding(code, severity, message) for code, severity, message in rows]
    has_invoices = await session.scalar(select(current.exists())) or False
    return route(findings, has_invoices=has_invoices)


async def validate_document(
    session: AsyncSession,
    document: Document,
    records: Sequence[ExtractedRecord],
    today: date,
    threshold: float,
) -> str:
    """Save the findings of every invoice (replacing earlier ones) and return the new status."""
    # Document-level findings are rebuilt on every run.
    await session.execute(
        delete(ValidationIssue).where(
            ValidationIssue.document_id == document.id, ValidationIssue.extraction_id.is_(None)
        )
    )
    for record in records:
        await validate_invoice_findings(session, document.id, record, today, threshold)
    if not records:
        missing = Finding("no_invoice_found", ERROR, "no invoice was found in this document")
        session.add(_issue(document.id, None, missing))
    return await document_status(session, document.id)


async def run_extraction(
    session: AsyncSession,
    document: Document,
    extractor: InvoiceExtractor,
    today: date,
    threshold: float,
) -> None:
    """The whole job for one document: extract, validate, and set `COMPLETED` or `NEEDS_REVIEW`."""
    records = await extract_document_invoices(session, document, extractor)
    document.status = await validate_document(session, document, records, today, threshold)
    await session.commit()
