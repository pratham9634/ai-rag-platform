"use client";

import React from "react";
import { OrganizationSwitcher, UserButton, useOrganization, useUser } from "@clerk/nextjs";
import { Terminal, Shield, Database, BarChart2, MessageSquare } from "lucide-react";

interface NavbarProps {
  activeTab: "chat" | "documents" | "admin";
  setActiveTab: (tab: "chat" | "documents" | "admin") => void;
}

export default function Navbar({
  activeTab,
  setActiveTab,
}: NavbarProps) {
  const { user } = useUser();
  const { organization } = useOrganization();

  const tenantDisplayName =
    organization?.name || (user?.firstName ? `${user.firstName}'s Workspace` : "Personal Workspace");

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-[var(--hairline)] bg-[var(--canvas)]/95 backdrop-blur-xl px-3 sm:px-6 py-2.5">
      {/* Left: Brand Mark & Responsive View Switcher */}
      <div className="flex items-center gap-2 sm:gap-5">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent)] text-white shadow-sm shrink-0">
            <Terminal className="h-4 w-4" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-[-0.02em] text-[var(--ink)] text-sm hidden sm:inline">
              Enterprise RAG
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-800/50 bg-[var(--success-muted)] px-2 py-0.5 text-[10px] font-mono text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-subtle-pulse" />
              Live
            </span>
          </div>
        </div>

        {/* View Switcher Tabs — Responsive pill navigation */}
        <nav className="flex items-center rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--surface-1)] p-0.5 sm:p-1">
          {[
            { id: "chat" as const, icon: MessageSquare, label: "Agent Chat" },
            { id: "documents" as const, icon: Database, label: "Documents" },
            { id: "admin" as const, icon: BarChart2, label: "Telemetry" },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`tab-btn-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 sm:gap-2 rounded-[var(--radius-md)] px-2 sm:px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
                  isActive
                    ? "bg-[var(--accent)] text-white shadow-sm"
                    : "text-[var(--ink-subtle)] hover:text-[var(--ink-muted)] hover:bg-[var(--surface-2)]"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Right Controls: Tenant Indicator & Clerk Auth */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Tenant Indicator */}
        <div className="hidden md:flex items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--surface-1)] px-2.5 py-1 text-[11px] text-[var(--ink-subtle)]">
          <Shield className="h-3 w-3 text-[var(--accent)]" />
          <span className="max-w-[120px] truncate text-[var(--ink-muted)] font-mono">{tenantDisplayName}</span>
        </div>

        {/* Clerk Org Switcher & User Profile */}
        <div className="flex items-center gap-1.5 sm:gap-2 border-l border-[var(--hairline)] pl-2 sm:pl-3">
          <OrganizationSwitcher
            appearance={{
              elements: {
                rootBox: "flex items-center",
                organizationSwitcherTrigger:
                  "text-xs text-[var(--ink-muted)] hover:text-[var(--ink)] bg-[var(--surface-1)] border border-[var(--hairline)] rounded-[var(--radius-md)] px-2 sm:px-2.5 py-1 transition-all",
              },
            }}
          />
          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-7 w-7 rounded-[var(--radius-md)] ring-1 ring-[var(--hairline-strong)]",
              },
            }}
          />
        </div>
      </div>
    </header>
  );
}
