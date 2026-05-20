import sys
from pathlib import Path

from langchain_core.messages import HumanMessage


project_root = Path(__file__).parent.parent

src_dir = project_root / "src"

sys.path.insert(
    0,
    str(src_dir)
)


from agentic_chatbot.pipelines.chatbot_pipeline import (
    ChatbotPipeline
)


bot = ChatbotPipeline()


while True:

    query = input(
        "You : "
    )

    if query=="exit":

        break


    response = bot.run(

        HumanMessage(
            content=query
        )
    )

    print(
        f"\nBot : {response['messages'][-1].content}\n"
    )