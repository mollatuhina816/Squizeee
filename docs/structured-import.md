# Structured quiz import

The question importer now offers **AI Smart Import** and **Structured Import (No AI API)** as visible, independent choices. Existing AI endpoints and provider integrations are retained. Shared text parsing now preserves mathematical notation, handles explicit letter-plus-text answers, and retains recoverable drafts. The structured upload endpoint does not reserve AI quota, call AI providers, use the remote conversion service, or offer AI answer suggestions.

Both methods create existing `ImportBatch` previews using the existing canonical schema. Approval converts questions through `to_bank` and `BankInput`; the existing commit endpoint writes `BankQuestion`. No database migration or second question bank is needed. Imports opened from a quiz retain the existing import-into-presentation behavior.

## Usage

1. Select Structured Import and PDF, PowerPoint, or Excel.
2. Download the matching template, fill it in, and upload it.
3. Select Extract and validate questions.
4. Review the table and edit fields below it. Select correct answers explicitly. Remove unwanted questions or use Keep valid rows only.
5. Acknowledge excluded/unmatched content when there are extraction errors, then save faculty approval. Approval validates the remaining questions again.
6. Confirm the import into the question bank (or current quiz).

PDF questions begin with `Question 1:` and have A–D options, `Correct Answer: B` or exact option text, and optional `Explanation:`. Multiple questions can use `--- QUESTION ---` separators. A question may continue onto the next selectable-text PDF page. PowerPoint uses one question per slide; blank slides are ignored. Excel uses exactly these headers on every sheet:

`Question | Option A | Option B | Option C | Option D | Correct Answer | Explanation`

Completely empty Excel rows are ignored. XLSX formula cells and formula-like text are rejected; XLS reads cached cell values without evaluating formulas. Errors include worksheet and source row. Duplicate statements are compared after case and whitespace normalization, both within the upload and against the organization's existing bank. Duplicates must be removed or changed before structured approval.

## Deployment

Install the backend dependencies from `requirements.lock` (or `pip install -e '.[test]'` for development). Added runtime packages: PyMuPDF, pytesseract, xlrd, and olefile. Existing python-pptx, openpyxl, Pydantic, Pillow, and reportlab are reused. xlwt is a test-only dependency for generating a genuine XLS fixture.

Install **Tesseract OCR** and its language data on the backend host. Install **LibreOffice Impress** to read legacy binary PPT files; python-pptx reads the converted PPTX. The backend Docker image installs both executables. Legacy XLS is read directly through xlrd without conversion or OCR.

Optional backend environment settings:

```dotenv
STRUCTURED_IMPORT_MAX_BYTES=40000000
STRUCTURED_OCR_LANGUAGE=eng
STRUCTURED_TESSERACT_COMMAND=tesseract
STRUCTURED_LIBREOFFICE_COMMAND=soffice
```

On Windows, command values may be full executable paths. No existing API keys or AI configuration need to change. Uploaded files are processed on the backend. PPT conversion uses an isolated temporary directory and LibreOffice profile, cleaned up afterward. Conversion has a 60-second timeout; each OCR call has a 30-second timeout. PDF rasterization processes one page at a time at a bounded resolution. Existing archive expansion limits apply to Office ZIP files. Limits are 100 PDF pages/slides, 500 questions, 10000 spreadsheet data rows, seven columns, and 20 megapixels per OCR image. The configurable upload limit can be reduced from its 40 MB maximum.

## OCR behavior and limits

Selectable PDF text is attempted first. Incomplete page structure with images or very little readable text triggers full-page OCR, replacing that page's text layer to avoid duplicate extraction. PowerPoint text is read first from text boxes, groups, and tables; embedded images are OCR'd when text does not form a complete template question. Duplicate embedded images are read once per slide. Decorative images accompanying complete template questions do not trigger OCR.

