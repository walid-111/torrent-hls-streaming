import type { Metadata } from 'next'
import './globals.css'
import Nav from './components/Nav'

export const metadata: Metadata = {
  title: 'Hypertube',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <header className="flex justify-between items-center px-6 py-4 border-b"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
          <a href="/library" className="text-xl font-bold">Hypertube</a>
          <Nav />
        </header>
        <main className="flex-1">{children}</main>
        <footer className="text-center p-4 text-sm muted border-t"
          style={{ borderColor: 'var(--border)' }}>
          Hypertube by Matteo & Walid
        </footer>
      </body>
    </html>
  )
}