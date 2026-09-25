"use client";

import React, { useState } from "react";
import { useOrganization, useUser } from "@clerk/nextjs";
import Navbar from "@/components/Navbar";
import StatsCards from "@/components/StatsCards";
import DocumentManager from "@/components/DocumentManager";
import ChatInterface from "@/components/ChatInterface";

export default function DashboardClient() {
  const { user } = useUser();
  const { organization } = useOrganization();
  const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
  const [docCount, setDocCount] = useState<number>(0);
  const [chunkCount, setChunkCount] = useState<number>(0);

  // Multi-tenant resolution: org_id takes precedence, fallback to user personal tenant
  const tenantId = organization?.id || (user?.id ? `user_${user.id}` : "default-tenant");

  const handleDocumentsChange = (count: number, chunks: number) => {
    setDocCount(count);
    setChunkCount(chunks);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-950 text-gray-100 selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Top Navbar */}
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Container */}
      <main className="flex-1 px-4 py-6 sm:px-8 max-w-7xl mx-auto w-full space-y-6">
        {/* Real-time Platform Metric Cards */}
        <StatsCards docCount={docCount} chunkCount={chunkCount} tenantId={tenantId} />

        {/* Tab Content */}
        {activeTab === "chat" ? (
          <section id="view-agentic-chat" className="transition-all animate-in fade-in duration-300">
            <ChatInterface tenantId={tenantId} />
          </section>
        ) : (
          <section id="view-document-manager" className="transition-all animate-in fade-in duration-300">
            <DocumentManager tenantId={tenantId} onDocumentsChange={handleDocumentsChange} />
          </section>
        )}
      </main>
    </div>
  );
}
