# Testing

Backend tests run in Docker with `make test` (unit and integration, real PostgreSQL, Tesseract installed). `make bench` runs the slow large-document benchmarks, which `make test` skips. Tests never call a real LLM. Test files (PDFs, images, spreadsheets) are generated in memory by `tests/pdf_samples.py`, `tests/image_samples.py` and `tests/spreadsheet_samples.py`; no binary fixtures are committed.

## Phase 1 coverage: file types and failures

Each row names the tests that cover it (`file::test`, under `backend/tests/`).

| Case | Covered by |
|---|---|
| Digital PDF | `unit/test_pdf.py::test_text_pages_are_extracted_without_images`, `integration/test_pdf_ingest.py::test_text_pdf_saves_one_native_row_per_page`, `integration/test_ingest_task.py::test_pdf_is_processed_into_pages` |
| Scanned PDF | `unit/test_pdf.py::test_image_only_page_is_scanned_and_rendered`, `integration/test_ingest_task.py::test_scanned_pdf_waits_for_ocr` |
| Mixed PDF (text and scanned pages) | `unit/test_pdf.py::test_mixed_pdf_renders_only_the_scanned_page`, `integration/test_pdf_ingest.py::test_images_are_stored_only_for_scanned_pages` |
| JPG and PNG | `unit/test_image.py::test_single_image_is_one_png_page`, `integration/test_ingest_task.py::test_image_waits_for_ocr_then_completes` |
| Multi-page TIFF | `unit/test_image.py::test_multi_frame_tiff_gives_one_page_per_frame`, `integration/test_image_ingest.py::test_multi_frame_tiff_becomes_one_page_per_frame` |
| XLSX with several sheets | `unit/test_spreadsheet.py::test_multi_sheet_workbook_gives_a_page_per_sheet_and_skips_the_empty_one`, `integration/test_spreadsheet_ingest.py::test_workbook_saves_one_native_page_per_sheet_with_data`, `integration/test_ingest_task.py::test_spreadsheet_is_completed_with_pages_and_no_ocr_job` |
| XLS | `unit/test_spreadsheet.py::test_legacy_xls` |
| CSV (`;` delimiter, Latin-1) | `unit/test_spreadsheet.py::test_csv_semicolon_latin1_keeps_the_accent_and_splits_cells`, `integration/test_spreadsheet_ingest.py::test_csv_document_is_named_after_its_file` |
| Poor image quality (skewed, noisy) | `unit/test_preprocess.py::test_noisy_page_still_has_dark_text_pixels`, `unit/test_ocr.py::test_skewed_and_noisy_images_are_still_read` |
| Corrupt PDF | `unit/test_pdf.py::test_truncated_pdf_is_reported_as_corrupt`, `integration/test_ingest_task.py::test_unusable_pdf_fails_once_without_retry` |
| Encrypted PDF | `unit/test_pdf.py::test_encrypted_pdf_is_reported` |
| Truncated image | `unit/test_image_samples.py::test_truncated_image_fails_to_decode`, `unit/test_image.py::test_undecodable_data_is_reported_as_corrupt`, `integration/test_ingest_task.py::test_truncated_image_fails_once_without_retry` |
| Truncated XLSX or XLS | `unit/test_spreadsheet.py::test_truncated_xlsx_is_corrupt`, `unit/test_spreadsheet.py::test_truncated_xls_is_corrupt`, `integration/test_ingest_task.py::test_unusable_spreadsheet_fails_once_without_retry` |
| Empty file (upload) | `integration/test_documents_service.py::test_empty_file_is_rejected`, `unit/test_filetypes.py::test_rejects_everything_else` |
| Empty workbook or blank CSV | `unit/test_spreadsheet.py::test_workbook_and_csv_without_data_are_empty` |
| Wrong extension | `unit/test_filetypes.py::test_binary_signature_wins_over_filename`, `unit/test_filetypes.py::test_pdf_named_jpg_is_still_a_pdf`, `integration/test_documents_service.py::test_wrong_extension_is_stored_by_what_the_bytes_are`, `integration/test_documents_service.py::test_unsupported_type_is_rejected` |
| Routing of each file type to its ingest step | `integration/test_ingest_task.py::test_each_file_type_is_routed_to_its_own_ingest` |
| OCR runs in parallel, same result at any limit | `integration/test_ocr_ingest.py::test_reads_overlap_but_never_exceed_the_limit`, `integration/test_ocr_ingest.py::test_a_limit_of_one_gives_the_same_result`, `integration/test_ocr_ingest.py::test_a_failed_read_keeps_the_batches_already_saved` |
| 1000-page PDF, memory flat (slow, `make bench`) | `integration/test_large_documents.py::test_memory_does_not_grow_with_page_count` |
| Concurrent OCR speedup (slow, `make bench`) | `integration/test_large_documents.py::test_concurrent_ocr_gives_the_same_pages_faster` |
