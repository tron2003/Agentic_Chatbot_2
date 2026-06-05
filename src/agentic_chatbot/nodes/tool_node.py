# BETTER FIXED tool_node.py - Uses thread pool for sync MCP tools

import asyncio
from concurrent.futures import ThreadPoolExecutor
from langchain_core.messages import HumanMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.tools.mcp_tools import get_mcp_tools

llm = LLMLoader().load_llm()
executor = ThreadPoolExecutor(max_workers=5)  # Thread pool for blocking calls


def should_use_mcp_tools(question: str) -> bool:
    """Detect if user explicitly wants to use MCP tools"""
    keywords = [
        "tool",
        "github",
        "repo",
        "check",
        "count",
        "how many",
        "list",
        "search",
        "file",
    ]
    return any(kw in question.lower() for kw in keywords)


def get_suggested_tools(question: str, available_tools: list) -> list:
    """Map user intent to appropriate MCP tools"""
    tool_names = {tool.name for tool in available_tools}
    
    intent_map = {
        "github": ["search_repositories"],
        "repo": ["search_repositories"],
        "count": ["search_repositories"],
        "how many": ["search_repositories"],
        "search": ["search_repositories", "search_code", "search_files"],
    }
    
    suggested = set()
    for keyword, tools in intent_map.items():
        if keyword in question.lower():
            suggested.update([t for t in tools if t in tool_names])
    
    return list(suggested)


def execute_tool_sync(tool, tool_args):
    """Execute tool synchronously (for MCP tools)"""
    try:
        result = tool.invoke(tool_args)
        return {
            "success": True,
            "result": result,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "result": None,
            "error": str(e)
        }


def format_tool_results(tool_results):
    """Format tool results for readability"""
    formatted = []
    for tool_name, execution in tool_results.items():
        if execution["success"]:
            formatted.append(f"✅ {tool_name}:\n{execution['result']}")
        else:
            formatted.append(f"❌ {tool_name} failed:\n{execution['error']}")
    return "\n\n".join(formatted)


def tool_node(state):
    """
    Tool node handler - works with sync MCP tools in LangGraph.
    
    This version runs sync tools without trying to force async,
    which is more compatible with LangGraph workflows.
    """
    
    question = state.messages[-1].content
    tools = [
        web_search,
        *get_mcp_tools(),
    ]
    
    # Build enhanced prompt if user asks for tools
    system_message = ""
    if should_use_mcp_tools(question):
        suggested_tools = get_suggested_tools(question, tools)
        system_message = f"""You MUST use the appropriate tools to answer this question.
Suggested tools: {', '.join(suggested_tools) if suggested_tools else 'Use your best judgment'}
Available tools: {', '.join([t.name for t in tools])}"""
        
        print(f"\n[TOOL MODE] User asked for tools")
        print(f"[SUGGESTED] {', '.join(suggested_tools)}")
    
    # First attempt: Let LLM decide which tools to use
    llm_with_tools = llm.bind_tools(tools)
    
    messages_for_llm = state.messages.copy()
    if system_message:
        messages_for_llm.insert(0, HumanMessage(content=system_message))
    
    response = llm_with_tools.invoke(messages_for_llm)
    
    # If no tool calls but user asked for tools, suggest them
    if not response.tool_calls and should_use_mcp_tools(question):
        suggested_tools = get_suggested_tools(question, tools)
        if suggested_tools:
            print(f"[AUTO-SUGGEST] LLM didn't call tools, suggesting: {suggested_tools}")
            response.tool_calls = [
                {"name": tool_name, "args": {}}
                for tool_name in suggested_tools
            ]
    
    # Execute tools
    tool_results = {}
    
    if response.tool_calls:
        print(f"\n[EXECUTING] {len(response.tool_calls)} tools...")
        
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            
            print(f"\n  → {tool_name}")
            
            selected_tool = next(
                (tool for tool in tools if tool.name == tool_name),
                None,
            )
            
            if selected_tool is None:
                print(f"    ❌ Tool not found")
                tool_results[tool_name] = {
                    "success": False,
                    "error": f"Tool '{tool_name}' not found in available tools"
                }
                continue
            
            # Execute tool synchronously
            print(f"    ⏳ Running...")
            execution = execute_tool_sync(selected_tool, tool_args)
            tool_results[tool_name] = execution
            
            if execution["success"]:
                result_preview = str(execution["result"])[:100]
                print(f"    ✅ Success: {result_preview}...")
            else:
                error_msg = execution["error"][:100]
                print(f"    ❌ Failed: {error_msg}")
    else:
        print(f"\n[NO TOOLS] No tools were called")
    
    # Build final response
    if tool_results:
        # Only include successful results in the prompt
        success_results = {k: v for k, v in tool_results.items() if v["success"]}
        
        if success_results:
            final_prompt = f"""Original Question:
{question}

Tool Results:
{format_tool_results(success_results)}

Please provide a clear answer based on these tool results."""
        else:
            # All tools failed
            failed_results = {k: v for k, v in tool_results.items() if not v["success"]}
            final_prompt = f"""Original Question:
{question}

Tool execution failed with these errors:
{format_tool_results(failed_results)}

These tools had errors. Try to answer the question anyway, or ask the user for clarification."""
    else:
        final_prompt = f"""Original Question:
{question}

No tools were executed. Please answer directly or suggest which tools could help."""
    
    # Get final response from LLM
    final_response = llm.invoke([
        *state.messages,
        HumanMessage(content=final_prompt)
    ])
    
    print(f"\n[RESPONSE] Generated final answer\n")
    
    return {"messages": [final_response]}