"use client";

import React, { useMemo, useCallback } from "react";
import { useOrganization, useUser } from "@clerk/nextjs";
import Navbar from "@/components/Navbar";
import DocumentManager from "@/components/DocumentManager";
import ChatInterface from "@/components/ChatInterface";
import AdminDashboard from "@/components/AdminDashboard";
import SettingsModal, { SystemSettings } from "@/components/SettingsModal";
import { useAppStore } from "@/lib/store";

export default function DashboardClient() {
  const { user } = useUser();
  const { organization } = useOrganization();

  // Zustand persistent UI state
  const activeTab = useAppStore((state) => state.activeTab);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const isSettingsOpen = useAppStore((state) => state.isSettingsOpen);
  const setIsSettingsOpen = useAppStore((state) => state.setIsSettingsOpen);
  const settings = useAppStore((state) => state.settings);
  const setAllSettings = useAppStore((state) => state.setAllSettings);

  // Normalize tenantId across Clerk personal and organization accounts
  const tenantId = useMemo(() => {
    if (organization?.id) return organization.id;
    if (user?.id) return user.id;
    return "default-tenant";
  }, [organization?.id, user?.id]);

  const orgDisplayName =
    organization?.name || (user?.firstName ? `${user.firstName}'s Workspace` : "Personal Workspace");

  const handleSaveSettings = useCallback((newSettings: SystemSettings) => {
    setAllSettings(newSettings);
    try {
      if (newSettings.byokKey) {
        sessionStorage.setItem("enterprise_rag_byok", newSettings.byokKey);
      } else {
        sessionStorage.removeItem("enterprise_rag_byok");
      }
    } catch {
      // Ignore sessionStorage errors
    }
  }, [setAllSettings]);

  return (
    <div className="min-h-screen flex flex-col dashboard-canvas text-[var(--ink)] selection:bg-[var(--surface-3)] selection:text-white">
      {/* Top Navigation Bar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* Main Workspace Container */}
      <main className="flex-1 px-4 py-5 sm:px-6 max-w-7xl mx-auto w-full space-y-5">
        {/* Tab Viewports: Preserved in DOM to prevent unmounting & state destruction on tab switch */}
        <section
          id="view-agentic-chat"
          className={activeTab === "chat" ? "block transition-all animate-in fade-in duration-150" : "hidden"}
        >
          <ChatInterface tenantId={tenantId} settings={settings} />
        </section>

        <section
          id="view-document-manager"
          className={activeTab === "documents" ? "block transition-all animate-in fade-in duration-150" : "hidden"}
        >
          <DocumentManager tenantId={tenantId} />
        </section>

        <section
          id="view-admin-dashboard"
          className={activeTab === "admin" ? "block transition-all animate-in fade-in duration-150" : "hidden"}
        >
          <AdminDashboard
            tenantId={tenantId}
            userRole={organization ? "Org Admin" : "Workspace Owner"}
            orgName={orgDisplayName}
            apiBaseUrl={process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
          />
        </section>
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
