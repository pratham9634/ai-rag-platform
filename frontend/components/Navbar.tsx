"use client";

import { OrganizationSwitcher, UserButton, useOrganization, useUser } from "@clerk/nextjs";
import { Sparkles, ShieldCheck, Database } from "lucide-react";

interface NavbarProps {
  activeTab: "chat" | "documents";
  setActiveTab: (tab: "chat" | "documents") => void;
}

export default function Navbar({ activeTab, setActiveTab }: NavbarProps) {
  const { user } = useUser();
  const { organization } = useOrganization();

  const tenantDisplayName = organization?.name || user?.firstName ? `${user?.firstName}'s Workspace` : "Personal Workspace";

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-white/[0.08] bg-gray-950/80 backdrop-blur-xl px-6 py-3.5">
      {/* Brand & Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/25">
            <Sparkles className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-white">Enterprise RAG</span>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
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
        <nav className="ml-6 hidden md:flex items-center rounded-lg border border-white/[0.06] bg-gray-900/60 p-1">
          <button
            id="tab-btn-chat"
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-2 rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
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
            className={`flex items-center gap-2 rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "documents"
                ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/50"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <Database className="h-3.5 w-3.5" />
            Documents & Ingestion
          </button>
        </nav>
      </div>

      {/* Right Controls: Clerk Org Switcher & User Profile */}
      <div className="flex items-center gap-3">
        <div className="hidden sm:block">
          <OrganizationSwitcher
            afterCreateOrganizationUrl="/dashboard"
            afterLeaveOrganizationUrl="/dashboard"
            afterSelectOrganizationUrl="/dashboard"
            appearance={{
              elements: {
                rootBox: "flex items-center",
                organizationSwitcherTrigger:
                  "border border-white/[0.08] bg-gray-900/80 px-3 py-1.5 text-xs text-gray-300 hover:border-gray-700 hover:text-white rounded-lg",
              },
            }}
          />
        </div>
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
