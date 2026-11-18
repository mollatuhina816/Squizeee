# PDF Import Flow

## Quick steps

1. Choose **Structured Import**, select PDF, and upload your document.
2. Click **Extract and validate questions**.
3. Check the extracted questions, options, and correct answers.
4. Click **Keep valid rows only** to exclude rows with validation errors and validate the remaining questions.
5. When the success message says the valid questions are ready, click **Import into this quiz** or **Import into question bank**.

There is no manual-add button in the import section. To restore a missed question, correct the source document and upload it again.

## What does Keep valid rows only do?

- Excludes question rows that have reported validation errors.
- Submits the remaining questions to the server for validation and approval.
- Acknowledges that invalid or unmatched extraction content is intentionally excluded.
- Enables the final Import button when validation succeeds.
- Does not import automatically: you choose the destination's Import button to finish.

Check the preview against your source document before using this action. If no valid questions remain, correct the source file and upload it again.

## Example

If the PDF contains five questions and one row is invalid:

```text
Upload PDF -> Extract -> Review five rows
                         |
                  Keep valid rows only
                         |
                  Four questions validated
                         |
                  Import into this quiz
```

The invalid row is excluded. Only the four remaining questions are imported.

## Editing questions

You can still expand question cards, edit text or answers, and remove unwanted questions. After editing, click **Save faculty approval** to validate the changes before importing. Keep valid rows only is disabled while there are unsaved edits because the displayed validation errors refer to the last validated preview.

## Other buttons

| Button | Purpose |
| --- | --- |
| Extract and validate questions | Creates a preview from a structured file. |
| Keep valid rows only | Excludes invalid rows and validates the remaining questions for import. |
| Remove question | Removes one question from the preview; save approval afterward. |
| Save faculty approval | Validates and saves your edited preview. |
| Import into this quiz | Saves approved questions into the current quiz. |
| Import into question bank | Saves approved questions for reuse in the question bank. |

AI Smart Import begins extraction when you select a file. Keep valid rows only belongs to Structured Import. AI answer suggestions still require checking and approval.

## If Import stays disabled

Wait for processing to finish and read any validation error. Correct remaining problems and save faculty approval, or fix the source document and upload it again. A successful valid-row action prepares the preview for import; later edits require approval again.
