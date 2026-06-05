# debug_mcp_tools.py - Check what methods MCP tools actually support

import sys
from agentic_chatbot.tools.mcp_tools import get_mcp_tools
from agentic_chatbot.tools.web_tool import web_search
import inspect

print("=" * 80)
print("MCP TOOLS INSPECTION")
print("=" * 80)

tools = get_mcp_tools()

print(f"\nTotal tools loaded: {len(tools)}\n")

# Check first 5 tools in detail
for i, tool in enumerate(tools[:10]):
    print(f"\n{i+1}. {tool.name}")
    print(f"   Type: {type(tool).__name__}")
    print(f"   Module: {type(tool).__module__}")
    
    # Check available methods
    has_invoke = hasattr(tool, 'invoke')
    has_invoke_async = hasattr(tool, 'invoke_async')
    has_call = hasattr(tool, '__call__')
    has_arun = hasattr(tool, 'arun')
    
    print(f"   Methods:")
    print(f"     - invoke: {has_invoke}")
    print(f"     - invoke_async: {has_invoke_async}")
    print(f"     - arun: {has_arun}")
    print(f"     - __call__: {has_call}")
    
    # Check if invoke is async
    if has_invoke:
        invoke_method = getattr(tool, 'invoke')
        is_async = inspect.iscoroutinefunction(invoke_method)
        print(f"     - invoke is async: {is_async}")
    
    # Try to show signature
    if has_invoke:
        try:
            sig = inspect.signature(tool.invoke)
            print(f"   invoke signature: {sig}")
        except:
            pass

print("\n" + "=" * 80)
print("WEB SEARCH TOOL")
print("=" * 80)

print(f"\nTool: {web_search.name}")
print(f"Type: {type(web_search).__name__}")
has_invoke = hasattr(web_search, 'invoke')
has_invoke_async = hasattr(web_search, 'invoke_async')
print(f"Methods: invoke={has_invoke}, invoke_async={has_invoke_async}")

if has_invoke:
    try:
        sig = inspect.signature(web_search.invoke)
        print(f"invoke signature: {sig}")
    except:
        pass

print("\n" + "=" * 80)
print("RECOMMENDED ACTION")
print("=" * 80)

# Check if tools support async
mcp_tools = get_mcp_tools()
sync_only = 0
async_capable = 0

for tool in mcp_tools:
    if hasattr(tool, 'invoke_async'):
        async_capable += 1
    elif hasattr(tool, 'invoke'):
        sync_only += 1

print(f"\nSync-only tools: {sync_only}")
print(f"Async-capable tools: {async_capable}")

if sync_only > async_capable:
    print("\n✅ RECOMMENDATION: Use SYNC invoke (tool.invoke())")
    print("   Your tools are primarily sync-based.")
    print("   Use: tool_node_better_fixed.py")
else:
    print("\n⚠️ Your tools support async!")
    print("   The async wrapper should work.")

print("\n" + "=" * 80)
print("TESTING TOOL EXECUTION")
print("=" * 80)

# Try to run search_repositories
search_repo_tool = next((t for t in mcp_tools if t.name == "search_repositories"), None)

if search_repo_tool:
    print(f"\nTrying to execute: search_repositories")
    print(f"Type: {type(search_repo_tool).__name__}")
    
    test_args = {"query": "test"}
    
    try:
        print(f"Calling: search_repositories.invoke({test_args})")
        result = search_repo_tool.invoke(test_args)
        print(f"✅ SUCCESS! Result type: {type(result)}")
        print(f"Result preview: {str(result)[:200]}")
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}")
        print(f"Error: {str(e)[:200]}")
else:
    print("\n❌ search_repositories tool not found")

print("\n" + "=" * 80)