"""
LangChain-powered chatbot endpoint for conversational scan control.

Provides:
- POST /v1/chat - Send messages to AI assistant with tool calling
"""

import os
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.routes.scan import execute_scan_task
from src.ops.logging import get_logger
from src.storage.models import Run
from src.strategies.registry import StrategyRegistry

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., description="User message to the AI assistant")
    conversation_id: str | None = Field(None, description="Optional conversation ID for context")


class ToolCall(BaseModel):
    """Information about a tool that was called."""

    tool: str = Field(..., description="Tool name")
    status: str = Field(..., description="Tool execution status")
    result: dict[str, Any] | None = Field(None, description="Tool execution result")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    message: str = Field(..., description="Assistant's response message")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Tools executed")
    conversation_id: str | None = Field(None, description="Conversation ID")


# ============================================================================
# Global state for background tasks
# ============================================================================

_background_tasks: BackgroundTasks | None = None


def set_chat_context(background_tasks: BackgroundTasks) -> None:
    """Set global context for tools."""
    global _background_tasks
    _background_tasks = background_tasks


# ============================================================================
# LangChain Tools
# ============================================================================


@tool
def scan_market(
    strategies: list[str] | None = None, scan_date: str | None = None
) -> dict[str, Any]:
    """
    Trigger a market scan to find recovery candidates.

    Use this tool when the user asks to:
    - "scan the market"
    - "find candidates"
    - "run a scan"
    - "look for opportunities"

    Args:
        strategies: List of strategy names to use (e.g., ["drop5"]).
                   If not provided, all enabled strategies will be used.
        scan_date: Date to scan in YYYY-MM-DD format. Defaults to today.

    Returns:
        dict with run_ids, status, strategies, and date
    """
    from src.storage.database import SessionLocal

    # Parse date
    target_date = date.fromisoformat(scan_date) if scan_date else date.today()

    logger.info(
        "scan_market tool called",
        strategies=strategies,
        scan_date=scan_date,
        target_date=str(target_date),
    )

    # Get strategies
    registry = StrategyRegistry()
    if strategies:
        strategy_names = strategies
    else:
        all_strategies_list = registry.list_strategies()
        # Type narrowing: we know this is list[StrategyProtocol] because names_only=False (default)
        assert not isinstance(all_strategies_list[0] if all_strategies_list else None, str)
        strategy_names = [s.name for s in all_strategies_list if s.config.enabled]

        # Fallback to default strategy if none found
        if not strategy_names:
            logger.warning("No enabled strategies found, using default 'drop5'")
            strategy_names = ["drop5"]

    # Create database session
    with SessionLocal() as db:
        run_ids = []

        for strategy_name in strategy_names:
            # Check for existing run for this strategy
            existing_run = (
                db.query(Run)
                .filter(
                    Run.run_date == target_date,
                    Run.strategy == strategy_name,
                    Run.status.in_(["pending", "running"]),
                )
                .first()
            )

            if existing_run:
                run_ids.append(str(existing_run.run_id))
                continue

            # Create new run
            new_run = Run(
                run_date=target_date,
                strategy=strategy_name,
                status="pending",
            )
            db.add(new_run)
            db.commit()
            db.refresh(new_run)

            run_ids.append(str(new_run.run_id))

            logger.info(
                "Scan triggered via chatbot",
                run_id=str(new_run.run_id),
                strategy=strategy_name,
                date=str(target_date),
            )

        # Trigger background scan for all runs (called once after loop)
        if _background_tasks and run_ids:
            _background_tasks.add_task(
                execute_scan_task,
                strategies=strategy_names,
                scan_date=target_date,
                run_ids=run_ids,
            )

            logger.info(
                "Background scan task queued",
                run_ids=run_ids,
                strategies=strategy_names,
                date=str(target_date),
            )

        result = {
            "run_ids": run_ids,
            "status": "queued",
            "strategies": strategy_names,
            "date": str(target_date),
        }

        logger.info("scan_market tool returning", result=result, num_runs=len(run_ids))

        return result


