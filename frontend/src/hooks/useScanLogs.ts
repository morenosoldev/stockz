import { useEffect, useRef } from "react";
import { useScanStore, type ScanLog } from "@/stores/scanStore";

export interface UseScanLogsOptions {
  runId: string | null;
  enabled?: boolean;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to stream scan logs via Server-Sent Events (SSE)
 */
export function useScanLogs({
  runId,
  enabled = true,
  onComplete,
  onError,
}: UseScanLogsOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const { addLog, updateStats } = useScanStore();

  useEffect(() => {
    // Don't connect if disabled or no runId
    if (!enabled || !runId) {
      return;
    }

    // Prevent duplicate connections
    if (eventSourceRef.current) {
      console.log("[SSE] Connection already exists, skipping");
      return;
    }

    // Create EventSource connection
    const url = `${
      import.meta.env.VITE_API_URL || "http://localhost:8000"
    }/v1/scan/logs/${runId}`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    console.log(`[SSE] Connecting to ${url}`);

    // Handle incoming log messages (event type: "log")
    eventSource.addEventListener("log", (event) => {
      try {
        console.log("[SSE] Received log event:", event.data);
        const data = JSON.parse(event.data);

        // Parse log entry
        if (data.level && data.message) {
          const log: ScanLog = {
            timestamp: data.timestamp || new Date().toISOString(),
            level: data.level as ScanLog["level"],
            message: data.message,
          };
          addLog(log);
          console.log("[SSE] Added log:", log);
        }
      } catch (error) {
        console.error("[SSE] Failed to parse log message:", event.data, error);
      }
    });

    // Handle stats updates (event type: "stats")
    eventSource.addEventListener("stats", (event) => {
      try {
        console.log("[SSE] Received stats event:", event.data);
        const data = JSON.parse(event.data);

        updateStats({
          tickersProcessed: data.tickersProcessed,
          totalTickers: data.totalTickers,
          candidatesFound: data.candidatesFound,
          errors: data.errors,
          durationSeconds: data.durationSeconds,
          status: data.status,
        });
      } catch (error) {
        console.error(
          "[SSE] Failed to parse stats message:",
          event.data,
          error
        );
      }
    });

    // Handle completion (event type: "complete")
    eventSource.addEventListener("complete", (event) => {
      try {
        console.log("[SSE] Received complete event:", event.data);
        const data = JSON.parse(event.data);

        // Update final stats
        updateStats({
          tickersProcessed: data.tickersProcessed,
          totalTickers: data.totalTickers,
          candidatesFound: data.candidatesFound,
          errors: data.errors,
          durationSeconds: data.durationSeconds,
          status: data.status,
        });

        // Close connection to prevent reconnection
        console.log("[SSE] Scan completed, closing connection");
        eventSource.close();
        eventSourceRef.current = null;

        // Call completion callback
        if (onComplete) {
          onComplete();
        }
      } catch (error) {
        console.error(
          "[SSE] Failed to parse complete message:",
          event.data,
          error
        );
      }
    });

    // Handle errors (prevent auto-reconnect on completion)
    eventSource.onerror = (error) => {
      console.error("[SSE] Connection error:", error);

      // Only handle errors if connection is CLOSED and we haven't completed
      if (eventSource.readyState === EventSource.CLOSED) {
        console.error("[SSE] Connection permanently closed");
        eventSourceRef.current = null;

        // Only call error callback if this wasn't a normal completion
        if (onError) {
          onError(new Error("SSE connection failed"));
        }
      } else if (eventSource.readyState === EventSource.CONNECTING) {
        console.log("[SSE] Connection lost, reconnecting...");
      }
    };

    // Handle connection open
    eventSource.onopen = () => {
      console.log("[SSE] Connection established");
    };

    // Cleanup on unmount
    return () => {
      console.log("[SSE] Cleaning up connection");
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, enabled]); // addLog, updateStats are stable from Zustand store

  // Return method to manually close connection
  const close = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  };

  return { close };
}
