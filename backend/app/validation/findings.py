"""The shape of a validation finding, shared by every step that can report one."""

import uuid
from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    code: str  # e.g. "total_mismatch"
    severity: str  # ERROR or WARNING
    message: str
    field: str | None = None
    related_document_id: uuid.UUID | None = None  # the other document of a duplicate
