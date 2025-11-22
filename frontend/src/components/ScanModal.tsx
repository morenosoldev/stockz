import { useRef } from "react";
import {
  X,
  Loader2,
  CheckCircle,
  XCircle,
  Activity,
  StopCircle,
} from "lucide-react";
import { useScanStore } from "@/stores/scanStore";
import { useScanLogs } from "@/hooks/useScanLogs";

export function ScanModal() {
  const {
    isOpen,
    runId,
    logs,
    stats,
    isStopping,
    closeModal,
    stopScan,
    reset,
  } = useScanStore();
  const logsEndRef = useRef<HTMLDivElement>(null);

  // SSE connection for streaming logs
  useScanLogs({
    runId,
    enabled: isOpen && !!runId,
    onComplete: () => {
      // Don't auto-close - let user manually close to review logs
      console.log("Scan completed. Modal remains open for log review.");
    },
    onError: (error) => {
      console.error("Scan logs error:", error);
    },
  });

  // Don't render if modal is closed
  if (!isOpen) {
    return null;
  }

  const isRunning = stats?.status === "running";
  const isCompleted = stats?.status === "completed";
  const isFailed = stats?.status === "failed";
  const isStopped = stats?.status === "stopped";
  const progress = stats?.totalTickers
    ? (stats.tickersProcessed / stats.totalTickers) * 100
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div
        className="bg-white dark:bg-gray-900 rounded-lg shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-800 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isRunning && (
                <Loader2 className="w-6 h-6 text-primary-500 animate-spin" />
              )}
              {isCompleted && (
                <CheckCircle className="w-6 h-6 text-success-500" />
              )}
              {isFailed && <XCircle className="w-6 h-6 text-error-500" />}
              {isStopped && <StopCircle className="w-6 h-6 text-warning-500" />}
              <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {isRunning &&
                    (isStopping ? "Stopping Scan..." : "Scanning Market...")}
                  {isCompleted && "Scan Complete!"}
                  {isFailed && "Scan Failed"}
                  {isStopped && "Scan Stopped"}
                </h2>
                {runId && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                    Run ID: {runId.slice(0, 8)}...
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => {
                closeModal();
                reset();
              }}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              disabled={isRunning}
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Progress Bar */}
          {stats && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-gray-600 dark:text-gray-400">
                  {stats.tickersProcessed} / {stats.totalTickers} tickers
                  processed
                </span>
                <span className="text-gray-900 dark:text-white font-semibold">
                  {progress.toFixed(0)}%
                </span>
              </div>
              <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    isCompleted
                      ? "bg-success-500"
                      : isFailed
                      ? "bg-error-500"
                      : isStopped
                      ? "bg-warning-500"
                      : "bg-primary-500"
                  }`}
                  style={{ width: `${Math.min(progress, 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Stats Grid */}
        {stats && (
          <div className="border-b border-gray-200 dark:border-gray-800 p-6">
            <div className="grid grid-cols-4 gap-4">
              <StatCard
                label="Processed"
                value={stats.tickersProcessed.toString()}
                icon={<Activity className="w-4 h-4" />}
              />
              <StatCard
                label="Candidates"
                value={stats.candidatesFound.toString()}
                icon={<CheckCircle className="w-4 h-4" />}
                valueClassName="text-success-600 dark:text-success-400"
              />
              <StatCard
                label="Errors"
                value={(stats.errors ?? 0).toString()}
                icon={<XCircle className="w-4 h-4" />}
                valueClassName={
                  (stats.errors ?? 0) > 0
                    ? "text-error-600 dark:text-error-400"
                    : ""
                }
              />
              <StatCard
                label="Duration"
                value={`${stats.durationSeconds}s`}
                icon={<Loader2 className="w-4 h-4" />}
              />
            </div>
          </div>
        )}

        {/* Logs Terminal */}
        <div className="flex-1 overflow-auto bg-gray-900 p-4 min-h-0">
          <div className="font-mono text-sm">
            {logs.length === 0 ? (
              <div className="text-gray-500 text-center py-8">
                Waiting for logs...
              </div>
            ) : (
              <div className="space-y-1">
                {logs.map((log, index) => (
                  <div key={index} className="flex gap-3">
                    <span className="text-gray-500 flex-shrink-0">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                    <span
                      className={`flex-1 ${
                        log.level === "error"
                          ? "text-error-400"
                          : log.level === "warning"
                          ? "text-warning-400"
                          : log.level === "debug"
                          ? "text-gray-500"
                          : "text-gray-300"
                      }`}
                    >
                      [{log.level.toUpperCase()}] {log.message}
                    </span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 dark:border-gray-800 p-4 bg-gray-50 dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {isRunning && !isStopping && "Scan in progress..."}
              {isRunning && isStopping && "Stopping scan gracefully..."}
              {isCompleted &&
                `Found ${
                  stats?.candidatesFound || 0
                } candidates! Review the logs above.`}
              {isFailed && "Scan failed. Check logs for details."}
              {isStopped &&
                "Scan was stopped by user. Partial results available."}
            </div>
            <div className="flex gap-2">
              {isRunning && !isStopping && (
                <button
                  onClick={stopScan}
                  className="px-4 py-2 bg-error-500 hover:bg-error-600 text-white rounded-lg transition-colors flex items-center gap-2"
                >
                  <StopCircle className="w-4 h-4" />
                  Stop Scan
                </button>
              )}
              <button
                onClick={() => {
                  closeModal();
                  reset();
                }}
                className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                disabled={isRunning && !isStopping}
              >
                {isRunning ? "Minimize" : "Close"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper component for stat cards
interface StatCardProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  valueClassName?: string;
}

function StatCard({ label, value, icon, valueClassName }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
      <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">
          {label}
        </span>
      </div>
      <div
        className={`text-xl font-bold ${
          valueClassName || "text-gray-900 dark:text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
