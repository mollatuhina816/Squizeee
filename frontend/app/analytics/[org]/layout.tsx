import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Session Analytics',
  description: 'Review session results, question insights and student performance in Quizeee analytics.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
