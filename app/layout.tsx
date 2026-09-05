import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Local Prompt Studio',
  description: 'Create images, audio, video, presentations and Markdown using local CLI tools.',
};

export const dynamic = 'force-static';

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
