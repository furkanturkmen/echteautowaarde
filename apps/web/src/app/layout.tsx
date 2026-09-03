import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Sans_Condensed } from "next/font/google";
import Link from "next/link";

import { BrandLockup } from "@/components/BrandMark";
import "./globals.css";

// Downloaded and self-hosted at build time, so the running application needs no
// external font request and keeps working offline.
const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

// Condensed carries the license plate, where character width matters.
const plexCondensed = IBM_Plex_Sans_Condensed({
  variable: "--font-plex-condensed",
  subsets: ["latin"],
  weight: ["600", "700"],
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
      <body className={`${plexSans.variable} ${plexCondensed.variable} min-h-screen antialiased`}>
        <a
          href="#inhoud"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-eaw focus:bg-brand focus:px-4 focus:py-2 focus:text-inverted"
        >
          Naar de inhoud
        </a>

        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
            <Link href="/" aria-label="Echte Auto Waarde — naar de startpagina">
              <BrandLockup />
            </Link>
            <span className="hidden text-sm text-muted sm:block">
              Marktwaarde op basis van vergelijkbare auto&apos;s
            </span>
          </div>
        </header>

        <main id="inhoud">{children}</main>

        <footer className="mt-20 border-t border-line bg-surface">
          <div className="mx-auto max-w-6xl px-5 py-8 text-sm text-muted sm:px-8">
            <BrandLockup withPayoff />
            <p className="mt-4 max-w-2xl">
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
