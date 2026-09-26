import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DocumentItem, TenantUsage } from "@/components/DocumentManager";
import { Conversation, Message } from "@/components/ChatInterface";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Query Keys Factory ────────────────────────────────────────────────────────
export const queryKeys = {
  tenantUsage: (tenantId: string) => ["tenantUsage", tenantId] as const,
  documents: (tenantId: string) => ["documents", tenantId] as const,
  conversations: (tenantId: string) => ["conversations", tenantId] as const,
  messages: (tenantId: string, convId: string | null) => ["messages", tenantId, convId] as const,
  adminMetrics: () => ["adminMetrics"] as const,
};

// ── 1. Tenant Quota & Usage Hook ─────────────────────────────────────────────
export function useTenantUsage(tenantId: string) {
  return useQuery<TenantUsage>({
    queryKey: queryKeys.tenantUsage(tenantId),
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/documents/usage`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch tenant usage (status ${res.status})`);
      }
      return res.json();
    },
    enabled: Boolean(tenantId),
    staleTime: 5000,
  });
}

// ── 2. Documents List Hook (with adaptive 500ms polling for processing docs) ─
export function useDocuments(tenantId: string) {
  return useQuery<DocumentItem[]>({
    queryKey: queryKeys.documents(tenantId),
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/documents`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch documents (status ${res.status})`);
      }
      return res.json();
    },
    enabled: Boolean(tenantId),
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!docs || !Array.isArray(docs)) return false;
      const isProcessing = docs.some(
        (d) =>
          d.status?.toLowerCase() === "processing" ||
          d.status?.toLowerCase() === "pending"
      );
      // Fast polling (500ms) only while ingestion is active, otherwise idle
      return isProcessing ? 500 : false;
    },
  });
}

// ── 3. Tenant Conversations Hook ─────────────────────────────────────────────
export function useConversations(tenantId: string) {
  return useQuery<Conversation[]>({
    queryKey: queryKeys.conversations(tenantId),
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/chat/conversations`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch conversations (status ${res.status})`);
      }
      return res.json();
    },
    enabled: Boolean(tenantId),
    staleTime: 10_000,
  });
}

// ── 4. Conversation Messages Hook ────────────────────────────────────────────
export function useConversationMessages(tenantId: string, conversationId: string | null) {
  return useQuery<Message[]>({
    queryKey: queryKeys.messages(tenantId, conversationId),
    queryFn: async () => {
      if (!conversationId) return [];
      const res = await fetch(`${API_BASE}/api/chat/conversations/${conversationId}/messages`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch messages for ${conversationId}`);
      }
      return res.json();
    },
    enabled: Boolean(tenantId && conversationId),
    staleTime: 30_000,
  });
}

// ── 5. Admin Metrics Hook ────────────────────────────────────────────────────
export function useAdminMetrics() {
  return useQuery({
    queryKey: queryKeys.adminMetrics(),
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/health/metrics`);
      if (!res.ok) {
        throw new Error(`Failed to fetch admin metrics (status ${res.status})`);
      }
      return res.json();
    },
    refetchInterval: 3000,
    staleTime: 2500,
  });
}

// ── 6. Document Delete Mutation (Optimistic) ─────────────────────────────────
export function useDeleteDocumentMutation(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string) => {
      const res = await fetch(`${API_BASE}/api/documents/${documentId}`, {
        method: "DELETE",
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Deletion failed" }));
        throw new Error(err.detail || "Deletion failed");
      }
      return documentId;
    },
    onMutate: async (deletedId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.documents(tenantId) });

      // Snapshot previous value
      const prevDocs = queryClient.getQueryData<DocumentItem[]>(queryKeys.documents(tenantId));

      // Optimistically remove from cache
      if (prevDocs) {
        queryClient.setQueryData<DocumentItem[]>(
          queryKeys.documents(tenantId),
          prevDocs.filter((d) => d.id !== deletedId)
        );
      }

      return { prevDocs };
    },
    onError: (_err, _deletedId, context) => {
      // Rollback on error
      if (context?.prevDocs) {
        queryClient.setQueryData(queryKeys.documents(tenantId), context.prevDocs);
      }
    },
    onSettled: () => {
      // Invalidate to synchronize accurate server counters
      queryClient.invalidateQueries({ queryKey: queryKeys.documents(tenantId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tenantUsage(tenantId) });
    },
  });
}

// ── 7. Conversation Delete Mutation (Optimistic) ─────────────────────────────
export function useDeleteConversationMutation(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (convId: string) => {
      const res = await fetch(`${API_BASE}/api/chat/conversations/${convId}`, {
        method: "DELETE",
        headers: { "X-Tenant-ID": tenantId },
      });
      if (!res.ok) {
        throw new Error("Failed to delete conversation");
      }
      return convId;
    },
    onMutate: async (deletedId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.conversations(tenantId) });
      const prevConvs = queryClient.getQueryData<Conversation[]>(queryKeys.conversations(tenantId));

      if (prevConvs) {
        queryClient.setQueryData<Conversation[]>(
          queryKeys.conversations(tenantId),
          prevConvs.filter((c) => c.id !== deletedId)
        );
      }

      return { prevConvs };
    },
    onError: (_err, _deletedId, context) => {
      if (context?.prevConvs) {
        queryClient.setQueryData(queryKeys.conversations(tenantId), context.prevConvs);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations(tenantId) });
    },
  });
}
