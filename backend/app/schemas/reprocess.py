import uuid
from typing import Literal

from pydantic import BaseModel


class ReprocessRequest(BaseModel):
    # ingest: the whole pipeline again; extract: only extraction and validation.
    from_stage: Literal["ingest", "extract"] = "ingest"


class ReprocessOut(BaseModel):
    document_id: uuid.UUID
    status: str
    from_stage: Literal["ingest", "extract"]


class RetryFailedOut(BaseModel):
    queued: list[uuid.UUID]
    not_queued: int  # failed documents that could not be queued (broker down, or just claimed)
