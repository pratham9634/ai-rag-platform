"use client";

import React, { useState, useRef, useEffect } from "react";
import { UploadCloud, FileText, Trash2, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

export interface DocumentItem {
  id: string;
  tenant_id: string;
  filename: string;
  file_size: number;
  status: string;
  total_chunks: number;
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
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
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
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [tenantId]);

  const handleFileUpload = async (file: File) => {
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF documents are supported.");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File size exceeds 10MB limit.");
      return;
    }

    setUploadError(null);
    setUploadSuccess(null);
    setUploading(true);

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
      setUploadSuccess(`Successfully ingested "${result.filename}" (${result.total_chunks} chunks).`);
      await fetchDocuments();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload document.";
      setUploadError(msg);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Are you sure you want to delete "${filename}"? All associated vectors will be purged.`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
        method: "DELETE",
        headers: { "X-Tenant-ID": tenantId },
      });

      if (res.ok) {
        await fetchDocuments();
      } else {
        alert("Failed to delete document.");
      }
    } catch (err) {
      console.error("Delete error:", err);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
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
        className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 transition-all ${
          isDragOver
            ? "border-indigo-500 bg-indigo-500/10 shadow-lg shadow-indigo-500/20"
            : "border-white/[0.12] bg-gray-900/40 hover:border-white/[0.25] hover:bg-gray-900/60"
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

        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600/30 to-violet-600/30 border border-indigo-500/30 text-indigo-400 mb-3 shadow-inner">
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
          ) : (
            <UploadCloud className="h-6 w-6 text-indigo-400" />
          )}
        </div>

        <h3 className="text-sm font-semibold text-white">
          {uploading ? "Parsing, Chunking & Embedding..." : "Upload PDF Knowledge Base"}
        </h3>
        <p className="mt-1 text-xs text-gray-400 text-center max-w-sm">
          Drag & drop your corporate policies, guides, or manuals here, or click to browse (up to 10MB).
        </p>

        <button
          id="btn-browse-file"
          type="button"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-indigo-600/30 transition-all hover:bg-indigo-500 hover:shadow-indigo-500/40 disabled:opacity-50"
        >
          {uploading ? "Processing Document..." : "Select PDF Document"}
        </button>

        {uploadError && (
          <div className="mt-3.5 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}

        {uploadSuccess && (
          <div className="mt-3.5 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>{uploadSuccess}</span>
          </div>
        )}
      </div>

      {/* Document Library Table */}
      <div className="rounded-xl border border-white/[0.08] bg-gray-900/50 backdrop-blur-sm overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5 bg-gray-900/80">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-indigo-400" />
            <h2 className="text-sm font-semibold text-white">Knowledge Documents</h2>
            <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[10px] font-mono text-gray-400">
              {documents.length}
            </span>
          </div>
          <button
            id="btn-refresh-docs"
            onClick={fetchDocuments}
            className="text-xs text-gray-400 hover:text-white transition-colors"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-12 text-xs text-gray-500 gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            Loading tenant document catalog...
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <FileText className="h-8 w-8 text-gray-600 mb-2" />
            <p className="text-xs text-gray-400 font-medium">No documents uploaded yet</p>
            <p className="text-[11px] text-gray-600 mt-0.5">Upload a PDF above to enable agentic retrieval and grounding.</p>
          </div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between px-5 py-3 hover:bg-white/[0.02] transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div className="truncate">
                    <p className="text-xs font-medium text-gray-200 truncate">{doc.filename}</p>
                    <div className="flex items-center gap-2.5 mt-0.5 text-[11px] text-gray-400">
                      <span>{formatBytes(doc.file_size)}</span>
                      <span>•</span>
                      <span>{doc.total_chunks} chunks indexed</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border ${
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
                    className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
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
