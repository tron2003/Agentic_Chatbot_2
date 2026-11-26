"""Assemble the agent's tool list."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from agentic_chatbot.integrations.registry import agent_tools as integration_agent_tools
from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.services.spreadsheets import sheets_available
from agentic_chatbot.tools.kb_tool import search_knowledge_base
from agentic_chatbot.tools.math_tool import calculator, current_datetime
from agentic_chatbot.tools.pdf_tool import read_pdf
from agentic_chatbot.tools.spreadsheet_tool import describe_spreadsheets, query_spreadsheet
from agentic_chatbot.tools.web_tool import web_search, web_search_available


def get_mcp_tools() -> list[BaseTool]:
    return mcp_manager.get_tools()


def get_agent_tools(include_kb: bool = True) -> list[BaseTool]:
    tools: list[BaseTool] = [calculator, current_datetime]
    if web_search_available():
        tools.insert(0, web_search)
    if include_kb:
        tools.append(search_knowledge_base)
    if sheets_available():
        tools += [describe_spreadsheets, query_spreadsheet]
    tools.append(read_pdf)
    seen = {t.name for t in tools}
    for t in [*integration_agent_tools(), *get_mcp_tools()]:
        if t.name not in seen:
            tools.append(t)
            seen.add(t.name)
    return tools
