"""Tool node — ReAct agentic loop with async MCP tools."""

import asyncio
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.tools.pdf_tool import read_pdf
from agentic_chatbot.tools.mcp_tools import get_mcp_tools

llm = LLMLoader().load_llm()

MAX_ITERATIONS = 8  # prevent infinite loops

SYSTEM_PROMPT = """You are an agentic assistant with access to tools.
Use the tools to answer the user's question step by step.
- Search the filesystem with search_files, then read files with read_file or read_text_file.
- For GitHub questions use search_repositories.
- For web questions use web_search.
Keep calling tools until you have enough information, then give a final answer.
Do NOT produce XML or code blocks describing tool calls — use the actual tool call mechanism.
"""


async def _invoke_tool(tool, args: dict):
    """Call a tool, handling both sync and async invoke."""
    try:
        if asyncio.iscoroutinefunction(tool.invoke):
            result = await tool.invoke(args)
        elif hasattr(tool, "arun"):
            result = await tool.arun(args)
        else:
            result = await asyncio.get_event_loop().run_in_executor(None, tool.invoke, args)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


async def tool_node(state):
    messages = state.messages if hasattr(state, "messages") else state["messages"]
    tools = [web_search, read_pdf, *get_mcp_tools()]
    tools_by_name = {t.name: t for t in tools}

    llm_with_tools = llm.bind_tools(tools)

    # Build conversation so far, prefixed with system instruction
    history = [SystemMessage(content=SYSTEM_PROMPT), *messages]

    for iteration in range(MAX_ITERATIONS):
        response: AIMessage = await llm_with_tools.ainvoke(history)
        history.append(response)

        # No tool calls → LLM has a final answer
        if not response.tool_calls:
            print(f"\n[TOOL NODE] Done after {iteration + 1} iteration(s)\n")
            break

        print(f"\n[TOOL NODE] Iteration {iteration + 1} — {len(response.tool_calls)} tool call(s)")

        # Execute every requested tool call and collect ToolMessages
        tool_messages = []
        tasks = [
            (tc["id"], tc["name"], tc.get("args", {}))
            for tc in response.tool_calls
        ]

        results = await asyncio.gather(*[
            _invoke_tool(tools_by_name[name], args)
            if name in tools_by_name
            else asyncio.coroutine(lambda: f"Tool '{name}' not found")()
            for _, name, args in tasks
        ], return_exceptions=True)

        for (call_id, name, _), result in zip(tasks, results):
            content = str(result) if not isinstance(result, Exception) else f"Error: {result}"
            preview = content[:120].replace("\n", " ")
            print(f"  -> {name}: {preview}...")
            tool_messages.append(ToolMessage(content=content, tool_call_id=call_id))

        history.extend(tool_messages)

    # Last message in history is the final AIMessage
    final = next(
        (m for m in reversed(history) if isinstance(m, AIMessage)),
        AIMessage(content="I was unable to complete the task."),
    )

    return {"messages": [final]}
