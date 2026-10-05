import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Quizeee · Teaching workspace', description: 'Your interactive teaching workspace' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
