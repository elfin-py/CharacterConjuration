import './globals.css'

export const metadata = {
  title: 'Character Conjuration',
  description: 'Build 5e characters, NPCs, and enemies in a retro tavern UI.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
