import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Question Bank',
  description: 'Search, filter and reuse questions from your Quizeee question bank.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
