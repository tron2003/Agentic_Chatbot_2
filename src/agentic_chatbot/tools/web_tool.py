from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from dotenv import load_dotenv
import os

load_dotenv()

# Initialize TavilySearch only if API key is available
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
search = None

if TAVILY_API_KEY:
    try:
        search = TavilySearch(
            api_key=TAVILY_API_KEY,
            max_results=5
        )
    except Exception as e:
        print(f"⚠️  Failed to initialize TavilySearch: {e}")
else:
    print("⚠️  TAVILY_API_KEY not set. Web search will return mock results.")


@tool
def web_search(query: str) -> str:
    """
    Search the web for latest information.
    Use for news, recent events, facts not in memory, internet queries.
    """
    if not search:
        return f"[Mock Search Result] No web search API available. Query was: '{query}'. Please set TAVILY_API_KEY in .env to enable real web search."

    try:
        raw = search.invoke(query)
        results = raw if isinstance(raw, list) else raw.get("results", [])

        if not results:
            return "No results found."

        print(f"Query asked: {query}")
        print(f"Answer from tool: {raw}")

        return "\n\n".join(
            f"Source: {r['url']}\nTitle: {r['title']}\n{r['content']}"
            for r in results
        )
    except Exception as e:
        return f"Error searching web: {str(e)}"