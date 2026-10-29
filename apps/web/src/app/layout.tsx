import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: "AI Film Studio",
  description: "Local AI film production studio — Seedance via BytePlus ModelArk",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="flex min-h-screen">
          <Nav />
          <main className="flex-1 ml-56 p-6 max-w-6xl">{children}</main>
        </div>
      </body>
    </html>
  );
}
