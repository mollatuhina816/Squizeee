import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Live Presenter',
  description: 'Present a live Quizeee session with join code, real-time responses and leaderboard.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
