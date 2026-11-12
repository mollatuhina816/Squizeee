# Extensible slide model

The proposed authoring contract is `frontend/app/slide-schema.ts`; the PostgreSQL target is `docs/slide-model.sql`. These are design artifacts, not a replacement for the running API. The existing SQLAlchemy `Slide.question` and `QuizQuestion` contracts remain active until an explicit migration and API integration are implemented.

Each slide combines metadata, a type discriminator, type-specific content/settings, and private assessment data. Content contains the question, options and timer. Assessment contains correct answers, explanation and point values; separating it makes accidental answer disclosure harder. Option IDs remain stable when labels or ordering change. Points use integer thousandths, matching the current backend's scoring approach.

`Slide` is a discriminated union: checking `slide.type === 'scale'` exposes scale bounds and prevents treating it as multiple-choice content. `SlideContent<'ranking'>` and `SettingsFor<'word-cloud'>` select individual shapes. `SlideSettings` contains shared voting, result visibility and background fields; each registered type adds its permitted result views.

## Adding a type

Extend `SlideTypeMap` through module augmentation, implement `SlidePlugin` parsing/defaults/version migrations, and register the renderer, participant input, aggregation and scoring handlers in the application. Register its `(type, schema_version)` in the database. No new slide columns or PostgreSQL enum changes are needed. TypeScript augmentation alone does not register runtime behavior. Unknown types or unsupported versions should open a read-only unsupported-slide placeholder and remain preserved, rather than being cast to a known type.

```ts
import type { BaseContent, SlideSettings } from '../app/slide-schema';

declare module '../app/slide-schema' {
  interface SlideTypeMap {
    'acme:timeline': {
      content: BaseContent & { startYear: number; endYear: number };
      settings: SlideSettings & { resultsView: 'timeline' };
      assessment: { mode: 'none' };
    };
  }
}
```

## Validation and runtime rules

Validate all incoming JSON with server-side type/version-specific validators; TypeScript types and JSONB object checks do not perform runtime validation. Reject unknown fields except namespaced `extensions`. Enforce bounded text, options, payload size, valid asset ownership, permitted colors and integer timer seconds. Require finite numbers throughout.

- Options: unique IDs, at least two choices, selection min/max within option count; correct IDs must reference existing options and obey selection limits. Exact matching awards full points only for equal sets. Partial matching needs an explicitly documented scoring algorithm before enabling it.
- Ranking: unique option IDs and unique answer IDs; an automatically graded ranking requires every option exactly once. `requireAll` determines whether participant submissions must contain every option.
- Scale: positive step, min below max, whole number of steps across the range; submitted and correct values must lie on the allowed grid. Tolerance must be nonnegative.
- Text: positive character/word limits, bounded nonempty accepted answers for automatic grading. Apply the specified whitespace and case normalization consistently.
- Voting: positive integer submission limit; changing an existing answer replaces that submission and does not consume another slot. Enforce limits atomically on the server per participant/session/slide, independently of client settings. Content slides accept no responses and require no assessment.
- Styling: validate overlay opacity between 0 and 1; resolve asset IDs through authorized storage. Result visibility and answer reveal authorization must be enforced on the server.

## Persistence and migration

Relational columns cover identity, ordering, revisions and version references; JSONB stores evolving type-specific fields. The deferred ordering constraint allows swaps inside one transaction. Update timestamps explicitly and compare/increment revisions on every save, including assessment-only changes. Perform presentation authorization before reading or writing a slide; derive organization membership through its presentation.

Store assessments separately with database privileges that exclude participant-facing readers. Construct participant DTOs using an explicit allowlist; assigning a full slide to `ParticipantSlide` does not remove runtime properties. Keep moderation and hidden results out of participant responses until permitted.

Before converting existing `slides.question`, map legacy kinds (`mcq`/`multiple_select` to `multiple-choice`, `word_cloud` to `word-cloud`, `short_answer` to `open-ended`), generate stable option IDs, translate text answers into IDs, and convert decimal marks to integer thousandths. Preserve unsupported legacy kinds rather than silently coercing them. Backfill and validate before switching reads/writes; retain a rollback path.

Live sessions must freeze content, settings, type/version and private scoring rules at launch so later author edits cannot change an active quiz. Responses should reference that session snapshot and stable option IDs, with participant/session/slide indexes and uniqueness rules appropriate to the submission limit. Keep existing live-session persistence until its own migration is designed.
