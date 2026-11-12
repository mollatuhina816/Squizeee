import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Presentation Editor',
  description: 'Build and edit interactive quiz presentations, questions and scoring in the Quizeee editor.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
