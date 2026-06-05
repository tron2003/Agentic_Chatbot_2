import sys
import io
import asyncio
import selectors
from pathlib import Path

# Fix Windows console Unicode issues
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # psycopg async requires SelectorEventLoop — Windows defaults to ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)

from langchain_core.messages import HumanMessage

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.components.memory import MemoryLoader
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline


async def main():
    await mcp_manager.initialize()

    memory_loader = MemoryLoader()
    checkpointer = await memory_loader.load_memory()

    bot = ChatbotPipeline(checkpointer=checkpointer)

    try:
        while True:
            try:
                query = input("You : ")

                if query == "exit":
                    break

                response = await bot.run(HumanMessage(content=query))

                print(f"\nBot : {response['messages'][-1].content}\n")
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                print("\nExiting...")
                break
    finally:
        await memory_loader.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.get_event_loop().run_until_complete(main())
    else:
        asyncio.run(main())
