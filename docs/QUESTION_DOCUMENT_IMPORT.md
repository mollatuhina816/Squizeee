# Question document import

Upload existing question documents from the Question Bank or quiz editor. This
workflow extracts existing questions; it does not generate questions or solve
missing answers.

Supported inputs are PDF, DOCX, PPTX, XLSX, CSV, UTF-8 TXT and JSON. File signatures
identify PDF and Office formats; misleading supported extensions are rejected.
Maximum upload size is 40 MB. Documents support 100 pages/slides and 100 extracted
questions; JSON and spreadsheets support 500 questions.

## Canonical document

`backend/app/import_schema.py` defines the version 1.0 Pydantic discriminated
union. All formats normalize into this document before bank conversion:

```json
{
  "schema_version": "1.0",
  "questions": [{
    "type": "mcq",
    "question": "Which planet is known as the Red Planet?",
    "options": [{"id": "A", "text": "Earth"}, {"id": "B", "text": "Mars"}],
    "correct_answers": ["B"],
    "source": {"filename": "science.pptx", "slide_number": 5, "sections": [5]},
    "answer_origin": "source"
  }]
}
```

MCQ/quiz accepts one correct option ID; the existing `multiple_select` variant
accepts multiple IDs. Missing scored answers remain empty and require review.
True/false has two fixed response texts. Survey may have response options or be
open-ended; option surveys map to the platform's poll type. Short answer accepts
optional `accepted_answers` and `model_answer`, without choice options. Ranking,
scale, rating, NPS and the existing free-response variants are also supported.
Unknown fields, invalid options, invalid answers and unsupported versions are
reported rather than silently discarded.

## PowerPoint understanding

Extraction preserves slide order and numbers, title/body paragraphs, recursive
groups, shape positions, table cells and formatting, notes, embedded images and
answer evidence. The conservative text parser handles numbered/multiple
questions, explicit continuation slides, inline options, checkmarks and separate
numbered answer keys. Duplicate numbers and unmatched keys are reported.
Standalone option-letter badges are paired with nearby text boxes using their
positions. Repeated footers and MCQ topic headings remain context; explicit cover,
overview and recap slides are not converted into response questions. Key idea
text is preserved as explanation.
Question identifiers are read from presentation banners such as
`MBA QUIZ COMPETITION | QUESTION 1/20`. Final answer-key slides may use `Q1: A`,
`Question 1: A` or numbered keys, and may span several slides. A continued key
slide can omit its heading when every row is an explicit numbered choice/boolean
answer. Question-number matching, not slide order, associates answers; source
records include both question and answer-key slide numbers. Leading-zero question
numbers are normalized. Duplicate or unmatched identifiers require review.
When a text-only banner/option layout and its answer keys are fully resolved,
import does not depend on a second AI extraction. Uninspected images, missing
answers, unknown shapes and ambiguous content still use the AI/review fallback.
Incomplete AI coverage retains the original text draft and supplied answers.

Multiple text boxes, tables, groups, varied colors, images, parsing issues and
missing answers trigger Gemini understanding using `GEMINI_API_KEY` and
`GEMINI_QUESTION_MODEL`. Gemini receives the structural context and images.
Configured rendering supplies full slide/page images to preserve visual layout.
No local Office applications, macros or embedded programs are executed.

An arbitrary highlight color does not establish correctness without explicit
source evidence such as a legend. Gemini is instructed to copy supplied answers,
never infer them from subject knowledge. Its output is schema-validated and always
requires faculty approval. Missing coverage and unreadable/unsupported visual
content remain visible as extraction issues.
Gemini receives a compact transport schema to avoid provider decoder limits;
the complete type-specific canonical union and all size/value constraints are
validated by Pydantic after extraction. Fixed schema values use single-value
enums in the transport schema.

If Gemini, rendering or AI usage controls fail, available text drafts remain
reviewable and require approval. Rendering failure still permits structural and
embedded-image understanding. Full visual interpretation requires a renderer
when the relevant content is not represented by readable text or embedded images.

## Review and save

1. `POST /api/v1/organizations/{org}/imports/preview/file` accepts multipart `file`.
2. Inspect the preview, correct question fields or canonical JSON, and resolve
   extraction issues against the original document.
3. `POST /imports/{batch}/review` accepts `document` and, for unresolved issues,
   an explicit `acknowledge_unresolved` flag. It validates bank compatibility and
   records faculty approval.
4. `POST /imports/{batch}/commit` atomically imports into the existing Question
   Bank. Repeated commits return the existing result. Preview expiry is 24 hours.

The existing `/imports/preview` base64 endpoint remains available. Reviewed
previews can also append to a presentation using its revision-checked endpoint.
All operations require bank permissions and are scoped to the preview owner.

`POST /imports/{batch}/questions/{index}/suggest-answer` is a separate, optional
Generate/Verify Answer with AI action. Suggestions are explicitly unverified,
do not mutate the saved preview, and require faculty approval before import.

## Optional conversion and rendering services

Configure deployment-owned, trusted sandboxed services; URLs come exclusively
from server configuration. These services receive uploaded faculty documents.
Use authenticated private services with process isolation and resource limits.

- `DOCUMENT_CONVERSION_URL`: accepts multipart `file` and `target=pdf`; returns
  PDF bytes. Without it, legacy DOC/PPT/XLS and other unsupported formats return a
  clear requirement to export DOCX/PPTX/XLSX or PDF.
- `DOCUMENT_RENDERER_URL`: accepts multipart `file`; returns JSON
  `{"images":[{"section_number":1,"mime_type":"image/png","data":"BASE64"}]}`.
  Return exactly one image for every extracted section. For DOCX, the current
  extraction treats the document as a single section; provide a bounded composite
  image or export PDF for page-by-page rendering.
- `DOCUMENT_SERVICE_TOKEN`: optional bearer token for both services.
- `IMPORT_AI_MAX_CONTEXT_CHARS`: bounds extracted context; oversized documents
  must be split. Archives, images, service responses and output question counts
  are separately bounded. Redirects are disabled for service requests.

Service deployment is separate from Quizeee. Leaving these values blank does not
enable full-slide rendering or legacy conversion.

## Apply code changes to the local Docker app

Compose builds application code into images; it does not mount the working tree.
Editing Python or frontend files alone does not update the running app. Rebuild
and recreate the affected services:

```powershell
docker compose build api web worker
docker compose up -d --no-deps api web worker
```

Refresh the browser and upload the file again to create a new preview. Existing
previews retain their original extraction result.

## Validation

From `backend`, run `venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.
Import regressions cover all seven input types, slide continuation, answer keys,
groups/tables/colors/notes, absent source answers, faculty approval, authorization,
idempotent commits, mocked Gemini vision, and rendering/AI failure recovery.
