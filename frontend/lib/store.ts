import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { SystemSettings } from "@/components/SettingsModal";

export type ActiveTab = "chat" | "documents" | "admin";

const DEFAULT_SETTINGS: SystemSettings = {
  model: "anthropic/claude-3.5-sonnet",
  byokKey: "",
  topK: 5,
  enableWebSearch: true,
};

interface AppUIState {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;

  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;

  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;

  settings: SystemSettings;
  updateSettings: (settings: Partial<SystemSettings>) => void;
  setAllSettings: (settings: SystemSettings) => void;
}

export const useAppStore = create<AppUIState>()(
  persist(
    (set) => ({
      activeTab: "chat",
      setActiveTab: (activeTab) => set({ activeTab }),

      activeConversationId: null,
      setActiveConversationId: (activeConversationId) => set({ activeConversationId }),

      isSettingsOpen: false,
      setIsSettingsOpen: (isSettingsOpen) => set({ isSettingsOpen }),

      settings: DEFAULT_SETTINGS,
      updateSettings: (partial) =>
        set((state) => ({
          settings: { ...state.settings, ...partial },
        })),
      setAllSettings: (settings) => set({ settings }),
    }),
    {
      name: "enterprise_rag_ui_state",
      storage: createJSONStorage(() => localStorage),
      // Only persist user workflow preferences, avoiding stale transient modals
      partialize: (state) => ({
        activeTab: state.activeTab,
        activeConversationId: state.activeConversationId,
        settings: {
          model: state.settings.model,
          topK: state.settings.topK,
          enableWebSearch: state.settings.enableWebSearch,
          // Exclude byokKey from persistent localStorage for security
          byokKey: "",
        },
      }),
    }
  )
);
