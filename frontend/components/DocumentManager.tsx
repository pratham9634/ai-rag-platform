"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  UploadCloud,
  FileText,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  RefreshCw,
  HardDrive,
  Layers,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";

export interface DocumentItem {
  id: string;
  tenant_id: string;
  filename: string;
  file_size: number;
  status: string;
  total_chunks?: number;
  chunk_count?: number;
  created_at?: string;
  expires_at?: string;
  error_message?: string | null;
}

export interface TenantUsage {
  tenant_id: string;
  document_count: number;
  max_documents: number;
  storage_bytes: number;
  max_storage_bytes: number;
  storage_mb: number;
  max_storage_mb: number;
  chunk_count: number;
  max_chunks: number;
  retention_days: number;
  oldest_document_expires_at?: string | null;
}

import {
  useTenantUsage,
  useDocuments,
  useDeleteDocumentMutation,
  queryKeys,
} from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

interface DocumentManagerProps {
  tenantId: string;
  onDocumentsChange?: (count: number, chunkCount: number) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DocumentManager({ tenantId, onDocumentsChange }: DocumentManagerProps) {
  const queryClient = useQueryClient();
  const {
    data: usage,
    refetch: fetchUsage,
  } = useTenantUsage(tenantId);

  const {
    data: documents = [],
    isLoading: loading,
    isFetching: isRefreshing,
    refetch: fetchDocuments,
  } = useDocuments(tenantId);

  const deleteMutation = useDeleteDocumentMutation(tenantId);

  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadStatusText, setUploadStatusText] = useState<string>("Processing Document...");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isDuplicateNotice, setIsDuplicateNotice] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync parent counter callback if provided
  useEffect(() => {
    if (documents && onDocumentsChange) {
      const totalChunks = documents.reduce(
        (sum, d) => sum + (d.total_chunks || d.chunk_count || 0),
        0
      );
      onDocumentsChange(documents.length, totalChunks);
    }
  }, [documents, onDocumentsChange]);

  const handleFileUpload = async (file: File) => {
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only standard PDF documents (.pdf) are supported.");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setUploadError("Document size exceeds maximum 10MB limit.");
      return;
    }

    // Pre-flight quota check
    if (usage && usage.document_count >= usage.max_documents) {
      setUploadError(
        `Workspace document quota reached (${usage.max_documents}/${usage.max_documents} PDFs). Please delete an older file.`
      );
      return;
    }

    setUploadError(null);
    setUploadSuccess(null);
    setIsDuplicateNotice(false);
    setUploading(true);
    setUploadStatusText("Validating & uploading document...");

    // Optimistic UI insert: Immediately show processing item in table in 0ms!
    const tempId = `temp-${Date.now()}`;
    const optimisticDoc: DocumentItem = {
      id: tempId,
      tenant_id: tenantId,
      filename: file.name,
      file_size: file.size,
      status: "PROCESSING",
      created_at: new Date().toISOString(),
    };
    queryClient.setQueryData<DocumentItem[]>(queryKeys.documents(tenantId), (prev) => [
      optimisticDoc,
      ...(prev || []),
    ]);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload`, {
        method: "POST",
        headers: {
          "X-Tenant-ID": tenantId,
        },
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: "Upload failed." }));
        // Revert optimistic insert on rejection
        queryClient.setQueryData<DocumentItem[]>(queryKeys.documents(tenantId), (prev) =>
          (prev || []).filter((d) => d.id !== tempId)
        );
        throw new Error(errData.detail || "Upload failed.");
      }

      const result = await res.json();

      if (result.is_duplicate) {
        setIsDuplicateNotice(true);
        setUploadSuccess(`"${result.filename}" is already indexed.`);
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(tenantId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.tenantUsage(tenantId) });
        setUploading(false);
        return;
      }

      const docId = result.document_id;
      setUploadStatusText("Extracting and indexing text sections...");

      // Fast-Phase Polling: Poll every 500ms for sub-second completion
      let attempts = 0;
      const maxAttempts = 30;
      const pollInterval = setInterval(async () => {
        attempts++;
        try {
          const statusRes = await fetch(`${API_BASE}/api/documents/${docId}/status`, {
            headers: { "X-Tenant-ID": tenantId },
          });
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (statusData.status === "READY") {
              clearInterval(pollInterval);
              setUploadSuccess(
                `Successfully indexed "${statusData.filename}" (${statusData.total_chunks || 0} chunks).`
              );
              setUploading(false);
              queryClient.invalidateQueries({ queryKey: queryKeys.documents(tenantId) });
              queryClient.invalidateQueries({ queryKey: queryKeys.tenantUsage(tenantId) });
              return;
            } else if (statusData.status === "FAILED") {
              clearInterval(pollInterval);
              setUploadError(`Ingestion failed: ${statusData.error_message || "Unknown error"}`);
              setUploading(false);
              queryClient.invalidateQueries({ queryKey: queryKeys.documents(tenantId) });
              queryClient.invalidateQueries({ queryKey: queryKeys.tenantUsage(tenantId) });
              return;
            }
          }
        } catch {
          // Continue polling
        }

        if (attempts >= maxAttempts) {
          clearInterval(pollInterval);
          setUploadSuccess("Document queued. Indexing will complete in background.");
          setUploading(false);
          queryClient.invalidateQueries({ queryKey: queryKeys.documents(tenantId) });
          queryClient.invalidateQueries({ queryKey: queryKeys.tenantUsage(tenantId) });
        }
      }, 500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload document.";
      setUploadError(msg);
      setUploading(false);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Permanently remove "${filename}"? All associated indexed chunks will be purged.`)) {
      return;
    }
    deleteMutation.mutate(docId);
  };

  const formatBytes = (bytes: number) => {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Quota percentages
  const docPercent = usage ? Math.min(100, Math.round((usage.document_count / usage.max_documents) * 100)) : 0;
  const storagePercent = usage
    ? Math.min(100, Math.round((usage.storage_bytes / usage.max_storage_bytes) * 100))
    : 0;
  const chunkPercent = usage ? Math.min(100, Math.round((usage.chunk_count / usage.max_chunks) * 100)) : 0;
  const isAtQuota = usage ? usage.document_count >= usage.max_documents : false;

  return (
    <div className="space-y-5 font-sans">
      {/* ── 1. Workspace Document Vault Quota & 7-Day Lifecycle Header ── */}
      <div className="card-surface p-5 sm:p-6 bg-[var(--surface-1)] border border-[var(--hairline)] rounded-2xl shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--hairline)] pb-4">
          <div>
            <h2 className="text-sm font-semibold text-[var(--ink)] tracking-[-0.01em]">
              Workspace Document Vault
            </h2>
            <p className="text-xs text-[var(--ink-subtle)] mt-0.5">
              Personalized knowledge storage with strict tenant isolation and rolling 7-day retention.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--hairline)] bg-[var(--surface-2)] px-2.5 py-1 text-[11px] font-mono text-[var(--ink-muted)]">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              Tenant Protected
            </span>
            <button
              onClick={() => {
                fetchDocuments();
                fetchUsage();
              }}
              title="Refresh quota"
              className="p-1.5 text-[var(--ink-tertiary)] hover:text-[var(--ink)] rounded-lg hover:bg-[var(--surface-2)] transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {/* 4 Clean Visual SaaS Quota Meters */}
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Documents Quota */}
          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--ink-subtle)] font-medium flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 text-[var(--accent)]" />
                Documents
              </span>
              <span className="text-xs font-semibold text-[var(--ink)] font-mono">
                {usage?.document_count ?? documents.length} / {usage?.max_documents ?? 10}
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[var(--surface-3)] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  docPercent >= 90 ? "bg-rose-500" : docPercent >= 70 ? "bg-amber-400" : "bg-[var(--accent)]"
                }`}
                style={{ width: `${docPercent}%` }}
              />
            </div>
            <p className="text-[10px] text-[var(--ink-tertiary)] font-mono">
              Limit: 10 PDFs (Max 10MB each)
            </p>
          </div>

          {/* Vault Storage Quota */}
          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--ink-subtle)] font-medium flex items-center gap-1.5">
                <HardDrive className="h-3.5 w-3.5 text-sky-400" />
                Vault Storage
              </span>
              <span className="text-xs font-semibold text-[var(--ink)] font-mono">
                {usage ? formatBytes(usage.storage_bytes) : "0 B"} / 100 MB
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[var(--surface-3)] overflow-hidden">
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-300"
                style={{ width: `${storagePercent}%` }}
              />
            </div>
            <p className="text-[10px] text-[var(--ink-tertiary)] font-mono">
              {usage ? `${usage.storage_mb} MB consumed` : "100 MB capacity"}
            </p>
          </div>

          {/* Knowledge Chunks */}
          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--ink-subtle)] font-medium flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-indigo-400" />
                Knowledge Chunks
              </span>
              <span className="text-xs font-semibold text-[var(--ink)] font-mono">
                {usage?.chunk_count ?? 0} / {usage?.max_chunks ?? 1000}
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[var(--surface-3)] overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${chunkPercent}%` }}
              />
            </div>
            <p className="text-[10px] text-[var(--ink-tertiary)] font-mono">
              Semantic vector partitions
            </p>
          </div>

          {/* 7-Day Lifecycle Cycle */}
          <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--ink-subtle)] font-medium flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5 text-emerald-400" />
                Retention Cycle
              </span>
              <span className="text-xs font-semibold text-emerald-400 font-mono">
                7 Days
              </span>
            </div>
            <div className="flex items-center gap-1.5 py-0.5">
              <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs text-[var(--ink-muted)] font-medium">Rolling TTL Active</span>
            </div>
            <p className="text-[10px] text-[var(--ink-tertiary)] font-mono">
              Automated data compliance
            </p>
          </div>
        </div>

        {/* Quota Exhaustion Warning Banner */}
        {isAtQuota && (
          <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-amber-900/40 bg-amber-950/20 px-3.5 py-2.5 text-xs text-amber-300 animate-in fade-in">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
            <span>
              Workspace document quota reached ({usage?.max_documents}/{usage?.max_documents} PDFs).
              Please delete an older file below to upload new documents.
            </span>
          </div>
        )}
      </div>

      {/* ── 2. Drag & Drop Upload Zone ─────────────────────────── */}
      <div
        id="dropzone-area"
        onDragOver={(e) => {
          e.preventDefault();
          if (!isAtQuota) setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (isAtQuota) return;
          if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
        }}
        className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 transition-all duration-200 ${
          isAtQuota
            ? "border-[var(--hairline)] bg-[var(--surface-1)]/50 opacity-60 cursor-not-allowed"
            : isDragOver
            ? "border-[var(--accent)] bg-[var(--accent)]/5"
            : "border-[var(--hairline)] bg-[var(--surface-1)] hover:border-[var(--hairline-strong)] hover:bg-[var(--surface-2)]"
        }`}
      >
        <input
          id="file-upload-input"
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          disabled={isAtQuota || uploading}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
          }}
        />

        <div
          className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--surface-2)] border border-[var(--hairline)] mb-3 shadow-sm transition-all ${
            isDragOver ? "scale-110" : ""
          }`}
        >
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-[var(--accent)]" />
          ) : (
            <UploadCloud className="h-6 w-6 text-[var(--ink-muted)]" />
          )}
        </div>

        <h3 className="text-sm font-semibold text-[var(--ink)]">
          {uploading ? uploadStatusText : isAtQuota ? "Quota Reached (10/10 PDFs)" : "Upload PDF Documents"}
        </h3>
        <p className="mt-1 text-xs text-[var(--ink-subtle)] text-center max-w-sm leading-relaxed">
          {isAtQuota
            ? "Remove an existing document from your vault to free up capacity."
            : "Upload PDF documents (up to 10MB) to make them searchable by your AI assistant."}
        </p>

        <div className="mt-4 flex items-center gap-3">
          <button
            id="btn-browse-file"
            type="button"
            disabled={uploading || isAtQuota}
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-4 py-2 text-xs font-medium transition-all shadow-sm disabled:opacity-40 disabled:pointer-events-none active:scale-95 cursor-pointer"
          >
            {uploading ? uploadStatusText : "Select PDF Document"}
          </button>
          {!isAtQuota && <span className="text-[11px] text-[var(--ink-tertiary)]">or drag & drop</span>}
        </div>

        {uploadError && (
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-900/60 bg-red-950/20 px-3.5 py-2 text-xs text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
            <span>{uploadError}</span>
          </div>
        )}

        {uploadSuccess && (
          <div
            className={`mt-4 flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs ${
              isDuplicateNotice
                ? "border-amber-900/60 bg-amber-950/20 text-amber-300"
                : "border-emerald-900/60 bg-emerald-950/20 text-emerald-300"
            }`}
          >
            {isDuplicateNotice ? (
              <AlertCircle className="h-4 w-4 shrink-0 text-amber-400" />
            ) : (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            )}
            <span>{uploadSuccess}</span>
          </div>
        )}
      </div>

      {/* ── 3. Indexed Document Table ────────────────────────── */}
      <div className="card-surface overflow-hidden rounded-2xl border border-[var(--hairline)] bg-[var(--surface-1)]">
        <div className="flex items-center justify-between border-b border-[var(--hairline)] px-5 py-3.5 bg-[var(--surface-2)]">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-[var(--ink-subtle)]" />
            <h2 className="text-xs font-semibold text-[var(--ink)]">Indexed Documents</h2>
            <span className="rounded-full bg-[var(--surface-3)] border border-[var(--hairline)] px-2 py-0.5 text-[10px] font-mono text-[var(--ink-muted)]">
              {documents.length} / 10
            </span>
          </div>

          <button
            id="btn-refresh-docs"
            type="button"
            onClick={() => {
              fetchDocuments();
              fetchUsage();
            }}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] hover:bg-[var(--surface-3)] px-2.5 py-1 text-xs text-[var(--ink-muted)] transition-colors"
          >
            <RefreshCw className={`h-3 w-3 ${isRefreshing ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-12 text-xs text-[var(--ink-subtle)] gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <FileText className="h-7 w-7 text-[var(--ink-tertiary)] mb-2" />
            <p className="text-xs font-medium text-[var(--ink-subtle)]">No documents uploaded yet</p>
            <p className="text-[11px] text-[var(--ink-tertiary)] mt-0.5">
              Upload a PDF above to enable AI question answering with citations.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[var(--hairline)]">
            {documents.map((doc) => {
              const isProcessing = doc.status === "PENDING" || doc.status === "PROCESSING";

              return (
                <div
                  key={doc.id}
                  className="flex items-center justify-between px-5 py-3.5 hover:bg-[var(--surface-2)]/60 transition-colors"
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-2)] border border-[var(--hairline)] text-[var(--ink-muted)]">
                      {isProcessing ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
                      ) : (
                        <FileText className="h-4 w-4" />
                      )}
                    </div>
                    <div className="truncate">
                      <p className="text-xs font-medium text-[var(--ink)] truncate">{doc.filename}</p>
                      <div className="flex flex-wrap items-center gap-2 mt-0.5 text-[11px] text-[var(--ink-tertiary)] font-mono">
                        <span>{formatBytes(doc.file_size)}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1 text-[var(--ink-subtle)]">
                          <Layers className="h-3 w-3" />
                          {doc.total_chunks || doc.chunk_count || 0} chunks
                        </span>
                        {doc.created_at && (
                          <>
                            <span>•</span>
                            <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                        doc.status === "READY"
                          ? "bg-emerald-950/40 text-emerald-400 border-emerald-800/40"
                          : isProcessing
                          ? "bg-sky-950/40 text-sky-400 border-sky-800/40 animate-pulse"
                          : "bg-red-950/40 text-red-400 border-red-800/40"
                      }`}
                    >
                      {doc.status}
                    </span>

                    {!doc.id.startsWith("temp-") && (
                      <button
                        type="button"
                        id={`btn-delete-doc-${doc.id}`}
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        title="Delete document"
                        className="rounded-lg p-1.5 text-[var(--ink-tertiary)] hover:text-red-400 hover:bg-[var(--surface-3)] transition-colors cursor-pointer"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
