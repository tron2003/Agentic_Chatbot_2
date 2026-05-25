from langgraph.graph import (
    StateGraph,
    START,
    END
)

from agentic_chatbot.entity.chat_state import (
    Chatbot
)

from agentic_chatbot.nodes.chat_node import (
    chat_node
)

from agentic_chatbot.utils.summarizer import (
    summarize_conversation,
    should_summarize
)

from agentic_chatbot.components.memory import (
    MemoryLoader
)


class ChatbotPipeline:

    def __init__(self):

        graph = StateGraph(
            Chatbot
        )

        graph.add_node(
            "chat",
            chat_node
        )

        graph.add_node(
            "summarize",
            summarize_conversation
        )


        graph.add_conditional_edges(

            START,

            should_summarize,

            {

                True:
                "summarize",

                False:
                "chat"

            }
        )


        graph.add_edge(
            "summarize",
            "chat"
        )


        graph.add_edge(
            "chat",
            END
        )


        self.memory_context = (
            MemoryLoader()
            .load_memory()
        )


        self.memory = (
            self.memory_context.__enter__()
        )


        self.memory.setup()


        self.workflow = graph.compile(
            checkpointer=self.memory
        )


    def run(

        self,
        message,
        thread_id="user_1"

    ):

        config = {

            "configurable": {

                "thread_id":
                thread_id
            }
        }


        result = self.workflow.invoke(

            {

                "messages":[
                    message
                ]
            },

            config=config
        )


        return result