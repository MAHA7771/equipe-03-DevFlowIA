import "./globals.css";
import Link from "next/link";

export const metadata = { title: "DevFlow AI", description: "De l'e-mail du PO à la Pull Request" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <header className="nav">
          <Link href="/" className="brand">DevFlow AI</Link>
          <nav>
            <Link href="/projects">Projets</Link>
            <Link href="/repository">Repository</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}