import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Autowaarde berekenen & auto's vergelijken | Echte Auto Waarde",
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
      <body className={inter.variable}>{children}</body>
    </html>
  );
}
