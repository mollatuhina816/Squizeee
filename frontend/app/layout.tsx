import type { Metadata, Viewport } from 'next';
import './globals.css';
import './student-quiz.css';
import './design-system.css';
import './student-pro.css';
import './student-dashboard.css';
import './student-titles.css';
import './teacher-pro.css';
// import './teacher.css';
import VisualRuntime from './visual-runtime';
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'),
  title: { default: 'Quizeee · Teaching workspace', template: '%s · Quizeee' },
  description: 'Quizeee is an interactive teaching workspace to build presentations and quizzes, run live sessions, manage a question bank and analyse student results.',
  applicationName: 'Quizeee',
  keywords: ['online quiz', 'live quiz', 'student quiz', 'classroom quiz', 'learning platform', 'Quizeee'],
  openGraph: { type: 'website', siteName: 'Quizeee', images: [{ url: '/images/og-student.svg', width: 1200, height: 630, alt: 'Quizeee' }] },
  twitter: { card: 'summary_large_image', images: ['/images/og-student.svg'] },
  robots: { index: true, follow: true },
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#1d4ed8' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body><VisualRuntime/>{children}</body></html>;
}
