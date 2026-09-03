import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Autowaarde berekenen & auto's vergelijken | Echte Auto Waarde",
    template: "%s | Echte Auto Waarde",
  },
  description:
    "Ontdek wat een auto écht waard is. Vergelijk soortgelijke auto's op prijs, " +
    "kilometerstand, uitvoering en opties en krijg een transparant prijsadvies.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="nl">
      <body className={`${inter.variable} min-h-screen antialiased`}>
        <a
          href="#inhoud"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-eaw focus:bg-brand focus:px-4 focus:py-2 focus:text-inverted"
        >
          Naar de inhoud
        </a>

        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-base font-semibold tracking-tight text-brand">
                Echte Auto Waarde
              </span>
            </Link>
            <span className="hidden text-sm text-muted sm:block">
              Marktwaarde op basis van vergelijkbare auto&apos;s
            </span>
          </div>
        </header>

        <main id="inhoud">{children}</main>

        <footer className="mt-20 border-t border-line bg-surface">
          <div className="mx-auto max-w-6xl px-5 py-8 text-sm text-muted sm:px-8">
            <p className="font-medium text-ink">Echte Auto Waarde</p>
            <p className="mt-2 max-w-2xl">
              Deze lokale versie werkt met een synthetische demomarkt: de advertenties,
              verkopers en prijzen zijn verzonnen voor ontwikkeling en test. Gebruik de
              uitkomsten niet voor echte aankoopbeslissingen.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
