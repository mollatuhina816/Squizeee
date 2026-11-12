# Student joining

The default live-quiz entry mode is **Join with name**.

1. Enter the quiz code, student name, institute name, stream, and semester.
2. On the first visit, enter a valid phone number (7–15 digits).
3. On future visits in the same browser, enter the quiz code, name, institute,
   stream, and semester.

The backend stores name and phone in a participation profile without requiring
email. Institute name, stream, and semester are saved with each quiz
participation, so students can provide the details applicable to that quiz. A
private, HttpOnly signed profile cookie identifies returning students for up to
30 days. Names are compared without case differences or repeated spaces. Names
are never used for a global profile lookup. Students with the same name remain
separate, and a new browser or cleared/expired cookie requires registration
again. Phone numbers are not shown on public leaderboards.

The browser also retains a separate per-quiz participant credential to resume
the same attempt without creating a duplicate. The existing **Use email
profile** flow is available as an alternative. Existing guest API clients are
unchanged; the new default browser flow sends `join_by_name: true` and
`guest: false` to `/api/v1/sessions/join`.

Apply database migrations and restart the API before using the new flow.
The stream/semester and institute migrations only add nullable columns to
`participants`; they do not rewrite or delete existing rows. Existing records
remain valid and show blank values for the newly added fields. Back up the
database before deploying and run `python -m alembic upgrade head` from
`backend`.
