import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import DashboardClient from "@/components/DashboardClient";

/**
 * Dashboard Page — Primary Authenticated Multi-Tenant Application View.
 *
 * Protected route verified by Clerk authentication middleware.
 * Orchestrates multi-tenant Agentic RAG chat, document ingestion, and citations.
 */
export default async function DashboardPage() {
  const user = await currentUser();

  if (!user) {
    redirect("/sign-in");
  }

  return <DashboardClient />;
}
