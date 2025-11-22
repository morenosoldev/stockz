import { create } from "zustand";

export interface ScanLog {
  timestamp: string;
  level: "info" | "warning" | "error" | "debug";
  message: string;
}

export interface ScanStats {
  tickersProcessed: number;
  totalTickers: number;
  candidatesFound: number;
  errors: number;
  durationSeconds: number;
  status: "pending" | "running" | "completed" | "failed" | "stopped";
}

interface ScanStore {
  // State
  isOpen: boolean;
  runId: string | null;
  logs: ScanLog[];
  stats: ScanStats | null;
  isStopping: boolean;

  // Actions
  openModal: (runId: string) => void;
  closeModal: () => void;
  addLog: (log: ScanLog) => void;
  updateStats: (stats: Partial<ScanStats>) => void;
  stopScan: () => Promise<void>;
  reset: () => void;
}

const initialStats: ScanStats = {
  tickersProcessed: 0,
  totalTickers: 0,
  candidatesFound: 0,
  errors: 0,
  durationSeconds: 0,
  status: "pending",
};

export const useScanStore = create<ScanStore>((set, get) => ({
  // Initial state
  isOpen: false,
  runId: null,
  logs: [],
  stats: null,
  isStopping: false,

  // Open modal with run ID
  openModal: (runId: string) => {
    set({
      isOpen: true,
      runId,
      logs: [],
      stats: { ...initialStats, status: "running" },
      isStopping: false,
    });
  },

  // Close modal
  closeModal: () => {
    set({ isOpen: false });
  },

  // Add a log entry
  addLog: (log: ScanLog) => {
    set((state) => ({
      logs: [...state.logs, log],
    }));
  },

  // Update stats
  updateStats: (updates: Partial<ScanStats>) => {
    set((state) => ({
      stats: state.stats
        ? { ...state.stats, ...updates }
        : { ...initialStats, ...updates },
    }));
  },

  // Stop the currently running scan
  stopScan: async () => {
    const { runId, isStopping } = get();

    if (!runId || isStopping) {
      return;
    }

    set({ isStopping: true });

    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const response = await fetch(`${baseUrl}/v1/scan/${runId}/stop`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to stop scan");
      }

      // Add a log entry about the stop request
      set((state) => ({
        logs: [
          ...state.logs,
          {
            timestamp: new Date().toISOString(),
            level: "warning" as const,
            message: "Stop request sent - scan will terminate gracefully",
          },
        ],
      }));
    } catch (error) {
      console.error("Failed to stop scan:", error);

      // Add error log
      set((state) => ({
        logs: [
          ...state.logs,
          {
            timestamp: new Date().toISOString(),
            level: "error" as const,
            message: `Failed to stop scan: ${
              error instanceof Error ? error.message : "Unknown error"
            }`,
          },
        ],
        isStopping: false,
      }));
    }
  },

  // Reset to initial state
  reset: () => {
    set({
      isOpen: false,
      runId: null,
      logs: [],
      stats: null,
      isStopping: false,
    });
  },
}));
