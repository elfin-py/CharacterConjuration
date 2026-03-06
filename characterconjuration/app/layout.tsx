import './globals.css'

export const metadata = {
  title: 'Character Conjuration',
  description: 'Build 5e characters, NPCs, and enemies in a retro tavern UI.',
  icons: {
    icon: '/logo.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css"
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
