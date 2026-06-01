from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from dotenv import load_dotenv
import os

load_dotenv()

search = TavilySearch(
    api_key=os.getenv("TAVILY_API_KEY"),
    max_results=5
)

@tool
def web_search(query: str) -> str:
    """
    Search the web for latest information.
    Use for news, recent events, facts not in memory, internet queries.
    """
    raw = search.invoke(query)

    results = raw if isinstance(raw, list) else raw.get("results", [])

    if not results:
        return "No results found."

    print(f"Query asked: {query}")
    print(f"Answer from tool: {raw}")         # ✅ debug print stays here

    return "\n\n".join(
        f"Source: {r['url']}\nTitle: {r['title']}\n{r['content']}"
        for r in results
    )