import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tagsmith",
  description: "Review and approve Gmail taxonomy labels",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top">
          <strong>Tagsmith</strong>
          <span className="muted">review dashboard · sign-in optional for local review</span>
          <a
            className="link"
            href={`${process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8080"}/auth/debug`}
            target="_blank"
            rel="noreferrer"
          >
            Auth debug
          </a>
          <a
            className="link"
            href={`${process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8080"}/auth/login`}
          >
            Sign in with Google
          </a>
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
