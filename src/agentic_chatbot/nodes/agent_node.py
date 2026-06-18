"""
Agent Node — Multi-step agentic reasoning with Claude tool use and extended thinking.
Shows reasoning steps for transparency (like Claude Code).
"""

import sys
import asyncio
import json
import logging
from typing import Optional
from datetime import datetime
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.tools.pdf_tool import read_pdf
from agentic_chatbot.tools.mcp_tools import get_mcp_tools
from agentic_chatbot.utils.message_builder import build_messages
from agentic_chatbot.exception.exception import LLMException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id,
    log_async,
)

logger = logging.getLogger(__name__)

llm = LLMLoader().load_llm()

MAX_ITERATIONS = 10
REASONING_BUDGET = 10000  # tokens for extended thinking (if using Claude)

AGENT_SYSTEM_PROMPT = """You are an advanced agentic AI assistant with access to multiple tools.
Your role is to break down complex problems into steps, reason through them, and use tools strategically.

CORE PRINCIPLES:
1. Think step-by-step before taking action
2. Break complex tasks into smaller subtasks
3. Use tools to gather information, not as a first resort
4. Verify information from multiple sources when possible
5. Explain your reasoning process clearly
6. Be transparent about limitations and uncertainties

AVAILABLE TOOLS:
- web_search: Search the internet for current information
- read_pdf: Extract and analyze PDF documents
- search_files: Find files in the filesystem
- read_file: Read file contents
- search_repositories: Search GitHub repositories
- read_text_file: Read text files

REASONING PROCESS:
1. Analyze the user's request carefully
2. Plan your approach (explain what you'll do)
3. Execute tools if needed
4. Synthesize information
5. Provide a comprehensive answer with sources

When done gathering information, provide your final answer with clear reasoning."""


class ReasoningStep(dict):
    """Represents a single step in the agent's reasoning process (JSON serializable)."""

    def __init__(self, step_type: str, content: str, timestamp: Optional[str] = None):
        super().__init__()
        self["type"] = (
            step_type  # "thinking", "tool_call", "tool_result", "final_answer"
        )
        self["content"] = content
        self["timestamp"] = timestamp or datetime.utcnow().isoformat()

    def to_dict(self):
        return dict(self)


async def _invoke_tool(tool, args: dict, correlation_id: str):
    """Call a tool, handling both sync and async invoke."""
    tool_name = getattr(tool, "name", "unknown")
    try:
        logger.debug(
            f"Invoking tool: {tool_name}", extra={"correlation_id": correlation_id}
        )

        if asyncio.iscoroutinefunction(tool.invoke):
            result = await tool.invoke(args)
        elif hasattr(tool, "arun"):
            result = await tool.arun(args)
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None, tool.invoke, args
            )

        logger.debug(
            f"Tool {tool_name} executed successfully",
            extra={"correlation_id": correlation_id},
        )
        return str(result)
    except Exception as e:
        logger.error(
            f"Tool execution failed: {tool_name}",
            extra={
                "correlation_id": correlation_id,
                "tool_name": tool_name,
                "error": str(e),
            },
            exc_info=True,
        )
        return f"Error executing {tool_name}: {str(e)}"


