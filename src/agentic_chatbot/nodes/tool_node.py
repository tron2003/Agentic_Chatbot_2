"""Tool node — ReAct agentic loop with async MCP tools."""

import sys
import asyncio
import logging
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.tools.pdf_tool import read_pdf
from agentic_chatbot.tools.mcp_tools import get_mcp_tools
from agentic_chatbot.prompts.web_search_prompt import WEB_SEARCH_SYSTEM_PROMPT
from agentic_chatbot.utils.message_builder import build_messages
from agentic_chatbot.exception.exception import LLMException, ToolExecutionException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id,
    log_async,
)

logger = logging.getLogger(__name__)

llm = LLMLoader().load_llm()

MAX_ITERATIONS = 8  # prevent infinite loops

# Combine general agent rules with the factual web search rules
SYSTEM_PROMPT = f"""You are an agentic assistant with access to tools.
Use the tools to answer the user's question step by step.
- Search the filesystem with search_files, then read files with read_file or read_text_file.
- For GitHub questions use search_repositories.
- For web questions use web_search.
Keep calling tools until you have enough information, then give a final answer.
Do NOT produce XML or code blocks describing tool calls — use the actual tool call mechanism.

{WEB_SEARCH_SYSTEM_PROMPT}"""


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
async def tool_node(state):
    """
    Tool execution node for agentic ReAct loop.
    Iteratively invokes tools until the LLM produces a final answer.
    """
    correlation_id = get_correlation_id()

    with ExecutionTimer("tool_node", correlation_id, logger):
        try:
            logger.debug(
                "Starting tool node processing",
                extra={"correlation_id": correlation_id},
            )

            tools = [web_search, read_pdf, *get_mcp_tools()]
            tools_by_name = {t.name: t for t in tools}

            logger.debug(
                f"Available tools: {list(tools_by_name.keys())}",
                extra={"correlation_id": correlation_id},
            )

            llm_with_tools = llm.bind_tools(tools)

            # Build conversation so far, prefixed with the combined system instruction
            history = [SystemMessage(content=SYSTEM_PROMPT)]
            history.extend(build_messages(state))

            logger.debug(
                f"Tool node context prepared with {len(history)} messages",
                extra={"correlation_id": correlation_id},
            )

            for iteration in range(MAX_ITERATIONS):
                logger.debug(
                    f"Tool iteration {iteration + 1}/{MAX_ITERATIONS}",
                    extra={"correlation_id": correlation_id},
                )

                response: AIMessage = await llm_with_tools.ainvoke(history)
                history.append(response)

                # No tool calls → LLM has a final answer
                if not response.tool_calls:
                    logger.info(
                        f"Tool node completed after {iteration + 1} iteration(s)",
                        extra={"correlation_id": correlation_id},
                    )
                    print(f"\n[TOOL NODE] Done after {iteration + 1} iteration(s)\n")
                    break

                logger.info(
                    f"Tool iteration {iteration + 1}: {len(response.tool_calls)} tool call(s)",
                    extra={"correlation_id": correlation_id},
                )
                print(
                    f"\n[TOOL NODE] Iteration {iteration + 1} — {len(response.tool_calls)} tool call(s)"
                )

                # Execute every requested tool call and collect ToolMessages
                tool_messages = []
                tasks = [
                    (tc["id"], tc["name"], tc.get("args", {}))
                    for tc in response.tool_calls
                ]

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
                    preview = content[:120].replace("\n", " ")
                    print(f"  -> {name}: {preview}...")
                    tool_messages.append(
                        ToolMessage(content=content, tool_call_id=call_id)
                    )

                history.extend(tool_messages)

            # Last message in history is the final AIMessage
            final = next(
                (m for m in reversed(history) if isinstance(m, AIMessage)),
                AIMessage(content="I was unable to complete the task."),
            )

            logger.info(
                "Tool node finished with final response",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": (
                        len(final.content) if hasattr(final, "content") else 0
                    ),
                },
            )

            return {"messages": [final]}

        except LLMException:
            raise
        except Exception as e:
            logger.error(
                f"Tool node failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Tool execution failed: {str(e)}", sys, correlation_id=correlation_id
            )
