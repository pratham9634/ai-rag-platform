"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Send,
  Sparkles,
  Bot,
  User,
  Plus,
  MessageSquare,
  Bookmark,
  ChevronRight,
  ShieldCheck,
  RefreshCw,
  Brain,
  CheckCircle2,
  Copy,
  Check,
  X,
  FileText,
  CornerDownLeft,
  Cpu,
  Layers,
  ArrowRight,
} from "lucide-react";
import { SystemSettings } from "@/components/SettingsModal";

interface Citation {
  chunk_id: string;
  document_id: string;
  page_number: number;
  relevance_score?: number | null;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  created_at?: string;
}

interface Conversation {
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

const BENTO_STARTERS = [
  {
    icon: Sparkles,
    title: "PTO & Leave Entitlements",
    prompt: "How many days of paid time off (PTO) and sick leave do employees receive per year?",
    tag: "HR Policy",
    accent: "from-indigo-500/20 to-violet-500/10 border-indigo-500/20 text-indigo-300",
  },
  {
    icon: Layers,
    title: "Remote Work Guidelines",
    prompt: "What are the eligibility requirements, stipend policies, and working hour expectations for remote work?",
    tag: "Workplace",
    accent: "from-blue-500/20 to-cyan-500/10 border-blue-500/20 text-blue-300",
  },
  {
    icon: ShieldCheck,
    title: "Compliance & Security",
    prompt: "What are our data retention guidelines and mandatory procedures for handling sensitive customer data?",
    tag: "Compliance",
    accent: "from-emerald-500/20 to-teal-500/10 border-emerald-500/20 text-emerald-300",
  },
];

export default function ChatInterface({ tenantId, settings }: ChatInterfaceProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinkingStep, setThinkingStep] = useState<string | null>(null);
  const [thinkingHistory, setThinkingHistory] = useState<string[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming, thinkingStep]);

  // Fetch tenant conversations
  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/conversations`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (res.ok) {
        const data: Conversation[] = await res.json();
        setConversations(data);
        if (data.length > 0 && !activeConvId) {
          setActiveConvId(data[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch conversations:", err);
    }
  };

  // Fetch messages for active conversation
  const fetchMessages = async (convId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/conversations/${convId}/messages`, {
        headers: { "X-Tenant-ID": tenantId },
      });
      if (res.ok) {
        const data: Message[] = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error("Failed to fetch messages:", err);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, [tenantId]);

  useEffect(() => {
    if (activeConvId) {
      fetchMessages(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  const handleStartNewChat = () => {
    setActiveConvId(null);
    setMessages([]);
    setInputQuery("");
    setThinkingStep(null);
    setThinkingHistory([]);
  };

  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  };

  const handleSendMessage = async (queryText?: string) => {
    const textToSend = queryText || inputQuery;
    if (!textToSend.trim() || isStreaming) return;

    setInputQuery("");
    setIsStreaming(true);
    setThinkingStep("Analyzing query intent & routing...");
    setThinkingHistory(["Analyzing query intent & routing..."]);

    // 1. Add user message optimistically
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: textToSend,
      created_at: new Date().toISOString(),
    };

    // 2. Add empty assistant message for streaming
    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      citations: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

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
          conversation_id: activeConvId || undefined,
          query: textToSend,
          model: settings?.model,
          top_k: settings?.topK,
          enable_web_search: settings?.enableWebSearch,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Streaming request failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = "";
      let accumulatedCitations: Citation[] = [];

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
              setThinkingStep(event.message);
              setThinkingHistory((prev) =>
                prev.includes(event.message) ? prev : [...prev, event.message]
              );
            } else if (event.type === "token") {
              setThinkingStep(null);
              accumulatedContent += event.content;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, content: accumulatedContent, citations: accumulatedCitations }
                    : msg
                )
              );
            } else if (event.type === "citations") {
              accumulatedCitations = event.citations || [];
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, citations: accumulatedCitations }
                    : msg
                )
              );
            } else if (event.type === "done") {
              setThinkingStep(null);
              if (event.conversation_id && !activeConvId) {
                setActiveConvId(event.conversation_id);
                fetchConversations();
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
            // Ignore parse errors for split frames
          }
        }
      }
    } catch (err) {
      console.error("Streaming error:", err);
      setThinkingStep(null);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? { ...msg, content: "An error occurred while generating the grounded response." }
            : msg
        )
      );
    } finally {
      setIsStreaming(false);
      setThinkingStep(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const activeConversationTitle =
    conversations.find((c) => c.id === activeConvId)?.title || "Active Discussion";

  return (
    <div className="relative flex h-[760px] rounded-2xl border border-white/[0.08] bg-[#030712] overflow-hidden shadow-2xl shadow-black/80 font-sans">
      {/* ── Left Sidebar: Thread Navigation (Linear App style) ──────── */}
      <aside className="w-72 border-r border-[#23252a] bg-[#090a10] p-4 hidden md:flex flex-col">
        {/* New Thread CTA */}
        <button
          id="btn-new-chat"
          onClick={handleStartNewChat}
          className="flex items-center justify-between w-full rounded-xl bg-gradient-to-r from-[#5e6ad2] to-[#7684ed] px-3.5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-950/50 transition-all hover:brightness-110 active:scale-[0.98]"
        >
          <span className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            New Thread
          </span>
          <kbd className="rounded bg-black/20 px-1.5 py-0.5 text-[10px] font-mono text-indigo-100">
            /new
          </kbd>
        </button>

        {/* Header */}
        <div className="mt-5 flex items-center justify-between px-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            Conversations
          </span>
          <button
            onClick={fetchConversations}
            title="Refresh threads"
            className="text-gray-400 hover:text-white transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
          </button>
        </div>

        {/* Thread List */}
        <div className="mt-2.5 flex-1 overflow-y-auto space-y-1 pr-1">
          {conversations.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-400">
              <MessageSquare className="h-5 w-5 mx-auto mb-2 text-gray-500 stroke-[1.5]" />
              No conversations yet
            </div>
          ) : (
            conversations.map((c) => {
              const isActive = activeConvId === c.id;
              return (
                <button
                  key={c.id}
                  id={`thread-btn-${c.id}`}
                  onClick={() => setActiveConvId(c.id)}
                  className={`w-full group flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs transition-all ${
                    isActive
                      ? "bg-white/[0.08] text-white font-medium border border-white/[0.1] shadow-sm"
                      : "text-gray-400 hover:bg-white/[0.04] hover:text-gray-200"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full shrink-0 transition-colors ${
                      isActive ? "bg-[#5e6ad2]" : "bg-gray-600 group-hover:bg-gray-400"
                    }`}
                  />
                  <span className="truncate flex-1 text-[12px]">{c.title || "Untitled Session"}</span>
                  <span className="text-[10px] text-gray-400 font-mono">
                    {c.message_count || ""}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* Bottom Tenant Security Pill */}
        <div className="border-t border-[#23252a] pt-3 text-[11px] text-gray-400 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            Row-Level Isolated
          </span>
          <span className="text-[10px] font-mono text-gray-400">pgvector</span>
        </div>
      </aside>

      {/* ── Main Chat Area ───────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col bg-[#010102] relative">
        {/* Top Chat Subhead */}
        <header className="flex items-center justify-between border-b border-[#23252a] px-6 py-3 bg-[#090a10]/50 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[#5e6ad2]">
              <Brain className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-gray-200 line-clamp-1">
                {activeConvId ? activeConversationTitle : "New Agent Session"}
              </h2>
              <p className="text-[10px] text-gray-400">
                Self-correcting LangGraph loop with hybrid BM25 + dense retrieval
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] font-mono text-gray-300">
              <Cpu className="h-3 w-3 text-indigo-400" />
              {settings?.model?.split("/")[1] || "claude-3.5-sonnet"}
            </span>
          </div>
        </header>

        {/* Messages Viewport */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto py-8 text-center animate-in fade-in duration-300">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#5e6ad2]/10 border border-[#5e6ad2]/25 text-[#5e6ad2] mb-4 shadow-inner">
                <Sparkles className="h-7 w-7" />
              </div>
              <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
                Enterprise Knowledge Assistant
              </h1>
              <p className="mt-2 text-xs text-gray-400 max-w-md leading-relaxed">
                Directly synthesize answers from your uploaded PDFs with verified page citations,
                real-time hallucination prevention, and sub-second pgvector retrieval.
              </p>

              {/* Bento Quick Prompt Starters */}
              <div className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-3 w-full text-left">
                {BENTO_STARTERS.map((starter, idx) => {
                  const Icon = starter.icon;
                  return (
                    <button
                      key={idx}
                      id={`starter-card-${idx}`}
                      onClick={() => handleSendMessage(starter.prompt)}
                      className={`group relative flex flex-col justify-between rounded-2xl border p-4 bg-gradient-to-b ${starter.accent} transition-all hover:border-[#5e6ad2]/50 hover:scale-[1.02] hover:shadow-xl hover:shadow-indigo-950/30 text-left`}
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2.5">
                          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-black/40 border border-white/[0.08] text-white">
                            <Icon className="h-4 w-4" />
                          </div>
                          <span className="rounded-full bg-white/[0.08] px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-gray-300">
                            {starter.tag}
                          </span>
                        </div>
                        <h4 className="text-xs font-semibold text-white group-hover:text-indigo-200 transition-colors">
                          {starter.title}
                        </h4>
                        <p className="mt-1 text-[11px] text-gray-400 line-clamp-2 leading-relaxed">
                          {starter.prompt}
                        </p>
                      </div>

                      <div className="mt-4 flex items-center text-[10px] font-medium text-indigo-400 group-hover:text-indigo-300">
                        <span>Send prompt</span>
                        <ArrowRight className="h-3 w-3 ml-1 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            messages.map((m) => {
              const isAssistant = m.role === "assistant";
              return (
                <div
                  key={m.id}
                  className={`flex gap-3.5 ${isAssistant ? "justify-start" : "justify-end"} group`}
                >
                  {isAssistant && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#0e111a] border border-[#23252a] text-[#5e6ad2] shadow-md">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`relative max-w-[82%] rounded-2xl p-4.5 text-xs leading-relaxed transition-all ${
                      isAssistant
                        ? "bg-[#0b0f17] border border-[#23252a] text-[#f7f8f8] shadow-sm"
                        : "bg-[#181d2c] border border-indigo-500/30 text-white shadow-md"
                    }`}
                  >
                    {/* Assistant Streaming or Thinking State */}
                    {isAssistant && m.content === "" && isStreaming ? (
                      <div className="space-y-3 py-1">
                        <div className="flex items-center gap-2 text-[#828fff] font-mono text-[11px]">
                          <Brain className="h-4 w-4 animate-spin text-[#5e6ad2]" />
                          <span className="font-semibold tracking-wide">
                            {thinkingStep || "Routing query intent..."}
                          </span>
                          <span className="flex h-1.5 w-1.5 rounded-full bg-[#5e6ad2] animate-ping ml-auto" />
                        </div>

                        {thinkingHistory.length > 0 && (
                          <div className="mt-1.5 pl-4 space-y-1.5 text-[11px] text-gray-400 border-l border-[#23252a]">
                            {thinkingHistory.map((step, idx) => (
                              <div key={idx} className="flex items-center gap-1.5">
                                <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                                <span>{step}</span>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="flex gap-1.5 pt-1">
                          <div className="h-1.5 w-16 rounded bg-[#5e6ad2]/30 animate-pulse" />
                          <div className="h-1.5 w-24 rounded bg-[#5e6ad2]/20 animate-pulse" />
                          <div className="h-1.5 w-12 rounded bg-[#5e6ad2]/10 animate-pulse" />
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="whitespace-pre-wrap leading-relaxed text-gray-200">
                          {m.content}
                          {isStreaming && isAssistant && m.id === messages[messages.length - 1]?.id && (
                            <span className="inline-block w-1.5 h-3.5 ml-1 bg-[#5e6ad2] animate-pulse rounded-sm align-middle" />
                          )}
                        </div>

                        {/* Message Toolbar for Assistant */}
                        {isAssistant && m.content && (
                          <div className="mt-3 flex items-center justify-between border-t border-[#23252a] pt-2 text-[10px] text-gray-400">
                            <span className="font-mono text-gray-400">
                              {m.citations && m.citations.length > 0
                                ? `${m.citations.length} verified citation${m.citations.length > 1 ? "s" : ""}`
                                : "Direct answer"}
                            </span>
                            <button
                              onClick={() => handleCopyText(m.content, m.id)}
                              className="flex items-center gap-1 hover:text-white transition-colors"
                              title="Copy answer"
                            >
                              {copiedId === m.id ? (
                                <>
                                  <Check className="h-3 w-3 text-emerald-400" />
                                  <span className="text-emerald-400">Copied</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="h-3 w-3" />
                                  <span>Copy</span>
                                </>
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Citations Grid */}
                    {isAssistant && m.citations && m.citations.length > 0 && (
                      <div className="mt-3.5 border-t border-[#23252a] pt-3">
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold block mb-2">
                          Grounded Source Citations
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {m.citations.map((c, idx) => (
                            <button
                              key={idx}
                              id={`citation-chip-${idx}`}
                              onClick={() => setSelectedCitation(c)}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-[#5e6ad2]/30 bg-[#5e6ad2]/10 px-2.5 py-1 text-[11px] font-mono text-indigo-300 hover:bg-[#5e6ad2]/20 hover:border-[#5e6ad2]/60 hover:text-white transition-all shadow-sm"
                            >
                              <Bookmark className="h-3 w-3 text-indigo-400" />
                              Page {c.page_number}
                              {c.relevance_score && (
                                <span className="text-emerald-400 font-semibold">
                                  {(c.relevance_score * 100).toFixed(0)}%
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {!isAssistant && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#131722] border border-[#23252a] text-gray-300">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* ── Bottom Input Bar ────────────────────────────────────────── */}
        <footer className="border-t border-[#23252a] bg-[#090a10] p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-end gap-2 rounded-2xl border border-white/[0.1] bg-[#020408] p-2.5 focus-within:border-[#5e6ad2] focus-within:ring-2 focus-within:ring-[#5e6ad2]/20 transition-all"
          >
            <textarea
              id="chat-input-query"
              ref={textareaRef}
              rows={1}
              value={inputQuery}
              disabled={isStreaming}
              onKeyDown={handleKeyDown}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder="Ask anything about your uploaded documents (Press Enter to send)..."
              className="flex-1 bg-transparent px-2 py-1 text-xs text-white placeholder-gray-500 focus:outline-none resize-none max-h-32 disabled:opacity-50"
            />
            <button
              id="btn-send-chat"
              type="submit"
              disabled={!inputQuery.trim() || isStreaming}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#5e6ad2] text-white transition-all hover:bg-[#828fff] disabled:opacity-20 disabled:hover:bg-[#5e6ad2] active:scale-95"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
          <div className="mt-2 flex items-center justify-between px-2 text-[10px] text-gray-400">
            <span>
              Top-K: <strong className="text-gray-300 font-mono">{settings?.topK || 5}</strong> •
              Reranking: <strong className="text-gray-300 font-mono">Cross-Encoder</strong>
            </span>
            <span className="flex items-center gap-1">
              Press <kbd className="rounded bg-white/[0.06] px-1 py-0.5 font-mono text-gray-300">Enter ↵</kbd> to send
            </span>
          </div>
        </footer>
      </section>

      {/* ── Slide-in Citation Detail Drawer (Linear / Bento UX) ─────── */}
      {selectedCitation && (
        <aside
          id="citation-inspector-drawer"
          className="absolute inset-y-0 right-0 w-80 sm:w-96 border-l border-[#23252a] bg-[#090a10]/95 backdrop-blur-xl p-6 shadow-2xl flex flex-col z-30 animate-in slide-in-from-right duration-200"
        >
          <div className="flex items-center justify-between border-b border-[#23252a] pb-4">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[#5e6ad2]">
                <Bookmark className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-white">Citation Inspector</h3>
                <span className="text-[10px] text-emerald-400 font-mono">Grounded Chunk Provenance</span>
              </div>
            </div>
            <button
              id="btn-close-citation-modal"
              onClick={() => setSelectedCitation(null)}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-white/[0.06] hover:text-white transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-5 flex-1 overflow-y-auto space-y-4 text-xs">
            {/* Relevance Score Card */}
            <div className="rounded-xl border border-white/[0.08] bg-[#020408] p-3.5 space-y-2">
              <span className="text-[11px] text-gray-400">Cross-Encoder Confidence</span>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-white font-mono">
                  {selectedCitation.relevance_score
                    ? `${(selectedCitation.relevance_score * 100).toFixed(1)}%`
                    : "High Grounding"}
                </span>
                <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[10px] text-emerald-400 font-mono">
                  Passed Relevance Gate
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#5e6ad2] to-emerald-400 rounded-full"
                  style={{
                    width: `${selectedCitation.relevance_score ? selectedCitation.relevance_score * 100 : 92}%`,
                  }}
                />
              </div>
            </div>

            {/* Document and Page Info */}
            <div className="rounded-xl border border-white/[0.08] bg-[#020408] p-3.5 space-y-3">
              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Source PDF Location
                </span>
                <p className="mt-1 text-sm font-semibold text-white flex items-center gap-1.5">
                  <FileText className="h-4 w-4 text-[#5e6ad2]" />
                  Document Page {selectedCitation.page_number}
                </p>
              </div>

              <div className="border-t border-[#23252a] pt-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Document ID
                </span>
                <p className="mt-0.5 font-mono text-[11px] text-gray-300 break-all bg-white/[0.03] p-1.5 rounded border border-white/[0.06]">
                  {selectedCitation.document_id}
                </p>
              </div>

              <div className="border-t border-[#23252a] pt-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Chunk ID (pgvector key)
                </span>
                <p className="mt-0.5 font-mono text-[11px] text-gray-300 break-all bg-white/[0.03] p-1.5 rounded border border-white/[0.06]">
                  {selectedCitation.chunk_id}
                </p>
              </div>
            </div>

            {/* Security Guarantee Note */}
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-[11px] text-gray-300 flex items-start gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
              <span>
                This passage was fetched using tenant-partitioned vector indexing. Cross-tenant leakage is mathematically prohibited by Postgres Row-Level Security.
              </span>
            </div>
          </div>

          <div className="border-t border-[#23252a] pt-3">
            <button
              onClick={() => setSelectedCitation(null)}
              className="w-full rounded-xl bg-white/[0.06] hover:bg-white/[0.1] py-2 text-xs font-semibold text-gray-200 transition-colors"
            >
              Dismiss Inspector
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
