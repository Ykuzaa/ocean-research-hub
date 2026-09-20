import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Ocean Research Hub — Ocean AI research, structured",
    template: "%s — Ocean Research Hub",
  },
  description:
    "Ocean Research Hub turns Ocean × AI scientific literature into structured, evidence-grounded research intelligence: models, datasets, experiments, and reported limitations, with source evidence and audit status kept visible.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
