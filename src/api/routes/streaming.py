"""
Server-Sent Events (SSE) streaming endpoints for real-time log streaming.

Provides:
- GET /v1/scan/logs/{run_id} - Stream scan logs in real-time
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

from src.api.dependencies import get_db
from src.ops.logging import get_logger, get_scan_stats, stream_logs
from src.storage.models import Run

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/scan/logs/{run_id}",
    summary="Stream scan logs in real-time",
    description="""
    Stream log events for a specific scan run using Server-Sent Events (SSE).

    The client should connect with EventSource or similar SSE client:
    ```javascript
    const eventSource = new EventSource('/v1/scan/logs/{run_id}');
    eventSource.onmessage = (event) => {
        const log = JSON.parse(event.data);
        console.log(log.message);
    };
    ```

    Each event contains:
    - `timestamp`: ISO 8601 timestamp
    - `level`: Log level (info, warning, error)
    - `message`: Log message
    - `ticker`: Ticker symbol (if applicable)
    - `strategy`: Strategy name (if applicable)
    - `score`: Candidate score (if applicable)

    The stream automatically closes when the scan completes or the client disconnects.
    """,
    response_class=EventSourceResponse,
)
async def stream_scan_logs(
    run_id: Annotated[UUID, Path(description="UUID of the scan run")],
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    """Stream real-time logs for a scan run via Server-Sent Events."""

    # Verify run exists
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    logger.info("SSE client connected", run_id=str(run_id))

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        """Generate SSE events from log stream and stats updates."""

        # Create queues to merge log and stats events
        event_queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

        async def stream_logs_task() -> None:
            """Stream logs in real-time from async queue."""
            try:
                async for log_entry in stream_logs(run_id):
                    # Use the beautifully formatted 'event' message from backend
                    message = log_entry.get("event", log_entry.get("message", ""))

                    await event_queue.put(
                        {
                            "event": "log",
                            "data": json.dumps(
                                {
                                    "timestamp": log_entry.get("timestamp"),
                                    "level": log_entry.get("level", "info"),
                                    "message": message,
                                    "ticker": log_entry.get("ticker"),
                                    "price": log_entry.get("price"),
                                    "score": log_entry.get("score"),
                                    "sector": log_entry.get("sector"),
                                    "drop_pct": log_entry.get("drop_pct"),
                                    "rsi": log_entry.get("rsi"),
                                    "skip_reason": log_entry.get("skip_reason"),
                                }
                            ),
                        }
                    )
            except Exception as e:
                logger.error("Log streaming task error", error=str(e))
            finally:
                await event_queue.put(None)  # Signal completion

        async def stream_stats_task() -> None:
            """Stream stats updates periodically from IN-MEMORY tracker (no database!)."""
            try:
                while True:
                    # Get stats from in-memory tracker (instant, no database query!)
                    stats = get_scan_stats(run_id)

                    # Send stats event
                    await event_queue.put(
                        {
                            "event": "stats",
                            "data": json.dumps(
                                {
                                    "tickersProcessed": stats["tickers_processed"],
                                    "totalTickers": stats["total_tickers"],
                                    "candidatesFound": stats["candidates_found"],
                                    "errors": stats["errors"],
                                    "durationSeconds": stats["duration_seconds"],
                                    "status": stats["status"],
                                }
                            ),
                        }
                    )

                    # If scan is complete, send final stats and stop
                    if stats["status"] in ["completed", "failed"]:
                        await event_queue.put(
                            {
                                "event": "complete",
                                "data": json.dumps(
                                    {
                                        "status": stats["status"],
                                        "tickersProcessed": stats["tickers_processed"],
                                        "totalTickers": stats["total_tickers"],
                                        "candidatesFound": stats["candidates_found"],
                                        "durationSeconds": stats["duration_seconds"],
                                    }
                                ),
                            }
                        )
                        break

                    # Update every 0.5s (doesn't block log streaming!)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Stats streaming task error", error=str(e))

        try:
            # Send initial connection message
            yield {
                "event": "log",
                "data": json.dumps(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "info",
                        "message": "🚀 Connected to scan",
                    }
                ),
            }

            # Start both tasks in parallel
            asyncio.create_task(stream_logs_task())
            stats_task = asyncio.create_task(stream_stats_task())

            # Yield events from the merged queue
            while True:
                event = await event_queue.get()
                if event is None:  # Log stream ended
                    # Cancel stats task and break
                    stats_task.cancel()
                    break
                yield event

        except asyncio.CancelledError:
            logger.info("SSE client disconnected", run_id=str(run_id))
            raise
        except Exception as e:
            logger.error("Error streaming logs", run_id=str(run_id), error=str(e))
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())
