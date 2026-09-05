import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scalping Bot | Foundation",
  description: "Paper-trading monitoring foundation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
