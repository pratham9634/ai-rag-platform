"use client";

import React, { useState, useEffect, useRef, useCallback, memo } from "react";
import {
  Sparkles,
  Bot,
  User,
  Plus,
  MessageSquare,
  Bookmark,
  RefreshCw,
  Copy,
  Check,
  X,
  FileText,
  Shield,
  Trash2,
  ArrowUp,
  Menu,
  SlidersHorizontal,
  Cpu,
  ChevronRight,
} from "lucide-react";
import { SystemSettings } from "@/components/SettingsModal";
import { useAppStore } from "@/lib/store";
import {
  useConversations,
  useConversationMessages,
  useDeleteConversationMutation,
  queryKeys,
} from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

export interface Citation {
  chunk_id: string;
  document_id: string;
  page_number: number;
  relevance_score?: number | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  created_at?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface ChatInterfaceProps {
  tenantId: string;
  settings?: SystemSettings;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const QUICK_PROMPTS = [
  {
    icon: Sparkles,
    label: "PTO & Leave Policy",
    prompt: "How many days of paid time off (PTO) and sick leave do employees receive per year?",
  },
  {
    icon: FileText,
    label: "Remote Work Guidelines",
    prompt: "What are the eligibility requirements, stipend policies, and working hour expectations for remote work?",
  },
  {
    icon: Shield,
    label: "Compliance & Security",
    prompt: "What are our data retention guidelines and mandatory procedures for handling sensitive customer data?",
  },
];

function getModelDisplayName(modelId?: string) {
  if (!modelId) return "Claude 3.5 Sonnet";
  if (modelId.includes("claude-3.5-sonnet")) return "Claude 3.5 Sonnet";
  if (modelId.includes("gpt-4o-mini")) return "GPT-4o Mini";
  if (modelId.includes("llama-3.1-8b")) return "Llama 3.1 8B";
  if (modelId.includes("mistral-7b")) return "Mistral 7B";
  const parts = modelId.split("/");
  return parts[1]?.split(":")[0] || parts[0] || modelId;
}

// ── Customization Trigger Card for Sidebar ──
const CustomizationCard = memo(function CustomizationCard({
  settings,
  onOpenSettings,
}: {
  settings?: SystemSettings;
  onOpenSettings: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      id="btn-sidebar-customization"
      onClick={onOpenSettings}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpenSettings();
        }
      }}
      className="w-full text-left group rounded-xl border border-[var(--hairline)] bg-[var(--surface-2)]/60 hover:bg-[var(--surface-2)] hover:border-[var(--hairline-strong)] p-2.5 transition-all mb-3 shadow-xs cursor-pointer focus:outline-none focus:ring-1 focus:ring-[var(--hairline-strong)] select-none"
      title="Configure LLM model, search parameters & API keys"
      aria-label="Agent customization and model settings"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--ink-tertiary)] group-hover:text-[var(--ink-subtle)] transition-colors">
          <SlidersHorizontal className="h-3 w-3 text-[var(--accent)]" />
          <span>Customization</span>
        </div>
        <span className="flex items-center gap-0.5 text-[10px] font-mono text-[var(--ink-tertiary)] group-hover:text-[var(--ink-muted)]">
          <span>Edit</span>
          <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 text-[var(--ink-tertiary)]" />
        </span>
      </div>

      <div className="mt-1.5 flex items-center justify-between">
        <div className="min-w-0 pr-1">
          <p className="text-xs font-semibold text-[var(--ink)] truncate">
            {getModelDisplayName(settings?.model)}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-[var(--ink-tertiary)]">
            <span className="font-mono">Top-{settings?.topK ?? 5}</span>
            <span>•</span>
            <span>{settings?.enableWebSearch ? "Web Search ON" : "Docs Only"}</span>
            {settings?.byokKey && (
              <>
                <span>•</span>
                <span className="text-emerald-400 font-mono font-medium">BYOK</span>
              </>
            )}
          </div>
        </div>
        <div className="h-6 w-6 rounded-lg bg-[var(--surface-1)] border border-[var(--hairline)] flex items-center justify-center text-[var(--ink-subtle)] group-hover:text-[var(--accent)] group-hover:border-[var(--hairline-strong)] transition-all shrink-0">
          <Cpu className="h-3.5 w-3.5" />
        </div>
      </div>
    </div>
  );
});

