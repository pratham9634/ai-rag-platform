"use client";

import React from "react";
import { FileText, Layers, Cpu, ShieldCheck } from "lucide-react";

interface StatsProps {
  docCount: number;
  chunkCount: number;
  tenantId?: string;
}

export default function StatsCards({ docCount, chunkCount }: StatsProps) {
  const stats = [
    {
      label: "Indexed Documents",
      value: docCount,
      detail: "Ready for search",
      icon: FileText,
    },
    {
      label: "Knowledge Chunks",
      value: chunkCount,
      detail: "Indexed text sections",
      icon: Layers,
    },
    {
      label: "Search Engine",
      value: "Hybrid RAG",
      detail: "Semantic & keyword match",
      icon: Cpu,
    },
    {
      label: "Data Isolation",
      value: "Active",
      detail: "Workspace protected",
      icon: ShieldCheck,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((s, idx) => {
        const Icon = s.icon;
        return (
          <div
            key={idx}
            className="metric-card group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--ink-subtle)] tracking-[-0.01em]">{s.label}</span>
              <div className="rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--surface-2)] p-1.5 text-[var(--accent)] group-hover:border-[var(--hairline-strong)] transition-colors">
                <Icon className="h-3.5 w-3.5" />
              </div>
            </div>
            <div className="mt-2.5 flex items-baseline gap-2">
              <span className="text-xl font-semibold tracking-[-0.03em] text-[var(--ink)] font-mono">{s.value}</span>
            </div>
            <p className="mt-1 text-[11px] text-[var(--ink-tertiary)] font-mono">{s.detail}</p>
          </div>
        );
      })}
    </div>
  );
}
