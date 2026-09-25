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
} from "lucide-react";

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
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const QUICK_PROMPTS = [
  "How many days of paid time off do employees get?",
  "What are the remote work eligibility guidelines?",
  "What is our policy on bereavement and medical leave?",
];

export default function ChatInterface({ tenantId }: ChatInterfaceProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinkingStep, setThinkingStep] = useState<string | null>(null);
  const [thinkingHistory, setThinkingHistory] = useState<string[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

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
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-ID": tenantId,
        },
        body: JSON.stringify({
          conversation_id: activeConvId || undefined,
          query: textToSend,
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
            // Ignore parse errors for split chunk frames
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

  return (
    <div className="flex h-[720px] rounded-2xl border border-white/[0.08] bg-gray-900/40 backdrop-blur-xl overflow-hidden shadow-2xl shadow-black/60">
      {/* Sidebar: Conversation Threads */}
      <div className="w-64 border-r border-white/[0.06] bg-gray-950/60 p-4 hidden md:flex flex-col">
        <button
          id="btn-new-chat"
          onClick={handleStartNewChat}
          className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:from-indigo-500 hover:to-violet-500 hover:shadow-indigo-500/35"
        >
          <Plus className="h-4 w-4" />
          New Thread
        </button>

        <div className="mt-4 flex items-center justify-between px-1">
          <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
            Recent Threads
          </span>
          <button onClick={fetchConversations} className="text-gray-400 hover:text-white">
            <RefreshCw className="h-3 w-3" />
          </button>
        </div>

        <div className="mt-2 flex-1 overflow-y-auto space-y-1 pr-1">
          {conversations.length === 0 ? (
            <div className="p-4 text-center text-xs text-gray-500">No chat history</div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                id={`thread-btn-${c.id}`}
                onClick={() => setActiveConvId(c.id)}
                className={`w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                  activeConvId === c.id
                    ? "bg-white/[0.08] text-white font-medium border border-white/[0.08]"
                    : "text-gray-400 hover:bg-white/[0.04] hover:text-gray-200"
                }`}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                <span className="truncate flex-1">{c.title || "Untitled Conversation"}</span>
              </button>
            ))
          )}
        </div>

        <div className="border-t border-white/[0.06] pt-3 text-[11px] text-gray-400 flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
          <span>Tenant Isolated History</span>
        </div>
      </div>

      {/* Main Chat Feed */}
      <div className="flex-1 flex flex-col bg-gray-900/20">
        {/* Messages Viewport */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 mb-3">
                <Sparkles className="h-6 w-6" />
              </div>
              <h2 className="text-base font-semibold text-white">Ask Enterprise Agent</h2>
              <p className="mt-1 text-xs text-gray-400">
                Queries are routed through dense pgvector and full-text keyword retrieval, evaluated by LangGraph, and grounded with source page citations.
              </p>

              {/* Quick Prompt Pills */}
              <div className="mt-6 w-full space-y-2">
                {QUICK_PROMPTS.map((prompt, i) => (
                  <button
                    key={i}
                    id={`quick-prompt-${i}`}
                    onClick={() => handleSendMessage(prompt)}
                    className="w-full flex items-center justify-between rounded-xl border border-white/[0.06] bg-gray-900/60 px-3.5 py-2.5 text-left text-xs text-gray-300 transition-all hover:border-indigo-500/40 hover:bg-gray-800/80 hover:text-white"
                  >
                    <span>{prompt}</span>
                    <ChevronRight className="h-3.5 w-3.5 text-gray-400" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => {
              const isAssistant = m.role === "assistant";
              return (
                <div
                  key={m.id}
                  className={`flex gap-3.5 ${isAssistant ? "justify-start" : "justify-end"}`}
                >
                  {isAssistant && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 shadow-md">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[80%] rounded-2xl p-4 text-xs leading-relaxed ${
                      isAssistant
                        ? "bg-gray-900/80 border border-white/[0.08] text-gray-100 shadow-sm"
                        : "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                    }`}
                  >
                    {isAssistant && m.content === "" && isStreaming ? (
                      <div className="space-y-2 py-1">
                        <div className="flex items-center gap-2 text-indigo-400 font-mono text-[11px]">
                          <Brain className="h-4 w-4 animate-spin text-indigo-400" />
                          <span className="font-semibold tracking-wide">
                            {thinkingStep || "Thinking & Routing..."}
                          </span>
                          <span className="flex h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping ml-auto" />
                        </div>
                        {thinkingHistory.length > 0 && (
                          <div className="mt-1.5 pl-5 space-y-1 text-[11px] text-gray-400 border-l border-indigo-500/20">
                            {thinkingHistory.map((step, idx) => (
                              <div key={idx} className="flex items-center gap-1.5">
                                <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                                <span>{step}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="flex gap-1.5 pt-1">
                          <div className="h-1.5 w-12 rounded bg-indigo-500/30 animate-pulse" />
                          <div className="h-1.5 w-20 rounded bg-indigo-500/20 animate-pulse" />
                          <div className="h-1.5 w-10 rounded bg-indigo-500/10 animate-pulse" />
                        </div>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">
                        {m.content}
                        {isStreaming && isAssistant && m.id === messages[messages.length - 1]?.id && (
                          <span className="inline-block w-1.5 h-3.5 ml-1 bg-indigo-400 animate-pulse rounded-sm align-middle" />
                        )}
                      </p>
                    )}

                    {/* Citations Footer */}
                    {isAssistant && m.citations && m.citations.length > 0 && (
                      <div className="mt-3.5 border-t border-white/[0.08] pt-2.5">
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold block mb-1.5">
                          Verified Grounded Citations
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {m.citations.map((c, idx) => (
                            <button
                              key={idx}
                              id={`citation-chip-${idx}`}
                              onClick={() => setSelectedCitation(c)}
                              className="inline-flex items-center gap-1 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2 py-1 text-[11px] font-mono text-indigo-300 hover:bg-indigo-500/20 hover:border-indigo-500/50 transition-colors"
                            >
                              <Bookmark className="h-3 w-3 text-indigo-400" />
                              Page {c.page_number}
                              {c.relevance_score && (
                                <span className="text-gray-400">
                                  ({(c.relevance_score * 100).toFixed(0)}%)
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {!isAssistant && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gray-800 border border-gray-700 text-gray-300">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Query Input Bar */}
        <div className="border-t border-white/[0.06] bg-gray-950/70 p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2 rounded-xl border border-white/[0.1] bg-gray-900/80 px-4 py-2.5 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all"
          >
            <input
              id="chat-input-query"
              type="text"
              value={inputQuery}
              disabled={isStreaming}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder="Ask anything about your uploaded documents..."
              className="flex-1 bg-transparent text-xs text-white placeholder-gray-500 focus:outline-none disabled:opacity-50"
            />
            <button
              id="btn-send-chat"
              type="submit"
              disabled={!inputQuery.trim() || isStreaming}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white transition-all hover:bg-indigo-500 disabled:opacity-30 disabled:hover:bg-indigo-600"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      </div>

      {/* Citation Detail Modal */}
      {selectedCitation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-white/[0.12] bg-gray-900 p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-3 mb-4">
              <div className="flex items-center gap-2">
                <Bookmark className="h-4 w-4 text-indigo-400" />
                <h3 className="text-sm font-semibold text-white">Grounded Source Citation</h3>
              </div>
              <button
                id="btn-close-citation-modal"
                onClick={() => setSelectedCitation(null)}
                className="text-xs text-gray-400 hover:text-white"
              >
                Close
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-gray-400">Document ID:</span>
                <p className="font-mono text-gray-200 mt-0.5">{selectedCitation.document_id}</p>
              </div>
              <div>
                <span className="text-gray-400">Chunk ID:</span>
                <p className="font-mono text-gray-200 mt-0.5">{selectedCitation.chunk_id}</p>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-gray-400">Source PDF Page:</span>
                  <p className="text-white font-semibold mt-0.5">Page {selectedCitation.page_number}</p>
                </div>
                {selectedCitation.relevance_score && (
                  <div>
                    <span className="text-gray-400">Cross-Encoder Relevance:</span>
                    <p className="text-emerald-400 font-semibold mt-0.5">
                      {(selectedCitation.relevance_score * 100).toFixed(1)}%
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
