/** Proposed authoring contract. Validate untrusted JSON on the server before use. */
export type UUID = string;
export type ISODateTime = string;
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface SlideOption {
  /** Stable across edits and reordering; never use the label as an answer key. */
  id: UUID;
  label: string;
  image?: { assetId: UUID; alt: string };
}

export interface BaseContent {
  question: string;
  description?: string;
  timer: { mode: 'none' } | { mode: 'countdown'; seconds: number };
}

export interface SlideSettings {
  voting: {
    maxSubmissionsPerParticipant: number;
    allowAnswerChanges: boolean;
  };
  results: {
    visibility: 'live' | 'after-close' | 'manual' | 'hidden';
    showCounts: boolean;
    showPercentages: boolean;
  };
  background:
    | { kind: 'solid'; color: string }
    | { kind: 'gradient'; from: string; to: string; angle: number }
    | { kind: 'image'; assetId: UUID; fit: 'cover' | 'contain'; overlayOpacity: number };
  textColor: string;
}

export interface PointValues {
  /** Integer thousandths of a point, avoiding floating-point scoring errors. */
  correctMilliPoints: number;
  incorrectPenaltyMilliPoints: number;
  maxSpeedBonusMilliPoints: number;
}

type NoAssessment = { mode: 'none' };
type Assessment<A> = NoAssessment | { mode: 'automatic'; points: PointValues; correctAnswer: A; explanation?: string };

/** Open registry: plugins extend this interface with TypeScript module augmentation. */
export interface SlideTypeMap {
  'multiple-choice': {
    content: BaseContent & { options: SlideOption[]; selection: { min: number; max: number } };
    settings: SlideSettings & { resultsView: 'bars' | 'donut'; shuffleOptions: boolean };
    assessment: Assessment<{ optionIds: UUID[]; matching: 'exact' | 'partial' }>;
  };
  'word-cloud': {
    content: BaseContent & { maxWordsPerEntry: number; maxCharactersPerEntry: number };
    settings: SlideSettings & { resultsView: 'cloud' | 'list'; moderation: 'off' | 'review'; normalizeCase: boolean };
    assessment: NoAssessment;
  };
  ranking: {
    content: BaseContent & { options: SlideOption[]; requireAll: boolean };
    settings: SlideSettings & { resultsView: 'ordered-list' | 'bars'; shuffleOptions: boolean };
    assessment: Assessment<{ orderedOptionIds: UUID[]; matching: 'exact' }>;
  };
  'open-ended': {
    content: BaseContent & { maxCharacters: number; placeholder?: string };
    settings: SlideSettings & { resultsView: 'cards' | 'list'; moderation: 'off' | 'review' };
    assessment: Assessment<{ acceptedTexts: string[]; caseSensitive: boolean; trimWhitespace: boolean }>;
  };
  scale: {
    content: BaseContent & { min: number; max: number; step: number; labels?: { min?: string; max?: string } };
    settings: SlideSettings & { resultsView: 'distribution' | 'average'; showAverage: boolean };
    assessment: Assessment<{ value: number; tolerance: number }>;
  };
  content: {
    content: BaseContent & { body: string; image?: { assetId: UUID; alt: string } };
    settings: SlideSettings & { resultsView: 'none' };
    assessment: NoAssessment;
  };
}

export type SlideType = keyof SlideTypeMap;
export type SlideContent<K extends SlideType = SlideType> = SlideTypeMap[K]['content'];
export type SettingsFor<K extends SlideType = SlideType> = SlideTypeMap[K]['settings'];
export type SlideAssessment<K extends SlideType = SlideType> = SlideTypeMap[K]['assessment'];

interface SlideMetadata {
  id: UUID;
  presentationId: UUID;
  position: number;
  /** Version of the plugin's persisted content/settings/assessment shape. */
  schemaVersion: number;
  /** Optimistic concurrency token, incremented on every saved edit. */
  revision: number;
  createdAt: ISODateTime;
  updatedAt: ISODateTime;
  extensions?: Record<string, JsonValue>;
}

/** Mapped union preserves type/content/settings correlation when narrowing. */
export type Slide<K extends SlideType = SlideType> = {
  [T in K]: SlideMetadata & {
    type: T;
    content: SlideContent<T>;
    settings: SettingsFor<T>;
    assessment: SlideAssessment<T>;
  }
}[K];

/** Construct explicitly on the server; a type annotation alone does not strip secrets. */
export type ParticipantSlide = {
  [T in SlideType]: Omit<Slide<T>, 'assessment' | 'extensions'>
}[SlideType];

export interface SlidePlugin<K extends SlideType> {
  type: K;
  schemaVersion: number;
  /** Must validate the discriminator, version, content, settings and assessment. */
  parse(input: unknown): Slide<K>;
  createDefault(): Pick<Slide<K>, 'type' | 'schemaVersion' | 'content' | 'settings' | 'assessment'>;
  /** Upgrade supported older JSON before parsing it as the current version. */
  migrate(input: unknown, fromVersion: number): unknown;
}
