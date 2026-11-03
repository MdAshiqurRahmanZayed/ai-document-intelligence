"""The document filters, as query parameters shared by the list and by search."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Query

from app.db.models import DocumentStatus
from app.services.listing import DocumentFilters


def document_filters(
    status: Annotated[DocumentStatus | None, Query()] = None,
    supplier: Annotated[str | None, Query(max_length=200)] = None,
    invoice_number: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    currency: Annotated[str | None, Query(max_length=10)] = None,
) -> DocumentFilters:
    return DocumentFilters(
        status=status,
        supplier=supplier,
        invoice_number=invoice_number,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        currency=currency,
    )
