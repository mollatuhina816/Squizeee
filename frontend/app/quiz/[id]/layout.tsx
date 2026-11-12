import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Assigned Quiz',
  description: 'Take your assigned Quizeee quiz with autosaved answers and a live timer.',
  robots: { index: false, follow: false },
};
export default function QuizLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
