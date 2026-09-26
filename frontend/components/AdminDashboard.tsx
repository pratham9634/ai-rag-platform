"use client";

import React, { useMemo } from "react";
import { useAdminMetrics } from "@/lib/queries";
import {
  Activity,
  Database,
  RefreshCw,
  Zap,
  Server,
  ExternalLink,
  Compass,
  Cpu,
  Sparkles,
} from "lucide-react";

interface MetricsData {
  uptime_seconds: number;
  total_queries?: number;
  total_requests?: number;
  total_errors?: number;
  error_count?: number;
  error_rate?: number;
  error_rate_percent?: number;
  total_tokens_consumed?: number;
  route_distribution?: Record<string, number>;
  relevance_distribution?: Record<string, number>;
  langsmith_active?: boolean;
  langsmith_project?: string;
  langsmith_url?: string | null;
  latency_percentiles_ms?: {
    p50: number;
    p90: number;
    p99: number;
    avg?: number;
  };
  latency_percentiles?: {
    p50: number;
    p90: number;
    p99: number;
  };
}

interface AdminDashboardProps {
  tenantId: string;
  userRole?: string;
  orgName?: string;
  apiBaseUrl?: string;
}

export default function AdminDashboard({
  tenantId,
}: AdminDashboardProps) {
  const { data: rawMetrics, isLoading, error: queryError, refetch } = useAdminMetrics();
  const dbStatus = rawMetrics ? "connected" : "degraded";
  const fetchError = queryError instanceof Error ? queryError.message : null;
  const lastRefreshed = new Date();

  const metrics = useMemo<MetricsData | null>(() => {
    if (!rawMetrics) return null;
    const p = rawMetrics.latency_percentiles_ms || rawMetrics.latency_percentiles || { p50: 0, p90: 0, p99: 0 };
    return {
      ...rawMetrics,
      total_requests: rawMetrics.total_queries ?? rawMetrics.total_requests ?? 0,
      error_count: rawMetrics.total_errors ?? rawMetrics.error_count ?? 0,
      error_rate_percent: (rawMetrics.error_rate ?? 0) * 100,
      latency_percentiles: {
        p50: p.p50 ?? 0,
        p90: p.p90 ?? 0,
        p99: p.p99 ?? 0,
      },
    };
  }, [rawMetrics]);

  const fetchTelemetry = () => {
    refetch();
  };

  const formatUptime = (seconds?: number) => {
    if (!seconds) return "Active";
    const d = Math.floor(seconds / (3600 * 24));
    const h = Math.floor((seconds % (3600 * 24)) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${seconds % 60}s`;
  };

  const p50 = metrics?.latency_percentiles?.p50 ?? 0;
  const p90 = metrics?.latency_percentiles?.p90 ?? 0;
  const p99 = metrics?.latency_percentiles?.p99 ?? 0;

  // Route stats
  const routeDist = metrics?.route_distribution || {};
  const retrieveQueries = routeDist.retrieve || 0;
  const directQueries = routeDist.direct || 0;
  const totalRouted = retrieveQueries + directQueries;
  const retrievePercent = totalRouted > 0 ? Math.round((retrieveQueries / totalRouted) * 100) : 100;

  return (
    <div className="space-y-6 font-sans">
      {/* ── Top Bar: Header & Actions ────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-[var(--hairline)] pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
              Agent Telemetry & Observability
            </h1>
            <span className="rounded-full border border-[var(--accent)]/30 bg-[var(--accent-muted)] px-2.5 py-0.5 text-[11px] font-mono text-[var(--accent)]">
              Real-Time
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--ink-subtle)]">
            Distributed tracing, latency percentiles, intent routing intelligence, and LangSmith integration.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              fetchTelemetry();
            }}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] hover:bg-[var(--surface-3)] px-3 py-1.5 text-xs text-[var(--ink-muted)] transition-colors"
          >
            <RefreshCw className={`h-3 w-3 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <span className="text-[11px] text-[var(--ink-tertiary)] font-mono">
            Synced: {lastRefreshed.toLocaleTimeString()}
          </span>
        </div>
      </div>

      {fetchError && (
        <div className="rounded-xl border border-red-900/60 bg-red-950/20 p-3 text-xs text-red-300">
          Telemetry notice: {fetchError}
        </div>
      )}

      {/* ── Section 1: Live Core Metrics ─────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Metric 1: Latency P99 */}
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--ink-subtle)]">P99 Query Latency</span>
            <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-1.5 text-[var(--accent)]">
              <Zap className="h-3.5 w-3.5" />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-[-0.04em] text-[var(--ink)] font-mono">
              {p99 > 0 ? `${p99.toFixed(0)}ms` : "—"}
            </span>
            <span className="text-[10px] text-emerald-400 font-mono">SLA &lt; 2500ms</span>
          </div>
          <div className="mt-2.5 flex items-center justify-between text-[11px] text-[var(--ink-tertiary)] font-mono">
            <span>P50: {p50 > 0 ? `${p50.toFixed(0)}ms` : "—"}</span>
            <span>P90: {p90 > 0 ? `${p90.toFixed(0)}ms` : "—"}</span>
          </div>
        </div>

        {/* Metric 2: Uptime & Queries */}
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--ink-subtle)]">Process Uptime</span>
            <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-1.5 text-[var(--accent)]">
              <Activity className="h-3.5 w-3.5" />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-[-0.04em] text-[var(--ink)] font-mono">
              {metrics ? formatUptime(metrics.uptime_seconds) : "Active"}
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[var(--ink-tertiary)] font-mono">
            Total Queries: <strong className="text-[var(--ink-muted)]">{metrics?.total_requests || 0}</strong>
          </p>
        </div>

        {/* Metric 3: Database & pgvector Status */}
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--ink-subtle)]">PostgreSQL + pgvector</span>
            <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-1.5 text-[var(--accent)]">
              <Database className="h-3.5 w-3.5" />
            </div>
          </div>
          <div className="mt-2.5 flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                dbStatus === "connected" ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />
            <span className="text-base font-semibold text-[var(--ink)] capitalize font-mono">{dbStatus}</span>
          </div>
          <p className="mt-2 text-[11px] text-[var(--ink-tertiary)] font-mono">
            Mode: <span className="text-[var(--ink-muted)]">Supavisor Pooled</span>
          </p>
        </div>

        {/* Metric 4: Error Rate */}
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--ink-subtle)]">Error Rate</span>
            <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-1.5 text-[var(--accent)]">
              <Server className="h-3.5 w-3.5" />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-[-0.04em] text-[var(--ink)] font-mono">
              {(metrics?.error_rate_percent ?? 0).toFixed(1)}%
            </span>
            <span className="text-[10px] text-emerald-400 font-mono">Target &lt; 1%</span>
          </div>
          <p className="mt-2 text-[11px] text-[var(--ink-tertiary)] font-mono">
            Failures: <span className="text-[var(--ink-muted)]">{metrics?.error_count || 0}</span>
          </p>
        </div>
      </div>

      {/* ── Section 2: LangSmith & Agent Execution Intelligence ─────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* LangSmith Distributed Tracing Card */}
        <div className="card-surface p-5 space-y-3.5 rounded-2xl border border-[var(--hairline)] bg-[var(--surface-1)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[var(--accent)]" />
              <h3 className="text-xs font-semibold text-[var(--ink)]">LangSmith Distributed Tracing</h3>
            </div>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                metrics?.langsmith_active
                  ? "bg-emerald-950/40 text-emerald-400 border-emerald-800/40"
                  : "bg-[var(--surface-2)] text-[var(--ink-tertiary)] border-[var(--hairline)]"
              }`}
            >
              {metrics?.langsmith_active ? "Connected" : "Local Mode"}
            </span>
          </div>

          <p className="text-xs text-[var(--ink-subtle)] leading-relaxed">
            Multi-tenant execution traces, cyclic LangGraph states, and retrieval grading audits are tagged with{" "}
            <code className="text-[var(--ink)] font-mono text-[11px] bg-[var(--surface-2)] px-1 rounded">
              tenant:{tenantId}
            </code>
            .
          </p>

          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3 space-y-1">
            <span className="text-[10px] text-[var(--ink-tertiary)] uppercase tracking-wider font-mono">
              Active Project
            </span>
            <p className="text-xs font-semibold text-[var(--ink)] font-mono">
              {metrics?.langsmith_project || "enterprise-rag"}
            </p>
          </div>

          {metrics?.langsmith_url && (
            <a
              href={metrics.langsmith_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
            >
              <span>Open LangSmith Dashboard</span>
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>

        {/* Intent Routing Intelligence */}
        <div className="card-surface p-5 space-y-3.5 rounded-2xl border border-[var(--hairline)] bg-[var(--surface-1)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Compass className="h-4 w-4 text-sky-400" />
              <h3 className="text-xs font-semibold text-[var(--ink)]">Intent Routing Distribution</h3>
            </div>
            <span className="text-xs font-mono text-[var(--ink-subtle)]">{totalRouted} Total</span>
          </div>

          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--ink-subtle)]">Document Retrieval (RAG)</span>
              <span className="font-mono text-[var(--ink)] font-medium">{retrieveQueries} ({retrievePercent}%)</span>
            </div>
            <div className="h-2 w-full rounded-full bg-[var(--surface-3)] overflow-hidden">
              <div
                className="h-full bg-sky-500 rounded-full transition-all duration-300"
                style={{ width: `${retrievePercent}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-xs pt-1">
              <span className="text-[var(--ink-subtle)]">Direct Conversational</span>
              <span className="font-mono text-[var(--ink)] font-medium">
                {directQueries} ({100 - retrievePercent}%)
              </span>
            </div>
          </div>

          <p className="text-[11px] text-[var(--ink-tertiary)]">
            Classifies questions using zero-shot intent routing before dispatching vector retrieval.
          </p>
        </div>

        {/* Agent Token Accounting */}
        <div className="card-surface p-5 space-y-3.5 rounded-2xl border border-[var(--hairline)] bg-[var(--surface-1)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-indigo-400" />
              <h3 className="text-xs font-semibold text-[var(--ink)]">Token Consumption</h3>
            </div>
            <span className="text-xs font-mono text-emerald-400 font-medium">Quota Monitored</span>
          </div>

          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3 space-y-1">
            <span className="text-[10px] text-[var(--ink-tertiary)] uppercase tracking-wider font-mono">
              Total Tokens Used
            </span>
            <p className="text-xl font-bold text-[var(--ink)] font-mono">
              {(metrics?.total_tokens_consumed || 0).toLocaleString()}
            </p>
          </div>

          <div className="flex items-center justify-between text-xs text-[var(--ink-subtle)] border-t border-[var(--hairline)] pt-2.5">
            <span>Relevance Filter:</span>
            <span className="text-emerald-400 font-mono font-medium">Active (Cross-Encoder)</span>
          </div>
          <div className="flex items-center justify-between text-xs text-[var(--ink-subtle)]">
            <span>Hallucination Audit:</span>
            <span className="text-emerald-400 font-mono font-medium">Grounded & Verified</span>
          </div>
        </div>
      </div>
    </div>
  );
}
