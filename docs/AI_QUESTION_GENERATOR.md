# AI Question Generator

The generator defaults to Gemini through the FastAPI backend. OpenAI remains available only when explicitly selected with AI_PROVIDER=openai; Gemini requests never fall back to OpenAI. It returns temporary drafts only. Review and edit them in the Question Bank or presentation editor before selecting **Save selected to Question Bank** or **Add selected to presentation**. Questions staged in an editor must still be saved before they can be presented. No AI-generated question is automatically published to a live session.

## Configuration

Set these values in the root `.env` file. Keep API keys private; they are passed to the backend only and must not use a `NEXT_PUBLIC_` prefix.

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_QUESTION_MODEL=gemini-2.5-flash-lite
# Optional alternative provider:
OPENAI_API_KEY=
OPENAI_QUESTION_MODEL=gpt-4.1-mini
AI_MAX_QUESTIONS_PER_REQUEST=20
AI_MAX_TEXT_LENGTH=20000
AI_MAX_IMAGE_SIZE_MB=10
AI_REQUEST_TIMEOUT_SECONDS=45
AI_MAX_OUTPUT_TOKENS=8000
AI_DAILY_LIMIT_FACULTY=50
AI_DAILY_LIMIT_ADMIN=100
AI_DAILY_LIMIT_FACULTY_LITE=10
AI_REQUESTS_PER_MINUTE=5
```

Create a Gemini API key at https://aistudio.google.com/apikey and put it in GEMINI_API_KEY. Gemini Flash-Lite offers a free tier with quota limits; this setting does not guarantee free usage for projects with paid billing enabled. For a local backend launched from the backend directory, set the same provider settings in backend/.env. The API key is optional for running Quizeee. Without one, generation returns a sanitized configuration error and unrelated quiz features continue to work. Restart/rebuild after editing `.env`:

```powershell
docker compose up --build -d
```

Daily limits count generation requests (not individual questions) and are enforced per user and organization in Redis. Owner/admin use the admin limit; faculty and department admins use the faculty limit; faculty-lite must also have the existing `bank.write` permission. Students and users without bank permission are denied. Redis failure fails closed for AI requests only.

## API

All routes require the existing authenticated session and trusted-origin checks. Requests are scoped to the organization in the URL and require `bank.write`.

### Generate from a topic or pasted text

`POST /api/v1/organizations/{org_id}/ai/generate-questions`

```json
{
  "source_type": "text",
  "content": "The left ventricle pumps oxygenated blood into the aorta.",
  "question_count": 2,
  "question_type": "mcq",
  "difficulty": "medium",
  "language": "English",
  "grade_level": "Class 8",
  "subject": "Biology",
  "exam_style": "General classroom",
  "avoid_questions": []
}
```

`source_type` is `topic` or `text`; question type is `mcq`, `true_false`, `short_answer`, or `mixed`; difficulty is `easy`, `medium`, `hard`, or `mixed`. Languages currently supported are English, Bengali, and Hindi. `avoid_questions` is optional and helps regeneration avoid previous drafts.

Example response (the `question` member is the same canonical model stored in the Question Bank):

```json
{
  "questions": [
    {
      "question": {
        "kind": "mcq",
        "title": "Which chamber pumps oxygenated blood into the aorta?",
        "body": "",
        "options": ["Left ventricle", "Right atrium", "Right ventricle", "Left atrium"],
        "correct_answers": ["Left ventricle"],
        "explanation": "The left ventricle pumps oxygenated blood into the aorta.",
        "marks": "1",
        "negative_marks": "0",
        "speed_bonus": "0",
        "duration_seconds": 30,
        "minimum": 1,
        "maximum": 5
      },
      "difficulty": "medium"
    }
  ],
  "generated_count": 1
}
```

The service requests JSON Schema output, then validates every draft against Quizeee's canonical `Question` model. It can return fewer questions than requested when the material is insufficient.

### Generate from an uploaded topic document

Choose **Upload topic document** in **Generate with AI**, select a lesson or notes file, then select **Generate questions**. An answer key is not required.

`POST /api/v1/organizations/{org_id}/ai/generate-questions/document` accepts multipart fields `document` (PDF, PPTX, or UTF-8 TXT) and `options_json` (the same settings as image generation). Limits are 40 MB, 100 pages/slides, and the configured text limit (20,000 characters by default). Text is extracted and questions are grounded in that material. Empty, unreadable, protected, and oversized documents are rejected before generation. Scanned pages can use **Upload image** instead. Documents are not saved.

### Generate from an image

`POST /api/v1/organizations/{org_id}/ai/generate-questions/image` as `multipart/form-data` with:

- `image`: JPG/JPEG, PNG, or WEBP file. The MIME type, file signature, configured size limit, and decodability are checked; the image is not saved.
- `options_json`: JSON containing `question_count`, `question_type`, `difficulty`, and optional `language`, `grade_level`, `subject`, `exam_style`, and `avoid_questions` fields.

Unreadable or irrelevant images return a controlled no-content error. Uploaded content is sent to the configured model for that request and is not retained by Quizeee.

### Save approved drafts

`POST /api/v1/organizations/{org_id}/bank/questions/bulk` accepts 1–20 normal bank items:

```json
{
  "items": [
    {
      "question": { "kind": "short_answer", "title": "Name the chamber...", "body": "", "options": [], "correct_answers": ["Left ventricle"], "explanation": "..." },
      "subject": "Biology",
      "topic": "Human heart",
      "difficulty": "medium",
      "tags": ["ai-generated"]
    }
  ]
}
```

Each entry uses the existing `BankInput` and `Question` validators and is saved atomically with the existing bank audit event. No AI question table or migration was added.

## Verification

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_questions.py -q
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Manual check: sign in as a faculty/owner, open **Question bank**, generate from a topic, edit/delete/select drafts, then save selected. Confirm they appear in the normal bank and can be selected in a presentation editor. In the editor, add a generated question, save changes, and only then choose **Present**. Try an unsupported image file, an image over the configured limit, a user without `bank.write`, and a user who exceeds the Redis limits.

No generation source text, image, or API key is written to the database or application logs. Operational logs contain organization/user IDs, source type, model, and requested/generated counts only.
