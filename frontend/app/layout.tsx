import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

// Fonts are self-hosted by the `geist` package, so the build works offline.

export const metadata: Metadata = {
  title: "Explain My Error Like I'm Losing My Mind",
  description:
    "An agentic AI debugging assistant: it explains Python errors, fixes them, runs the fix to prove it works, and tells you why it worked.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
