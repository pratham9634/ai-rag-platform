"use client";

import React, { useState, useEffect } from "react";
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
    badgeColor: "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
    desc: "Top-tier agentic reasoning, citation accuracy & complex synthesis",
  },
  {
    id: "openai/gpt-4o-mini",
    name: "GPT-4o Mini",
    provider: "OpenAI",
    badge: "Fast & Low-Cost",
    badgeColor: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    desc: "Sub-second token latency, balanced precision and cost",
  },
  {
    id: "meta-llama/llama-3.1-8b-instruct:free",
    name: "Llama 3.1 8B Instruct",
    provider: "Meta (Open-Source)",
    badge: "100% Free Tier",
    badgeColor: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    desc: "Zero-cost open weights inference via OpenRouter free pool",
  },
  {
    id: "mistralai/mistral-7b-instruct:free",
    name: "Mistral 7B Instruct",
    provider: "Mistral AI",
    badge: "100% Free Tier",
    badgeColor: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    desc: "Fast, concise European open-source baseline model",
  },
];

export default function SettingsModal({
  isOpen,
  onClose,
  settings,
  onSave,
}: SettingsModalProps) {
  const [selectedModel, setSelectedModel] = useState(settings.model);
  const [byokKey, setByokKey] = useState(settings.byokKey);
  const [showKey, setShowKey] = useState(false);
  const [topK, setTopK] = useState(settings.topK);
  const [enableWebSearch, setEnableWebSearch] = useState(settings.enableWebSearch);
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    setSelectedModel(settings.model);
    setByokKey(settings.byokKey);
    setTopK(settings.topK);
    setEnableWebSearch(settings.enableWebSearch);
  }, [settings, isOpen]);

  if (!isOpen) return null;

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-white/[0.12] bg-[#090a0f] text-gray-100 shadow-2xl shadow-black/80"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-6 py-4.5 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-indigo-500/30 bg-indigo-500/10 text-indigo-400">
              <Sliders className="h-4.5 w-4.5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">System & Model Configuration</h2>
              <p className="text-xs text-gray-400">Customize LLM routing, ephemeral BYOK keys, and retrieval bounds</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-white/[0.06] hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="max-h-[75vh] overflow-y-auto p-6 space-y-6">
          {/* 1. LLM Model Selection */}
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
              <Cpu className="h-3.5 w-3.5 text-indigo-400" />
              Active Generation Model
            </label>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {AVAILABLE_MODELS.map((m) => {
                const isSelected = selectedModel === m.id;
                return (
                  <div
                    key={m.id}
                    onClick={() => setSelectedModel(m.id)}
                    className={`relative cursor-pointer rounded-xl border p-3.5 transition-all ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-500/[0.08] ring-1 ring-indigo-500/50 shadow-md shadow-indigo-500/10"
                        : "border-white/[0.08] bg-white/[0.02] hover:border-white/[0.18] hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-white">{m.name}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${m.badgeColor}`}>
                        {m.badge}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-gray-400 line-clamp-2 leading-relaxed">{m.desc}</p>
                    <span className="mt-2 block text-[10px] text-gray-400 font-mono">{m.provider}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 2. BYOK Key Configuration */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                <Key className="h-3.5 w-3.5 text-amber-400" />
                OpenRouter BYOK (Bring Your Own Key)
              </label>
              {byokKey && (
                <button
                  type="button"
                  onClick={handleClearKey}
                  className="text-[11px] text-rose-400 hover:text-rose-300 transition-colors"
                >
                  Clear Key
                </button>
              )}
            </div>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={byokKey}
                onChange={(e) => setByokKey(e.target.value)}
                placeholder="sk-or-v1-xxxxxxxxxxxxxxxx (Leave blank to use server default)"
                className="w-full rounded-xl border border-white/[0.1] bg-black/40 px-3.5 py-2.5 pr-20 text-xs text-white placeholder-gray-400 font-mono focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-gray-400 hover:text-white transition-colors"
              >
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-gray-400">
              <Shield className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
              <span>
                <strong>Ephemeral Security:</strong> Your key is stored in your browser session only. It is passed via
                headers and strictly scrubbed from server logs and traces.
              </span>
            </div>
          </div>

          {/* 3. Retrieval Parameters */}
          <div className="space-y-3 pt-2 border-t border-white/[0.08]">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold text-gray-200">Cross-Encoder Top-K Candidates</label>
                <p className="text-[11px] text-gray-400">Number of reranked chunks injected into grounded context</p>
              </div>
              <span className="rounded-md border border-white/[0.1] bg-white/[0.04] px-2.5 py-1 text-xs font-mono font-bold text-indigo-300">
                {topK} Chunks
              </span>
            </div>
            <input
              type="range"
              min={2}
              max={10}
              step={1}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
          </div>

          {/* 4. External Web Search Toggle */}
          <div className="flex items-center justify-between pt-2 border-t border-white/[0.08]">
            <div className="flex items-center gap-2.5">
              <div className="rounded-lg border border-teal-500/30 bg-teal-500/10 p-1.5 text-teal-400">
                <Globe className="h-4 w-4" />
              </div>
              <div>
                <span className="text-xs font-semibold text-gray-200">Autonomous Web Search Tool</span>
                <p className="text-[11px] text-gray-400">Allow agent to search public web when private docs lack answers</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enableWebSearch}
                onChange={(e) => setEnableWebSearch(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-10 h-5 bg-gray-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
            </label>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-white/[0.08] px-6 py-4 bg-white/[0.02]">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-white/[0.1] bg-white/[0.04] px-4 py-2 text-xs font-medium text-gray-300 hover:bg-white/[0.08] hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaved}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2 text-xs font-medium text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-500 transition-all"
          >
            {isSaved ? (
              <>
                <Check className="h-4 w-4" />
                Saved!
              </>
            ) : (
              "Save Changes"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
