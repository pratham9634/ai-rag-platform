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
  Fingerprint,
  RefreshCw,
  Database,
  Layers,
} from "lucide-react";

export interface DocumentItem {
  id: string;
  tenant_id: string;
  filename: string;
  file_size: number;
  status: string;
  total_chunks: number;
  file_hash?: string;
  created_at?: string;
  error_message?: string | null;
}

interface DocumentManagerProps {
  tenantId: string;
  onDocumentsChange?: (count: number, chunkCount: number) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DocumentManager({ tenantId, onDocumentsChange }: DocumentManagerProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadStatusText, setUploadStatusText] = useState<string>("Processing Document...");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isDuplicateNotice, setIsDuplicateNotice] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async (showRefreshingIndicator = false) => {
    try {
      if (showRefreshingIndicator) setIsRefreshing(true);
      else setLoading(true);

      const res = await fetch(`${API_BASE}/api/documents`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (res.ok) {
        const data: DocumentItem[] = await res.json();
        setDocuments(data);
        const totalChunks = data.reduce((sum, d) => sum + (d.total_chunks || 0), 0);
        onDocumentsChange?.(data.length, totalChunks);
      }
    } catch (err) {
      console.error("Error fetching documents:", err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [tenantId]);

  // Periodic polling while any document is actively in PENDING or PROCESSING state
  useEffect(() => {
    const hasActiveProcessing = documents.some(
      (d) => d.status === "PENDING" || d.status === "PROCESSING"
    );
    if (!hasActiveProcessing) return;

    const timer = setInterval(() => {
      fetchDocuments(true);
    }, 2500);

    return () => clearInterval(timer);
  }, [documents, tenantId]);

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

    setUploadError(null);
    setUploadSuccess(null);
    setIsDuplicateNotice(false);
    setUploading(true);
    setUploadStatusText("Computing SHA-256 fingerprint & validating...");

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
        throw new Error(errData.detail || "Upload failed.");
      }

      const result = await res.json();

      if (result.is_duplicate) {
        setIsDuplicateNotice(true);
        setUploadSuccess(`Identical document "${result.filename}" already indexed (SHA-256 duplicate skipped).`);
        await fetchDocuments(true);
        setUploading(false);
        return;
      }

      const docId = result.document_id;
      setUploadStatusText("Extracting structure, chunking & computing pgvector embeddings...");
      await fetchDocuments(true);

      let attempts = 0;
      const maxAttempts = 30; // 30 * 1.5s = 45s
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
              setUploadSuccess(`Successfully indexed "${statusData.filename}" into ${statusData.total_chunks || 0} vector chunks.`);
              setUploading(false);
              await fetchDocuments(true);
              return;
            } else if (statusData.status === "FAILED") {
              clearInterval(pollInterval);
              setUploadError(`Ingestion failed: ${statusData.error_message || "Unknown error"}`);
              setUploading(false);
              await fetchDocuments(true);
              return;
            }
          }
        } catch {
          // Keep polling
        }

        if (attempts >= maxAttempts) {
          clearInterval(pollInterval);
          setUploadSuccess(`Document queued in background. Status will update automatically.`);
          setUploading(false);
          await fetchDocuments(true);
        }
      }, 1500);

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload document.";
      setUploadError(msg);
      setUploading(false);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Permanently remove "${filename}"? All associated pgvector embeddings and cache entries will be purged.`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
        method: "DELETE",
        headers: { "X-Tenant-ID": tenantId },
      });

      if (res.ok) {
        await fetchDocuments(true);
      } else {
        alert("Failed to delete document from vault.");
      }
    } catch (err) {
      console.error("Delete error:", err);
    }
  };

  const formatBytes = (bytes: number) => {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="space-y-6 font-sans">
      {/* ── Linear / Bento Dropzone Card ─────────────────────────────── */}
      <div
        id="dropzone-area"
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (e.dataTransfer.files?.[0]) {
            handleFileUpload(e.dataTransfer.files[0]);
          }
        }}
        className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 sm:p-10 transition-all ${
          isDragOver
            ? "border-[#5e6ad2] bg-[#5e6ad2]/10 shadow-xl shadow-indigo-950/40"
            : "border-[#23252a] bg-[#090a10] hover:border-white/[0.2] hover:bg-[#0c0e17]"
        }`}
      >
        <input
          id="file-upload-input"
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
          }}
        />

        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-[#5e6ad2]/20 to-[#828fff]/20 border border-[#5e6ad2]/30 text-[#828fff] mb-3.5 shadow-inner">
          {uploading ? (
            <Loader2 className="h-7 w-7 animate-spin text-[#828fff]" />
          ) : (
            <UploadCloud className="h-7 w-7 text-[#5e6ad2]" />
          )}
        </div>

        <h3 className="text-sm font-semibold text-white">
          {uploading ? uploadStatusText : "Upload PDF to Document Vault"}
        </h3>
        <p className="mt-1.5 text-xs text-gray-400 text-center max-w-md leading-relaxed">
          Upload corporate PDFs (max 10MB). Text is parsed with PyMuPDF, chunked into semantically
          overlapping windows, embedded with all-MiniLM-L6-v2, and indexed in pgvector.
        </p>

        <div className="mt-4 flex items-center gap-3">
          <button
            id="btn-browse-file"
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="rounded-xl bg-[#5e6ad2] px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-950/40 transition-all hover:bg-[#828fff] active:scale-95 disabled:opacity-50"
          >
            {uploading ? uploadStatusText : "Choose PDF File"}
          </button>
          <span className="text-[11px] text-gray-400">or drag & drop here</span>
        </div>

        {uploadError && (
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2 text-xs text-red-300 animate-in fade-in duration-200">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
            <span>{uploadError}</span>
          </div>
        )}

        {uploadSuccess && (
          <div
            className={`mt-4 flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs animate-in fade-in duration-200 ${
              isDuplicateNotice
                ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
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

      {/* ── Document Catalog (Linear App Bento Table) ────────────────── */}
      <div className="rounded-2xl border border-[#23252a] bg-[#090a10] overflow-hidden shadow-xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-[#23252a] px-5 py-3.5 bg-[#0e111a]/80">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[#5e6ad2]">
              <Database className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-white">Indexed Knowledge Assets</h2>
              <span className="text-[10px] text-gray-400">
                Tenant: <code className="font-mono text-gray-300">{tenantId}</code>
              </span>
            </div>
            <span className="rounded-full bg-white/[0.06] border border-white/[0.08] px-2 py-0.5 text-[10px] font-mono text-gray-300 ml-1">
              {documents.length} doc{documents.length !== 1 ? "s" : ""}
            </span>
          </div>

          <button
            id="btn-refresh-docs"
            onClick={() => fetchDocuments(true)}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs text-gray-300 hover:bg-white/[0.08] hover:text-white transition-all disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isRefreshing ? "animate-spin text-[#5e6ad2]" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-14 text-xs text-gray-400 gap-2.5">
            <Loader2 className="h-4 w-4 animate-spin text-[#5e6ad2]" />
            Loading tenant document catalog...
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-14 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.03] border border-[#23252a] text-gray-500 mb-3">
              <FileText className="h-6 w-6" />
            </div>
            <p className="text-xs font-semibold text-gray-300">Vault is empty</p>
            <p className="text-[11px] text-gray-400 mt-1 max-w-sm">
              Upload PDF manuals or policy guides above to initialize pgvector chunks and enable
              grounded conversational QA.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[#23252a]">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02] transition-colors group"
              >
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#131722] border border-[#23252a] text-[#828fff]">
                    <FileText className="h-4.5 w-4.5" />
                  </div>
                  <div className="truncate">
                    <p className="text-xs font-medium text-gray-100 truncate group-hover:text-indigo-200 transition-colors">
                      {doc.filename}
                    </p>
                    <div className="flex flex-wrap items-center gap-2.5 mt-0.5 text-[11px] text-gray-400 font-mono">
                      <span>{formatBytes(doc.file_size)}</span>
                      <span>•</span>
                      <span className="flex items-center gap-1 text-indigo-300">
                        <Layers className="h-3 w-3 text-indigo-400" />
                        {doc.total_chunks} chunks
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1 text-gray-400" title="Automatic 7-day storage retention">
                        <Clock className="h-3 w-3 text-amber-400" />
                        7d TTL
                      </span>
                      {doc.file_hash && (
                        <>
                          <span>•</span>
                          <span className="flex items-center gap-1 text-gray-400" title={`SHA-256: ${doc.file_hash}`}>
                            <Fingerprint className="h-3 w-3 text-gray-400" />
                            {doc.file_hash.slice(0, 8)}...
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-medium font-mono border ${
                      doc.status === "READY"
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                        : doc.status === "PROCESSING"
                        ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                        : "border-red-500/30 bg-red-500/10 text-red-400"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        doc.status === "READY" ? "bg-emerald-400" : "bg-amber-400"
                      }`}
                    />
                    {doc.status}
                  </span>

                  <button
                    id={`btn-delete-doc-${doc.id}`}
                    onClick={() => handleDelete(doc.id, doc.filename)}
                    title="Delete document and purge vectors"
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
