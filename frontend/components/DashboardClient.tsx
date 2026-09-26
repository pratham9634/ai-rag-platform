"use client";

import React, { useState, useEffect } from "react";
import { useOrganization, useUser } from "@clerk/nextjs";
import Navbar from "@/components/Navbar";
import StatsCards from "@/components/StatsCards";
import DocumentManager from "@/components/DocumentManager";
import ChatInterface from "@/components/ChatInterface";
import AdminDashboard from "@/components/AdminDashboard";
import SettingsModal, { SystemSettings } from "@/components/SettingsModal";

const DEFAULT_SETTINGS: SystemSettings = {
  model: "anthropic/claude-3.5-sonnet",
  byokKey: "",
  topK: 5,
  enableWebSearch: true,
};

export default function DashboardClient() {
  const { user } = useUser();
  const { organization } = useOrganization();
  const [activeTab, setActiveTab] = useState<"chat" | "documents" | "admin">("chat");
  const [docCount, setDocCount] = useState<number>(0);
  const [chunkCount, setChunkCount] = useState<number>(0);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [settings, setSettings] = useState<SystemSettings>(DEFAULT_SETTINGS);

  // Multi-tenant resolution: org_id takes precedence, fallback to user personal tenant
  const tenantId = organization?.id || (user?.id ? `user_${user.id}` : "default-tenant");
  const orgDisplayName = organization?.name || (user?.firstName ? `${user.firstName}'s Workspace` : "Personal Workspace");

  // Load persistent user settings from storage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("enterprise_rag_settings");
      const byok = sessionStorage.getItem("enterprise_rag_byok") || "";
      if (saved) {
        const parsed = JSON.parse(saved);
        setSettings((prev) => ({
          ...prev,
          ...parsed,
          byokKey: byok,
        }));
      } else if (byok) {
        setSettings((prev) => ({ ...prev, byokKey: byok }));
      }
    } catch {
      // Fallback to default
    }
  }, []);

  const handleSaveSettings = (newSettings: SystemSettings) => {
    setSettings(newSettings);
    try {
      if (newSettings.byokKey) {
        sessionStorage.setItem("enterprise_rag_byok", newSettings.byokKey);
      } else {
        sessionStorage.removeItem("enterprise_rag_byok");
      }
      const persistable = {
        model: newSettings.model,
        topK: newSettings.topK,
        enableWebSearch: newSettings.enableWebSearch,
      };
      localStorage.setItem("enterprise_rag_settings", JSON.stringify(persistable));
    } catch {
      // Ignore storage errors
    }
  };

  const getModelDisplayName = (modelId: string) => {
    if (modelId.includes("claude-3.5-sonnet")) return "Claude 3.5 Sonnet";
    if (modelId.includes("gpt-4o-mini")) return "GPT-4o Mini";
    if (modelId.includes("llama-3.1-8b")) return "Llama 3.1 8B Free";
    if (modelId.includes("mistral-7b")) return "Mistral 7B Free";
    return modelId.split("/")[1] || modelId;
  };

  const handleDocumentsChange = (count: number, chunks: number) => {
    setDocCount(count);
    setChunkCount(chunks);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#030712] text-gray-100 selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Top Navigation Bar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenSettings={() => setIsSettingsOpen(true)}
        currentModelName={getModelDisplayName(settings.model)}
      />

      {/* Main Workspace Container */}
      <main className="flex-1 px-4 py-6 sm:px-8 max-w-7xl mx-auto w-full space-y-6">
        {/* Top Metric Cards - shown on Chat and Documents tabs */}
        {activeTab !== "admin" && (
          <StatsCards docCount={docCount} chunkCount={chunkCount} tenantId={tenantId} />
        )}

        {/* Tab Viewport */}
        {activeTab === "chat" && (
          <section id="view-agentic-chat" className="transition-all animate-in fade-in duration-200">
            <ChatInterface tenantId={tenantId} settings={settings} />
          </section>
        )}

        {activeTab === "documents" && (
          <section id="view-document-manager" className="transition-all animate-in fade-in duration-200">
            <DocumentManager tenantId={tenantId} onDocumentsChange={handleDocumentsChange} />
          </section>
        )}

        {activeTab === "admin" && (
          <section id="view-admin-dashboard" className="transition-all animate-in fade-in duration-200">
            <AdminDashboard
              tenantId={tenantId}
              userRole={organization ? "Org Admin" : "Workspace Owner"}
              orgName={orgDisplayName}
              apiBaseUrl={process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
            />
          </section>
        )}
      </main>

      {/* Global Settings & BYOK Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSave={handleSaveSettings}
      />
    </div>
  );
}
