"use client";

import React from "react";
import { OrganizationSwitcher, UserButton, useOrganization, useUser } from "@clerk/nextjs";
import { Sparkles, ShieldCheck, Database, BarChart3, Sliders, Cpu } from "lucide-react";

interface NavbarProps {
  activeTab: "chat" | "documents" | "admin";
  setActiveTab: (tab: "chat" | "documents" | "admin") => void;
  onOpenSettings: () => void;
  currentModelName: string;
}

export default function Navbar({
  activeTab,
  setActiveTab,
  onOpenSettings,
  currentModelName,
}: NavbarProps) {
  const { user } = useUser();
  const { organization } = useOrganization();

  const tenantDisplayName = organization?.name || (user?.firstName ? `${user?.firstName}'s Workspace` : "Personal Workspace");

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-white/[0.08] bg-[#030712]/80 backdrop-blur-xl px-4 py-3 sm:px-8">
      {/* Left: Brand & Organization */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/25">
            <Sparkles className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-white text-sm sm:text-base">Enterprise RAG</span>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live
              </span>
            </div>
            <span className="text-[11px] text-gray-400 flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-indigo-400" />
              Tenant: <span className="text-gray-200 font-mono">{tenantDisplayName}</span>
            </span>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <nav className="ml-4 hidden lg:flex items-center rounded-xl border border-white/[0.08] bg-white/[0.02] p-1">
          <button
            id="tab-btn-chat"
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "chat"
                ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/50"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Agentic Chat
          </button>
          <button
            id="tab-btn-documents"
            onClick={() => setActiveTab("documents")}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "documents"
                ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/50"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <Database className="h-3.5 w-3.5" />
            Document Vault
          </button>
          <button
            id="tab-btn-admin"
            onClick={() => setActiveTab("admin")}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "admin"
                ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/50"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Admin Telemetry
          </button>
        </nav>
      </div>

      {/* Right Controls: Model Badge, Settings Modal, Clerk Org & Profile */}
      <div className="flex items-center gap-2.5">
        {/* Model Indicator & Settings Trigger */}
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-gray-300 hover:border-indigo-500/40 hover:bg-white/[0.06] hover:text-white transition-all"
          title="Open Model Selection & BYOK Key Settings"
        >
          <Cpu className="h-3.5 w-3.5 text-indigo-400" />
          <span className="hidden sm:inline font-mono text-[11px] text-gray-300">{currentModelName}</span>
          <Sliders className="h-3.5 w-3.5 text-gray-400" />
        </button>

        {/* Clerk Organization Switcher */}
        <div className="hidden sm:block">
          <OrganizationSwitcher
            afterCreateOrganizationUrl="/dashboard"
            afterLeaveOrganizationUrl="/dashboard"
            afterSelectOrganizationUrl="/dashboard"
            appearance={{
              elements: {
                rootBox: "flex items-center",
                organizationSwitcherTrigger:
                  "border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-gray-300 hover:border-gray-700 hover:text-white rounded-xl",
              },
            }}
          />
        </div>

        {/* User Profile */}
        <UserButton
          appearance={{
            elements: {
              avatarBox: "h-8 w-8 ring-2 ring-indigo-500/30",
            },
          }}
        />
      </div>
    </header>
  );
}
