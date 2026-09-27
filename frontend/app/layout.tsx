import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Inter } from "next/font/google";
import "./globals.css";
import QueryProvider from "@/components/QueryProvider";

/**
 * Using Inter font — clean, modern, widely used in SaaS products.
 * Loaded from Google Fonts via next/font (automatic optimization).
 */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Enterprise RAG Platform",
  description:
    "Multi-tenant Agentic RAG platform with hybrid retrieval, reranking, and BYOK support.",
};

/**
 * Root Layout — wraps the entire application.
 *
 * ClerkProvider:
 *   - Makes Clerk authentication available to all pages
 *   - Handles session management automatically
 *   - Provides useUser(), useAuth(), useOrganization() hooks
 *   - Reads NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY from env
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="en" className={`${inter.variable} h-full antialiased`}>
        <body className="min-h-full flex flex-col bg-[var(--canvas)] text-[var(--ink)] font-[family-name:var(--font-inter)]">
          <QueryProvider>
            {children}
          </QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
