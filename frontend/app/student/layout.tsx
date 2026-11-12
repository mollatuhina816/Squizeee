import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'My Learning Hub',
  description: 'Your Quizeee student dashboard: assigned quizzes, scores, achievements and progress in one place.',
  alternates: { canonical: '/student' },
  robots: { index: false, follow: true },
};
export default function StudentLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