@log_async()
async def agent_node(state):
    """
    Multi-step agent with reasoning transparency.
    Shows all thinking and tool calls to the frontend.
    """
    correlation_id = get_correlation_id()

    with ExecutionTimer("agent_node", correlation_id, logger):
        try:
            logger.debug(
                "Starting agent node processing",
                extra={"correlation_id": correlation_id},
            )

            tools = [web_search, read_pdf, *get_mcp_tools()]
            tools_by_name = {t.name: t for t in tools}

            logger.debug(
                f"Available tools: {list(tools_by_name.keys())}",
                extra={"correlation_id": correlation_id},
            )

            llm_with_tools = llm.bind_tools(tools)

            # Initialize reasoning steps list
            reasoning_steps = []

            # Build conversation history
            history = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
            if state.summary:
                logger.debug(
                    "Including conversation summary in agent context",
                    extra={"correlation_id": correlation_id},
                )
                history.append(
                    SystemMessage(content=f"Conversation Summary:\n{state.summary}")
                )
            history.extend(build_messages(state))

            user_query = state.messages[-1].content if state.messages else "No query"

            logger.debug(
                f"Agent query: {user_query[:100]}...",
                extra={"correlation_id": correlation_id},
            )

            # Step 1: Planning Phase (initial thinking)
            planning_step = ReasoningStep(
                "thinking",
                f"Analyzing request: {user_query[:100]}...\nWill determine what tools and approaches are needed.",
            )
            reasoning_steps.append(planning_step)

            print(f"\n[AGENT] Starting agentic reasoning for: {user_query[:60]}...")

            for iteration in range(MAX_ITERATIONS):
                logger.debug(
                    f"Agent iteration {iteration + 1}/{MAX_ITERATIONS}",
                    extra={"correlation_id": correlation_id},
                )

                response: AIMessage = await llm_with_tools.ainvoke(history)
                history.append(response)

                # Extract thinking if available (Claude's internal reasoning)
                if hasattr(response, "content") and response.content:
                    thought = response.content
                    if thought and len(thought) > 20:
                        thinking_step = ReasoningStep("thinking", thought[:500])
                        reasoning_steps.append(thinking_step)

                # No tool calls → agent has final answer
                if not response.tool_calls:
                    logger.info(
                        f"Agent completed after {iteration + 1} iteration(s)",
                        extra={"correlation_id": correlation_id},
                    )
                    print(
                        f"\n[AGENT] Reasoning complete after {iteration + 1} iteration(s)"
                    )
                    break

                logger.info(
                    f"Agent iteration {iteration + 1}: {len(response.tool_calls)} tool call(s)",
                    extra={"correlation_id": correlation_id},
                )
                print(
                    f"[AGENT] Iteration {iteration + 1} — {len(response.tool_calls)} tool call(s)"
                )

                # Execute tool calls
                tool_messages = []
                tasks = [
                    (tc["id"], tc["name"], tc.get("args", {}))
                    for tc in response.tool_calls
                ]

                # Add tool call steps to reasoning
                for call_id, tool_name, args in tasks:
                    tool_step = ReasoningStep(
                        "tool_call",
                        f"Calling {tool_name} with arguments: {json.dumps(args)[:200]}...",
                    )
                    reasoning_steps.append(tool_step)
                    print(f"  → Calling {tool_name}")

                results = await asyncio.gather(
                    *[
                        (
                            _invoke_tool(tools_by_name[name], args, correlation_id)
                            if name in tools_by_name
                            else asyncio.coroutine(lambda: f"Tool '{name}' not found")()
                        )
                        for _, name, args in tasks
                    ],
                    return_exceptions=True,
                )

                for (call_id, name, _), result in zip(tasks, results):
                    content = (
                        str(result)
                        if not isinstance(result, Exception)
                        else f"Error: {result}"
                    )
                    preview = content[:150].replace("\n", " ")

                    # Add tool result to reasoning
                    result_step = ReasoningStep(
                        "tool_result",
                        f"{name} result: {preview}...",
                    )
                    reasoning_steps.append(result_step)

                    print(f"    ✓ {name}: {preview}...")
                    tool_messages.append(
                        ToolMessage(content=content, tool_call_id=call_id)
                    )

                history.extend(tool_messages)

            # Get final answer
            final = next(
                (m for m in reversed(history) if isinstance(m, AIMessage)),
                AIMessage(content="I was unable to complete the task."),
            )

            # Add final answer to reasoning
            final_step = ReasoningStep(
                "final_answer",
                final.content[:1000] if final.content else "No response generated",
            )
            reasoning_steps.append(final_step)

            logger.info(
                "Agent node finished with final response",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": (
                        len(final.content) if hasattr(final, "content") else 0
                    ),
                    "reasoning_steps": len(reasoning_steps),
                },
            )

            # Store reasoning steps in message metadata (not in state)
            final.metadata = {"reasoning_steps": reasoning_steps}

            return {"messages": [final]}

        except LLMException:
            raise
        except Exception as e:
            logger.error(
                f"Agent node failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Agent execution failed: {str(e)}", sys, correlation_id=correlation_id
            )
