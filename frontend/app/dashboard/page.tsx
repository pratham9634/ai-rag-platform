import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import DashboardClient from "@/components/DashboardClient";

/**
 * Dashboard Page — Primary Authenticated Multi-Tenant Application View.
 *
 * Protected route verified by Clerk authentication middleware.
 * Orchestrates multi-tenant Agentic RAG chat, document ingestion, and citations.
 */
export default async function DashboardPage() {
  let userId: string | null = null;
  try {
    const session = await auth();
    userId = session?.userId ?? null;
  } catch {
    userId = null;
  }

  if (!userId) {
    redirect("/sign-in");
  }

  return <DashboardClient />;
}
