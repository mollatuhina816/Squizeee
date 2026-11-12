import type { Metadata } from 'next';
export const metadata: Metadata = {
  title: 'Join a Live Quiz',
  description: 'Enter your Quiz ID and registered email to join a live Quizeee quiz, answer questions in real time and see the leaderboard.',
  alternates: { canonical: '/join' },
  openGraph: { title: 'Join a Live Quiz · Quizeee', description: 'Enter your Quiz ID to join a live classroom quiz on Quizeee.', url: '/join' },
};
export default function JoinLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
