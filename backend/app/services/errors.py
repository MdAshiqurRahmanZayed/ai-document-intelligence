import uuid


class DocumentNotFound(Exception):
    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(str(document_id))
        self.document_id = document_id
