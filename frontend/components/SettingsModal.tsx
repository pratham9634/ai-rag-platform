"use client";

import React, { useState } from "react";
import { X, Key, Cpu, Sliders, Shield, Check, Globe } from "lucide-react";

export interface SystemSettings {
  model: string;
  byokKey: string;
  topK: number;
  enableWebSearch: boolean;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: SystemSettings;
  onSave: (newSettings: SystemSettings) => void;
}

const AVAILABLE_MODELS = [
  {
    id: "anthropic/claude-3.5-sonnet",
    name: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    badge: "Recommended",
    desc: "Top-tier agentic reasoning, citation accuracy & complex synthesis",
  },
  {
    id: "openai/gpt-4o-mini",
    name: "GPT-4o Mini",
    provider: "OpenAI",
    badge: "Fast & Efficient",
    desc: "Sub-second token latency, balanced precision and cost",
  },
  {
    id: "meta-llama/llama-3.1-8b-instruct:free",
    name: "Llama 3.1 8B Instruct",
    provider: "Meta (Open-Source)",
    badge: "100% Free Tier",
    desc: "Zero-cost open weights inference via OpenRouter free pool",
  },
  {
    id: "mistralai/mistral-7b-instruct:free",
    name: "Mistral 7B Instruct",
    provider: "Mistral AI",
    badge: "100% Free Tier",
    desc: "Fast, concise European open-source baseline model",
  },
];