OCR output always requires explicit faculty review. The parser accepts missing punctuation on recognized A–D labels and field headings. It deliberately does not substitute O/0 or I/1 in answer values or infer damaged option labels: missing or unrecognized answers stay blank for correction. OCR is fallible even when the text appears valid, so administrators must compare scanned text and answers against the source.

Template structure remains mandatory. This method does not interpret arbitrary visual layouts. Mixed image/text layouts and cross-page scanned questions may need manual editing. Missing OCR/conversion executables produce actionable errors rather than falling back to AI. Install extra Tesseract language packs for languages beyond English. Legacy PPT conversion runs a local document parser; keep LibreOffice and Tesseract patched and run the backend with its existing unprivileged account.

Explicit letter-plus-text answers such as `Answer: B) O(log n)` are accepted when the letter and text agree. Mathematical parentheses are preserved rather than mistaken for option labels. Unlabelled prose after a verified answer is retained as a tentative explanation and requires faculty review. Conflicting letter/text answers stay blank for correction; they are never guessed. AI document previews retain recoverable questions even if parsing or the AI fallback fails. Empty previews cannot be approved, and a manual-question action allows reconstruction when no usable draft exists. Re-upload files after a parser update; already-saved previews contain the earlier extraction results.

## Implementation files

Created:

- `backend/app/structured_import.py`: extraction, OCR, validation, local PPT conversion, and template generation.
- `backend/app/import_answers.py`: shared explicit-answer resolution with conflict detection.
- `backend/tests/test_structured_import.py`: parser, templates, OCR fallback/failure, XLS, validation, editing, partial approval, shared bank, and no-AI regression coverage.
- `backend/tests/test_import_recovery.py`: the five reported PDF examples, mathematical notation, tentative explanations, conflicting-answer recovery, both upload routes, and shared-bank commits.
- `docs/structured-import.md`: usage, deployment, and limitations.

Modified:

- `backend/app/import_routes.py`: separate structured upload/template/review endpoints; existing commit reused.
- `backend/app/document_import.py`, `backend/app/import_parser.py`, `backend/app/import_pipeline.py`: token boundaries, explicit answer resolution, retained drafts, and avoidance of redundant AI extraction for already-resolved text.
- `backend/app/config.py`: upload size, language, and executable settings.
- `backend/pyproject.toml`, `backend/requirements.lock`: dependencies.
- `backend/Dockerfile`: OCR and PPT conversion executables.
- `frontend/app/question-importer.tsx`: method/file selection, templates, structured preview table, editing, removal, valid-row selection, and approval.

Regression checks include the existing AI/document import suites, direct XLS/XLSX/PDF/PPTX template extraction, mocked scanned PDF/image-slide OCR, edited partial imports into the existing bank, frontend TypeScript checks, and the full backend suite. The actual Tesseract integration test runs only when the executable is installed. Real LibreOffice binary PPT conversion requires the executable and a representative legacy PPT file on the deployment host; its unavailable-executable path is tested locally.

Verification on 2026-11-17: the full backend run passed 260 tests with three skips (two PostgreSQL concurrency checks requiring a test PostgreSQL URL, and actual Tesseract execution requiring the executable). After the final duplicate-query and diagnostic-sanitization changes, the structured suite passed 20 tests with the Tesseract test skipped. Frontend `tsc --noEmit`, the Next.js production build, and `git diff --check` passed. The 100-row/95-valid partial import and correction of invalid extracted questions are covered by API tests. Browser interaction and real legacy PPT conversion were not exercised on this host.

After the reported PDF parsing failure was corrected, the full backend suite passed 272 tests with the same three skips. The regression PDF returns all five questions through both import methods, preserves their explanations, and commits through the same bank endpoint after approval. Frontend TypeScript checks passed. The local API was restarted with the changes and its dependency readiness endpoint and website returned HTTP 200. Browser automation was stopped because the tool could not reliably identify the current Chrome URL; this follow-up was verified with API and parser tests rather than browser interaction. Tesseract and LibreOffice are still not installed on this Windows host; Docker includes both.
