import { create } from 'zustand';

export interface ScanLog {
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'debug';
  message: string;
}

export interface ScanStats {
  tickersProcessed: number;
  totalTickers: number;
  candidatesFound: number;
  errors: number;
  durationSeconds: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

interface ScanStore {
  // State
  isOpen: boolean;
  runId: string | null;
  logs: ScanLog[];
  stats: ScanStats | null;

  // Actions
  openModal: (runId: string) => void;
  closeModal: () => void;
  addLog: (log: ScanLog) => void;
  updateStats: (stats: Partial<ScanStats>) => void;
  reset: () => void;
}

const initialStats: ScanStats = {
  tickersProcessed: 0,
  totalTickers: 0,
  candidatesFound: 0,
  errors: 0,
  durationSeconds: 0,
  status: 'pending',
};

export const useScanStore = create<ScanStore>((set) => ({
  // Initial state
  isOpen: false,
  runId: null,
  logs: [],
  stats: null,

  // Open modal with run ID
  openModal: (runId: string) => {
    set({
      isOpen: true,
      runId,
      logs: [],
      stats: { ...initialStats, status: 'running' },
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
      stats: state.stats ? { ...state.stats, ...updates } : { ...initialStats, ...updates },
    }));
  },

  // Reset to initial state
  reset: () => {
    set({
      isOpen: false,
      runId: null,
      logs: [],
      stats: null,
    });
  },
}));