// ── Memoized Message Item to avoid re-rendering entire list on keystroke or stream ──
const MessageBubble = memo(function MessageBubble({
  msg,
  isLatest,
  isStreaming,
  thinkingStep,
  copiedId,
  onCopy,
  onSelectCitation,
}: {
  msg: Message;
  isLatest: boolean;
  isStreaming: boolean;
  thinkingStep: string | null;
  copiedId: string | null;
  onCopy: (text: string, id: string) => void;
  onSelectCitation: (c: Citation) => void;
}) {
  const isAssistant = msg.role === "assistant";

  return (
    <div className={`flex gap-3 ${isAssistant ? "justify-start" : "justify-end"} group`}>
      {isAssistant && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)] border border-[var(--hairline)] text-[var(--accent)] mt-0.5 shadow-sm">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div
        className={`relative max-w-[85%] sm:max-w-[78%] rounded-2xl px-4 py-3 text-xs leading-relaxed transition-all ${
          isAssistant
            ? "bg-[var(--surface-1)] border border-[var(--hairline)] text-[var(--ink)]"
            : "bg-[var(--accent)] text-white font-normal"
        }`}
      >
        {isAssistant && msg.content === "" && isStreaming ? (
          <div className="flex items-center gap-2 py-1 text-[var(--ink-subtle)] font-medium text-xs">
            <span className="flex h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
            <span>{thinkingStep || "Thinking..."}</span>
          </div>
        ) : (
          <div>
            <div className="whitespace-pre-wrap leading-relaxed">
              {msg.content}
              {isStreaming && isAssistant && isLatest && (
                <span className="inline-block w-1.5 h-3 ml-1 bg-[var(--accent)] animate-pulse align-middle" />
              )}
            </div>

            {/* Citations & Copy Footer for Assistant */}
            {isAssistant && msg.content && (
              <div className="mt-3 flex items-center justify-between border-t border-[var(--hairline)] pt-2 text-[11px] text-[var(--ink-tertiary)]">
                <span className="font-mono text-[10px]">
                  {msg.citations && msg.citations.length > 0
                    ? `${msg.citations.length} citation${msg.citations.length > 1 ? "s" : ""}`
                    : "Direct response"}
                </span>

                <button
                  type="button"
                  onClick={() => onCopy(msg.content, msg.id)}
                  className="flex items-center gap-1 text-[var(--ink-subtle)] hover:text-[var(--ink)] transition-colors py-0.5 px-1.5 rounded hover:bg-[var(--surface-2)]"
                  title="Copy response"
                >
                  {copiedId === msg.id ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" />
                      <span className="text-emerald-400 text-[10px]">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span className="text-[10px]">Copy</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Citations Chips */}
        {isAssistant && msg.citations && msg.citations.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {msg.citations.map((c, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectCitation(c)}
                className="inline-flex items-center gap-1 rounded-md border border-[var(--hairline)] bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-mono text-[var(--ink-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all cursor-pointer"
              >
                <Bookmark className="h-2.5 w-2.5" />
                Page {c.page_number}
                {c.relevance_score && (
                  <span className="text-[var(--ink-tertiary)]">
                    ({(c.relevance_score * 100).toFixed(0)}%)
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {!isAssistant && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)] border border-[var(--hairline)] text-[var(--ink-subtle)] mt-0.5">
          <User className="h-3.5 w-3.5" />
        </div>
      )}
    </div>
  );
});

// ── Memoized Thread Item to avoid re-rendering entire sidebar on changes ──
const ThreadItem = memo(function ThreadItem({
  conv,
  isActive,
  onSelect,
  onDelete,
}: {
  conv: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}) {
  return (
    <div
      onClick={() => onSelect(conv.id)}
      role="button"
      tabIndex={0}
      className={`w-full group relative flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-xs transition-all cursor-pointer ${
        isActive
          ? "bg-[var(--surface-2)] text-[var(--ink)] font-medium border border-[var(--hairline-strong)]"
          : "text-[var(--ink-subtle)] hover:bg-[var(--surface-2)]/60 hover:text-[var(--ink)] border border-transparent"
      }`}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <MessageSquare
          className={`h-3.5 w-3.5 shrink-0 ${
            isActive ? "text-[var(--accent)]" : "text-[var(--ink-tertiary)] group-hover:text-[var(--ink-subtle)]"
          }`}
        />
        <span className="truncate text-[12px]">{conv.title || "Untitled Session"}</span>
      </div>

      <button
        type="button"
        title="Delete conversation"
        onClick={(e) => onDelete(e, conv.id)}
        className="opacity-0 group-hover:opacity-100 p-1 text-[var(--ink-tertiary)] hover:text-red-400 transition-all rounded hover:bg-[var(--surface-3)]"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  );
});

// ── Memoized Input Bar to isolate typing re-renders from message list ──
const ChatInput = memo(function ChatInput({
  isStreaming,
  onSendMessage,
}: {
  isStreaming: boolean;
  onSendMessage: (query: string) => void;
}) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!text.trim() || isStreaming) return;
    onSendMessage(text.trim());
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  return (
    <footer className="border-t border-[var(--hairline)] bg-[var(--surface-1)] p-3 sm:p-4">
      <form
        onSubmit={handleSubmit}
        className="relative flex items-end gap-2 rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-2 focus-within:border-[var(--hairline-strong)] focus-within:ring-1 focus-within:ring-[var(--hairline-strong)] transition-all shadow-sm"
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          disabled={isStreaming}
          onKeyDown={handleKeyDown}
          onChange={handleChange}
          placeholder="Ask a question about your knowledge base (Enter to send)..."
          className="flex-1 bg-transparent px-2.5 py-1 text-xs text-[var(--ink)] placeholder-[var(--ink-tertiary)] focus:outline-none resize-none max-h-32 disabled:opacity-50 font-sans"
        />

        <button
          type="submit"
          disabled={!text.trim() || isStreaming}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white transition-all hover:bg-[var(--accent-hover)] disabled:opacity-30 disabled:pointer-events-none active:scale-95"
          title="Send message"
        >
          <ArrowUp className="h-3.5 w-3.5 stroke-[2.5]" />
        </button>
      </form>

      <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-[var(--ink-tertiary)]">
        <span>Grounded search with automatic citations</span>
        <span>
          <kbd className="rounded bg-[var(--surface-2)] border border-[var(--hairline)] px-1 py-0.5 font-mono text-[10px] text-[var(--ink-subtle)]">
            Enter ↵
          </kbd>{" "}
          to send
        </span>
      </div>
    </footer>
  );
});

export default function ChatInterface({ tenantId, settings }: ChatInterfaceProps) {
  const queryClient = useQueryClient();
  const activeConvId = useAppStore((state) => state.activeConversationId);
  const setActiveConvId = useAppStore((state) => state.setActiveConversationId);
  const setIsSettingsOpen = useAppStore((state) => state.setIsSettingsOpen);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const {
    data: conversations = [],
    isLoading: isConversationsLoading,
    refetch: fetchConversations,
  } = useConversations(tenantId);

  const {
    data: serverMessages = [],
    isLoading: isLoadingHistory,
  } = useConversationMessages(tenantId, activeConvId);

  const deleteConvMutation = useDeleteConversationMutation(tenantId);

  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinkingStep, setThinkingStep] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const activeConvIdRef = useRef<string | null>(activeConvId);
  const messagesScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    activeConvIdRef.current = activeConvId;
  }, [activeConvId]);

  // Close mobile drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isMobileSidebarOpen) {
        setIsMobileSidebarOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMobileSidebarOpen]);

  // Effective messages: use live streaming tokens during generation, otherwise server query cache
  const effectiveMessages = isStreaming
    ? messages
    : (activeConvId && serverMessages.length > 0 ? serverMessages : messages);

  // Buttery-smooth instant scroll during streaming, smooth on message send
  const scrollToBottom = useCallback((smooth = false) => {
    if (messagesScrollRef.current) {
      if (smooth) {
        messagesScrollRef.current.scrollTo({
          top: messagesScrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      } else {
        messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      }
    }
  }, []);

  useEffect(() => {
    scrollToBottom(false);
  }, [effectiveMessages, isStreaming, scrollToBottom]);

  // Switch conversation with instant cache hit
  const handleSelectConversation = useCallback(
    (convId: string) => {
      if (activeConvId === convId) return;
      setActiveConvId(convId);
      activeConvIdRef.current = convId;
    },
    [activeConvId, setActiveConvId]
  );

  // Start a fresh thread
  const handleStartNewChat = useCallback(() => {
    setActiveConvId(null);
    activeConvIdRef.current = null;
    setMessages([]);
    setThinkingStep(null);
  }, [setActiveConvId]);

  // Listen for Ctrl+N / Cmd+N global shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        handleStartNewChat();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleStartNewChat]);

  // Delete conversation
  const handleDeleteConversation = useCallback(
    async (e: React.MouseEvent, convId: string) => {
      e.stopPropagation();
      deleteConvMutation.mutate(convId);
      if (activeConvId === convId) {
        handleStartNewChat();
      }
    },
    [deleteConvMutation, activeConvId, handleStartNewChat]
  );

  const handleCopyText = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  }, []);

  // Send message with multi-turn conversation memory passed to backend
  const handleSendMessage = useCallback(
    async (queryText: string) => {
      if (!queryText.trim() || isStreaming) return;

      setIsStreaming(true);
      setThinkingStep("Searching documents & reasoning...");

      const currentConvId = activeConvIdRef.current;
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: queryText,
        created_at: new Date().toISOString(),
      };

      const assistantMsgId = `assistant-${Date.now()}`;
      const assistantMsg: Message = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        citations: [],
      };

      // Multi-turn context awareness: gather last 6 messages from current thread
      const previousTurns = effectiveMessages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const updatedMessagesWithUser = [...effectiveMessages, userMsg, assistantMsg];
      setMessages(updatedMessagesWithUser);
      scrollToBottom(true);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          "X-Tenant-ID": tenantId,
        };

        if (settings?.byokKey) {
          headers["X-BYOK-API-Key"] = settings.byokKey;
        }

        const response = await fetch(`${API_BASE}/api/chat/stream`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            conversation_id: currentConvId || undefined,
            query: queryText,
            model: settings?.model,
            top_k: settings?.topK,
            enable_web_search: settings?.enableWebSearch,
            history: previousTurns, // Pass multi-turn history to backend agent
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error("Streaming request failed");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulatedContent = "";
        let currentCitations: Citation[] = [];

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n\n");

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const jsonStr = line.replace("data: ", "").trim();
            if (!jsonStr) continue;

            try {
              const event = JSON.parse(jsonStr);

              if (event.type === "status") {
                setThinkingStep(event.message || "Searching documents...");
              } else if (event.type === "token") {
                setThinkingStep(null);
                accumulatedContent += event.content;
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: accumulatedContent, citations: currentCitations }
                      : msg
                  )
                );
              } else if (event.type === "citations") {
                currentCitations = event.citations || [];
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, citations: currentCitations }
                      : msg
                  )
                );
              } else if (event.type === "done") {
                setThinkingStep(null);
                const assignedConvId = event.conversation_id;

                if (assignedConvId) {
                  activeConvIdRef.current = assignedConvId;
                  setActiveConvId(assignedConvId);

                  // Invalidate conversation list and message cache for instant fresh state
                  queryClient.invalidateQueries({ queryKey: queryKeys.conversations(tenantId) });
                  queryClient.invalidateQueries({ queryKey: queryKeys.messages(tenantId, assignedConvId) });
                }
              } else if (event.type === "error") {
                setThinkingStep(null);
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: `Error: ${event.message || "Failed to generate answer."}` }
                      : msg
                  )
                );
              }
            } catch {
              // Ignore split chunk frames
            }
          }
        }
      } catch (err) {
        console.error("Streaming error:", err);
        setThinkingStep(null);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: "An error occurred while generating the response." }
              : msg
          )
        );
      } finally {
        setIsStreaming(false);
        setThinkingStep(null);
      }
    },
    [effectiveMessages, isStreaming, tenantId, settings, scrollToBottom, queryClient, setActiveConvId]
  );

  const activeConversationTitle =
    conversations.find((c) => c.id === activeConvId)?.title || "Active Discussion";

  return (
    <div className="relative flex h-[780px] rounded-2xl border border-[var(--hairline)] bg-[var(--canvas)] overflow-hidden font-sans shadow-lg">
      {/* ── Left Sidebar: Clean Thread Navigation & Customization ─────── */}
      <aside className="w-64 border-r border-[var(--hairline)] bg-[var(--surface-1)] p-3.5 hidden md:flex flex-col">
        {/* Model & System Customization Card (Directly above New Chat) */}
        <CustomizationCard
          settings={settings}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />

        {/* New Thread CTA */}
        <button
          type="button"
          id="btn-new-chat"
          onClick={handleStartNewChat}
          className="flex items-center justify-between w-full rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-3.5 py-2.5 text-xs font-medium transition-all shadow-sm active:scale-95"
        >
          <span className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            New Chat
          </span>
          <kbd className="rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-mono text-white/80">
            Ctrl+N
          </kbd>
        </button>

        {/* Threads Header */}
        <div className="mt-4 flex items-center justify-between px-1">
          <span className="text-[11px] font-medium text-[var(--ink-tertiary)] uppercase tracking-wider">
            History
          </span>
          <button
            type="button"
            onClick={() => fetchConversations()}
            title="Refresh history"
            className="text-[var(--ink-tertiary)] hover:text-[var(--ink)] transition-colors p-1 rounded hover:bg-[var(--surface-2)] cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${isConversationsLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Thread List */}
        <div className="mt-2 flex-1 overflow-y-auto space-y-1 pr-0.5">
          {conversations.length === 0 ? (
            <div className="py-12 text-center text-xs text-[var(--ink-tertiary)]">
              <MessageSquare className="h-5 w-5 mx-auto mb-2 text-[var(--ink-tertiary)] stroke-[1.5]" />
              No previous chats
            </div>
          ) : (
            conversations.map((c) => (
              <ThreadItem
                key={c.id}
                conv={c}
                isActive={activeConvId === c.id}
                onSelect={handleSelectConversation}
                onDelete={handleDeleteConversation}
              />
            ))
          )}
        </div>
      </aside>

      {/* ── Mobile Sidebar Drawer & Backdrop ──────────────────────────── */}
      {isMobileSidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
            onClick={() => setIsMobileSidebarOpen(false)}
            aria-hidden="true"
          />

          {/* Drawer Panel */}
          <div className="relative z-10 w-72 max-w-[85vw] h-full bg-[var(--surface-1)] border-r border-[var(--hairline)] p-4 flex flex-col shadow-2xl animate-in slide-in-from-left duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-[var(--hairline)]">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent)] text-white shadow-xs">
                  <Bot className="h-4 w-4" />
                </div>
                <span className="text-xs font-semibold text-[var(--ink)]">Assistant & Chats</span>
              </div>
              <button
                type="button"
                onClick={() => setIsMobileSidebarOpen(false)}
                className="h-7 w-7 rounded-lg flex items-center justify-center text-[var(--ink-tertiary)] hover:text-[var(--ink)] hover:bg-[var(--surface-2)] transition-colors cursor-pointer"
                aria-label="Close menu"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Customization Card (Directly above New Chat, matching desktop) */}
            <CustomizationCard
              settings={settings}
              onOpenSettings={() => {
                setIsSettingsOpen(true);
                setIsMobileSidebarOpen(false);
              }}
            />

            {/* New Chat CTA */}
            <button
              type="button"
              id="btn-mobile-drawer-new-chat"
              onClick={() => {
                handleStartNewChat();
                setIsMobileSidebarOpen(false);
              }}
              className="flex items-center justify-between w-full rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-3.5 py-2.5 text-xs font-medium transition-all shadow-sm active:scale-95"
            >
              <span className="flex items-center gap-2">
                <Plus className="h-4 w-4" />
                New Chat
              </span>
              <kbd className="rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-mono text-white/80">
                New
              </kbd>
            </button>

            {/* Threads Header */}
            <div className="mt-4 flex items-center justify-between px-1">
              <span className="text-[11px] font-medium text-[var(--ink-tertiary)] uppercase tracking-wider">
                History
              </span>
              <button
                type="button"
                onClick={() => fetchConversations()}
                title="Refresh history"
                className="text-[var(--ink-tertiary)] hover:text-[var(--ink)] transition-colors p-1 rounded hover:bg-[var(--surface-2)] cursor-pointer"
              >
                <RefreshCw className={`h-3 w-3 ${isConversationsLoading ? "animate-spin" : ""}`} />
              </button>
            </div>

            {/* Thread List */}
            <div className="mt-2 flex-1 overflow-y-auto space-y-1 pr-0.5">
              {conversations.length === 0 ? (
                <div className="py-12 text-center text-xs text-[var(--ink-tertiary)]">
                  <MessageSquare className="h-5 w-5 mx-auto mb-2 text-[var(--ink-tertiary)] stroke-[1.5]" />
                  No previous chats
                </div>
              ) : (
                conversations.map((c) => (
                  <ThreadItem
                    key={c.id}
                    conv={c}
                    isActive={activeConvId === c.id}
                    onSelect={(id) => {
                      handleSelectConversation(id);
                      setIsMobileSidebarOpen(false);
                    }}
                    onDelete={handleDeleteConversation}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Main Chat Area ───────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col bg-[var(--canvas)] relative">
        {/* Top Chat Header */}
        <header className="flex items-center justify-between border-b border-[var(--hairline)] px-3.5 sm:px-5 py-3 bg-[var(--surface-1)]">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            {/* Hamburger Button for Mobile Drawer */}
            <button
              type="button"
              id="btn-chat-hamburger"
              onClick={() => setIsMobileSidebarOpen(true)}
              className="md:hidden flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] text-[var(--ink-muted)] hover:text-[var(--ink)] hover:border-[var(--hairline-strong)] active:scale-95 transition-all cursor-pointer"
              title="Open Navigation & Settings"
              aria-label="Open Navigation & Settings"
            >
              <Menu className="h-4 w-4" />
            </button>

            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)] border border-[var(--hairline)] text-[var(--accent)]">
              <Bot className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xs font-semibold text-[var(--ink)] truncate">
                {activeConvId ? activeConversationTitle : "AI Knowledge Assistant"}
              </h2>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span className="text-[10px] text-[var(--ink-tertiary)]">Ready to answer</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              id="btn-mobile-quick-new"
              onClick={handleStartNewChat}
              className="md:hidden flex items-center gap-1 text-xs text-[var(--accent)] font-medium px-2 py-1 rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] hover:bg-[var(--surface-3)] active:scale-95 transition-all"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New</span>
            </button>
            <button
              type="button"
              id="btn-header-model-customization"
              onClick={() => setIsSettingsOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] hover:border-[var(--hairline-strong)] hover:bg-[var(--surface-3)] px-2.5 py-1 text-[11px] font-mono text-[var(--ink-subtle)] hover:text-[var(--ink)] transition-all cursor-pointer"
              title="Click to customize model settings"
            >
              <SlidersHorizontal className="h-3 w-3 text-[var(--accent)]" />
              <span className="max-w-[120px] sm:max-w-none truncate">
                {getModelDisplayName(settings?.model)}
              </span>
            </button>
          </div>
        </header>

        {/* Messages Viewport */}
        <div ref={messagesScrollRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {isLoadingHistory ? (
            <div className="h-full flex items-center justify-center text-xs text-[var(--ink-tertiary)] gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-[var(--accent)]" />
              Loading conversation...
            </div>
          ) : effectiveMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto py-8 text-center animate-fade-in">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--surface-2)] border border-[var(--hairline)] text-[var(--accent)] mb-3 shadow-sm">
                <Sparkles className="h-5 w-5" />
              </div>
              <h1 className="text-lg font-semibold tracking-[-0.02em] text-[var(--ink)] sm:text-xl">
                How can I help you today?
              </h1>
              <p className="mt-1.5 text-xs text-[var(--ink-subtle)] max-w-sm leading-relaxed">
                Ask questions across your uploaded documents with instant grounded citations and memory.
              </p>

              {/* Minimal Clean Prompt Pills */}
              <div className="mt-6 flex flex-col sm:flex-row gap-2 w-full max-w-md">
                {QUICK_PROMPTS.map((starter, idx) => {
                  const Icon = starter.icon;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSendMessage(starter.prompt)}
                      className="flex-1 group flex items-center gap-2 rounded-xl border border-[var(--hairline)] bg-[var(--surface-1)] hover:border-[var(--hairline-strong)] hover:bg-[var(--surface-2)] p-2.5 text-left transition-all"
                    >
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--surface-2)] text-[var(--accent)] border border-[var(--hairline)]">
                        <Icon className="h-3 w-3" />
                      </div>
                      <span className="text-[11px] font-medium text-[var(--ink-muted)] group-hover:text-[var(--ink)] transition-colors truncate">
                        {starter.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            effectiveMessages.map((m, idx) => (
              <MessageBubble
                key={m.id}
                msg={m}
                isLatest={idx === effectiveMessages.length - 1}
                isStreaming={isStreaming}
                thinkingStep={thinkingStep}
                copiedId={copiedId}
                onCopy={handleCopyText}
                onSelectCitation={setSelectedCitation}
              />
            ))
          )}
        </div>

        {/* ── Bottom Input Bar ────────────────────────────────────────── */}
        <ChatInput isStreaming={isStreaming} onSendMessage={handleSendMessage} />
      </section>

      {/* ── Slide-in Citation Detail Drawer ────────────── */}
      {selectedCitation && (
        <aside
          id="citation-inspector-drawer"
          className="absolute inset-y-0 right-0 w-80 sm:w-88 border-l border-[var(--hairline)] bg-[var(--surface-1)] p-4 shadow-2xl flex flex-col z-30 animate-in slide-in-from-right duration-200"
        >
          <div className="flex items-center justify-between border-b border-[var(--hairline)] pb-3">
            <div className="flex items-center gap-2">
              <Bookmark className="h-4 w-4 text-[var(--accent)]" />
              <h3 className="text-xs font-semibold text-[var(--ink)]">Source Citation</h3>
            </div>
            <button
              type="button"
              onClick={() => setSelectedCitation(null)}
              className="rounded p-1 text-[var(--ink-tertiary)] hover:text-[var(--ink)] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 flex-1 overflow-y-auto space-y-3 text-xs">
            <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3 space-y-1.5">
              <span className="text-[10px] text-[var(--ink-tertiary)] uppercase tracking-wider font-medium">
                Document Page
              </span>
              <p className="text-sm font-semibold text-[var(--ink)]">
                Page {selectedCitation.page_number}
              </p>
              {selectedCitation.relevance_score && (
                <p className="text-[11px] text-emerald-400 font-mono">
                  Relevance Score: {(selectedCitation.relevance_score * 100).toFixed(1)}%
                </p>
              )}
            </div>

            <div className="rounded-xl border border-[var(--hairline)] bg-[var(--canvas)] p-3 space-y-1">
              <span className="text-[10px] text-[var(--ink-tertiary)] uppercase tracking-wider font-medium">
                Document Reference
              </span>
              <p className="font-mono text-[11px] text-[var(--ink-subtle)] break-all">
                {selectedCitation.document_id}
              </p>
            </div>
          </div>

          <div className="border-t border-[var(--hairline)] pt-3">
            <button
              type="button"
              onClick={() => setSelectedCitation(null)}
              className="w-full rounded-lg bg-[var(--surface-2)] hover:bg-[var(--surface-3)] text-xs text-[var(--ink-muted)] py-2 transition-colors font-medium border border-[var(--hairline)]"
            >
              Close
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
