# Database schema

PostgreSQL 16 with the `pgvector` extension. Models live in `backend/app/db/models/`, migrations in `backend/alembic/versions/`. Keep this file in sync with both.

## Where data lives

```mermaid
flowchart LR
    Client -->|HTTP| API
    API -->|rows| PG[("PostgreSQL + pgvector")]
    API -->|files| S3[("SeaweedFS bucket: documents")]
    API -->|jobs| Redis[("Redis queue")]
    Redis --> Worker
    Worker -->|status, events, pages| PG
    Worker -->|read files, write page images| S3
```

- **PostgreSQL** holds every structured fact: documents, pages, events, and later extractions and search data.
- **SeaweedFS** holds the files. A document row points to its file through `documents.storage_key`.
- **Redis** holds only the job queue. Nothing in it is permanent.
- **Vector search** is the `pgvector` extension inside PostgreSQL, not a separate database. It is enabled; the vector column arrives with `chunks` (Phase 4).

## Entities that exist now

Migration `0001`.

```mermaid
erDiagram
    documents ||--o{ pages : "has pages"
    documents ||--o{ processing_events : "has history"

    documents {
        uuid id PK
        varchar filename "original name, display only"
        varchar mime "detected from contents"
        bigint size "bytes"
        varchar sha256 UK "exact-duplicate check"
        varchar storage_key "raw/id/original.ext"
        varchar status "UPLOADED QUEUED PROCESSING COMPLETED NEEDS_REVIEW FAILED"
        varchar source_type "pdf image spreadsheet"
        integer page_count "nullable"
        varchar error_code "nullable"
        text error_message "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    pages {
        bigint id PK
        uuid document_id FK "cascade delete"
        integer page_no "unique with document_id"
        text text "nullable, extracted text"
        varchar method "nullable: native ocr vision"
        float ocr_confidence "nullable"
        varchar image_key "nullable, page image in storage"
    }

    processing_events {
        bigint id PK
        uuid document_id FK "cascade delete"
        varchar stage "ingest"
        varchar status "started succeeded failed"
        integer duration_ms "nullable"
        varchar error_code "nullable"
        text error_message "nullable"
        integer attempt "1, 2, 3 ..."
        timestamptz created_at "indexed with document_id"
    }
```

Constraints and indexes:

| Table | Constraint / index |
|---|---|
| `documents` | primary key `id`; unique `sha256` (also the duplicate lookup index) |
| `pages` | primary key `id`; foreign key `document_id` with cascade delete; unique `(document_id, page_no)` |
| `processing_events` | primary key `id`; foreign key `document_id` with cascade delete; index `(document_id, created_at)` |

Rules worth knowing:
- Deleting a document deletes its pages and events (database-level cascade).
- `status` is a plain string checked in code (`DocumentStatus`), so new statuses need no migration.
- Storage keys are built from the document id and a type-derived extension, never from the client filename.

## Planned entities

Not created yet. Shown so the whole model is visible. Columns are indicative and will be fixed by each phase's change.

```mermaid
erDiagram
    documents ||--o{ documents : "split into (parent_id)"
    documents ||--o{ extractions : "has versions"
    extractions ||--o{ line_items : "has"
    extractions ||--o{ corrections : "audit trail"
    documents ||--o{ validation_errors : "has"
    documents ||--o{ chunks : "searchable text"
    documents ||--o{ cross_checks : "left side"
    documents ||--o{ cross_checks : "right side"

    extractions {
        uuid id PK
        uuid document_id FK
        integer version
        jsonb data "invoice fields"
        jsonb field_confidence
        jsonb grounding "source page and quote"
        varchar model
        varchar prompt_version
        boolean is_current
        timestamptz created_at
    }

    line_items {
        bigint id PK
        uuid extraction_id FK
        text description
        numeric quantity
        numeric unit_price
        numeric amount
        integer position
    }

    validation_errors {
        bigint id PK
        uuid document_id FK
        uuid extraction_id FK
        varchar code
        varchar field
        varchar severity "error warning"
        text message
        boolean resolved
    }

    corrections {
        bigint id PK
        uuid extraction_id FK
        varchar field
        text old_value
        text new_value
        varchar edited_by
        timestamptz created_at
    }

    chunks {
        bigint id PK
        uuid document_id FK
        integer page_no
        text text
        tsvector tsv "keyword search, GIN index"
        vector embedding "semantic search, HNSW index"
    }

    cross_checks {
        bigint id PK
        uuid left_document_id FK
        uuid right_document_id FK
        varchar match_key "invoice number"
        jsonb diffs
        varchar status
    }
```

| Planned table | Phase | Purpose |
|---|---|---|
| `documents.parent_id` (new column) | 2 | a PDF holding several invoices is split into child documents |
| `extractions`, `line_items` | 2 | structured invoice data from Gemini, versioned; money columns are `numeric`, never float |
| `validation_errors`, `cross_checks` | 3 | rule failures, and comparisons between documents |
| `corrections` | 4 | manual edits with who and when |
| `chunks` | 4 | text pieces for keyword and semantic search; the `embedding vector(N)` size must match the embedding model pinned in Phase 2 |