@tool
def explain_strategy(strategy_name: str) -> dict[str, Any]:
    """
    Explain how a specific trading strategy works.

    Use this tool when the user asks to:
    - "explain the drop5 strategy"
    - "how does X strategy work"
    - "what is the X strategy"

    Args:
        strategy_name: Name of the strategy to explain (e.g., "drop5")

    Returns:
        dict with name, description, and parameters
    """
    registry = StrategyRegistry()
    strategy = registry.get(strategy_name)

    if not strategy:
        all_strats = registry.list_strategies()
        return {
            "error": f"Strategy '{strategy_name}' not found",
            "available_strategies": [s.name if hasattr(s, "name") else s for s in all_strats],
        }

    return {
        "name": strategy.name,
        "version": strategy.version,
        "description": f"The {strategy.name} strategy looks for stocks that have dropped "
        f"by at least 5% and shows signs of recovery. It analyzes technical "
        f"indicators like RSI, volume, and price action to score recovery probability.",
        "enabled": strategy.config.enabled,
    }


# ============================================================================
# Chat Endpoint
# ============================================================================


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with AI assistant",
    description="""
    Send a message to the AI assistant for conversational interaction.

    The assistant can:
    - Trigger market scans
    - Explain strategies
    - Answer questions about the system

    Requires OPENAI_API_KEY environment variable to be set.
    """,
)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Process chat message with LangChain agent."""

    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
        )

    try:
        # Set context for tools
        set_chat_context(background_tasks)

        # Initialize LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",  # Fast and cost-effective
            temperature=0.7,
        )

        # Define tools
        tools = [scan_market, explain_strategy]

        # Create agent with system prompt
        system_prompt = """You are a helpful AI assistant for Recover-Bot, a market scanning system
that identifies recovery candidates after price drops.

You can help users:
1. Trigger market scans to find recovery candidates
2. Explain how strategies work
3. Answer questions about the system

Be concise and friendly. When a user asks to scan the market, use the scan_market tool.
When they ask about strategies, use the explain_strategy tool."""

        # Create agent
        agent = create_react_agent(llm, tools, prompt=system_prompt)

        # Execute agent
        result = {"messages": [("user", request.message)]}

        # Stream agent execution
        response_text = ""
        tool_calls_list: list[ToolCall] = []
        all_messages = []

        for event in agent.stream(result, stream_mode="values"):
            last_message = event["messages"][-1]
            all_messages = event["messages"]

            # Extract assistant response
            if hasattr(last_message, "content") and last_message.content:
                response_text = last_message.content

        # Extract tool calls and their results from the message history
        for msg in all_messages:
            # Check for tool calls (before execution)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get("name", "unknown")
                    tool_id = tool_call.get("id", "")

                    # Find the corresponding tool result message
                    tool_result = None
                    for result_msg in all_messages:
                        if (
                            hasattr(result_msg, "tool_call_id")
                            and result_msg.tool_call_id == tool_id
                        ):
                            tool_result = result_msg.content
                            break

                    # Parse tool result if it's a JSON string
                    result_data = {}
                    if tool_result:
                        try:
                            import json

                            result_data = (
                                json.loads(tool_result)
                                if isinstance(tool_result, str)
                                else tool_result
                            )
                        except (json.JSONDecodeError, TypeError):
                            result_data = {"raw_result": tool_result}

                    tool_calls_list.append(
                        ToolCall(
                            tool=tool_name,
                            status="completed",
                            result=result_data,
                        )
                    )

        logger.info(
            "Chat processed",
            message=request.message,
            response=response_text,
            tool_calls=len(tool_calls_list),
            tool_call_details=[{"tool": tc.tool, "result": tc.result} for tc in tool_calls_list],
        )

        return ChatResponse(
            message=response_text or "I'm not sure how to help with that.",
            tool_calls=tool_calls_list,
            conversation_id=request.conversation_id,
        )

    except Exception as e:
        logger.error("Chat error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}",
        ) from e
