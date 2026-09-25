"use client";

import { FileText, Layers, Cpu, ShieldCheck } from "lucide-react";

interface StatsProps {
  docCount: number;
  chunkCount: number;
  tenantId: string;
}

export default function StatsCards({ docCount, chunkCount, tenantId }: StatsProps) {
  const stats = [
    {
      label: "Indexed Documents",
      value: docCount,
      detail: "Isolated per tenant",
      icon: FileText,
      color: "from-blue-500/20 to-indigo-500/20 text-blue-400 border-blue-500/30",
    },
    {
      label: "pgvector Chunks",
      value: chunkCount,
      detail: "1536-dim HNSW indexed",
      icon: Layers,
      color: "from-purple-500/20 to-pink-500/20 text-purple-400 border-purple-500/30",
    },
    {
      label: "Agentic RAG Engine",
      value: "Hybrid + Rerank",
      detail: "Dense + Sparse RRF",
      icon: Cpu,
      color: "from-emerald-500/20 to-teal-500/20 text-emerald-400 border-emerald-500/30",
    },
    {
      label: "Tenant Isolation",
      value: "Active",
      detail: tenantId.length > 16 ? `${tenantId.substring(0, 16)}...` : tenantId,
      icon: ShieldCheck,
      color: "from-amber-500/20 to-orange-500/20 text-amber-400 border-amber-500/30",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((s, idx) => {
        const Icon = s.icon;
        return (
          <div
            key={idx}
            className="group relative overflow-hidden rounded-xl border border-white/[0.08] bg-gray-900/50 p-4 transition-all hover:border-white/[0.16] hover:bg-gray-900/80 hover:shadow-lg hover:shadow-black/40"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400">{s.label}</span>
              <div className={`rounded-lg border bg-gradient-to-br p-1.5 ${s.color}`}>
                <Icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-white">{s.value}</span>
            </div>
            <p className="mt-1 text-[11px] text-gray-400 font-mono">{s.detail}</p>
          </div>
        );
      })}
    </div>
  );
}
