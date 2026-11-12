export type QuizQuestion = {
  kind: string;
  title: string;
  body: string;
  options: string[];
  correct_answers: string[];
  explanation: string;
  marks: string;
  negative_marks: string;
  speed_bonus: string;
  duration_seconds: number;
  minimum: number;
  maximum: number;
  speaker_notes?: string;
  image_url?: string;
  image_alt?: string;
  hotspot_target?: { x: number; y: number; radius: number } | null;
};
