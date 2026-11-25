"""
Delegate tasks to external agents (OpenClaw, Hermes, …) as tools.

Each enabled agent in ``config/integrations.yaml`` becomes a tool named
``ask_<name>``. Calling it sends the task to the agent's OpenAI-compatible
``/chat/completions`` endpoint and returns the agent's reply. With
``session: per_conversation`` the Junction conversation ID is sent as the
OpenAI ``user`` field, which OpenClaw uses to keep one session per thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.integrations.config import ExternalAgentConfig

logger = logging.getLogger(__name__)

# Overridable in tests (httpx.MockTransport).
client_factory: Callable[[float], httpx.AsyncClient] = lambda timeout: httpx.AsyncClient(timeout=timeout)  # noqa: E731


class AskAgentInput(BaseModel):
    task: str = Field(description="The complete, self-contained instruction or question for the agent.")


def _headers(agent: ExternalAgentConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json", **agent.headers}
    if agent.api_key:
        headers["Authorization"] = f"Bearer {agent.api_key}"
    return headers


def _url(agent: ExternalAgentConfig, path: str) -> str:
    return f"{agent.base_url.rstrip('/')}/{path.lstrip('/')}"


def _reply_text(data: dict) -> str:
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    if isinstance(content, list):  # content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return (content or "").strip()


class AgentUnavailable(ToolException):
    """The external agent couldn't be reached or refused the request."""


async def ask_agent(agent: ExternalAgentConfig, task: str, conversation_id: str | None = None) -> str:
    """Send a task to the agent and return its reply. Raises AgentUnavailable on failure."""
    body: dict = {"model": agent.model, "messages": [{"role": "user", "content": task}], "stream": False}
    if agent.session == "per_conversation" and conversation_id:
        body["user"] = f"junction:{conversation_id}"
    name = agent.display
    try:
        async with client_factory(agent.timeout_seconds) as client:
            res = await client.post(_url(agent, "chat/completions"), json=body, headers=_headers(agent))
    except httpx.TimeoutException:
        raise AgentUnavailable(f"{name} didn't answer within {agent.timeout_seconds:.0f} seconds. The task may still be running there.")
    except httpx.HTTPError as exc:
        logger.warning("Agent %s unreachable: %s", agent.name, exc)
        raise AgentUnavailable(f"Couldn't reach {name} at {agent.base_url} ({type(exc).__name__}). Is it running?")

    if res.status_code in (401, 403):
        raise AgentUnavailable(f"{name} rejected {get_settings().app_name}'s credentials (HTTP {res.status_code}). Check the token in .env.")
    if res.status_code == 404:
        raise AgentUnavailable(f"{name} has no chat endpoint at {agent.base_url}. Is its OpenAI-compatible API turned on?")
    if res.status_code >= 400:
        raise AgentUnavailable(f"{name} returned an error (HTTP {res.status_code}): {res.text[:300]}")
    try:
        text = _reply_text(res.json())
    except ValueError:
        text = ""
    return text or f"{name} finished the task without a text reply."


async def probe_agent(agent: ExternalAgentConfig, timeout: float = 4.0) -> str:
    """Cheap reachability check via GET /models: ok | unauthorized | unreachable | error."""
    try:
        async with client_factory(timeout) as client:
            res = await client.get(_url(agent, "models"), headers=_headers(agent))
    except httpx.HTTPError:
        return "unreachable"
    if res.status_code in (401, 403):
        return "unauthorized"
    return "ok" if res.status_code < 400 else "error"


def make_agent_tool(agent: ExternalAgentConfig) -> BaseTool:
    async def _ask(task: str, config: RunnableConfig) -> str:
        thread = ((config or {}).get("configurable") or {}).get("thread_id")
        return await ask_agent(agent, task, thread)

    description = (
        f"Delegate a task to {agent.display}, an external agent the user has connected. "
        f"{agent.description.strip()} "
        f"Only call this when the user asks for something {agent.display} handles. "
        "Its reply comes back as text; report what it did, and never claim an action happened if the reply says otherwise."
    )
    return StructuredTool.from_function(
        coroutine=_ask, name=agent.tool_name, description=description, args_schema=AskAgentInput
    )