function SettingsModalContent({
  onClose,
  settings,
  onSave,
}: {
  onClose: () => void;
  settings: SystemSettings;
  onSave: (newSettings: SystemSettings) => void;
}) {
  const [selectedModel, setSelectedModel] = useState(settings.model);
  const [byokKey, setByokKey] = useState(settings.byokKey);
  const [showKey, setShowKey] = useState(false);
  const [topK, setTopK] = useState(settings.topK);
  const [enableWebSearch, setEnableWebSearch] = useState(settings.enableWebSearch);
  const [isSaved, setIsSaved] = useState(false);

  const handleSave = () => {
    onSave({
      model: selectedModel,
      byokKey: byokKey.trim(),
      topK,
      enableWebSearch,
    });
    setIsSaved(true);
    setTimeout(() => {
      setIsSaved(false);
      onClose();
    }, 600);
  };

  const handleClearKey = () => {
    setByokKey("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div
        className="relative w-full max-w-xl overflow-hidden rounded-[var(--radius-xl)] border border-[var(--hairline)] bg-[var(--surface-1)] text-[var(--ink)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--hairline)] px-6 py-4 bg-[var(--surface-2)]">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent-muted)] border border-[var(--accent)]/20 text-[var(--accent)]">
              <Sliders className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[var(--ink)] tracking-[-0.01em]">Inference & Model Settings</h2>
              <p className="text-[11px] text-[var(--ink-subtle)]">
                Configure primary LLM provider, BYOK credentials, and retrieval depth
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-[var(--ink-tertiary)] hover:text-[var(--ink)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[75vh] overflow-y-auto p-6 space-y-6 text-xs">
          {/* Section 1: Model Selection */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[var(--ink)] flex items-center gap-1.5">
                <Cpu className="h-3.5 w-3.5 text-[var(--accent)]" />
                Select Language Model
              </label>
              <span className="text-[11px] text-[var(--ink-tertiary)] font-mono">OpenRouter Gateway</span>
            </div>

            <div className="grid grid-cols-1 gap-2.5">
              {AVAILABLE_MODELS.map((m) => {
                const isSelected = selectedModel === m.id;
                return (
                  <div
                    key={m.id}
                    onClick={() => setSelectedModel(m.id)}
                    className={`cursor-pointer rounded-[var(--radius-lg)] border p-3 transition-all ${
                      isSelected
                        ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
                        : "border-[var(--hairline)] bg-[var(--canvas)] hover:border-[var(--hairline-strong)] hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full transition-colors ${
                            isSelected ? "bg-[var(--accent)]" : "bg-[var(--ink-tertiary)]"
                          }`}
                        />
                        <span className="font-semibold text-[var(--ink)] text-xs">{m.name}</span>
                        <span className="text-[10px] text-[var(--ink-tertiary)] font-mono">({m.provider})</span>
                      </div>
                      <span className={`rounded-[var(--radius-sm)] border px-2 py-0.5 text-[10px] font-mono ${
                        isSelected
                          ? "border-[var(--accent)]/30 bg-[var(--accent-muted)] text-[var(--accent)]"
                          : "border-[var(--hairline)] bg-[var(--surface-2)] text-[var(--ink-subtle)]"
                      }`}>
                        {m.badge}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[var(--ink-subtle)] pl-4">{m.desc}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section 2: BYOK (Bring Your Own Key) */}
          <div className="space-y-2 border-t border-[var(--hairline)] pt-5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[var(--ink)] flex items-center gap-1.5">
                <Key className="h-3.5 w-3.5 text-[var(--accent)]" />
                Bring Your Own Key (BYOK)
              </label>
              <span className="text-[10px] font-mono text-[var(--ink-tertiary)]">Ephemeral Session</span>
            </div>
            <p className="text-[11px] text-[var(--ink-subtle)] leading-relaxed">
              Supply an OpenRouter API key (<code className="text-[var(--ink-muted)]">sk-or-v1-...</code>) to use your own quota.
              Held in browser memory only and passed via headers. Zero database persistence.
            </p>

            <div className="relative mt-2 flex items-center">
              <input
                type={showKey ? "text" : "password"}
                value={byokKey}
                onChange={(e) => setByokKey(e.target.value)}
                placeholder="sk-or-v1-xxxxxxxxxxxxxxxx..."
                className="w-full rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--canvas)] px-3 py-2 pr-20 text-xs font-mono text-[var(--ink)] placeholder-[var(--ink-tertiary)] focus:border-[var(--accent)]/50 focus:outline-none transition-colors"
              />
              <div className="absolute right-2 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="rounded px-1.5 py-0.5 text-[10px] text-[var(--ink-subtle)] hover:text-[var(--ink)]"
                >
                  {showKey ? "Hide" : "Show"}
                </button>
                {byokKey && (
                  <button
                    type="button"
                    onClick={handleClearKey}
                    className="rounded px-1.5 py-0.5 text-[10px] text-red-400 hover:text-red-300"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--ink-tertiary)]">
              <Shield className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span>If left blank, the platform defaults to server-configured open-weight models.</span>
            </div>
          </div>

          {/* Section 3: Retrieval Depth (Top-K) */}
          <div className="space-y-2 border-t border-[var(--hairline)] pt-5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[var(--ink)] flex items-center gap-1.5">
                <Sliders className="h-3.5 w-3.5 text-[var(--accent)]" />
                Retrieval Depth (Top-K Candidates)
              </label>
              <span className="font-mono text-xs font-bold text-[var(--accent)]">{topK} chunks</span>
            </div>
            <p className="text-[11px] text-[var(--ink-subtle)]">
              Number of hybrid-retrieved and reranked chunks provided to the generator context window.
            </p>
            <input
              type="range"
              min={2}
              max={15}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-[10px] text-[var(--ink-tertiary)] font-mono">
              <span>2 (Fastest)</span>
              <span>5 (Recommended)</span>
              <span>15 (Deep Synthesis)</span>
            </div>
          </div>

          {/* Section 4: Web Search Toggle */}
          <div className="flex items-center justify-between rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--canvas)] p-3.5">
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-[var(--ink)] flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-[var(--accent)]" />
                Augment with Web Search
              </span>
              <p className="text-[11px] text-[var(--ink-subtle)]">
                Fallback to live search when query relevance falls below confidence threshold
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enableWebSearch}
                onChange={(e) => setEnableWebSearch(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-[var(--surface-3)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[var(--ink-subtle)] after:border-[var(--hairline)] after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[var(--accent)] peer-checked:after:bg-white peer-checked:after:border-white"></div>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[var(--hairline)] px-6 py-4 bg-[var(--surface-2)]">
          <button
            onClick={onClose}
            className="rounded-[var(--radius-md)] px-3 py-1.5 text-xs text-[var(--ink-subtle)] hover:text-[var(--ink)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="btn-primary"
          >
            {isSaved ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-300" />
                <span>Saved</span>
              </>
            ) : (
              <span>Save Preferences</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SettingsModal({
  isOpen,
  onClose,
  settings,
  onSave,
}: SettingsModalProps) {
  if (!isOpen) return null;

  return (
    <SettingsModalContent
      key={`${settings.model}-${settings.topK}-${settings.enableWebSearch}`}
      onClose={onClose}
      settings={settings}
      onSave={onSave}
    />
  );
}
